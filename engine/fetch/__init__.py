#!/usr/bin/env python3
"""Listing fetch pipeline: sources -> ledger -> jobs.json.

One file per source (`speedyapply_usa`, `speedyapply_intl`), one shared schema
(`common.record`), one dedupe across sources.

Two things this package adds over the single-file fetcher it replaces:

1. A LEDGER (`data/jobs_seen.json`). Key is (company.lower, position.lower);
   value is {first_seen, last_seen, alive}. A key that today's fetch does not
   carry becomes alive=false and KEEPS its last_seen — that is how a listing's
   life span becomes measurable at all.

2. A STRUCTURAL death gate. jobs.json carries only alive=true records, so a dead
   listing never enters the data at all. build_site / send_mail / match need no
   change and cannot print a dead listing, because they never see one.

An empty fetch is a failure, not a quiet success: if the total is zero, or ANY
single source returns zero rows, nothing is written and the caller gets a
non-zero exit. A source silently changing its format used to leave the product
green and empty; now it goes red.

Nothing here reads the clock or the network on its own — `now` and the source
texts are passed in. That keeps the tests hermetic and the replay byte-exact.
"""
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from . import common, speedyapply_intl, speedyapply_usa
from .common import dedupe, job_key  # noqa: F401  (re-exported)

# order matters: it decides which source owns a listing carried by both
SOURCES = [speedyapply_usa, speedyapply_intl]

DATA = Path(__file__).parent.parent / "data"


class EmptyFetch(RuntimeError):
    """A source (or the whole fetch) returned zero rows. Never write on this."""


def fetch_texts(timeout: int = 30) -> dict[str, str]:
    out = {}
    for src in SOURCES:
        with urllib.request.urlopen(src.URL, timeout=timeout) as resp:
            out[src.NAME] = resp.read().decode("utf-8")
    return out


def parse_all(texts: dict[str, str], fetched_at: str) -> list[tuple[str, list[dict]]]:
    return [(src.NAME, src.parse(texts[src.NAME], fetched_at)) for src in SOURCES]


def check_not_empty(per_source: list[tuple[str, list[dict]]]) -> None:
    """Raise before any write happens. Partial writes are not a thing here."""
    for name, rows in per_source:
        if not rows:
            raise EmptyFetch(f"source returned 0 listings: {name}")
    if not sum(len(rows) for _, rows in per_source):
        raise EmptyFetch("fetch returned 0 listings in total")


def load_ledger(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text())
    return {}


def update_ledger(ledger: dict, jobs: list[dict], today: str) -> dict:
    """Mark today's listings alive, everything else dead. last_seen is preserved.

    Returns a NEW dict; the input is not mutated.
    """
    out = {}
    for key, entry in ledger.items():
        if not isinstance(entry, dict) or "first_seen" not in entry:
            continue  # unrecognised row: drop it, today's fetch relearns the listing
        out[key] = dict(entry)
    today_keys = set()
    for job in jobs:
        key = job_key(job)
        today_keys.add(key)
        entry = out.get(key)
        if entry is None:
            out[key] = {"first_seen": today, "last_seen": today, "alive": True}
        else:
            entry["last_seen"] = today
            entry["alive"] = True
    for key, entry in out.items():
        if key not in today_keys:
            entry["alive"] = False  # last_seen deliberately untouched
    return out


def build_jobs(jobs: list[dict], ledger: dict) -> list[dict]:
    """THE DEATH GATE. Today's order, today's bytes, alive records only."""
    return [j for j in jobs if ledger.get(job_key(j), {}).get("alive")]


def dumps_jobs(jobs: list[dict]) -> str:
    return json.dumps(jobs, ensure_ascii=False, indent=1)


def dumps_ledger(ledger: dict) -> str:
    return json.dumps(ledger, ensure_ascii=False, indent=1, sort_keys=True)


def run(texts: dict[str, str], out_dir: Path, now: datetime,
        verbose: bool = True) -> dict:
    """Full pipeline over already-fetched text. Writes only if every source spoke."""
    fetched_at = now.isoformat(timespec="seconds")
    today = now.date().isoformat()

    per_source = parse_all(texts, fetched_at)
    if verbose:
        for name, rows in per_source:
            print(f"{name}: {len(rows)} listings")
    check_not_empty(per_source)

    flat = [job for _, rows in per_source for job in rows]
    deduped, removed = common.dedupe(flat)
    if verbose:
        print(f"duplicates removed: {removed}")

    ledger_file = out_dir / "jobs_seen.json"
    ledger = update_ledger(load_ledger(ledger_file), deduped, today)
    live = build_jobs(deduped, ledger)
    dead = sum(1 for e in ledger.values() if not e["alive"])

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "fetch_meta.json").write_text(json.dumps({
        "fetched_at": fetched_at,
        "raw_rows": len(deduped) + removed,
        "duplicates_removed": removed,
    }))
    (out_dir / "jobs.json").write_text(dumps_jobs(live), encoding="utf-8")
    ledger_file.write_text(dumps_ledger(ledger), encoding="utf-8")

    if verbose:
        missing = sum(1 for j in live if j["link_missing"])
        remote = sum(1 for j in live if j["remote"])
        print(f"total: {len(live)} live listings -> {out_dir / 'jobs.json'}")
        print(f"remote: {remote}, link_missing: {missing}")
        # scope breakdown, unknown included even at zero: a scope that stops
        # being printed is a scope that stops being checked
        census = common.scope_census(live)
        print("remote scope: " + ", ".join(
            f"{name}={n}" for name, n in sorted(census.items())))
        print(f"ledger: {len(ledger)} known listings, {dead} no longer open")
    return {"live": len(live), "dead": dead, "duplicates_removed": removed}


def main() -> int:
    now = datetime.now(timezone.utc)
    try:
        texts = fetch_texts()
        run(texts, DATA, now)
    except EmptyFetch as exc:
        print(f"fetch failed, nothing written: {exc}")
        return 2
    return 0
