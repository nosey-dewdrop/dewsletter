#!/usr/bin/env python3
"""Daily match mail. Deterministic, idempotent, no LLM.

Contract (printed on the site): a mail is sent ONLY when new listings match the
subscriber's profile. Nothing new -> no mail. Already-mailed listings are never
repeated; state lives in data/mail_state.json and is committed by the daily
workflow, so re-runs cannot double-send.

Env:
  SMTP_USER         gmail address that sends
  SMTP_PASS         gmail app password
  SUBSCRIBER_EMAIL  recipient (single-subscriber mode until the backend ships)

Usage: python3 send_mail.py [--dry-run] [--min-score N]
"""
import argparse
import hashlib
import json
import os
import smtplib
import sys
from datetime import date
from email.mime.text import MIMEText
from pathlib import Path

import match

DATA = Path(__file__).parent / "data"
STATE_FILE = DATA / "mail_state.json"
SITE = "https://nosey-dewdrop.github.io/sightstone"


def job_key(r: dict) -> str:
    raw = r.get("link") or f'{r["company"]}|{r["position"]}'
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {}


def compose(new: list[dict], total: int) -> str:
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
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--min-score", type=int, default=5,
                    help="mail only matches at or above this score")
    args = ap.parse_args()

    user = os.environ.get("SMTP_USER")
    password = os.environ.get("SMTP_PASS")
    to_addr = os.environ.get("SUBSCRIBER_EMAIL")
    if not args.dry_run and not (user and password and to_addr):
        print("missing SMTP_USER / SMTP_PASS / SUBSCRIBER_EMAIL", file=sys.stderr)
        sys.exit(1)

    profile = json.loads((Path(__file__).parent.parent / "profile.json").read_text())
    jobs = json.loads((DATA / "jobs.json").read_text())
    results, stats = match.run(profile, jobs)

    sub_id = hashlib.sha1((to_addr or "dry").encode()).hexdigest()[:12]
    state = load_state()
    sent = set(state.get(sub_id, {}).get("sent_keys", []))

    eligible = [r for r in results if r["score"] >= args.min_score]
    new = [r for r in eligible if job_key(r) not in sent]

    print(f"matched {stats['matched']} | eligible (score>={args.min_score}) "
          f"{len(eligible)} | already mailed {len(eligible) - len(new)} | new {len(new)}")

    if not new:
        print("nothing new, no mail.")
        return

    body = compose(new, stats["considered"])
    subject = f"{len(new)} new internship match(es) · {date.today().isoformat()}"

    if args.dry_run:
        print(f"\nDRY RUN — would send to {to_addr or '(unset)'}:\nsubject: {subject}\n\n{body}")
        return

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = f"the engine <{user}>"
    msg["To"] = to_addr
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as s:
        s.login(user, password)
        s.send_message(msg)
    print(f"sent to {to_addr}: {subject}")

    state.setdefault(sub_id, {})["sent_keys"] = sorted(sent | {job_key(r) for r in new})
    state[sub_id]["last_sent"] = date.today().isoformat()
    STATE_FILE.write_text(json.dumps(state, indent=1))
    print(f"state updated: {STATE_FILE}")


if __name__ == "__main__":
    main()
