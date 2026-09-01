#!/usr/bin/env python3
"""The live reach count on the signup form must be the MAILER's number.

Type "seks" into the interests box and today that silently means zero mail,
forever, with nothing on the page saying so. The count that fixes it is a
promise, and a promise computed by a second implementation is a promise that
drifts. So build_site ships the titles already normalised by match.norm_title,
plus the matcher's own expansion table and split rule, and the browser only
splits and substring-tests.

This file runs BOTH and compares. Same precedent as the CV engine's Python-JS
parity test; it skips when node is unavailable rather than pretending.

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
DOCS = ENGINE.parent / "docs"
sys.path.insert(0, str(ENGINE))

import match  # noqa: E402

CASES = [
    "ai infra",
    "seks",
    "machine learning",
    "computer vision, nlp",
    "ai infra, agents, devtools",
    "asdkjhasd",
    "a",
    "  ",
    "data science and robotics",
    "LLM Systems",
    "security/cloud",
    "AI INFRA",
    "compiler",
    "on-device and cpu-efficient",
]


def python_reach(text: str, titles: list[str]) -> int:
    """Exactly what the mailer would count: listings with >=1 interest hit."""
    interests, _ = match.keywords_from_profile(
        {"direction_and_motivation": {"target_field": text}})
    return sum(1 for t in titles
               if any(f" {k} " in t for k in interests if k))


class ReachParity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which("node"):
            raise unittest.SkipTest("node not available")
        cls.board = DOCS / "board.js"
        if not cls.board.exists():
            raise unittest.SkipTest("board.js not built yet")
        cls.titles = json.loads(
            re.search(r"const BOARD = (\[.*?\]);", cls.board.read_text(),
                      re.S).group(1))

    def js_reach(self, cases):
        """Run the page's own keyword+count logic under node, verbatim."""
        script = self.board.read_text() + """
function keywords(text) {
  const out = new Set();
  for (let t of text.split(new RegExp(SPLIT))) {
    t = t.trim().toLowerCase();
    if (t.length > KWMIN && t.length < KWMAX) out.add(t);
  }
  for (const key in EXPANSION) {
    const head = key.split(' ')[0];
    for (const i of out) if (i.includes(head)) { EXPANSION[key].forEach(e => out.add(e)); break; }
  }
  return [...out];
}
const cases = JSON.parse(process.argv[2]);
console.log(JSON.stringify(cases.map(c => {
  const kws = keywords(c);
  let n = 0;
  for (const t of BOARD) if (kws.some(k => t.includes(' ' + k + ' '))) n++;
  return n;
})));
"""
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
            f.write(script)
            path = f.name
        out = subprocess.run([shutil.which("node"), path, json.dumps(cases)],
                             capture_output=True, text=True)
        Path(path).unlink()
        if out.returncode:
            self.fail(f"node failed: {out.stderr[:400]}")
        return json.loads(out.stdout)

    def test_the_browser_counts_what_the_matcher_counts(self):
        js = self.js_reach(CASES)
        for text, got in zip(CASES, js):
            with self.subTest(interests=text):
                self.assertEqual(got, python_reach(text, self.titles))

    def test_nonsense_really_is_zero_in_both(self):
        """The case that started this: a word no title contains."""
        self.assertEqual(python_reach("seks", self.titles), 0)
        self.assertEqual(self.js_reach(["seks"])[0], 0)

    def test_a_real_interest_is_not_zero(self):
        """A parity test that passes because BOTH are broken proves nothing."""
        self.assertGreater(python_reach("machine learning", self.titles), 0)

    def test_the_expansion_table_actually_widens_the_count(self):
        """"ai infra" is six keywords, not one; a browser that did not know
        would under-count exactly the wording the placeholder suggests."""
        narrow = python_reach("ai infrastructure", self.titles)
        wide = python_reach("ai infra", self.titles)
        self.assertGreater(wide, narrow)
        self.assertEqual(self.js_reach(["ai infra"])[0], wide)

    def test_the_shipped_titles_are_already_normalised(self):
        """If they were raw the browser would have to normalise, and that is
        the second implementation this whole design exists to avoid."""
        for t in self.titles[:50]:
            self.assertEqual(t, match.norm_title(t), t)


if __name__ == "__main__":
    unittest.main()
