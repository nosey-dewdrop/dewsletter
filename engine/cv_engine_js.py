#!/usr/bin/env python3
"""Emit the browser port of cv_critique as docs/cv-engine.js.

The JS engine mirrors cv_critique.py exactly; test_engine_parity.py locks the
two implementations to identical scores on the fixtures. Data (live titles,
demand counts) is baked in at build time so the CV never leaves the browser.
"""
import json
import re
from pathlib import Path

import cv_critique
import match

TEMPLATE = r"""
// sightstone cv engine — deterministic browser port of engine/cv_critique.py.
// the CV text NEVER leaves this page: no upload, no server, no model.
'use strict';
const CVE = __PAYLOAD__;

function cvEvidence(text) {
  const low = text.toLowerCase();
  const words = low.match(/[a-z][a-z+#.-]*/g) || [];
  const skills = CVE.skill_words.filter(s =>
    new RegExp('(?<![a-z0-9])' + s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '(?![a-z0-9])').test(low));
  const terms = Object.keys(CVE.cv_evidence).filter(t => new RegExp(CVE.cv_evidence[t]).test(low));
  const quantified = (text.match(new RegExp(CVE.number_re, 'gi')) || []).length;
  const sections = (text.match(new RegExp(CVE.section_re, 'gim')) || []).map(s => s.trim().toLowerCase());
  const buzz = CVE.buzzwords.filter(b => low.includes(b));
  const bullets = (text.match(new RegExp(CVE.verb_re, 'gim')) || []).length;
  return {
    word_count: words.length, skills: skills, terms: terms,
    has_github: /github\.com\/[A-Za-z0-9_.-]+/i.test(text),
    quantified_claims: quantified, sections: sections,
    buzzwords: buzz, action_bullets: bullets,
  };
}

function matchCount(ev) {
  const kws = [...new Set([...ev.terms, ...ev.skills])];
  const res = kws.map(k => new RegExp(
    CVE.terms[k] || ('(?<![a-z])' + k.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '(?![a-z])')));
  let n = 0;
  for (const t of CVE.titles) if (res.some(r => r.test(t))) n++;
  return n;
}

function strength(ev) {
  let pts = 0; const parts = [];
  const top = CVE.demand_top.map(d => d[0]);
  const covered = top.filter(t => ev.terms.includes(t));
  let p = Math.min(30, covered.length * 6); pts += p;
  parts.push(['market coverage', covered.length + '/8 top demand terms present', p + '/30']);
  p = Math.min(20, ev.quantified_claims * 4); pts += p;
  parts.push(['quantified claims', ev.quantified_claims + ' numbers with units', p + '/20']);
  p = Math.min(15, ev.skills.length * 2); pts += p;
  parts.push(['named tools', ev.skills.length + ' recognizable tools', p + '/15']);
  p = ev.has_github ? 10 : 0; pts += p;
  parts.push(['github link', ev.has_github ? 'present' : 'missing', p + '/10']);
  p = Math.min(10, ev.action_bullets * 2); pts += p;
  parts.push(['action-verb bullets', ev.action_bullets + ' found', p + '/10']);
  p = ev.sections.join(' ').includes('project') ? 10 : 0; pts += p;
  parts.push(['projects section', p ? 'present' : 'missing', p + '/10']);
  p = (ev.word_count >= 250 && ev.word_count <= 900) ? 5 : 0; pts += p;
  parts.push(['length sanity', ev.word_count + ' words', p + '/5']);
  const pen = Math.min(10, ev.buzzwords.length * 2);
  if (pen) parts.push(['buzzword penalty', ev.buzzwords.join(', '), '-' + pen]);
  return [Math.max(0, pts - pen), parts];
}

function gaps(ev) {
  const out = [];
  for (const [term, cnt] of CVE.demand_sorted) {
    if (cnt >= 10 && !ev.terms.includes(term))
      out.push({term: term, market: cnt, move: CVE.moves[term] ||
        ('add one concrete, measured project that proves ' + term)});
    if (out.length === 5) break;
  }
  return out;
}

function heartsNote(found, score) {
  if (found === true && score < 45) return 'this CV did not get you that job. something else did. probably your connections <3';
  if (found === false && score >= 70) return 'the CV is not the problem. you probably had no connections <3';
  if (found === false && score < 45) return 'no connections needed to explain this one. the CV alone did it.';
  if (found === true && score >= 70) return 'for once, both the CV and the network did their job.';
  return null;
}

function critique(text, found) {
  const ev = cvEvidence(text);
  const matched = matchCount(ev);
  const total = CVE.titles.length;
  const [score, parts] = strength(ev);
  const g = gaps(ev);
  const lines = [];
  lines.push('your vocabulary reaches ' + matched + ' of ' + total +
    ' live internships. the other ' + (total - matched) + ' cannot even see you.');
  if (ev.quantified_claims === 0)
    lines.push("zero numbers in the whole document. every claim is unpriced: 'improved performance' is a mood, '41% fewer duplicates' is a fact.");
  else if (ev.quantified_claims < 3)
    lines.push(ev.quantified_claims + ' quantified claim(s). recruiters scan for numbers first; give every project its number.');
  if (!ev.has_github)
    lines.push("no github link. for an engineering internship this reads as 'the work does not exist'.");
  if (ev.buzzwords.length)
    lines.push(ev.buzzwords.length + ' buzzword(s) with no evidence attached: ' +
      ev.buzzwords.join(', ') + '. delete them, the space is expensive.');
  if (ev.action_bullets === 0)
    lines.push("no bullet starts with a verb that did something. 'responsible for' is not a result.");
  for (const gap of g)
    lines.push("'" + gap.term + "' appears in " + gap.market +
      ' live titles; your CV has zero evidence of it. move: ' + gap.move + '.');
  return {score: score, matched: matched, total: total, parts: parts,
          lines: lines, gaps: g, note: heartsNote(found, score), evidence: ev};
}

if (typeof module !== 'undefined') module.exports = {critique: critique};
"""


def payload() -> dict:
    jobs = json.loads((Path(__file__).parent / "data" / "jobs.json").read_text())
    jobs, _ = match.dedupe(jobs)
    demand = cv_critique.market_demand(jobs)
    demand_sorted = sorted(demand.items(), key=lambda kv: -kv[1])
    return {
        "titles": [j["position"].lower() for j in jobs],
        "terms": cv_critique.TERMS,
        "cv_evidence": cv_critique.CV_EVIDENCE,
        "skill_words": cv_critique.SKILL_WORDS,
        "buzzwords": cv_critique.BUZZWORDS,
        "moves": {  # single source: keep in sync via parity test
            t: m for t, m in _moves().items()
        },
        "number_re": cv_critique.NUMBER_EVIDENCE_RE.pattern,
        "section_re": r"^\s*(education|experience|projects?|skills?|publications?|awards?|activities|leadership)\b.{0,20}$",
        "verb_re": r"^\s*[-•*]?\s*(built|shipped|wrote|designed|led|created|measured|reduced|increased|deployed|launched|implemented|trained|optimized|automated|published)\b",
        "demand_top": demand_sorted[:8],
        "demand_sorted": demand_sorted,
    }


def _moves() -> dict:
    src = Path(cv_critique.__file__).read_text()
    m = re.search(r"moves = \{(.+?)\n    \}", src, re.S)
    pairs = re.findall(r'"([^"]+)": "([^"]+)"', m.group(1))
    return dict(pairs)


def emit(out: Path) -> None:
    js = TEMPLATE.replace("__PAYLOAD__", json.dumps(payload(), ensure_ascii=False))
    out.write_text(js)
    print(f"cv engine: {out} ({out.stat().st_size // 1024}kb)")


if __name__ == "__main__":
    emit(Path(__file__).parent.parent / "docs" / "cv-engine.js")
