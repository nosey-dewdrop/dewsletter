#!/usr/bin/env python3
"""Golden tests for the deterministic engines. Run: python3 -m unittest discover engine/tests -v"""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import cv_critique  # noqa: E402

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
        self.assertGreater(self.strong["matched"], 200)
        self.assertEqual(self.empty["matched"], 0)

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


if __name__ == "__main__":
    unittest.main()
