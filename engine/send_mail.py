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
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import match

DATA = Path(__file__).parent / "data"
STATE_FILE = DATA / "mail_state.json"
QUOTA_FILENAME = "quota_state.json"
# Derived from DATA at call time, never bound at import: tests patch DATA,
# and a module-level path would keep pointing at the real engine/data.
CONFIRM_FILENAME = "confirm_state.json"
SITE = "https://nosey-dewdrop.github.io/sightstone"
SUPABASE_URL = "https://xjtmqncfhuidctxgthhv.supabase.co"
RESEND_ENDPOINT = "https://api.resend.com/emails"
USER_AGENT = "sightstone/1.0 (+https://nosey-dewdrop.github.io/sightstone)"
RESEND_MAX_RECIPIENTS = 50  # provider limit on the `to` field


# ------------------------------------------------------------------------ quota
#
# S9a -- "the quota does not blow up on launch day".
#
# The free tier stops at a hundred mails a day and three thousand a month. Two
# hundred people signing up in one morning is two hundred confirmation mails;
# person 101 never gets one and their account dies unconfirmed. The counter
# below exists so that never happens silently.
#
# THE BUDGET IS 2.550 A MONTH, NOT 2.850. The provider's own docs say, under
# BOTH `daily_quota_exceeded` and `monthly_quota_exceeded`: "Both sent and
# received emails count towards this quota." Inbound mail eats the same budget
# and this ledger CANNOT see it -- every number here is a LOWER BOUND on real
# consumption. A 15% reserve (450) absorbs that blind spot; 5% (150) does not.
#
# THE WINDOWS ROLL. The docs say "wait until 24 hours have passed"; they never
# name a reset moment. So the daily window is the last 24 HOURS, not a calendar
# day. `date.today()` is FORBIDDEN anywhere on this path: the runner is UTC and
# Damla is UTC+3, so a run hand-triggered at 01:00 TRT opens a SECOND calendar
# bucket for the same real day -- two days' worth of mail against one day's cap.
# The monthly window is the rolling 30 days AND the calendar month, whichever
# fills first: the docs do not define the month, so we take the tightest one.
RESEND_DAILY_QUOTA = 100      # provider free tier, per rolling 24 hours
DAILY_MAIL_CAP = 90           # the daily quota minus a ten-mail safety margin
RESEND_MONTHLY_QUOTA = 3000   # hard ceiling; nothing at all passes this
MONTHLY_BULLETIN_CAP = 2550   # 15% reserve for the inbound mail we cannot see

# The unit that is spent is a MAIL, never a call: one request may carry up to
# RESEND_MAX_RECIPIENTS addresses, and counting it as 1 would overshoot by 50x.
MAIL_KINDS = frozenset({"bulletin", "confirm", "invite"})

# Seeing one of these come BACK from the provider means our own counter was
# wrong. Running out of quota is a plan; being told we ran out is a fault.
PROVIDER_QUOTA_ERRORS = frozenset({"daily_quota_exceeded", "monthly_quota_exceeded"})

DAILY_WINDOW = timedelta(hours=24)
MONTHLY_WINDOW = timedelta(days=30)


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


@dataclass(frozen=True)
class QuotaHalt:
    """PLANNED. The budget was gone, so the send was never ATTEMPTED.

    Not a failure: nothing was asked of the provider, no address is suspect,
    the mail is simply deferred to a run that has budget. This is the outcome
    that distinguishes "we stopped" from "we were stopped".
    """
    reason: str       # "daily" | "monthly"
    deferred: int     # mails not attempted by this call


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


# ---------------------------------------------------------------- quota ledger

def _now() -> datetime:
    """The ONE clock on the quota path, and it is UTC-aware.

    Deliberately not date.today(): a naive calendar day is the bug this whole
    section exists to prevent. Tests replace this function, never the windows.
    """
    return datetime.now(timezone.utc)


def quota_path() -> Path:
    """Derived from DATA at call time, so a sandboxed run cannot touch the live
    ledger by forgetting to patch a second constant."""
    return DATA / QUOTA_FILENAME


def _atomic_write_json(target: Path, obj) -> None:
    """Same discipline as save_state: temp file beside the target, then replace."""
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(target.parent),
                               prefix=f".{target.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(obj, fh, indent=1)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, target)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


class QuotaLedger:
    """Every mail this account has sent recently, with a UTC stamp and a kind.

    One record per accepted send: {"at": iso8601 utc, "kind": ..., "count": n}
    where n is the number of RECIPIENTS, because that is what the provider
    charges. Rejected calls are absent: a 4xx never reached the quota.
    """

    def __init__(self, path: Path):
        self.path = path
        raw = {}
        if path.exists():
            try:
                raw = json.loads(path.read_text())
            except (ValueError, OSError):
                raw = {}
        self.sends: list[dict] = list(raw.get("sends") or [])
        # what the PREVIOUS run left behind, so a growing backlog is visible
        self.previous_deferred = int(((raw.get("halted") or {}).get("deferred")) or 0)
        self.deferred = 0
        self.halt_reason: str | None = None
        self.halt_at: str | None = None

    # ------------------------------------------------------------- windows
    @staticmethod
    def _stamp(rec: dict) -> datetime | None:
        try:
            dt = datetime.fromisoformat(rec["at"])
        except (KeyError, TypeError, ValueError):
            return None
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

    def _sum(self, predicate) -> int:
        total = 0
        for rec in self.sends:
            when = self._stamp(rec)
            if when is not None and predicate(when):
                total += int(rec.get("count") or 0)
        return total

    def used_today(self, now: datetime | None = None) -> int:
        """Mails in the last 24 HOURS. Rolling, so a UTC/UTC+3 midnight cannot
        hand the same real day two fresh buckets."""
        now = now or _now()
        return self._sum(lambda w: w > now - DAILY_WINDOW)

    def used_month(self, now: datetime | None = None) -> int:
        """The TIGHTER of the rolling 30 days and the calendar month.

        The provider documents neither, so we refuse to pick the generous one.
        """
        now = now or _now()
        rolling = self._sum(lambda w: w > now - MONTHLY_WINDOW)
        calendar = self._sum(lambda w: (w.year, w.month) == (now.year, now.month))
        return max(rolling, calendar)

    def monthly_cap(self, kind: str) -> int:
        """The bulletin stops early so confirm/invite still have room. A person
        who cannot confirm is lost; a person who misses one digest is not."""
        return MONTHLY_BULLETIN_CAP if kind == "bulletin" else RESEND_MONTHLY_QUOTA

    def remaining_today(self, now: datetime | None = None) -> int:
        return max(0, DAILY_MAIL_CAP - self.used_today(now))

    def remaining_month(self, kind: str, now: datetime | None = None) -> int:
        return max(0, self.monthly_cap(kind) - self.used_month(now))

    # ------------------------------------------------------------ decisions
    def would_exceed(self, kind: str, count: int,
                     now: datetime | None = None) -> str | None:
        """"daily" | "monthly" | None -- asked BEFORE anything is attempted."""
        now = now or _now()
        if self.used_today(now) + count > DAILY_MAIL_CAP:
            return "daily"
        if self.used_month(now) + count > self.monthly_cap(kind):
            return "monthly"
        return None

    def record(self, kind: str, count: int, now: datetime | None = None) -> None:
        now = now or _now()
        self.sends.append({"at": now.isoformat(), "kind": kind, "count": int(count)})
        self.save(now)

    def defer(self, reason: str, count: int, now: datetime | None = None) -> None:
        now = now or _now()
        self.deferred += int(count)
        if self.halt_reason is None:
            self.halt_reason, self.halt_at = reason, now.isoformat()

    def backlog_grew(self) -> bool:
        return self.deferred > self.previous_deferred

    # -------------------------------------------------------------- storage
    def _prune(self, now: datetime) -> None:
        """Drop what no window can see again. Keep whichever reaches further
        back: 30 rolling days, or the first instant of this calendar month."""
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        cutoff = min(now - MONTHLY_WINDOW, month_start)
        self.sends = [r for r in self.sends
                      if (self._stamp(r) or now) >= cutoff]

    def as_dict(self, now: datetime | None = None) -> dict:
        """`halted` is ALWAYS present. Absence must never stand for a state:
        a missing key reads as "no halt" whether the run was clean or the
        writer crashed before it got there."""
        now = now or _now()
        halted = None
        if self.halt_reason is not None:
            halted = {"at": self.halt_at, "reason": self.halt_reason,
                      "deferred": self.deferred}
        return {"sends": self.sends, "halted": halted}

    def save(self, now: datetime | None = None) -> None:
        now = now or _now()
        self._prune(now)
        _atomic_write_json(self.path, self.as_dict(now))


_LEDGER: QuotaLedger | None = None


def ledger() -> QuotaLedger:
    global _LEDGER
    if _LEDGER is None:
        _LEDGER = QuotaLedger(quota_path())
    return _LEDGER


def reset_ledger() -> QuotaLedger:
    """Re-read the ledger from whatever DATA points at right now."""
    global _LEDGER
    _LEDGER = QuotaLedger(quota_path())
    return _LEDGER


def remaining_today(now: datetime | None = None) -> int:
    """How many more mails may go out in the next instant.

    Exported on purpose: S9b hands this straight to
    sightstone_run_invites(daily_limit) so the seat opener cannot outrun the
    mailer. Nothing here knows about seats.
    """
    return ledger().remaining_today(now)


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
    """send() is the only throat. Subclasses implement deliver() only.

    Because it is the only throat, it is also the only place a mail can be
    counted, and the only place a send can be refused before it is attempted.
    """

    #: does traffic from this provider reach the account the quota is on?
    #: True by default: a subclass that forgets to answer must be counted, not
    #: silently exempted.
    consumes_quota = True

    def __init__(self, from_addr: str):
        self.from_addr = from_addr
        self.payloads: list[dict] = []

    def send(self, to: str, subject: str, html: str, *, kind: str,
             text: str | None = None, unsub_url: str | None = None
             ) -> MessageId | HardBounce | SoftFail | QuotaHalt:
        """`kind` is REQUIRED and closed. There is no default on purpose: the
        three kinds share one budget but not one stop line, so a caller that
        does not say which one it is cannot be guessed for."""
        if kind not in MAIL_KINDS:
            raise ValueError(f"unknown mail kind {kind!r}; "
                             f"expected one of {sorted(MAIL_KINDS)}")
        payload = build_payload(self.from_addr, to, subject, html, text,
                                unsub_url or unsubscribe_url(None))
        # what the provider charges is one mail per ADDRESS, not per request
        mails = len(payload["to"])
        if self.consumes_quota:
            book = ledger()
            reason = book.would_exceed(kind, mails)
            if reason:
                # planned stop: deliver() is never called, so nothing is spent
                # and no address is implicated.
                book.defer(reason, mails)
                return QuotaHalt(reason, mails)
        self.payloads.append(payload)
        result = self.deliver(payload)
        if self.consumes_quota and isinstance(result, MessageId):
            # only an accepted call cost us anything; a rejected 4xx did not.
            ledger().record(kind, mails)
        return result

    def deliver(self, payload: dict) -> MessageId | HardBounce | SoftFail:
        raise NotImplementedError


class ResendProvider(Provider):
    """POST https://api.resend.com/emails with a Bearer token. stdlib only."""

    consumes_quota = True   # the real account, the real budget

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
            # User-Agent is REQUIRED, not decoration. Resend sits behind
            # Cloudflare, which 403s urllib's default "Python-urllib/x.y" with
            # error code 1010. Measured 2026-09-01: default UA -> 403, this UA
            # -> 200, same key, same endpoint. Without it every send soft-fails
            # and the bulletin silently never arrives.
            headers={"Authorization": f"Bearer {self.api_key}",
                     "Content-Type": "application/json",
                     "User-Agent": USER_AGENT},
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

    #: nothing leaves the process, so nothing is charged. A rehearsal that ate
    #: the real budget would be worse than no rehearsal.
    consumes_quota = False

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
        "?unsubscribed_at=is.null&select=email,name,level,interests,location,"
        "unsubscribe_token,confirmed_at",
        headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            rows = json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        # The live table can be OLDER than schema.sql. confirmed_at was added by
        # S6 and the file was never applied to the cluster, so asking for the
        # column answered 400 and the whole run died on a raw traceback.
        #
        # Fail CLOSED and say why. Not falling back to the unfiltered query on
        # purpose: that fallback is precisely the D2 hole -- one missing
        # migration and the mailer quietly goes back to mailing people who never
        # consented. No column means nobody is confirmed, so there is nothing
        # honest to send anyway.
        body = ""
        try:
            body = exc.read().decode()
        except Exception:
            pass
        if exc.code == 400 and "confirmed_at" in body:
            raise SystemExit(
                "sightstone_subscribers has no confirmed_at column: engine/"
                "schema.sql has not been applied to this cluster.\n"
                "No mail sent -- without that column nobody is confirmed, and "
                "mailing unconfirmed addresses is the D2 violation.\n"
                "Fix: run engine/schema.sql in the Supabase SQL editor. It also "
                "creates sightstone_run_invites(), which the invite loop needs."
            ) from exc
        raise

    # D2. An address that never clicked confirm has not consented, and mailing
    # it is the KVKK/GDPR violation this whole column exists to prevent. The
    # schema has had confirmed_at, confirm_token and sightstone_confirm() since
    # S6; the query simply never used them, so every address ever mailed was by
    # definition unconfirmed.
    #
    # Filtered HERE and not in the URL on purpose: the count of who was held
    # back has to be printable. A silent `&confirmed_at=not.is.null` would turn
    # "nobody has confirmed yet" into "zero subscribers today" with no line in
    # the log saying why, and the bulletin would just stop with nothing to
    # explain it.
    confirmed = [r for r in rows if r.get("confirmed_at")]
    held = len(rows) - len(confirmed)
    if held:
        print(f"held back {held} unconfirmed subscriber(s): no confirm click, "
              f"no mail (D2)")
    return confirmed


# ------------------------------------------------------------ seats / invites
#
# S9b -- "seats open at the speed of the quota".
#
# Two holes were measured here, and they are different holes.
#
# HOLE 1 was in the SQL. sightstone_run_invites() took no argument and stamped
# invited_at on every free seat at once. The stamp is a PROMISE -- "your turn,
# you have 48 hours" -- and the only way that promise is ever delivered is a
# mail. With every seat freeing at once the function stamped every waiting row,
# the provider allowed one DAILY_MAIL_CAP worth of mail, and the remainder were
# quietly marked dropped_at 48 hours later without ever hearing from us. (The
# cap is not written as a digit here on purpose: a quota number loose in a
# comment is a number that drifts from the constant. See test_send_provider's
# one-named-line gate.) Passing
# remaining_today() as daily_limit is what makes the stamp and the mail the
# same number.
#
# HOLE 2 was that NOTHING CALLED IT. The function existed, the tests called it,
# and no shipped code path did: no workflow step, no pg_cron row. The comment at
# the head of schema.sql said "runs once a day" and it ran zero times a day.
# This module is the caller. It is reached by the mail step of the daily
# workflow, which is the one place that already has both the service key and
# the quota ledger open.
#
# STAMPED-BUT-UNMAILED MUST STAY ZERO, and the quota is not the only way to
# break that: a stamp lands, then the provider softfails on that one address,
# and the row sits reserved-and-silent until it expires. So a send that is not
# ACCEPTED gives the stamp back -- invited_at and invite_expires_at go to null
# and the person returns to the head of the queue for the next run. Releasing
# is a write against the row's own invite_token, nothing else.

WAITLIST_TABLE = "sightstone_waitlist"
LIVE_INVITE_FILTER = ("invited_at=not.is.null&accepted_at=is.null"
                      "&dropped_at=is.null")


class SeatBackend:
    """The three seat operations the invite loop needs, and nothing else.

    Kept behind a class so the loop can be driven against a throwaway
    PostgreSQL in the tests. The tests substitute an implementation that talks
    to a local cluster; no test ever reaches this file's HTTP.
    """

    def run_invites(self, daily_limit: int) -> int:
        raise NotImplementedError

    def fresh_invites(self, count: int) -> list[dict]:
        raise NotImplementedError

    def release_invite(self, token: str) -> None:
        raise NotImplementedError


class SupabaseSeats(SeatBackend):
    """PostgREST. Same key handling and same urllib as fetch_subscribers."""

    def __init__(self, service_key: str, timeout: int = 30):
        if not service_key:
            raise RuntimeError("SUPABASE_SERVICE_KEY is not set")
        self.service_key = service_key
        self.timeout = timeout

    def _headers(self) -> dict:
        # legacy service_role keys are JWTs ("eyJ...") and need the Bearer
        # header; new-format secret keys ("sb_secret_...") use apikey alone.
        headers = {"apikey": self.service_key, "Content-Type": "application/json"}
        if self.service_key.startswith("eyJ"):
            headers["Authorization"] = f"Bearer {self.service_key}"
        return headers

    def _call(self, path: str, *, method: str = "GET", body=None):
        req = urllib.request.Request(
            f"{SUPABASE_URL}{path}",
            data=None if body is None else json.dumps(body).encode(),
            headers=self._headers(), method=method)
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            raw = resp.read().decode()
        return json.loads(raw) if raw.strip() else None

    def run_invites(self, daily_limit: int) -> int:
        """The RPC. daily_limit is REQUIRED by the function's signature now, so
        a caller that forgets it gets an error instead of the old behaviour."""
        out = self._call("/rest/v1/rpc/sightstone_run_invites",
                         method="POST", body={"daily_limit": int(daily_limit)})
        return int(out or 0)

    def fresh_invites(self, count: int) -> list[dict]:
        """The rows the call above just stamped.

        run_invites stamps every row of one batch inside ONE transaction, so
        all of them carry the identical invited_at and every older invite is
        strictly earlier. Newest-first, limit `count`, is therefore exactly
        that batch -- no row from a previous day can be pulled in and mailed a
        second time.
        """
        if count <= 0:
            return []
        rows = self._call(
            f"/rest/v1/{WAITLIST_TABLE}?{LIVE_INVITE_FILTER}"
            f"&select=email,invite_token&order=invited_at.desc,email.asc"
            f"&limit={int(count)}")
        return list(rows or [])

    def release_invite(self, token: str) -> None:
        """Hand the stamp back. The seat is freed in the same instant, because
        the third term of sightstone_seats_taken() stops counting this row."""
        self._call(f"/rest/v1/{WAITLIST_TABLE}?invite_token=eq.{token}",
                   method="PATCH",
                   body={"invited_at": None, "invite_expires_at": None})


def compose_invite(token: str | None) -> str:
    """Plain text; the html part is this text escaped, as everywhere else."""
    # /accept.html, not the home page: the home page reads no token, so the
    # seat could be offered, clicked, and still expire unaccepted.
    link = f"{SITE}/accept.html?token={token}" if token else SITE
    return "\n".join([
        "a seat opened up and it is yours for the next 48 hours.",
        "",
        "you asked to be told when the engine had room. it has room now, and "
        "you are next in line.",
        f"    {link}",
        "",
        "after 48 hours the seat passes to whoever is behind you. nothing is "
        "lost if you miss it -- you keep your place and get asked again.",
        "",
        "--",
        f"the engine · {SITE}",
    ])


def compose_confirm(token: str | None) -> str:
    """Plain text; the html part is this text escaped, as everywhere else."""
    link = f"{SITE}/confirm.html?token={token}" if token else SITE
    return "\n".join([
        "one click and the engine starts reading for you.",
        "",
        "somebody put this address into the engine. if that was you, confirm "
        "it here:",
        f"    {link}",
        "",
        "if it was not you, do nothing at all. the link dies after 48 hours "
        "and the address is dropped -- you will not hear from us again.",
        "",
        "--",
        f"the engine · {SITE}",
    ])


def pending_confirmations(service_key: str) -> list[dict]:
    """Addresses that signed up, have not confirmed, and are still in time.

    The 48-hour window is the schema's, not a second opinion: sightstone_confirm
    refuses a token older than that, so mailing a link we know is already dead
    would be a worse lie than sending nothing.
    """
    headers = {"apikey": service_key}
    if service_key.startswith("eyJ"):
        headers["Authorization"] = f"Bearer {service_key}"
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/sightstone_subscribers"
        "?confirmed_at=is.null&unsubscribed_at=is.null"
        f"&created_at=gt.{urllib.parse.quote(cutoff)}"
        "&select=email,confirm_token",
        headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def send_confirmations(rows: list[dict], provider: Provider) -> dict:
    """Mail each pending address its confirm link, at most once, ever.

    Kept in its own small ledger rather than in mail_state.json: mail_state is
    keyed by subscriber id and its shape is nailed by tests, and an unconfirmed
    person is not a subscriber yet. Once-ever and not once-a-day because a
    confirmation is not a reminder campaign -- the schema gives them 48 hours,
    and nagging an address that never asked for us is how a young sending
    domain gets burned.
    """
    state_file = DATA / CONFIRM_FILENAME
    seen = {}
    if state_file.exists():
        seen = json.loads(state_file.read_text())
    tally = {"sent": 0, "already": 0, "halted": 0, "failed": 0}
    for row in rows:
        email = row["email"]
        if email in seen:
            tally["already"] += 1
            continue
        text = compose_confirm(row.get("confirm_token"))
        result = provider.send(email, "confirm your address · the engine",
                               as_html(text), kind="confirm", text=text)
        if isinstance(result, MessageId):
            seen[email] = datetime.now(timezone.utc).isoformat()
            tally["sent"] += 1
            # written per address, not at the end: a crash halfway through must
            # not re-mail the people who already got theirs.
            state_file.parent.mkdir(parents=True, exist_ok=True)
            state_file.write_text(json.dumps(seen, indent=1, sort_keys=True))
        elif isinstance(result, QuotaHalt):
            tally["halted"] += 1
        else:
            tally["failed"] += 1
    if rows:
        print(f"confirmations: sent {tally['sent']} | already {tally['already']} "
              f"| quota halt {tally['halted']} | failed {tally['failed']}")
    return tally


def run_invite_loop(seats: SeatBackend, provider: Provider,
                    now: datetime | None = None) -> dict:
    """Open as many seats as today's quota can actually mail, then mail them.

    Order matters and it is the whole point: the budget is read FIRST and
    handed to the database, so the database never stamps a promise this run
    cannot keep. Returns a tally; the caller prints it.
    """
    tally = {"budget": 0, "opened": 0, "mailed": 0, "released": 0, "missing": 0}
    tally["budget"] = budget = remaining_today(now)
    if budget <= 0:
        print("invites: no daily budget left, no seat opened")
        return tally

    tally["opened"] = opened = seats.run_invites(budget)
    print(f"invites: budget {budget} | opened {opened}")
    if opened <= 0:
        return tally

    rows = seats.fresh_invites(opened)
    # Fewer rows than stamps would mean stamped-and-unfindable, which is the
    # exact state this card exists to make impossible. Say it out loud.
    tally["missing"] = max(0, opened - len(rows))

    for row in rows:
        email, token = row.get("email"), row.get("invite_token")
        result = provider.send(
            email, "a seat opened up · the engine",
            as_html(compose_invite(token)), kind="invite",
            text=compose_invite(token), unsub_url=unsubscribe_url(None))
        if isinstance(result, MessageId):
            tally["mailed"] += 1
            print(f"invited {email} [{result.id}]")
            continue
        # Not accepted. The stamp goes back rather than sitting on a seat in
        # silence until it expires.
        reason = getattr(result, "reason", str(result))
        print(f"invite NOT sent to {email}: {reason}; releasing the seat",
              file=sys.stderr)
        seats.release_invite(token)
        tally["released"] += 1
    return tally


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
        # NOT "one-click". One-click is a POST (RFC 8058) and this page is
        # static GitHub Pages: measured live 2026-09-01, POST -> 405, GET -> 200.
        # It said "one-click unsubscribe" in every mail that ever went out,
        # which was a promise the page could not keep. It opens and you click
        # once on the page; that is what it now says.
        lines.append(f"unsubscribe: {SITE}/unsubscribe.html?token={unsubscribe_token}")
    return "\n".join(lines)


def as_html(body: str) -> str:
    """The mail is written as plain text; the html part is that text, escaped."""
    return f"<pre style=\"font-family:ui-monospace,monospace\">{html_mod.escape(body)}</pre>"


def process_subscriber(email: str, profile: dict, jobs: list, state: dict,
                       min_score: int, dry_run: bool, provider: Provider,
                       unsubscribe_token: str | None) -> str:
    """Match, mail if anything is new, update state in place.

    Returns one of: sent | nothing_new | dry_run | quota_halt | quota_error |
    hard_bounce | soft_fail.
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

    result = provider.send(email, subject, as_html(body), kind="bulletin",
                           text=body,
                           unsub_url=unsubscribe_url(unsubscribe_token))
    if isinstance(result, QuotaHalt):
        # Nothing was attempted, so nothing is marked as mailed: the same
        # listings must still reach this person on a run that has budget.
        print(f"deferred {email}: quota exhausted ({result.reason})")
        return "quota_halt"
    if isinstance(result, HardBounce):
        print(f"HARD BOUNCE {email}: {result.name or '-'} {result.code or ''} "
              f"{result.reason}")
        return "hard_bounce"
    if isinstance(result, SoftFail):
        print(f"SOFT FAIL {email}: {result.name or '-'} {result.code or ''} "
              f"{result.reason}")
        # The provider telling US about the quota means our own counter was
        # already wrong. That is a fault, not a plan, and the run must say so.
        if result.name in PROVIDER_QUOTA_ERRORS:
            return "quota_error"
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
    # 4 == "at least one INTEREST hit" on the current scale (interest +4 each,
    # skill +2 each). It was 5 when geography and freshness still scored, where
    # 5 meant "one interest hit plus any padding". Those points are gone, so 5
    # now means "two interest hits" and the measured result was eligible 0 --
    # a bulletin that never sends. 4 keeps the old intent: an interest match is
    # required to mail; a skill-only listing (2) is not enough on its own.
    ap.add_argument("--min-score", type=int, default=4,
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
    book = reset_ledger()   # read AFTER DATA is settled, never before

    # S10 -- CONFIRMATIONS GO FIRST, before any bulletin.
    #
    # D2 holds back every unconfirmed address. Without this call that hold is
    # permanent for everyone new: they sign up, they are never mailed, and the
    # front door is shut. It runs before the bulletins because a person who
    # cannot confirm is lost outright, while a person whose digest slips a day
    # is not -- the same reasoning the monthly cap already encodes.
    if service_key and not args.dry_run:
        try:
            send_confirmations(pending_confirmations(service_key), provider)
        except Exception as exc:
            # never let the front door take the bulletins down with it
            print(f"ERROR confirmations: {type(exc).__name__}: {exc}",
                  file=sys.stderr)

    # A25 -- ABONE IZOLASYONU. Every subscriber sits inside its own try. One
    # dead address, one provider failure, one unexpected exception: the run logs
    # it and moves to the next person. Nobody goes unprocessed because of
    # somebody else. A28: there is no teardown around this loop that could
    # swallow the original exception -- the transport is a stateless POST, there
    # is nothing to quit().
    tally = {"sent": 0, "nothing_new": 0, "dry_run": 0, "quota_halt": 0,
             "quota_error": 0, "hard_bounce": 0, "soft_fail": 0, "error": 0}
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

    # S9b -- THE INVITE LOOP RUNS HERE, and this is the only place it runs.
    #
    # AFTER the bulletins, not before: what is left of the day's budget is what
    # gets handed to the database. Opening seats first would push the bulletins
    # into a halt, and a halted bulletin backlog exits non-zero, so the run
    # would report a fault for doing the right thing. A deferred seat is not a
    # fault -- nobody was stamped, nobody was promised anything, and tomorrow's
    # run opens it.
    #
    # A dry run does not come in here AT ALL. DryRunProvider spends no quota,
    # but sightstone_run_invites writes to the real database: a rehearsal would
    # stamp real people with a real 48 hour clock and mail none of them.
    invites = None
    if args.dry_run:
        print("invites: skipped (--dry-run never stamps a real seat)")
    elif service_key:
        try:
            invites = run_invite_loop(SupabaseSeats(service_key), provider)
        except Exception as exc:
            print(f"ERROR invite loop: {type(exc).__name__}: {exc}",
                  file=sys.stderr)
    else:
        print("invites: skipped (no SUPABASE_SERVICE_KEY, no waitlist to read)")

    # No bulk write here on purpose: process_subscriber already flushed state to
    # disk after every successful send. A write at this point could only ever be
    # reached when nothing crashed, which is exactly the case that needed no
    # protection.
    print(f"done: {mailed} mail(s) sent, {len(targets) - mailed} had nothing new.")
    print(f"summary: processed {processed}/{len(targets)} | sent {tally['sent']} | "
          f"nothing new {tally['nothing_new']} | dry run {tally['dry_run']} | "
          f"quota halt {tally['quota_halt']} | quota error {tally['quota_error']} | "
          f"hard bounce {tally['hard_bounce']} | soft fail {tally['soft_fail']} | "
          f"error {tally['error']}")
    if invites is not None:
        print(f"invites: opened {invites['opened']} | mailed {invites['mailed']} "
              f"| released {invites['released']} | missing {invites['missing']}")

    # The ledger is written on EVERY run, halt or no halt, so that `halted`
    # being null is a statement and not an absence.
    book.save()
    print(f"quota: {book.used_today()} mail(s) in the last 24h | "
          f"{book.used_month()} this month | {book.remaining_today()} left today")
    if book.halt_reason:
        print(f"QUOTA HALT reason={book.halt_reason} deferred={book.deferred}",
              file=sys.stderr)

    # Four outcomes, in order of what they mean:
    #  * the provider told us about the quota  -> our counter was wrong. FAULT.
    #  * the backlog is bigger than last run's -> we are falling behind, and a
    #    queue that grows must not read as a green run.
    #  * a planned stop that did not grow      -> working as designed. 0.
    #  * nothing happened                      -> 0.
    if tally["quota_error"]:
        print(f"EXIT: provider reported a quota error on {tally['quota_error']} "
              f"send(s); the local counter is wrong", file=sys.stderr)
        sys.exit(1)
    if invites is not None and invites["missing"]:
        # Rows were stamped and then could not be read back, so somebody is
        # holding a 48 hour promise nobody mailed. That is this card's one
        # forbidden state; it may not exit green.
        print(f"EXIT: {invites['missing']} seat(s) stamped but not mailed",
              file=sys.stderr)
        sys.exit(1)
    if book.backlog_grew():
        print(f"EXIT: deferred grew {book.previous_deferred} -> {book.deferred}",
              file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
