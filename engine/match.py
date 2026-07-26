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
  - fresh listings (<=7 days) score up, stale ones (>90 days) score down

Usage: python3 match.py <profile.json> [--top N] [--json out.json] [--stats]
"""
import argparse
import json
import re
from pathlib import Path

PHD_RE = re.compile(r"\bphd\b", re.I)
MS_RE = re.compile(r"\b(ms|msc|master(?:'?s)?)\b", re.I)
MBA_RE = re.compile(r"\bmba\b", re.I)
US_AUTH_RE = re.compile(r"citizen|clearance|us persons|no sponsorship|security clearance", re.I)
AGE_RE = re.compile(r"^\s*(\d+)\s*(h|d|w|mo|y)\s*$", re.I)
AGE_DAYS = {"h": 0, "d": 1, "w": 7, "mo": 30, "y": 365}


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


def norm_title(title: str) -> str:
    return " " + re.sub(r"[^a-z0-9+#]+", " ", title.lower()).strip() + " "


def keywords_from_profile(profile: dict) -> tuple[list[str], list[str]]:
    """Returns (interest_keywords, skill_keywords), lowercased."""
    interests = set()
    target = profile.get("direction_and_motivation", {}).get("target_field", "")
    for token in re.split(r"[;,/]| and ", target):
        token = token.strip().lower()
        if 2 < len(token) < 40:
            interests.add(token)
    expansion = {
        "ai infra": ["ai infrastructure", "ml infra", "ml platform", "inference",
                     "training platform", "machine learning platform"],
        "devtools": ["developer tools", "developer platform", "sdk", "compiler", "tooling"],
        "llm systems": ["llm", "language model", "genai", "generative ai", "foundation model"],
        "agent platforms": ["agent", "agentic", "automation"],
        "on-device and cpu-efficient": ["on-device", "edge ai", "quantization", "efficient ml"],
    }
    for key, extra in expansion.items():
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
              level: str, us_work_auth: bool, country: str) -> tuple[int, list[str]] | str:
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

    if job.get("remote"):
        score += 3
        reasons.append("remote")
    if country and country in location:
        score += 3
        reasons.append(f"location fits ({job.get('location')})")
    if job.get("salary"):
        score += 1
        reasons.append(f"salary posted ({job['salary']})")

    days = parse_age_days(job.get("age"))
    if days is not None:
        if days <= 7:
            score += 2
            reasons.append(f"fresh ({job['age']})")
        elif days > 90:
            score -= 2
            reasons.append(f"stale ({job['age']})")

    return (score, reasons) if score > 0 else "no_signal"


def run(profile: dict, jobs: list[dict]) -> tuple[list[dict], dict]:
    jobs, removed = dedupe(jobs)
    interests, skills = keywords_from_profile(profile)
    edu_text = json.dumps(profile.get("education", "")).lower()
    level = "phd" if "phd student" in edu_text else "ms" if re.search(r"\bmsc? student\b", edu_text) else "bs"
    loc = profile.get("identity", {}).get("location", "").lower()
    country = "turkey" if "turkey" in loc or "türkiye" in loc or "ankara" in loc else ""
    us_work_auth = "united states" in loc or "usa" in loc

    results, excluded = [], {"phd_only": 0, "mba": 0, "us_work_auth": 0, "no_signal": 0}
    for job in jobs:
        scored = score_job(job, interests, skills, level, us_work_auth, country)
        if isinstance(scored, str):
            excluded[scored] += 1
            continue
        days = parse_age_days(job.get("age"))
        results.append({**job, "score": scored[0], "reasons": scored[1],
                        "age_days": days})
    results.sort(key=lambda r: (-r["score"], r["age_days"] if r["age_days"] is not None else 999,
                                r["company"].lower()))
    stats = {"total_raw": len(jobs) + removed, "duplicates_removed": removed,
             "considered": len(jobs), "matched": len(results), **excluded}
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
        print(f"excluded: phd_only {stats['phd_only']}, mba {stats['mba']}, "
              f"us_work_auth {stats['us_work_auth']}, no_signal {stats['no_signal']}, "
              f"duplicates {stats['duplicates_removed']}")
    for r in results[: args.top]:
        link = r["link"] or f"link not found, search: {r['company']} {r['position']}"
        print(f"\n[{r['score']:>2}] {r['company']} - {r['position']}")
        print(f"     {r.get('location') or '?'} | {link}")
        print(f"     reasons: {'; '.join(r['reasons'])}")
    if args.json:
        Path(args.json).write_text(json.dumps(results, ensure_ascii=False, indent=1))
        print(f"\nwritten: {args.json} ({len(results)} matches)")


if __name__ == "__main__":
    main()
