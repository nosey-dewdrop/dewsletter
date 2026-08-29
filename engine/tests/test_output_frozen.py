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

# measured, 2026-08-30, on the frozen fixtures. size in bytes, then sha256.
FROZEN_SURFACES = {
    "index": (8792,
              "6d0f7ceee3224519504355b928062eda1d21927210d59c07cd8b51c56607441c"),
    "cv": (9295,
           "d2de8c1c76e9fee8762dfd69bbdda4f3e95ffb34d162441273bec455621ba6c2"),
    "jobs_index": (265046,
                   "ba8a9b5ec6a02b825394ed7533822c0b7de995ccccb296053d589269b8d74b52"),
    "job_pages": (1811188,
                  "7cf10d770a0e5bec5ef2f4e56b10a491f6b83e0309f8ed18d3b55c83fd964165"),
    "unsubscribe": (2395,
                    "a995b6d1c6613b2031d4672eab9a0a7f24d92b7bec1257c45da74c23a57152b9"),
}
FROZEN_TOTAL_BYTES = 2096716

# sha256 of the sorted multiset of string literals in build_site.py BEFORE S5a
# touched it (git 9af98b1). The two helpers S5a adds carry their own literals;
# everything outside them has to hash to this.
CONSTANTS_BEFORE_S5A = "c0477c0e9fcd184e3ba59450f7e721e56674fef44c25f3d715c36d9f89f984f5"
NEW_HELPERS = ("json_in_html", "safe_url")


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
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


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
        }

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


if __name__ == "__main__":
    unittest.main()
