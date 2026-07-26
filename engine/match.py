#!/usr/bin/env python3
"""Deterministic job-profile matcher. No LLM anywhere.

Input:  data/jobs.json (from fetch_speedyapply.py) + a profile JSON.
Output: scored matches with human-readable reasons, best first.

Scoring is transparent: every point has a named reason. A hiring-area
keyword hit in the position title is worth more than a skill hit in
free text. PhD-only listings are excluded for non-PhD profiles.

Usage: python3 match.py <profile.json> [--top N] [--json out.json]
"""
import argparse
import json
import re
from pathlib import Path

# level markers in position titles
PHD_RE = re.compile(r"\bphd\b", re.I)
MS_RE = re.compile(r"\b(ms|msc|master)\b", re.I)
MBA_RE = re.compile(r"\bmba\b", re.I)


def keywords_from_profile(profile: dict) -> tuple[list[str], list[str]]:
    """Returns (interest_keywords, skill_keywords), lowercased."""
    interests = set()
    target = profile.get("direction_and_motivation", {}).get("target_field", "")
    for token in re.split(r"[;,/]| and ", target):
        token = token.strip().lower()
        if 2 < len(token) < 40:
            interests.add(token)
    # common expansions of her field vocabulary
    expansion = {
        "ai infra": ["ai infrastructure", "ml infra", "ml platform", "inference", "training platform"],
        "devtools": ["developer tools", "developer platform", "sdk", "compiler", "tooling"],
        "llm systems": ["llm", "language model", "genai", "generative ai", "foundation model"],
        "agent platforms": ["agent", "agentic", "automation"],
        "on-device and cpu-efficient": ["on-device", "edge ai", "quantization", "efficient ml"],
    }
    for key, extra in expansion.items():
        if any(key.split()[0] in i for i in interests):
            interests.update(extra)
    skills = set()
    sk = profile.get("skills", {})
    for v in sk.values():
        if isinstance(v, list):
            skills.update(s.split(" (")[0].strip().lower() for s in v if isinstance(s, str))
        elif isinstance(v, str):
            skills.add(v.strip().lower())
    return sorted(interests), sorted(k for k in skills if 1 < len(k) < 30)


def score_job(job: dict, interests: list[str], skills: list[str],
              level: str, remote_ok: bool, country: str) -> tuple[int, list[str]] | None:
    title = job["position"].lower()
    location = (job.get("location") or "").lower()
    score, reasons = 0, []

    if level != "phd" and PHD_RE.search(job["position"]) and not MS_RE.search(job["position"]):
        return None  # PhD-only listing
    if MBA_RE.search(job["position"]):
        return None  # MBA program listing

    for kw in interests:
        if kw and kw in title:
            score += 4
            reasons.append(f"ilgi alanı '{kw}' pozisyon adında")
    for kw in skills:
        if kw and re.search(rf"(?<![a-z]){re.escape(kw)}(?![a-z])", title):
            score += 2
            reasons.append(f"beceri '{kw}' pozisyon adında")
    if job.get("remote"):
        score += 3
        reasons.append("remote pozisyon")
    if country and country in location:
        score += 3
        reasons.append(f"konum uygun ({job.get('location')})")
    if job.get("salary"):
        score += 1
        reasons.append(f"maaş açık ({job['salary']})")
    return (score, reasons) if score > 0 else None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("profile")
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument("--json", help="also write full results to this path")
    args = ap.parse_args()

    profile = json.loads(Path(args.profile).read_text())
    jobs = json.loads((Path(__file__).parent / "data" / "jobs.json").read_text())
    interests, skills = keywords_from_profile(profile)
    level = "bs"
    country = "turkey" if "turkey" in profile.get("identity", {}).get("location", "").lower() else ""

    results = []
    for job in jobs:
        scored = score_job(job, interests, skills, level, True, country)
        if scored:
            results.append({**job, "score": scored[0], "reasons": scored[1]})
    results.sort(key=lambda r: -r["score"])

    print(f"profil: {profile.get('identity', {}).get('name')} | ilan: {len(jobs)} | eşleşme: {len(results)}")
    for r in results[: args.top]:
        link = r["link"] or f"link bulunamadı, kendin ara: {r['company']} {r['position']}"
        print(f"\n[{r['score']:>2}] {r['company']} — {r['position']}")
        print(f"     {r.get('location') or '?'} | {link}")
        print(f"     neden: {'; '.join(r['reasons'])}")
    if args.json:
        Path(args.json).write_text(json.dumps(results, ensure_ascii=False, indent=1))
        print(f"\nyazıldı: {args.json} ({len(results)} eşleşme)")


if __name__ == "__main__":
    main()
