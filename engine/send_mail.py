#!/usr/bin/env python3
"""Daily match mail. Deterministic, idempotent, no LLM.

Contract (printed on the site): a mail is sent ONLY when new listings match the
subscriber's profile. Nothing new -> no mail. Already-mailed listings are never
repeated; state lives in data/mail_state.json and is committed by the daily
workflow, so re-runs cannot double-send.

Delivery goes through ONE throat -- Provider.send with to, subject and html --
returning MessageId | HardBounce | SoftFail. Nothing else in the codebase talks
to a mail transport. Swapping providers is one class; the signature does not move.

Env:
  RESEND_API_KEY        required for a real send (Bearer token for api.resend.com)
  MAIL_FROM             required for a real send, e.g. 'the engine <x@domain>'
  SUPABASE_SERVICE_KEY  if set, subscribers are read from Supabase (multi-subscriber)
  SUBSCRIBER_EMAIL      fallback single recipient when no service key is set

Usage: python3 send_mail.py [--dry-run] [--min-score N]
"""
import argparse
import hashlib
import html as html_mod
import json
import os
import sys
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import match

DATA = Path(__file__).parent / "data"
STATE_FILE = DATA / "mail_state.json"
SITE = "https://nosey-dewdrop.github.io/sightstone"
SUPABASE_URL = "https://xjtmqncfhuidctxgthhv.supabase.co"
RESEND_ENDPOINT = "https://api.resend.com/emails"
RESEND_MAX_RECIPIENTS = 50  # provider limit on the `to` field


# --------------------------------------------------------------------- outcomes

@dataclass(frozen=True)
class MessageId:
    """Accepted by the provider. `id` is the provider's own message id."""
    id: str


@dataclass(frozen=True)
class HardBounce:
    """PERMANENT for this recipient. Retrying the same address cannot work."""
    reason: str
    code: int | None = None
    name: str | None = None


@dataclass(frozen=True)
class SoftFail:
    """TEMPORARY. Tomorrow's run may succeed; the subscriber stays alive."""
    reason: str
    code: int | None = None
    name: str | None = None


# A31 -- classification is READ, not invented.
#
# RESEND_ERROR_DOC is a transcript of every row of
# https://resend.com/docs/api-reference/errors (fetched 2026-08-30): the error
# `name`, every HTTP status the doc shows it under, and the fault SCOPE the
# doc's own Message/Suggested-action text puts it in. Nothing is in this table
# that is not on that page; test_send_provider.py holds an independent copy of
# the same transcript and fails if the two drift.
#
# SCOPE is the whole decision. Our two outcomes are per-SUBSCRIBER, and only
# one of them is destructive: a HardBounce marks a person permanently dead.
# So HardBounce is for one thing only -- an error that says something PERMANENT
# about THIS RECIPIENT. Read that way the doc splits into:
#
#   "account"   the API key / plan / domain / quota. Says nothing about the
#               subscriber. Killing an address because our key expired or our
#               sending domain lost its DNS record is the exact catastrophe the
#               card describes: one bad deploy, every subscriber marked dead.
#               validation_error @403 lives here -- the doc's three 403 bodies
#               are "The domain.com domain is not verified", "You can only send
#               testing emails to your own email address" and "domain has been
#               registered already". All three are about OUR account, not about
#               who we mailed.
#   "request"   our own payload or endpoint is wrong (missing field, bad UUID,
#               bad attachment, bad idempotency key, wrong path/method). That is
#               a bug in this repo. Fixing the bug reaches the same person
#               tomorrow, so the person must survive it.
#   "temporary" quota, rate limit, lock, 5xx. Obviously retryable.
#
# There is no fourth bucket. The send endpoint's error list contains NO
# condition that proves a recipient is permanently undeliverable -- Resend
# reports that asynchronously, as a bounce event, not in this response. So
# classify() never returns HardBounce, and RESEND_RECIPIENT_PERMANENT is empty
# on purpose rather than stuffed with the closest-looking names.
# HardBounce stays in the throat's contract because it is the outcome a bounce
# signal maps to; it is not something an HTTP status may be guessed into.
#
# Unknown name, `None` name, unparsable body, transport error, any status at
# all -> SoftFail. When in doubt the subscriber lives.
RESEND_ERROR_DOC = {
    #  name                            statuses    scope
    "invalid_idempotency_key":        ((400,),     "request"),
    "validation_error":               ((400, 403), "account"),
    "missing_api_key":                ((401,),     "account"),
    "restricted_api_key":             ((401, 403), "account"),
    "email_above_quota":              ((403,),     "account"),
    "invalid_permission":             ((403,),     "account"),
    "suspended_api_key":              ((403,),     "account"),
    "not_found":                      ((404,),     "request"),
    "method_not_allowed":             ((405,),     "request"),
    "concurrent_idempotent_requests": ((409,),     "temporary"),
    "invalid_idempotent_request":     ((409,),     "request"),
    "resource_locked":                ((409,),     "temporary"),
    "invalid_attachment":             ((422,),     "request"),
    "invalid_parameter":              ((422,),     "request"),
    "missing_required_field":         ((422,),     "request"),
    "missing_required_parameter":     ((422,),     "request"),
    "daily_quota_exceeded":           ((429,),     "temporary"),
    "monthly_quota_exceeded":         ((429,),     "temporary"),
    "rate_limit_exceeded":            ((429,),     "temporary"),
    "application_error":              ((500,),     "temporary"),
    "service_unavailable":            ((503,),     "temporary"),
}

# validation_error is the reason a name alone can never decide this: the doc
# shows it at 400 (some field of our request) AND at 403 (our domain is not
# verified). Neither reading is about the recipient, so the ambiguity resolves
# to SoftFail without needing the status at all -- but if a future row ever did
# name a recipient, the status would have to be part of the key, not the name.
RESEND_RECIPIENT_PERMANENT: frozenset[str] = frozenset()


def classify(status: int, name: str | None, message: str) -> HardBounce | SoftFail:
    """HTTP status + Resend error `name` -> per-subscriber outcome.

    HardBounce only for a name the doc marks permanent FOR THIS RECIPIENT.
    Everything else -- account, domain, quota, key, rate limit, server, our own
    malformed request, and every name this code has never heard of -- is a
    SoftFail, whatever the status. There is no status-based fallback: 422 with
    an unknown name is not evidence about a person.
    """
    if name in RESEND_RECIPIENT_PERMANENT:
        return HardBounce(message, status, name)
    return SoftFail(message, status, name)


# -------------------------------------------------------------------- providers

def unsubscribe_url(token: str | None) -> str:
    """Every mail carries a working way out, token or not."""
    if token:
        return f"{SITE}/unsubscribe.html?token={token}"
    return f"{SITE}/unsubscribe.html"


def build_payload(from_addr: str, to: str, subject: str, html: str,
                  text: str | None, unsub_url: str) -> dict:
    """The ONE place a mail body is assembled. Fields per the provider's docs:
    `from`, `to` (max 50), `subject` required; `html`, `text`, `headers` optional.

    List-Unsubscribe is added here and nowhere else, which is why it cannot be
    missing from a generated mail. List-Unsubscribe-Post is deliberately NOT
    added: the unsubscribe page is static GitHub Pages and answers POST with
    405, so advertising one-click would burn sender reputation (A29 -> S10).
    """
    recipients = [to] if isinstance(to, str) else list(to)
    if not recipients:
        raise ValueError("no recipient")
    if len(recipients) > RESEND_MAX_RECIPIENTS:
        raise ValueError(f"to accepts at most {RESEND_MAX_RECIPIENTS} recipients, "
                         f"got {len(recipients)}")
    if not subject:
        raise ValueError("subject is required")
    payload = {
        "from": from_addr,
        "to": recipients,
        "subject": subject,
        "html": html,
        "headers": {"List-Unsubscribe": f"<{unsub_url}>"},
    }
    if text is not None:
        payload["text"] = text
    return payload


class Provider:
    """send() is the only throat. Subclasses implement deliver() only."""

    def __init__(self, from_addr: str):
        self.from_addr = from_addr
        self.payloads: list[dict] = []

    def send(self, to: str, subject: str, html: str, *, text: str | None = None,
             unsub_url: str | None = None) -> MessageId | HardBounce | SoftFail:
        payload = build_payload(self.from_addr, to, subject, html, text,
                                unsub_url or unsubscribe_url(None))
        self.payloads.append(payload)
        return self.deliver(payload)

    def deliver(self, payload: dict) -> MessageId | HardBounce | SoftFail:
        raise NotImplementedError


class ResendProvider(Provider):
    """POST https://api.resend.com/emails with a Bearer token. stdlib only."""

    def __init__(self, from_addr: str, api_key: str, timeout: int = 30):
        super().__init__(from_addr)
        if not api_key:
            raise RuntimeError("RESEND_API_KEY is not set")
        self.api_key = api_key
        self.timeout = timeout

    def deliver(self, payload: dict) -> MessageId | HardBounce | SoftFail:
        req = urllib.request.Request(
            RESEND_ENDPOINT,
            data=json.dumps(payload).encode(),
            headers={"Authorization": f"Bearer {self.api_key}",
                     "Content-Type": "application/json"},
            method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            raw = ""
            try:
                raw = exc.read().decode()
            except Exception:
                pass
            name, message = None, raw or str(exc)
            try:
                parsed = json.loads(raw)
                name = parsed.get("name")
                message = parsed.get("message") or message
            except Exception:
                pass
            return classify(exc.code, name, message)
        except Exception as exc:  # URLError, timeout, socket, bad JSON
            return SoftFail(f"{type(exc).__name__}: {exc}")
        mid = body.get("id") if isinstance(body, dict) else None
        if not mid:
            return SoftFail(f"provider returned no id: {body!r}")
        return MessageId(mid)


class DryRunProvider(Provider):
    """A32 -- --dry-run binds HERE, never to None.

    A None provider is only safe while an early `return` happens to stand in
    front of it; reorder that return, or add the obvious
    `provider = provider or ResendProvider(...)` default, and --dry-run mails
    real people. A provider object that has no transport at all cannot do that
    no matter how the call site moves. It also keeps the payload (headers
    included) inspectable, which is what the dry run is for.
    """

    def deliver(self, payload: dict) -> MessageId:
        return MessageId("dry-run")


# ------------------------------------------------------------------ subscribers

def fetch_subscribers(service_key: str) -> list[dict]:
    # legacy service_role keys are JWTs ("eyJ...") and need the Bearer header;
    # new-format secret keys ("sb_secret_...") authenticate via apikey alone.
    headers = {"apikey": service_key}
    if service_key.startswith("eyJ"):
        headers["Authorization"] = f"Bearer {service_key}"
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/sightstone_subscribers"
        "?unsubscribed_at=is.null&select=email,name,level,interests,location,unsubscribe_token",
        headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def pseudo_profile(sub: dict) -> dict:
    """A Supabase subscriber row in the shape match.run expects."""
    return {
        "identity": {"name": sub.get("name") or sub["email"],
                     "location": sub.get("location") or ""},
        "education": [f'{sub.get("level") or "bs"} student'],
        "skills": {},
        "direction_and_motivation": {"target_field": "; ".join(sub.get("interests") or [])},
    }


def job_key(r: dict) -> str:
    raw = r.get("link") or f'{r["company"]}|{r["position"]}'
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {}


def save_state(state: dict) -> None:
    """Persist state ATOMICALLY: temp file in the same directory, then os.replace.

    Never a partial mail_state.json on disk. A crash mid-write leaves the old
    file untouched, so load_state() cannot die on a truncated JSON. Same
    directory is required: os.replace is only atomic within one filesystem.
    """
    target = STATE_FILE
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(target.parent),
                               prefix=".mail_state.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(state, fh, indent=1)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, target)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def compose(new: list[dict], total: int, unsubscribe_token: str | None = None) -> str:
    lines = [
        f"{len(new)} new internship listing(s) matched your profile this morning.",
        f"the engine read {total} live listings; only these are new for you, "
        "each with its named reasons. no black box, no language model.",
        "",
    ]
    for r in new:
        link = r.get("link") or f"link not found, search it yourself: {r['company']} {r['position']}"
        lines += [
            f"[{r['score']:>2}] {r['company']} - {r['position']}",
            f"     {r.get('location') or 'location unlisted'}"
            + (f" | {r['salary']}" if r.get("salary") else ""),
            f"     {link}",
            f"     why: {'; '.join(r['reasons'])}",
            "",
        ]
    lines += [
        "--",
        f"the engine · {SITE}",
        "you get mail only when something new matches. nothing new, no mail.",
    ]
    if unsubscribe_token:
        lines.append(f"one-click unsubscribe: {SITE}/unsubscribe.html?token={unsubscribe_token}")
    return "\n".join(lines)


def as_html(body: str) -> str:
    """The mail is written as plain text; the html part is that text, escaped."""
    return f"<pre style=\"font-family:ui-monospace,monospace\">{html_mod.escape(body)}</pre>"


def process_subscriber(email: str, profile: dict, jobs: list, state: dict,
                       min_score: int, dry_run: bool, provider: Provider,
                       unsubscribe_token: str | None) -> str:
    """Match, mail if anything is new, update state in place.

    Returns one of: sent | nothing_new | dry_run | hard_bounce | soft_fail.
    """
    results, stats = match.run(profile, jobs)
    sub_id = hashlib.sha1(email.encode()).hexdigest()[:12]
    sent = set(state.get(sub_id, {}).get("sent_keys", []))
    eligible = [r for r in results if r["score"] >= min_score]
    new = [r for r in eligible if job_key(r) not in sent]

    print(f"{email}: matched {stats['matched']} | eligible {len(eligible)} | "
          f"already mailed {len(eligible) - len(new)} | new {len(new)}")
    if not new:
        return "nothing_new"

    body = compose(new, stats["considered"], unsubscribe_token)
    subject = f"{len(new)} new internship match(es) · {date.today().isoformat()}"
    if dry_run:
        print(f"DRY RUN — would send to {email}: {subject}")
        return "dry_run"

    result = provider.send(email, subject, as_html(body), text=body,
                           unsub_url=unsubscribe_url(unsubscribe_token))
    if isinstance(result, HardBounce):
        print(f"HARD BOUNCE {email}: {result.name or '-'} {result.code or ''} "
              f"{result.reason}")
        return "hard_bounce"
    if isinstance(result, SoftFail):
        print(f"SOFT FAIL {email}: {result.name or '-'} {result.code or ''} "
              f"{result.reason}")
        return "soft_fail"
    print(f"sent to {email}: {subject} [{result.id}]")

    # The mail is out. Persist BEFORE touching the next subscriber: if the run
    # dies on subscriber n+1, what n already received must never be re-sent.
    # Existing sent_keys are unioned, never reset -- a profile edit rescores,
    # it does not un-send.
    state.setdefault(sub_id, {})["sent_keys"] = sorted(sent | {job_key(r) for r in new})
    state[sub_id]["last_sent"] = date.today().isoformat()
    save_state(state)
    print(f"state written: {STATE_FILE}")
    return "sent"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--min-score", type=int, default=5,
                    help="mail only matches at or above this score")
    args = ap.parse_args()

    api_key = os.environ.get("RESEND_API_KEY")
    from_addr = os.environ.get("MAIL_FROM")
    service_key = os.environ.get("SUPABASE_SERVICE_KEY")
    fallback_addr = os.environ.get("SUBSCRIBER_EMAIL")

    # who gets mail today
    targets = []  # (email, profile, unsubscribe_token)
    if service_key:
        subs = fetch_subscribers(service_key)
        print(f"subscribers from supabase: {len(subs)}")
        for s in subs:
            targets.append((s["email"], pseudo_profile(s), s.get("unsubscribe_token")))
    elif fallback_addr:
        profile = json.loads((Path(__file__).parent.parent / "profile.json").read_text())
        targets.append((fallback_addr, profile, None))
        print("single-subscriber fallback mode (no SUPABASE_SERVICE_KEY)")
    elif args.dry_run:
        profile = json.loads((Path(__file__).parent.parent / "profile.json").read_text())
        targets.append(("dry@example.com", profile, None))
    else:
        print("no subscribers configured", file=sys.stderr)
        sys.exit(1)

    if args.dry_run:
        provider = DryRunProvider("the engine <dry-run@invalid>")
    else:
        if not api_key:
            print("missing RESEND_API_KEY", file=sys.stderr)
            sys.exit(1)
        if not from_addr:
            print("missing MAIL_FROM", file=sys.stderr)
            sys.exit(1)
        provider = ResendProvider(from_addr, api_key)

    jobs = json.loads((DATA / "jobs.json").read_text())
    state = load_state()

    # A25 -- ABONE IZOLASYONU. Every subscriber sits inside its own try. One
    # dead address, one provider failure, one unexpected exception: the run logs
    # it and moves to the next person. Nobody goes unprocessed because of
    # somebody else. A28: there is no teardown around this loop that could
    # swallow the original exception -- the transport is a stateless POST, there
    # is nothing to quit().
    tally = {"sent": 0, "nothing_new": 0, "dry_run": 0,
             "hard_bounce": 0, "soft_fail": 0, "error": 0}
    processed = 0
    for email, profile, token in targets:
        processed += 1
        try:
            outcome = process_subscriber(email, profile, jobs, state,
                                         args.min_score, args.dry_run,
                                         provider, token)
        except Exception as exc:
            tally["error"] += 1
            print(f"ERROR {email}: {type(exc).__name__}: {exc}", file=sys.stderr)
            continue
        tally[outcome] += 1
    mailed = tally["sent"]

    # No bulk write here on purpose: process_subscriber already flushed state to
    # disk after every successful send. A write at this point could only ever be
    # reached when nothing crashed, which is exactly the case that needed no
    # protection.
    print(f"done: {mailed} mail(s) sent, {len(targets) - mailed} had nothing new.")
    print(f"summary: processed {processed}/{len(targets)} | sent {tally['sent']} | "
          f"nothing new {tally['nothing_new']} | dry run {tally['dry_run']} | "
          f"hard bounce {tally['hard_bounce']} | soft fail {tally['soft_fail']} | "
          f"error {tally['error']}")


if __name__ == "__main__":
    main()
