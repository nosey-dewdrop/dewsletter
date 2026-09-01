#!/usr/bin/env python3
"""Byte freeze for every surface build_site.py emits.

The escaping work of S5a is only safe if it changes nothing else. This module
builds the five surfaces from the FROZEN fixture corpus (engine/tests/fixtures,
599 listings after dedupe) with the clock pinned to 2026-07-27, and compares
sha256 of the exact bytes. A template edit, a stray space, a reworded sentence:
all of them turn this red.

engine/data/jobs.json is deliberately NOT an input. daily.yml rewrites it every
morning, so binding the freeze to it would break CI at 09:00 every day.

Slug note: the frozen job_pages surface is the concatenation of one page per
listing keyed on the BASE slug, i.e. slugify(company-position) with no
collision counter. 583 base slugs cover 599 listings (16 collisions); main()
adds "-2"/"-3" suffixes when it writes them to disk. The freeze measures the
page bodies, not the on-disk filenames.

Run: python3 -m unittest discover engine/tests
"""
import ast
import hashlib
import json
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path

HERE = Path(__file__).parent
FIXTURES = HERE / "fixtures"
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE.parent))

import build_site  # noqa: E402
import cv_critique  # noqa: E402
import fetch  # noqa: E402
import match  # noqa: E402

FROZEN_FETCHED_AT = "2026-08-30T09:00:00+00:00"  # only lands in fields the site never prints
FROZEN_TODAY = "July 27, 2026"
FROZEN_TODAY_ISO = "2026-07-27"
FROZEN_VERSION = "v2 · built 2026-07-27"
FROZEN_DUPES_REMOVED = 41          # engine/data/fetch_meta.json, the number main() prints
FROZEN_SEATS = {"capacity": 100, "taken": 1}
FIXTURE_TOTAL = 599

# measured on the frozen fixtures. size in bytes, then sha256.
#
# Re-frozen by the scoring card (2026-09-01). Only `index`, `user_page` and
# FROZEN_USER_FEED moved: they are the three surfaces that render Damla's
# matches, and matches fell 3 -> 1 when geography stopped scoring. `cv`,
# `jobs_index`, `job_pages` and `unsubscribe` are byte-IDENTICAL to the S5a
# freeze, and test_no_template_literal_moved still passes -- so this re-freeze
# is the corpus speaking, not a template edit sneaking through.
FROZEN_SURFACES = {
    # re-frozen 2026-09-01 by S10's landing copy. The form used to say "you are
    # in" the instant the row was inserted, which stopped being true when D2
    # started holding unconfirmed rows back; and the consent line promised
    # one-click unsubscribe on a page that answers POST with 405.
    # re-frozen again by S13: the header claimed "updated daily at 09:00 UTC+3".
    # Measured over 37 scheduled runs the median build lands 78 minutes late and
    # one landed 12 hours late, so the page named a time it does not keep. It
    # now says "rebuilt once a day" and the footnote carries the measurement.
    # re-frozen again: the front page gained a door to the waitlist (the queue
    # was written in SQL and unreachable from the site, so run_invites and
    # accept.html were dead code), and the showcase now prints the measured geo
    # cut so "matched: 1" reads as a hard profile instead of a broken engine.
    "index": (16369,
              "028f11bc490a4bd4b4a2435f77fe2a550649a7b443b28ff76d81e0fff1e01f13"),
    "cv": (9296,
           "8fd87f669df359ca87d3689a63b6ab0ea273aa077cb198630b48d73261225be4"),
    "jobs_index": (265046,
                   "ec9c4790c3797e8356b268c189904621d311f6cb69808752a4ae78c700c551e8"),
    "job_pages": (1811188,
                  "3b31542ceced7a0e91543c2e9ce6f437ce2bcc5c7d2d3914e5fa2b8b2bda7efa"),
    # re-frozen 2026-09-01 by the S10 card. ONE literal moved and it is named
    # in the diff: "One-click unsubscribe." -> "Leave in one click, on this
    # page." The old string was false -- the page is static GitHub Pages and
    # POST answers 405, so RFC 8058 one-click is impossible on it.
    "unsubscribe": (2406,
                    "06cd1f67e45f45e58486e86b5e81c8f5951ccd11d6dfff3a83b6392e91b5b5cf"),
    # S5b, the sixth surface. Built off the same frozen corpus, from the base
    # slug map (main() writes the collision-suffixed one to disk).
    "user_page": (2499,
                  "b8ec4dd7ca4f6542038b27ebba0075e54e9f3cb6b1c6eb68f1a67c9e0773e887"),
}
FROZEN_TOTAL_BYTES = 2106804
FROZEN_USER_FEED = (693,
                    "7c879008f9349fd3bf6892e34328aa61f00477fc61cc01eb57f5d68e9360d62b")

# sha256 of the sorted multiset of string literals in build_site.py BEFORE S5a
# touched it (git 9af98b1). The two helpers S5a adds carry their own literals;
# everything outside them has to hash to this.
CONSTANTS_BEFORE_S5A = "53e17461acb438d9925813c5700ebac21ee75db2d86f7f89c13e66440cccab0e"
NEW_HELPERS = ("json_in_html", "safe_url",
               # S5b: the whole user-page surface. Every literal it needs lives
               # inside these functions; main() gained none.
               "robots_extra", "job_slug_map", "slugs_on_disk", "result_key",
               "xml_text", "user_row_html", "user_page_html", "user_feed_xml",
               "write_user_pages",
               # S10: the confirmation page. D2 holds back every unconfirmed
               # address, so without this surface nobody new can ever be
               # mailed. write_confirm owns the filename so main() still gains
               # a call and not a literal.
               "build_confirm", "write_confirm",
               # S9b left the invite with nowhere to land: the mail pointed at
               # the home page, which reads no token, so an offered seat could
               # never actually be accepted. This is that page.
               "build_accept", "write_accept")

# sha256 of the sorted multiset of string literals inside main() alone. S5b adds
# two calls to main() and not one literal; this locks that separately from the
# module-wide gate above.
MAIN_CONSTANTS = "ab44c922149b8237298eb9e17611d6de22a2b4189ee3fffb0581016bcc6c0c6e"


def fixture_corpus() -> list[dict]:
    texts = {m.NAME: (FIXTURES / m.FIXTURE).read_text(encoding="utf-8")
             for m in fetch.SOURCES}
    per = fetch.parse_all(texts, FROZEN_FETCHED_AT)
    flat = [job for _, rows in per for job in rows]
    deduped, _ = fetch.dedupe(flat)
    return deduped


def string_constants(tree: ast.AST) -> Counter:
    return Counter(n.value for n in ast.walk(tree)
                   if isinstance(n, ast.Constant) and isinstance(n.value, str))


def multiset_sha(counter: Counter) -> str:
    payload = json.dumps(sorted(counter.elements()), ensure_ascii=False)
    # surrogatepass: a source literal may hold a lone surrogate (the XML filter
    # needs the \\ud800-\\udfff range). Bytes are unchanged for every other
    # literal, so the frozen hash below still means what it meant.
    return hashlib.sha256(payload.encode("utf-8", "surrogatepass")).hexdigest()


class FrozenOutput(unittest.TestCase):
    """Every surface, byte for byte, off the frozen corpus."""

    @classmethod
    def setUpClass(cls):
        cls._clock = (build_site.TODAY, build_site.TODAY_ISO, build_site.VERSION)
        cls._jobs_path = cv_critique.JOBS
        build_site.TODAY = FROZEN_TODAY
        build_site.TODAY_ISO = FROZEN_TODAY_ISO
        build_site.VERSION = FROZEN_VERSION

        corpus = fixture_corpus()
        cls.jobs, _ = match.dedupe(corpus)
        cls._tmp = tempfile.TemporaryDirectory()
        corpus_json = Path(cls._tmp.name) / "jobs.json"
        corpus_json.write_text(json.dumps(corpus), encoding="utf-8")
        cv_critique.JOBS = corpus_json

        profile = json.loads((ROOT / "profile.json").read_text())
        results, stats = match.run(profile, cls.jobs)
        cls.surfaces = {
            "index": build_site.build_index(cls.jobs, results, stats,
                                            FROZEN_DUPES_REMOVED, FROZEN_SEATS),
            "cv": build_site.build_cv_page(len(cls.jobs)),
            "jobs_index": build_site.build_jobs_index(cls.jobs),
            "job_pages": "".join(
                build_site.build_job_page(j, build_site.slugify(
                    f'{j["company"]}-{j["position"]}')) for j in cls.jobs),
            "unsubscribe": build_site.build_unsubscribe(),
            "user_page": build_site.user_page_html(
                results, build_site.job_slug_map(cls.jobs)),
        }
        cls.results = results
        cls.smap = build_site.job_slug_map(cls.jobs)

    @classmethod
    def tearDownClass(cls):
        build_site.TODAY, build_site.TODAY_ISO, build_site.VERSION = cls._clock
        cv_critique.JOBS = cls._jobs_path
        cls._tmp.cleanup()

    def test_corpus_is_the_frozen_599(self):
        self.assertEqual(len(self.jobs), FIXTURE_TOTAL)

    def test_every_surface_is_byte_identical(self):
        for name, (size, sha) in FROZEN_SURFACES.items():
            with self.subTest(surface=name):
                raw = self.surfaces[name].encode("utf-8")
                self.assertEqual(len(raw), size, f"{name} size drifted")
                self.assertEqual(hashlib.sha256(raw).hexdigest(), sha,
                                 f"{name} bytes drifted")

    def test_total_bytes(self):
        total = sum(len(s.encode("utf-8")) for s in self.surfaces.values())
        self.assertEqual(total, FROZEN_TOTAL_BYTES)

    def test_no_template_literal_moved(self):
        """Outside the two new helpers, not one string literal changed.

        The multiset (not the set) is compared, so a duplicated or deleted
        literal shows up too.
        """
        tree = ast.parse((HERE.parent / "build_site.py").read_text())
        every = string_constants(tree)
        helper_owned = Counter()
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name in NEW_HELPERS:
                helper_owned += string_constants(node)
        self.assertEqual(len(helper_owned) > 0, True, "helpers vanished")
        self.assertEqual(multiset_sha(every - helper_owned), CONSTANTS_BEFORE_S5A)

    def test_user_feed_is_byte_identical(self):
        raw = build_site.user_feed_xml(self.results, self.smap).encode("utf-8")
        size, sha = FROZEN_USER_FEED
        self.assertEqual(len(raw), size)
        self.assertEqual(hashlib.sha256(raw).hexdigest(), sha)

    def test_main_gained_no_literal(self):
        """main() may gain calls, never a string of its own."""
        tree = ast.parse((HERE.parent / "build_site.py").read_text())
        mains = [n for n in ast.walk(tree)
                 if isinstance(n, ast.FunctionDef) and n.name == "main"]
        self.assertEqual(len(mains), 1)
        self.assertEqual(multiset_sha(string_constants(mains[0])), MAIN_CONSTANTS)


if __name__ == "__main__":
    unittest.main()
