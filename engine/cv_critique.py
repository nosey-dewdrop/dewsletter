#!/usr/bin/env python3
"""Deterministic CV critique against the live internship market. No LLM.

Every sentence in the verdict is backed by a measured number: either a count
from the CV text itself or a demand count over the live jobs.json titles.
Tone is theyseeyourphotos-sharp, but unlike theyseeyourphotos it must always
say WHY and WHAT TO DO, with evidence.

Usage:
  python3 cv_critique.py <cv.txt|cv.md> [--found-job | --no-job] [--json out.json]

Input is plain text (the site backend extracts PDF text before calling this).
Output: human-readable report on stdout, optional findings JSON.
"""
import argparse
import json
import re
from pathlib import Path

JOBS = Path(__file__).parent / "data" / "jobs.json"

# ---------------------------------------------------------------- market model
# curated tech vocabulary: term -> regex that finds it in titles AND in CVs.
# every demand claim in the verdict comes from counting these over live titles.
TERMS = {
    "machine learning": r"\bmachine learning\b|\bml\b",
    "ai": r"\bai\b|artificial intelligence",
    "generative ai": r"generative ai|\bgenai\b|\bgen ai\b",
    "agentic ai": r"\bagentic\b|\bagents?\b",
    "llm": r"\bllms?\b|large language model",
    "research": r"\bresearch\b",
    "data science": r"\bdata scien",
    "data engineering": r"\bdata engineer",
    "computer vision": r"computer vision|\bcv engineer\b",
    "nlp": r"\bnlp\b|natural language",
    "robotics": r"\brobotic",
    "software engineering": r"software engineer|\bswe\b|software develop",
    "infrastructure": r"\binfra(structure)?\b|\bplatform\b",
    "cloud": r"\bcloud\b|\baws\b|\bazure\b|\bgcp\b",
    "security": r"\bsecurity\b|\bcyber",
    "product": r"\bproduct\b",
    "automation": r"\bautomation\b",
    "deep learning": r"deep learning|neural network",
}

# CV-side evidence detection is MORPHOLOGY-LOOSE on purpose: "automated" proves
# automation, "pytorch" proves deep learning. Title-side demand stays strict.
CV_EVIDENCE = {
    "machine learning": r"machine learning|\bml\b|scikit|model train|trained a",
    "ai": r"\bai\b|artificial intelligence|\bagent|\bllm|generative|pytorch|tensorflow",
    "generative ai": r"generative|\bgenai\b|diffusion|\bgpt\b|\bllm",
    "agentic ai": r"\bagent(ic|s)?\b",
    "llm": r"\bllms?\b|large language model|prompt|\beval harness\b",
    "research": r"\bresearch\b|\bpaper|reproduc|publish|\bf1\b|\blab\b",
    "data science": r"data scien|dataset|kaggle|notebook|\bpandas\b",
    "data engineering": r"data engineer|data pipeline|\betl\b|\bairflow\b|\bspark\b",
    "computer vision": r"computer vision|opencv|image (classification|detection|segmentation)|\bfps\b|vision model",
    "nlp": r"\bnlp\b|natural language|text (classification|generation)",
    "robotics": r"\brobot",
    "software engineering": r"software (engineer|develop)|shipped|deployed|\bapp\b|\bapi\b",
    "infrastructure": r"\binfra|deploy|pipeline|benchmark|\bplatform\b|kubernetes|docker",
    "cloud": r"\baws\b|\bazure\b|\bgcp\b|\bcloud\b",
    "security": r"\bsecurity\b|\bctf\b|\bcyber",
    "product": r"\bproduct\b|retention|cohort|\busers\b|downloads",
    "automation": r"\bautomat",  # automated / automation / automating
    "deep learning": r"deep learning|neural|pytorch|tensorflow|keras|\bcuda\b",
}

SKILL_WORDS = [
    "python", "c++", "c", "java", "javascript", "typescript", "swift", "kotlin",
    "go", "rust", "sql", "react", "node", "pytorch", "tensorflow", "keras",
    "scikit-learn", "pandas", "numpy", "docker", "kubernetes", "git", "linux",
    "supabase", "firebase", "postgres", "mongodb", "redis", "graphql", "flask",
    "django", "fastapi", "spark", "hadoop", "airflow", "mlflow", "onnx",
    "cuda", "opencv", "swiftui", "flutter", "unity",
]

BUZZWORDS = [
    "passionate", "hardworking", "hard-working", "team player", "motivated",
    "detail-oriented", "fast learner", "results-driven", "dynamic",
    "self-starter", "go-getter", "synergy", "outside the box",
]

LINK_RE = re.compile(r"(github\.com|gitlab\.com|linkedin\.com|behance|kaggle\.com|huggingface\.co|https?://[a-z0-9.-]+\.[a-z]{2,})", re.I)
GITHUB_RE = re.compile(r"github\.com/[A-Za-z0-9_.-]+", re.I)
NUMBER_EVIDENCE_RE = re.compile(
    r"\b\d[\d,.]*\s*(%|percent|users?|downloads?|stars?|requests?|ms\b|x\b|hours?|weeks?|people|members|k\b|m\b|tps|qps|rows|images|samples|accuracy|f1|mae|rmse|fps|issues?|papers?|teams?|prompts?|models?|rating|-day)",
    re.I)
SECTION_RE = re.compile(r"^\s*(education|experience|projects?|skills?|publications?|awards?|activities|leadership)\b.{0,20}$",
                        re.I | re.M)
VERB_FIRST_RE = re.compile(r"^\s*[-•*]?\s*(built|shipped|wrote|designed|led|created|measured|reduced|increased|deployed|launched|implemented|trained|optimized|automated|published)\b",
                           re.I | re.M)


def market_demand(jobs: list[dict]) -> dict[str, int]:
    """term -> number of live titles that ask for it."""
    titles = [j["position"].lower() for j in jobs]
    return {
        term: sum(1 for t in titles if re.search(rx, t))
        for term, rx in TERMS.items()
    }


# ---------------------------------------------------------------- cv evidence
def cv_evidence(text: str) -> dict:
    low = text.lower()
    words = re.findall(r"[a-zA-Z][a-zA-Z+#.-]*", low)
    skills = sorted({s for s in SKILL_WORDS
                     if re.search(rf"(?<![a-z0-9]){re.escape(s)}(?![a-z0-9])", low)})
    terms = sorted(t for t, rx in CV_EVIDENCE.items() if re.search(rx, low))
    links = LINK_RE.findall(text)
    numbers = NUMBER_EVIDENCE_RE.findall(text)
    sections = [m.group(1).lower() for m in SECTION_RE.finditer(text)]
    buzz = [b for b in BUZZWORDS if b in low]
    action_bullets = len(VERB_FIRST_RE.findall(text))
    return {
        "word_count": len(words),
        "skills": skills,
        "terms": terms,
        "links": len(links),
        "has_github": bool(GITHUB_RE.search(text)),
        "quantified_claims": len(numbers),
        "sections": sorted(set(sections)),
        "buzzwords": buzz,
        "action_bullets": action_bullets,
    }


# ---------------------------------------------------------------- match count
def match_count(evidence: dict, jobs: list[dict]) -> int:
    """How many live listings this CV's vocabulary reaches at all."""
    kws = set(evidence["terms"]) | set(evidence["skills"])
    n = 0
    for j in jobs:
        title = j["position"].lower()
        if any(re.search(TERMS.get(k, rf"(?<![a-z]){re.escape(k)}(?![a-z])"), title) for k in kws):
            n += 1
    return n


# ---------------------------------------------------------------- scoring
def strength(evidence: dict, demand: dict) -> tuple[int, list[str]]:
    """0-100, each component named. Deterministic."""
    pts, parts = 0, []

    top_terms = [t for t, _ in sorted(demand.items(), key=lambda kv: -kv[1])[:8]]
    covered = [t for t in top_terms if t in evidence["terms"]]
    p = min(30, len(covered) * 6)
    pts += p
    parts.append(f"market coverage {p}/30 ({len(covered)}/8 top demand terms present)")

    p = min(20, evidence["quantified_claims"] * 4)
    pts += p
    parts.append(f"quantified claims {p}/20 ({evidence['quantified_claims']} numbers with units)")

    p = min(15, len(evidence["skills"]) * 2)
    pts += p
    parts.append(f"named tools {p}/15 ({len(evidence['skills'])} recognizable tools)")

    p = 10 if evidence["has_github"] else 0
    pts += p
    parts.append(f"github link {p}/10")

    p = min(10, evidence["action_bullets"] * 2)
    pts += p
    parts.append(f"action-verb bullets {p}/10 ({evidence['action_bullets']} found)")

    p = 10 if "projects" in " ".join(evidence["sections"]) else 0
    pts += p
    parts.append(f"projects section {p}/10")

    p = 5 if 250 <= evidence["word_count"] <= 900 else 0
    pts += p
    parts.append(f"length sanity {p}/5 ({evidence['word_count']} words)")

    pts -= min(10, len(evidence["buzzwords"]) * 2)
    if evidence["buzzwords"]:
        parts.append(f"buzzword penalty -{min(10, len(evidence['buzzwords']) * 2)} ({', '.join(evidence['buzzwords'])})")
    return max(0, pts), parts


# ---------------------------------------------------------------- verdict copy
def gaps(evidence: dict, demand: dict) -> list[dict]:
    """Top demand terms with zero evidence in the CV + the concrete move."""
    moves = {
        "machine learning": "train one real model on real data, report a metric (accuracy, MAE), put the number in the bullet",
        "ai": "one working AI project with a measured result beats ten courses; build it, measure it, link it",
        "agentic ai": "build one agent that does a real task end to end, link the repo, state what it automates",
        "generative ai": "ship one genai project with a measured output (latency, cost per run, eval score)",
        "llm": "wrap a deterministic engine around an llm task and benchmark it, numbers in the bullet",
        "research": "one reading-group writeup or reproduction of a paper with your measured results counts as research evidence",
        "data science": "one dataset, one question, one chart, one number, linked notebook",
        "data engineering": "one pipeline that moves real data on a schedule; row counts and runtime in the bullet",
        "computer vision": "one on-device or classical cv project with fps/accuracy measured",
        "nlp": "one text-processing project with a scored benchmark, even a small one",
        "robotics": "one hardware or sim project with a video link and a measured behavior",
        "software engineering": "one shipped thing with users or downloads, count them, cite them",
        "infrastructure": "one benchmark harness or deploy pipeline you built, with before/after numbers",
        "cloud": "deploy one project to a cloud with a public url; region, cost and uptime in the bullet",
        "security": "one ctf writeup or one responsibly-disclosed finding, linked",
        "product": "pick one project and report a user-facing number: users, retention, rating",
        "automation": "automate one boring real workflow end to end and count the hours it saves",
        "deep learning": "one trained network with the training curve and final metric in the repo readme",
    }
    out = []
    for term, cnt in sorted(demand.items(), key=lambda kv: -kv[1]):
        if cnt >= 10 and term not in evidence["terms"]:
            out.append({"term": term, "market": cnt,
                        "move": moves.get(term, f"add one concrete, measured project that proves {term}")})
    return out[:5]


def hearts_note(found_job: bool | None, score: int) -> str | None:
    if found_job is True and score < 45:
        return "this CV did not get you that job. something else did. probably your connections <3"
    if found_job is False and score >= 70:
        return "the CV is not the problem. you probably had no connections <3"
    if found_job is False and score < 45:
        return "no connections needed to explain this one. the CV alone did it."
    if found_job is True and score >= 70:
        return "for once, both the CV and the network did their job."
    return None


def verdict(evidence: dict, demand: dict, matched: int, total: int,
            score: int, found_job: bool | None) -> dict:
    g = gaps(evidence, demand)
    lines = []

    lines.append(f"your vocabulary reaches {matched} of {total} live internships. "
                 f"the other {total - matched} cannot even see you.")

    if evidence["quantified_claims"] == 0:
        lines.append("zero numbers in the whole document. every claim is unpriced: "
                     "'improved performance' is a mood, '41% fewer duplicates' is a fact.")
    elif evidence["quantified_claims"] < 3:
        lines.append(f"{evidence['quantified_claims']} quantified claim(s). recruiters scan for numbers first; "
                     f"give every project its number.")

    if not evidence["has_github"]:
        lines.append("no github link. for an engineering internship this reads as 'the work does not exist'.")

    if evidence["buzzwords"]:
        lines.append(f"{len(evidence['buzzwords'])} buzzword(s) with no evidence attached: "
                     f"{', '.join(evidence['buzzwords'])}. delete them, the space is expensive.")

    if evidence["action_bullets"] == 0:
        lines.append("no bullet starts with a verb that did something. 'responsible for' is not a result.")

    for gap in g:
        lines.append(f"'{gap['term']}' appears in {gap['market']} live titles; your CV has zero evidence of it. "
                     f"move: {gap['move']}.")

    note = hearts_note(found_job, score)
    return {"score": score, "matched": matched, "total": total,
            "lines": lines, "gaps": g, "note": note}


# ---------------------------------------------------------------- cli
def critique_text(text: str, found_job: bool | None = None) -> dict:
    jobs = json.loads(JOBS.read_text())
    demand = market_demand(jobs)
    ev = cv_evidence(text)
    matched = match_count(ev, jobs)
    score, score_parts = strength(ev, demand)
    v = verdict(ev, demand, matched, len(jobs), score, found_job)
    v["evidence"] = ev
    v["score_parts"] = score_parts
    v["demand_top"] = sorted(demand.items(), key=lambda kv: -kv[1])[:8]
    return v


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cv", help="plain-text CV file")
    flag = ap.add_mutually_exclusive_group()
    flag.add_argument("--found-job", action="store_true")
    flag.add_argument("--no-job", action="store_true")
    ap.add_argument("--json", help="write findings JSON here")
    args = ap.parse_args()

    found = True if args.found_job else False if args.no_job else None
    v = critique_text(Path(args.cv).read_text(), found)

    print(f"score {v['score']}/100 | reach {v['matched']}/{v['total']} live listings")
    for p in v["score_parts"]:
        print(f"  · {p}")
    print()
    for line in v["lines"]:
        print(f"— {line}")
    if v["note"]:
        print(f"\nnote: {v['note']}")
    if args.json:
        Path(args.json).write_text(json.dumps(v, ensure_ascii=False, indent=1))
        print(f"\nwritten: {args.json}")


if __name__ == "__main__":
    main()
