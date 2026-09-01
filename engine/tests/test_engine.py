#!/usr/bin/env python3
"""Golden tests for the deterministic engines. Run: python3 -m unittest discover engine/tests -v"""
import json
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import cv_critique  # noqa: E402
import match  # noqa: E402

HERE = Path(__file__).parent
STRONG = (HERE / "cv_strong.txt").read_text()
EMPTY = (HERE / "cv_empty.txt").read_text()


class CVCritique(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.strong = cv_critique.critique_text(STRONG, found_job=False)
        cls.empty = cv_critique.critique_text(EMPTY, found_job=True)

    def test_score_separation(self):
        self.assertGreaterEqual(self.strong["score"], 75)
        self.assertLessEqual(self.empty["score"], 20)

    def test_reach(self):
        """A5. This asserted `matched > 200` against the LIVE corpus.

        cv_critique counts against engine/data/jobs.json, which the cron
        rewrites every morning, and daily.yml runs this suite BEFORE the
        mailer. Measured 2026-09-01: 408 of 613. The literal 200 meant that a
        morning fetch returning under ~300 listings turned this red, failed the
        job, and sent no mail -- silently, with nothing in the output naming
        the corpus as the cause. The corpus has already been as low as 437 in
        this repo's own history.

        The claim here is SEPARATION and reach, not a magnitude: a strong CV
        reaches a large share of whatever is on the board today, an empty one
        reaches nothing. Stated as a share, it survives the board moving.
        """
        corpus = len(json.loads(cv_critique.JOBS.read_text()))
        self.assertEqual(self.empty["matched"], 0)
        self.assertGreater(self.strong["matched"], corpus // 3,
                           "a strong CV stopped reaching even a third of the "
                           "board; that is the engine changing, not the corpus")

    def test_no_false_gap_claims(self):
        """A gap may only be claimed if the CV truly has zero evidence of it."""
        for report, text in [(self.strong, STRONG), (self.empty, EMPTY)]:
            for gap in report["gaps"]:
                rx = cv_critique.CV_EVIDENCE[gap["term"]]
                self.assertIsNone(
                    re.search(rx, text.lower()),
                    f"false gap claim: '{gap['term']}' is evidenced in the CV",
                )

    def test_every_gap_has_a_concrete_move(self):
        for gap in self.strong["gaps"] + self.empty["gaps"]:
            self.assertGreater(len(gap["move"]), 20)
            self.assertNotIn("proves " + gap["term"], gap["move"],
                             "generic fallback move leaked into output")

    def test_hearts_notes(self):
        self.assertIn("no connections", self.strong["note"])   # strong + no job
        self.assertIn("your connections", self.empty["note"])  # empty + found job
        ok = cv_critique.critique_text(STRONG, found_job=True)
        self.assertIn("both the CV and the network", ok["note"])
        none_flag = cv_critique.critique_text(STRONG, found_job=None)
        self.assertIsNone(none_flag["note"])

    def test_buzzword_detection(self):
        self.assertIn("team player", self.empty["evidence"]["buzzwords"])
        self.assertEqual(self.strong["evidence"]["buzzwords"], [])

    def test_every_line_is_backed(self):
        """Sharp claims must carry a number or a named fact."""
        for line in self.empty["lines"]:
            self.assertTrue(re.search(r"\d|github|verb", line), f"unbacked claim: {line}")


class BrowserEngineParity(unittest.TestCase):
    """The JS port must give IDENTICAL scores to the Python engine."""

    @classmethod
    def setUpClass(cls):
        import shutil
        import subprocess
        import tempfile
        if not shutil.which("node"):
            raise unittest.SkipTest("node not available")
        import cv_engine_js
        cls.tmp = Path(tempfile.mkdtemp()) / "cv-engine.js"
        cv_engine_js.emit(cls.tmp)
        script = f"""
const {{critique}} = require({json.dumps(str(cls.tmp))});
const fs = require('fs');
const out = {{}};
for (const f of {json.dumps([str(HERE / 'cv_strong.txt'), str(HERE / 'cv_empty.txt')])})
  out[f] = (v => ({{score: v.score, matched: v.matched, total: v.total}}))(critique(fs.readFileSync(f, 'utf8'), false));
console.log(JSON.stringify(out));
"""
        cls.js = json.loads(subprocess.run(["node", "-e", script],
                                           capture_output=True, text=True, check=True).stdout)

    def test_scores_match_python(self):
        for path, text in [(str(HERE / "cv_strong.txt"), STRONG), (str(HERE / "cv_empty.txt"), EMPTY)]:
            py = cv_critique.critique_text(text, found_job=False)
            self.assertEqual(self.js[path]["score"], py["score"], path)
            self.assertEqual(self.js[path]["matched"], py["matched"], path)
            self.assertEqual(self.js[path]["total"], py["total"], path)


def job(**kw):
    base = {"company": "Acme", "position": "AI Intern", "location": "Remote - USA",
            "remote": True, "salary": None, "link": "https://x", "age": "3d"}
    base.update(kw)
    return base


PROFILE = {
    "identity": {"name": "t", "location": "Ankara, Turkey"},
    "education": ["BS Computer Science"],
    "skills": {"languages": ["Python", "C++"]},
    "direction_and_motivation": {"target_field": "AI infra; agent platforms; LLM systems"},
}


class Matcher(unittest.TestCase):
    def test_parse_age_days(self):
        cases = {"3d": 3, "2w": 14, "2mo": 60, "1y": 365, "5h": 0, None: None, "?": None}
        for raw, want in cases.items():
            self.assertEqual(match.parse_age_days(raw), want, raw)

    def test_dedupe_keeps_newest_first(self):
        a, b = job(age="3d"), job(age="40d")
        out, removed = match.dedupe([a, b])
        self.assertEqual(removed, 1)
        self.assertEqual(out, [a])

    def test_phd_only_excluded_for_bs(self):
        results, stats = match.run(PROFILE, [job(position="Research Intern - PhD")])
        self.assertEqual(stats["phd_only"], 1)
        self.assertEqual(results, [])

    def test_us_auth_excluded_for_non_us(self):
        results, stats = match.run(PROFILE, [job(position="AI Intern - US Citizenship Required")])
        self.assertEqual(stats["us_work_auth"], 1)

    def test_ms_penalty_not_exclusion(self):
        results, _ = match.run(PROFILE, [job(position="Agentic AI Intern - MS preferred")])
        self.assertEqual(len(results), 1)
        self.assertIn("listing prefers MS", results[0]["reasons"])

    def test_every_reason_is_a_reason_and_not_a_filter(self):
        """Inverted by the scoring card. It used to REQUIRE "remote" and "fresh".

        The user sentence this enforces: "next to every listing it says why it
        concerns ME, not 'I did not eliminate you'". remote / fresh / stale /
        salary / location are things the filter knows about the listing, not
        things that make it worth Damla's morning.
        """
        results, _ = match.run(PROFILE, [job(position="Agentic AI Infrastructure Intern")])
        r = results[0]
        self.assertGreater(r["score"], 0)
        self.assertTrue(any("in title" in x for x in r["reasons"]))
        for banned in ("remote", "fresh", "stale", "salary", "location fits"):
            for reason in r["reasons"]:
                self.assertNotIn(banned, reason.lower(),
                                 f"{banned!r} is a filter, not a reason: {reason!r}")

    def test_freshness_does_not_move_the_score(self):
        """Inverted by the scoring card. It used to assert fresh > stale.

        Age still ORDERS the bulletin (see the sort in match.run) -- it just
        cannot decide who gets into it. A 6-month-old listing that matches an
        interest beats a 3-day-old one that matches nothing.
        """
        fresh, _ = match.run(PROFILE, [job(position="Agentic AI Intern", age="3d")])
        stale, _ = match.run(PROFILE, [job(position="Agentic AI Intern", age="6mo")])
        self.assertEqual(fresh[0]["score"], stale[0]["score"])

    def test_a_listing_whose_only_distinction_is_remote_is_not_a_match(self):
        """The card's whole point, in one assertion.

        Ensemble Health and Hone Health were mailed to Damla on exactly this:
        a title with no interest and no skill in it, carried by remote +3.
        """
        results, stats = match.run(
            PROFILE, [job(position="Warehouse Operations Intern", remote=True)])
        self.assertEqual(results, [])
        self.assertEqual(stats["no_signal"], 1)


if __name__ == "__main__":
    unittest.main()
