#!/usr/bin/env python3
"""Every script the site ships must actually PARSE.

Written after shipping a dead one. A '\\n' inside a JavaScript string was
written as a single backslash-n in the Python source, so Python turned it into
a real newline, the JS string literal ran off the end of the line, and the
whole inline script -- signup, consent check, waitlist, CV reader, live reach
-- was a SyntaxError. The page looked perfect. Every one of the 448 tests
passed. The form simply did nothing, and nothing anywhere said so.

That is the worst shape a bug can have here: invisible in the HTML, invisible
in the suite, visible only to a person who clicks. The generator is Python
producing JavaScript, so this class of bug is always one escape away.

Skips when node is missing rather than pretending to check.

Run: python3 -m unittest discover engine/tests
"""
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).parent
ENGINE = HERE.parent
sys.path.insert(0, str(ENGINE))

import build_site  # noqa: E402

SCRIPT_RE = re.compile(r"<script([^>]*)>(.*?)</script>", re.S)
TYPE_RE = re.compile(r'type\s*=\s*["\']([^"\']*)["\']', re.I)


def inline_scripts(html: str) -> list[str]:
    """Only scripts a browser would EXECUTE.

    A src= tag has no body here, and application/ld+json is structured data,
    not JavaScript -- running a JS parser over it would fail for a reason that
    says nothing about whether the page works.
    """
    out = []
    for attrs, body in SCRIPT_RE.findall(html):
        if "src=" in attrs.lower() or not body.strip():
            continue
        m = TYPE_RE.search(attrs)
        typ = (m.group(1) if m else "").lower()
        if typ and "javascript" not in typ and typ != "module":
            continue
        out.append(body)
    return out


class EveryInlineScriptParses(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.node = shutil.which("node")
        if not cls.node:
            raise unittest.SkipTest("node not available")
        jobs = json.loads((ENGINE / "data" / "jobs.json").read_text())
        import match
        profile = json.loads((ENGINE.parent / "profile.json").read_text())
        results, stats = match.run(profile, jobs)
        cls.surfaces = {
            "index": build_site.build_index(jobs, results, stats, 0,
                                            {"capacity": 200, "taken": 1}),
            "cv": build_site.build_cv_page(len(jobs)),
            "unsubscribe": build_site.build_unsubscribe(),
            "confirm": build_site.build_confirm(),
            "accept": build_site.build_accept(),
            "jobs_index": build_site.build_jobs_index(jobs),
            "job_page": build_site.build_job_page(jobs[0], "x"),
        }

    def check(self, source: str) -> subprocess.CompletedProcess:
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False,
                                         encoding="utf-8") as f:
            f.write(source)
            path = f.name
        try:
            return subprocess.run([self.node, "--check", path],
                                  capture_output=True, text=True)
        finally:
            Path(path).unlink()

    def test_every_inline_script_on_every_surface_parses(self):
        checked = 0
        for name, html in self.surfaces.items():
            for i, body in enumerate(inline_scripts(html)):
                with self.subTest(surface=name, script=i):
                    r = self.check(body)
                    self.assertEqual(r.returncode, 0,
                                     f"{name} ships an unparsable script:\n"
                                     f"{r.stderr[:600]}")
                    checked += 1
        self.assertGreater(checked, 0, "no inline script was checked at all")

    def test_the_generated_board_parses(self):
        """board.js is Python-written JavaScript too, and it carries listing
        text -- the most likely thing in the repo to contain a stray quote."""
        board = ENGINE.parent / "docs" / "board.js"
        if not board.exists():
            self.skipTest("board.js not built yet")
        r = self.check(board.read_text(encoding="utf-8"))
        self.assertEqual(r.returncode, 0, r.stderr[:600])

    def test_the_cv_engine_parses(self):
        js = ENGINE.parent / "docs" / "cv-engine.js"
        if not js.exists():
            self.skipTest("cv-engine.js not built yet")
        r = self.check(js.read_text(encoding="utf-8"))
        self.assertEqual(r.returncode, 0, r.stderr[:600])

    def test_a_broken_script_would_actually_be_caught(self):
        """A checker that passes everything proves nothing."""
        r = self.check("const a = 'unterminated\n;")
        self.assertNotEqual(r.returncode, 0)


if __name__ == "__main__":
    unittest.main()
