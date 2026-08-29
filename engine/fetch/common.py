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


# ---------------------------------------------------------------- remote scope
#
# `remote` is a boolean, and a boolean cannot tell "apply from anywhere on
# earth" apart from "live in the US, just skip the office". Both are true. The
# difference was always written in the location string -- `Remote` vs
# `Remote - USA` -- and nothing read it.
#
# `remote_scope` reads it. It is DERIVED, never stored: FIELDS and record() are
# untouched, jobs.json keeps the same 13 fields and the same bytes.
#
# The rule is the COUNTRY CODE, not a list of places seen before. A city list
# would answer only for cities already met and lie by omission about the rest,
# so no city is a key here. Two tables, in this order:
#   (a) the last comma-part is a country name  -> that country's code
#   (b) else it is a 2-letter US state/DC code -> US
#   (c) neither                                -> "unknown", never a guess.
#
# `unknown` is the whole point of (c). Nearest-match and a silent "global"
# default are both banned: "Remote - Anywhere" READS like global, and reading
# like it is not knowing it.

# ISO 3166-1 alpha-2 for every country name measured in the corpus' locations.
COUNTRY_CODES = {
    "argentina": "AR",
    "australia": "AU",
    "austria": "AT",
    "belarus": "BY",
    "belgium": "BE",
    "botswana": "BW",
    "brazil": "BR",
    "canada": "CA",
    "chile": "CL",
    "china": "CN",
    "colombia": "CO",
    "finland": "FI",
    "france": "FR",
    "germany": "DE",
    "greece": "GR",
    "honduras": "HN",
    "hong kong": "HK",
    "hungary": "HU",
    "india": "IN",
    "indonesia": "ID",
    "ireland": "IE",
    "israel": "IL",
    "italy": "IT",
    "malaysia": "MY",
    "mexico": "MX",
    "new zealand": "NZ",
    "philippines": "PH",
    "poland": "PL",
    "portugal": "PT",
    "romania": "RO",
    "saudi arabia": "SA",
    "serbia": "RS",
    "singapore": "SG",
    "slovakia": "SK",
    "south korea": "KR",
    "spain": "ES",
    "sweden": "SE",
    "switzerland": "CH",
    "taiwan": "TW",
    "the netherlands": "NL",
    "tunisia": "TN",
    "usa": "US",
    "united arab emirates": "AE",
    "united kingdom": "GB",
    "uruguay": "UY",
    "uzbekistan": "UZ",
    "vietnam": "VN",
}

# 50 states + DC. The corpus only ever showed 27 of them; a table that stopped
# at what the corpus happened to contain would be a hardcode, not a rule.
US_STATE_CODES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut",
    "DE": "Delaware", "FL": "Florida", "GA": "Georgia", "HI": "Hawaii",
    "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa",
    "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine",
    "MD": "Maryland", "MA": "Massachusetts", "MI": "Michigan",
    "MN": "Minnesota", "MS": "Mississippi", "MO": "Missouri", "MT": "Montana",
    "NE": "Nebraska", "NV": "Nevada", "NH": "New Hampshire",
    "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio",
    "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania",
    "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota",
    "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont",
    "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
    "WI": "Wisconsin", "WY": "Wyoming", "DC": "District of Columbia",
}

# "+3" means "and 3 more locations". It names no place, so it decides nothing.
PLUS_N_RE = re.compile(r"\s*\+\d+\s*$")
# "Remote - <somewhere>". The dash may be hyphen, en dash or em dash.
REMOTE_PREFIX_RE = re.compile(r"^remote\s*[-–—]\s*(.*)$", re.I)


def remote_scope(job: dict) -> str | None:
    """How far a remote listing actually reaches. Pure: no network, no clock.

    None -> not a remote listing at all (NOT "global", NOT "").
    "global" -> plain "Remote": no place is named, so no place is excluded.
    "country:XX" -> remote within one country, XX being ISO 3166-1 alpha-2.
    "unknown" -> remote, but the scope could not be READ. Never guessed.
    """
    if not job.get("remote"):
        return None
    text = PLUS_N_RE.sub("", (job.get("location") or "").strip())
    if text.strip().lower() == "remote":
        return "global"
    match = REMOTE_PREFIX_RE.match(text.strip())
    if not match:
        return "unknown"
    parts = [p.strip() for p in match.group(1).split(",") if p.strip()]
    if not parts:
        return "unknown"
    last = parts[-1]
    code = COUNTRY_CODES.get(last.lower())
    if code:
        return f"country:{code}"
    if last.upper() in US_STATE_CODES:
        return "country:US"
    return "unknown"


def scope_census(jobs: list[dict]) -> dict:
    """Scope breakdown of the remote listings. Non-remote records are not counted.

    "global" and "unknown" are always present, at zero if need be: an unknown
    that disappears from the report is exactly the silent default this replaces.
    """
    census = {"global": 0, "unknown": 0}
    for job in jobs:
        scope = remote_scope(job)
        if scope is None:
            continue
        census[scope] = census.get(scope, 0) + 1
    return census


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
