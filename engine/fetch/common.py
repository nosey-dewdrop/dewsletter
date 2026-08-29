#!/usr/bin/env python3
"""Shared schema and pure helpers for every listing source.

Every source module produces records in ONE schema (`record()` below), so the
orchestrator can dedupe across sources and keep jobs.json byte-identical to the
single-file fetcher it replaces.

Nothing in this module touches the network or the clock: `now` is always passed
in. That is what makes the tests hermetic and the replay byte-exact.
"""
import re

LINK_RE = re.compile(r'<a href="([^"]+)"')
TAG_RE = re.compile(r"<[^>]+>")

# field order is part of the on-disk contract: jobs.json bytes depend on it
FIELDS = [
    "source", "company", "company_url", "position", "location", "remote",
    "salary", "link", "link_missing", "age", "student_ok", "deadline",
    "fetched_at",
]


def split_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def record(source: str, row: dict, fetched_at: str) -> dict:
    """One markdown table row -> the shared listing schema."""
    company_link = LINK_RE.search(row.get("company", ""))
    posting_link = LINK_RE.search(row.get("posting", ""))
    link = posting_link.group(1) if posting_link else None
    location = TAG_RE.sub("", row.get("location", "")).strip()
    return {
        "source": source,
        "company": TAG_RE.sub("", row.get("company", "")).strip(),
        "company_url": company_link.group(1) if company_link else None,
        "position": TAG_RE.sub("", row.get("position", "")).strip(),
        "location": location,
        "remote": "remote" in location.lower(),
        "salary": TAG_RE.sub("", row.get("salary", "")).strip() or None,
        "link": link,
        "link_missing": link is None,
        "age": TAG_RE.sub("", row.get("age", "")).strip() or None,
        "student_ok": True,
        "deadline": None,
        "fetched_at": fetched_at,
    }


def parse_markdown_table(markdown: str, source: str, fetched_at: str) -> list[dict]:
    """Header-driven parse: each table declares its own columns."""
    jobs = []
    columns: list[str] = []
    for line in markdown.splitlines():
        if not line.startswith("|"):
            continue
        cells = split_row(line)
        if cells and cells[0].lower() == "company":
            columns = [c.lower() for c in cells]
            continue
        if not columns or line.startswith("|---") or set(line) <= {"|", "-", " "}:
            continue
        if len(cells) != len(columns):
            continue
        jobs.append(record(source, dict(zip(columns, cells)), fetched_at))
    return jobs


def job_key(job: dict) -> str:
    """Identity of a listing across days and across sources."""
    return f'{job["company"].strip().lower()}|{job["position"].strip().lower()}'


def dedupe(jobs: list[dict]) -> tuple[list[dict], int]:
    """Same company + position twice = same job re-posted; keep first (newest).

    Runs across sources, in source order, so the first source to carry a listing
    owns it.
    """
    seen, out = set(), []
    for job in jobs:
        key = job_key(job)
        if key in seen:
            continue
        seen.add(key)
        out.append(job)
    return out, len(jobs) - len(out)
