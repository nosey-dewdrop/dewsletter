#!/usr/bin/env python3
"""Daily match mail. Deterministic, idempotent, no LLM.

Contract (printed on the site): a mail is sent ONLY when new listings match the
subscriber's profile. Nothing new -> no mail. Already-mailed listings are never
repeated; state lives in data/mail_state.json and is committed by the daily
workflow, so re-runs cannot double-send.

Env:
  SMTP_USER             gmail address that sends
  SMTP_PASS             gmail app password
  SUPABASE_SERVICE_KEY  if set, subscribers are read from Supabase (multi-subscriber)
  SUBSCRIBER_EMAIL      fallback single recipient when no service key is set

Usage: python3 send_mail.py [--dry-run] [--min-score N]
"""
import argparse
import hashlib
import json
import os
import smtplib
import sys
import tempfile
import urllib.request
from datetime import date
from email.mime.text import MIMEText
from pathlib import Path

import match

DATA = Path(__file__).parent / "data"
STATE_FILE = DATA / "mail_state.json"
SITE = "https://nosey-dewdrop.github.io/sightstone"
SUPABASE_URL = "https://xjtmqncfhuidctxgthhv.supabase.co"


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


def process_subscriber(email: str, profile: dict, jobs: list, state: dict,
                       min_score: int, dry_run: bool, smtp_conn,
                       user: str | None, unsubscribe_token: str | None) -> bool:
    """Match, mail if anything is new, update state in place. Returns True if mailed."""
    results, stats = match.run(profile, jobs)
    sub_id = hashlib.sha1(email.encode()).hexdigest()[:12]
    sent = set(state.get(sub_id, {}).get("sent_keys", []))
    eligible = [r for r in results if r["score"] >= min_score]
    new = [r for r in eligible if job_key(r) not in sent]

    print(f"{email}: matched {stats['matched']} | eligible {len(eligible)} | "
          f"already mailed {len(eligible) - len(new)} | new {len(new)}")
    if not new:
        return False

    body = compose(new, stats["considered"], unsubscribe_token)
    subject = f"{len(new)} new internship match(es) · {date.today().isoformat()}"
    if dry_run:
        print(f"DRY RUN — would send to {email}: {subject}")
        return False

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = f"the engine <{user}>"
    msg["To"] = email
    smtp_conn.send_message(msg)
    print(f"sent to {email}: {subject}")

    # The mail is out. Persist BEFORE touching the next subscriber: if the run
    # dies on subscriber n+1, what n already received must never be re-sent.
    # Existing sent_keys are unioned, never reset -- a profile edit rescores,
    # it does not un-send.
    state.setdefault(sub_id, {})["sent_keys"] = sorted(sent | {job_key(r) for r in new})
    state[sub_id]["last_sent"] = date.today().isoformat()
    save_state(state)
    print(f"state written: {STATE_FILE}")
    return True


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--min-score", type=int, default=5,
                    help="mail only matches at or above this score")
    args = ap.parse_args()

    user = os.environ.get("SMTP_USER")
    password = os.environ.get("SMTP_PASS")
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

    if not args.dry_run and not (user and password):
        print("missing SMTP_USER / SMTP_PASS", file=sys.stderr)
        sys.exit(1)

    jobs = json.loads((DATA / "jobs.json").read_text())
    state = load_state()

    mailed = 0
    smtp_conn = None
    try:
        if not args.dry_run:
            smtp_conn = smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30)
            smtp_conn.login(user, password)
        for email, profile, token in targets:
            if process_subscriber(email, profile, jobs, state, args.min_score,
                                  args.dry_run, smtp_conn, user, token):
                mailed += 1
    finally:
        if smtp_conn:
            smtp_conn.quit()

    # No bulk write here on purpose: process_subscriber already flushed state to
    # disk after every successful send. A write at this point could only ever be
    # reached when nothing crashed, which is exactly the case that needed no
    # protection.
    print(f"done: {mailed} mail(s) sent, {len(targets) - mailed} had nothing new.")


if __name__ == "__main__":
    main()
