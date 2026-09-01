#!/usr/bin/env python3
"""Deterministic job-profile matcher. No LLM anywhere.

Input:  data/jobs.json (from fetch_speedyapply.py) + a profile JSON.
Output: scored matches with named reasons, best first.

Scoring is transparent: every point has a named reason string. Reasons are
English because they ship on the public site and in mails.

v2 accuracy rules:
  - duplicate listings (same company + position) are collapsed, newest kept
  - PhD-only listings excluded for non-PhD profiles; MBA listings excluded
  - listings requiring US citizenship / clearance / no-sponsorship are excluded
    for profiles without US work authorization
  - MS-flavored titles get a penalty for BS profiles, not an exclusion
  - ONLY interest / skill / role fit scores. Geography, freshness and salary
    score nothing: they are filters and ordering, never a reason to be mailed.
    A listing whose only distinction is "remote" scores 0 and is not a match.

Usage: python3 match.py <profile.json> [--top N] [--json out.json] [--stats]
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from fetch.common import listing_country, remote_scope  # noqa: E402

PHD_RE = re.compile(r"\bphd\b", re.I)
MS_RE = re.compile(r"\b(ms|msc|master(?:'?s)?)\b", re.I)
MBA_RE = re.compile(r"\bmba\b", re.I)
US_AUTH_RE = re.compile(r"citizen|clearance|us persons|no sponsorship|security clearance", re.I)
AGE_RE = re.compile(r"^\s*(\d+)\s*(h|d|w|mo|y)\s*$", re.I)
AGE_DAYS = {"h": 0, "d": 1, "w": 7, "mo": 30, "y": 365}

# ------------------------------------------------------------------ geo reach
#
# `us_work_auth` reads the TITLE for the words "citizen"/"clearance". Real
# listings almost never spell that out, so on the shipped corpus it fires zero
# times: a rule that excludes nothing. Meanwhile 133 of the 142 things sent to a
# profile that cannot relocate were jobs it could not take -- onsite abroad, or
# remote fenced to one foreign country.
#
# The geo rule below is the one that actually reaches. It runs on DECLARED
# constraints only (`relocation: false` + `home_country`), never on a guess
# scraped out of the identity string, and it refuses to run half-declared:
# `relocation: false` without a `home_country` is a SystemExit, not a silent
# pass. `us_work_auth` stays exactly where it was; this is a second rule beside
# it, not a replacement for it.
GEO_BUCKETS = [
    "onsite_abroad",
    "remote_scope_country_mismatch",
    "remote_scope_unknown",
    "location_country_unknown",
]


def home_country(profile: dict) -> str | None:
    """The country a profile is stuck in, or None if it is not stuck.

    Only a profile that DECLARES `relocation: false` has a home country that
    excludes anything. Anything else -> None, and the geo rule stays off.
    """
    constraints = profile.get("constraints", {}) or {}
    if constraints.get("relocation") is not False:
        return None
    home = constraints.get("home_country")
    if not isinstance(home, str) or not home.strip():
        raise SystemExit(
            "profile error: constraints.relocation is false but "
            "constraints.home_country is missing. A profile that cannot "
            "relocate must say where it is; refusing to guess."
        )
    return home.strip().upper()


def geo_exclusion(job: dict, home: str) -> str | None:
    """Why `home` cannot take this job, or None if it can. Named, never silent."""
    scope = remote_scope(job)
    if scope == "global":
        return None
    if scope == "unknown":
        return "remote_scope_unknown"
    if scope is not None:
        return None if scope == f"country:{home}" else "remote_scope_country_mismatch"
    country = listing_country(job.get("location"))
    if country == "unknown":
        return "location_country_unknown"
    return None if country == home else "onsite_abroad"


def parse_age_days(age: str | None) -> int | None:
    if not age:
        return None
    m = AGE_RE.match(age)
    if not m:
        return None
    n, unit = int(m.group(1)), m.group(2).lower()
    return n * AGE_DAYS[unit] if unit != "h" else 0


def dedupe(jobs: list[dict]) -> tuple[list[dict], int]:
    """Same company + position = same job posted twice; keep first (newest)."""
    seen, out = set(), []
    for j in jobs:
        key = (j["company"].strip().lower(), j["position"].strip().lower())
        if key in seen:
            continue
        seen.add(key)
        out.append(j)
    return out, len(jobs) - len(out)


# Lifted out of keywords_from_profile so the signup form can ship the SAME
# table to the browser instead of a JavaScript retyping of it. "ai infra" is
# not one keyword, it is six, and a live preview that did not know that would
# under-count every profile that uses the placeholder's own wording.
INTEREST_EXPANSION = {
    "ai infra": ["ai infrastructure", "ml infra", "ml platform", "inference",
                 "training platform", "machine learning platform"],
    "devtools": ["developer tools", "developer platform", "sdk", "compiler", "tooling"],
    "llm systems": ["llm", "language model", "genai", "generative ai", "foundation model"],
    "agent platforms": ["agent", "agentic", "automation"],
    "on-device and cpu-efficient": ["on-device", "edge ai", "quantization", "efficient ml"],
}

# The split the browser must reproduce exactly, kept next to the table it feeds.
INTEREST_SPLIT = r"[;,/]| and "
INTEREST_MIN, INTEREST_MAX = 2, 40


def norm_title(title: str) -> str:
    return " " + re.sub(r"[^a-z0-9+#]+", " ", title.lower()).strip() + " "


def keywords_from_profile(profile: dict) -> tuple[list[str], list[str]]:
    """Returns (interest_keywords, skill_keywords), lowercased."""
    interests = set()
    target = profile.get("direction_and_motivation", {}).get("target_field", "")
    for token in re.split(INTEREST_SPLIT, target):
        token = token.strip().lower()
        if INTEREST_MIN < len(token) < INTEREST_MAX:
            interests.add(token)
    for key, extra in INTEREST_EXPANSION.items():
        if any(key.split()[0] in i for i in interests):
            interests.update(extra)
    skills = set()
    for v in profile.get("skills", {}).values():
        if isinstance(v, list):
            skills.update(s.split(" (")[0].strip().lower() for s in v if isinstance(s, str))
        elif isinstance(v, str):
            skills.add(v.strip().lower())
    return sorted(interests), sorted(k for k in skills if 1 < len(k) < 30)


def score_job(job: dict, interests: list[str], skills: list[str],
              level: str, us_work_auth: bool, home: str | None) -> tuple[int, list[str]] | str:
    """Returns (score, reasons) or an exclusion-reason string."""
    title = job["position"]
    ntitle = norm_title(title)
    location = (job.get("location") or "").lower()
    score, reasons = 0, []

    if level != "phd" and PHD_RE.search(title) and not MS_RE.search(title):
        return "phd_only"
    if MBA_RE.search(title):
        return "mba"
    if not us_work_auth and (US_AUTH_RE.search(title) or US_AUTH_RE.search(location)):
        return "us_work_auth"
    if home:
        blocked = geo_exclusion(job, home)
        if blocked:
            return blocked

    hits = 0
    for kw in interests:
        if kw and f" {kw} " in ntitle:
            hits += 1
            reasons.append(f"interest '{kw}' in title")
    score += min(12, hits * 4)

    hits = 0
    for kw in skills:
        if kw and f" {kw} " in ntitle:
            hits += 1
            reasons.append(f"skill '{kw}' in title")
    score += min(6, hits * 2)

    if level == "bs" and MS_RE.search(title):
        score -= 3
        reasons.append("listing prefers MS")

    # Geography, freshness and salary deliberately score NOTHING.
    #
    # They used to: remote +3, location-fits +3, salary +1, fresh +2, stale -2.
    # That let a listing reach the mail on geography alone, and the reason line
    # then read "remote" -- which is not a reason, it is the filter that failed
    # to eliminate it. Measured on the 599-listing corpus: 2 of 3 matches were
    # in on "remote" and nothing else.
    #
    # Geography stays a FILTER: geo_exclusion above still eliminates, and its
    # buckets are untouched. What it may not do is manufacture a score.
    # Freshness still orders the results (see the sort in run()); it just does
    # not decide who gets in.
    return (score, reasons) if score > 0 else "no_signal"


def run(profile: dict, jobs: list[dict]) -> tuple[list[dict], dict]:
    jobs, removed = dedupe(jobs)
    interests, skills = keywords_from_profile(profile)
    edu_text = json.dumps(profile.get("education", "")).lower()
    level = "phd" if "phd student" in edu_text else "ms" if re.search(r"\bmsc? student\b", edu_text) else "bs"
    loc = profile.get("identity", {}).get("location", "").lower()
    us_work_auth = "united states" in loc or "usa" in loc
    home = home_country(profile)

    excluded = {"phd_only": 0, "mba": 0, "us_work_auth": 0}
    excluded.update({b: 0 for b in GEO_BUCKETS})
    excluded["no_signal"] = 0
    results = []
    for job in jobs:
        scored = score_job(job, interests, skills, level, us_work_auth, home)
        if isinstance(scored, str):
            excluded[scored] += 1
            continue
        days = parse_age_days(job.get("age"))
        results.append({**job, "score": scored[0], "reasons": scored[1],
                        "age_days": days})
    results.sort(key=lambda r: (-r["score"], r["age_days"] if r["age_days"] is not None else 999,
                                r["company"].lower()))
    stats = {"total_raw": len(jobs) + removed, "duplicates_removed": removed,
             "considered": len(jobs), "matched": len(results),
             "geo_rule": "on" if home else "off", "home_country": home,
             **excluded}
    return results, stats


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("profile")
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument("--json", help="also write full results to this path")
    ap.add_argument("--stats", action="store_true")
    args = ap.parse_args()

    profile = json.loads(Path(args.profile).read_text())
    jobs = json.loads((Path(__file__).parent / "data" / "jobs.json").read_text())
    results, stats = run(profile, jobs)

    print(f"profile: {profile.get('identity', {}).get('name')} | "
          f"raw {stats['total_raw']} | deduped {stats['considered']} | matched {stats['matched']}")
    if args.stats:
        buckets = ["phd_only", "mba", "us_work_auth", *GEO_BUCKETS, "no_signal"]
        # every bucket is printed, zeros included: a rule that fires zero times
        # is the finding, and a report that hides it is how `us_work_auth` sat
        # dead for weeks.
        print("excluded: " + ", ".join(f"{b} {stats[b]}" for b in buckets)
              + f", duplicates {stats['duplicates_removed']}")
        if stats["geo_rule"] == "on":
            print(f"geo rule: on, home {stats['home_country']}")
        else:
            print("geo rule: off, profile declares no relocation constraint")
        print(f"matched: {stats['matched']}")
        if stats["matched"] == 0:
            top = max(buckets, key=lambda b: stats[b])
            print(f"dead end: nothing matched; largest exclusion is "
                  f"{top} ({stats[top]})")
    for r in results[: args.top]:
        link = r["link"] or f"link not found, search: {r['company']} {r['position']}"
        print(f"\n[{r['score']:>2}] {r['company']} - {r['position']}")
        print(f"     {r.get('location') or '?'} | {link}")
        print(f"     reasons: {'; '.join(r['reasons'])}")
    if args.json:
        Path(args.json).write_text(json.dumps(results, ensure_ascii=False, indent=1))
        print(f"\nwritten: {args.json} ({len(results)} matches)")
    if not results:
        # A run that reached nobody is not a success. Exiting 0 here is how a
        # cron job keeps mailing an empty list every morning and nobody notices.
        raise SystemExit(1)


if __name__ == "__main__":
    main()
