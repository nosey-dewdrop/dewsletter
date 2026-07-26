#!/usr/bin/env python3
"""Fetch AI/ML student internship listings from speedyapply GitHub repo.

Source tables are markdown with HTML anchors, updated daily.
Output: data/jobs.json — one record per listing, schema below.
Link can be missing: record enters with link=None, link_missing=True.
"""
import json
import re
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

BASE = "https://raw.githubusercontent.com/speedyapply/2027-AI-College-Jobs/main"
SOURCES = [
    ("speedyapply-intern-usa", f"{BASE}/README.md"),
    ("speedyapply-intern-intl", f"{BASE}/INTERN_INTL.md"),
]

LINK_RE = re.compile(r'<a href="([^"]+)"')
TAG_RE = re.compile(r"<[^>]+>")


def split_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def parse_table_rows(markdown: str, source: str) -> list[dict]:
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
        row = dict(zip(columns, cells))
        company_link = LINK_RE.search(row.get("company", ""))
        posting_link = LINK_RE.search(row.get("posting", ""))
        link = posting_link.group(1) if posting_link else None
        location = TAG_RE.sub("", row.get("location", "")).strip()
        jobs.append({
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
            "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        })
    return jobs


def main() -> None:
    all_jobs = []
    for source, url in SOURCES:
        with urllib.request.urlopen(url, timeout=30) as resp:
            markdown = resp.read().decode("utf-8")
        rows = parse_table_rows(markdown, source)
        print(f"{source}: {len(rows)} listings")
        all_jobs.append((source, rows))

    out_dir = Path(__file__).parent / "data"
    out_dir.mkdir(exist_ok=True)
    flat = [job for _, rows in all_jobs for job in rows]
    # same company + position twice = same job re-posted; keep first (newest)
    seen, deduped = set(), []
    for job in flat:
        key = (job["company"].lower(), job["position"].lower())
        if key in seen:
            continue
        seen.add(key)
        deduped.append(job)
    removed = len(flat) - len(deduped)
    print(f"duplicates removed: {removed}")
    flat = deduped
    (out_dir / "fetch_meta.json").write_text(json.dumps({
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "raw_rows": len(flat) + removed,
        "duplicates_removed": removed,
    }))
    out_file = out_dir / "jobs.json"
    out_file.write_text(json.dumps(flat, ensure_ascii=False, indent=1))
    missing = sum(1 for j in flat if j["link_missing"])
    remote = sum(1 for j in flat if j["remote"])
    print(f"total: {len(flat)} listings -> {out_file}")
    print(f"remote: {remote}, link_missing: {missing}")


if __name__ == "__main__":
    main()
