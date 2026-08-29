#!/usr/bin/env python3
"""Tests for `remote_scope` / `scope_census`: what "remote" actually means.

A boolean cannot tell "apply from anywhere on earth" apart from "live in the US,
skip the office". Both are `remote: true`. The distinction was always sitting in
the location string (`Remote` vs `Remote - USA`) and nobody read it.

`remote_scope` is DERIVED: it reads a record, it never writes one. jobs.json
keeps exactly the 13 fields it had. Nothing here touches the network or the
clock; the corpus and the frozen fixtures are the only inputs.

Guessing is a bug, not a feature: an unresolved location is `unknown`, never a
nearest match and never a silent `global`.

Run: python3 -m unittest discover engine/tests -v
"""
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).parent
FIXTURES = HERE / "fixtures"
sys.path.insert(0, str(HERE.parent))

import fetch  # noqa: E402
from fetch.common import (  # noqa: E402
    COUNTRY_CODES, FIELDS, US_STATE_CODES, remote_scope, scope_census,
)

FROZEN_AT = "2026-08-30T09:00:00+00:00"

# the 47 country names measured in the corpus' location strings
CORPUS_COUNTRY_NAMES = [
    "Argentina", "Australia", "Austria", "Belarus", "Belgium", "Botswana",
    "Brazil", "Canada", "Chile", "China", "Colombia", "Finland", "France",
    "Germany", "Greece", "Honduras", "Hong Kong", "Hungary", "India",
    "Indonesia", "Ireland", "Israel", "Italy", "Malaysia", "Mexico",
    "New Zealand", "Philippines", "Poland", "Portugal", "Romania",
    "Saudi Arabia", "Serbia", "Singapore", "Slovakia", "South Korea", "Spain",
    "Sweden", "Switzerland", "Taiwan", "The Netherlands", "Tunisia", "USA",
    "United Arab Emirates", "United Kingdom", "Uruguay", "Uzbekistan",
    "Vietnam",
]

# 50 states + DC. The corpus only ever showed 27 of them; a table that stops at
# what the corpus happened to contain is a hardcode, not a rule.
ALL_US_STATE_CODES = [
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID",
    "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS",
    "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK",
    "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV",
    "WI", "WY", "DC",
]

# cities (and one province) that appear in corpus locations. A city may never be
# a lookup key: the rule is "country code", not "place I have seen before".
CITY_NAMES = [
    "Arlington", "Amsterdam", "Austin", "Berlin", "Boston", "Dubai",
    "Green Bay", "Gurugram", "Leuven", "London", "Mannheim", "Mountain View",
    "New York City", "Ontario", "Paris", "San Francisco", "Seoul", "Toronto",
    "Zurich",
]


def scope_of(location: str, remote: bool = True) -> str | None:
    """Scope of a synthetic record. Only `remote` and `location` are read."""
    return remote_scope({"remote": remote, "location": location})


def fixture_records() -> list[dict]:
    """The frozen fixtures, parsed and deduped exactly as the pipeline does."""
    texts = {m.NAME: (FIXTURES / m.FIXTURE).read_text(encoding="utf-8")
             for m in fetch.SOURCES}
    per = fetch.parse_all(texts, FROZEN_AT)
    flat = [job for _, rows in per for job in rows]
    deduped, _ = fetch.dedupe(flat)
    return deduped


def corpus_records() -> list[dict]:
    return json.loads((HERE.parent / "data" / "jobs.json").read_text(encoding="utf-8"))


class NotRemoteHasNoScope(unittest.TestCase):
    def test_non_remote_record_returns_none(self):
        """None, not "global" and not "": an on-site job has no remote scope."""
        self.assertIsNone(scope_of("Boston, MA", remote=False))

    def test_non_remote_returns_none_even_when_location_looks_remote(self):
        """The boolean rules. A stale string may not resurrect a scope."""
        self.assertIsNone(scope_of("Remote - USA", remote=False))

    def test_every_non_remote_corpus_record_has_no_scope(self):
        for job in corpus_records():
            if not job["remote"]:
                self.assertIsNone(remote_scope(job), job["location"])


class PlainRemoteIsGlobal(unittest.TestCase):
    def test_bare_remote_is_global(self):
        self.assertEqual(scope_of("Remote"), "global")

    def test_bare_remote_is_case_and_space_insensitive(self):
        for text in ("remote", "REMOTE", "  Remote  "):
            self.assertEqual(scope_of(text), "global", text)


class CountryResolution(unittest.TestCase):
    def test_corpus_shapes_resolve(self):
        cases = {
            "Remote - USA": "country:US",
            "Remote - Ontario, Canada": "country:CA",
            "Remote - Berlin, Germany": "country:DE",
            "Remote - Mannheim, Germany": "country:DE",
            "Remote - Gurugram, India": "country:IN",
            "Remote - Leuven, Belgium": "country:BE",
            "Remote - New York City, NY": "country:US",
            "Remote - Mountain View, CA": "country:US",
            "Remote - Green Bay, WI": "country:US",
        }
        for location, expected in cases.items():
            self.assertEqual(scope_of(location), expected, location)

    def test_all_47_measured_country_names_resolve(self):
        """Anti-hardcode: the table answers for every name the corpus showed."""
        for name in CORPUS_COUNTRY_NAMES:
            scope = scope_of(f"Remote - {name}")
            self.assertRegex(scope or "", r"^country:[A-Z]{2}$", name)

    def test_all_51_us_state_codes_resolve_to_us(self):
        """Anti-hardcode: 50 states + DC, not the 27 the corpus happened to hold."""
        for code in ALL_US_STATE_CODES:
            self.assertEqual(scope_of(f"Remote - Springfield, {code}"),
                             "country:US", code)

    def test_countries_never_seen_as_remote_in_the_corpus_resolve(self):
        """The rule generalises; it was not fitted to the 5 remote countries."""
        cases = {
            "Remote - Zurich, Switzerland": "country:CH",
            "Remote - Singapore": "country:SG",
            "Remote - London, United Kingdom": "country:GB",
            "Remote - Amsterdam, The Netherlands": "country:NL",
            "Remote - Seoul, South Korea": "country:KR",
            "Remote - Dubai, United Arab Emirates": "country:AE",
        }
        for location, expected in cases.items():
            self.assertEqual(scope_of(location), expected, location)

    def test_codes_are_uppercase_iso_alpha_2(self):
        for code in COUNTRY_CODES.values():
            self.assertRegex(code, r"^[A-Z]{2}$", code)


class TablesAreRulesNotSamples(unittest.TestCase):
    def test_country_table_covers_every_measured_name(self):
        missing = [n for n in CORPUS_COUNTRY_NAMES
                   if n.lower() not in COUNTRY_CODES]
        self.assertEqual(missing, [])

    def test_us_table_holds_all_51_codes(self):
        self.assertEqual(sorted(US_STATE_CODES), sorted(ALL_US_STATE_CODES))
        self.assertEqual(len(US_STATE_CODES), 51)

    def test_no_city_is_a_key_in_either_table(self):
        for city in CITY_NAMES:
            self.assertNotIn(city.lower(), COUNTRY_CODES, city)
            self.assertNotIn(city.upper(), US_STATE_CODES, city)

    def test_latam_is_a_region_and_is_not_a_country_key(self):
        for region in ("latam", "emea", "apac", "europe"):
            self.assertNotIn(region, COUNTRY_CODES, region)


class UnresolvedIsUnknown(unittest.TestCase):
    """The corpus has zero unknowns, so only synthetic input proves this path."""

    SYNTHETIC = [
        "Remote - LATAM",
        "Remote - EMEA",
        "Remote - Anywhere",
        "Remote - ",
        "Remote - Wakanda",
    ]

    def test_unresolvable_locations_are_unknown(self):
        for location in self.SYNTHETIC:
            self.assertEqual(scope_of(location), "unknown", location)

    def test_unresolvable_locations_are_never_global(self):
        """"Anywhere" reads like global. Reading like it is not knowing it."""
        for location in self.SYNTHETIC:
            self.assertNotEqual(scope_of(location), "global", location)

    def test_unknown_is_not_none(self):
        """None means "not remote". Unknown means "remote, scope unread"."""
        for location in self.SYNTHETIC:
            self.assertIsNotNone(scope_of(location), location)


class PlusNSuffix(unittest.TestCase):
    """`+3` means "3 more locations". The first written place owns the scope."""

    def test_plus_n_does_not_change_the_scope(self):
        cases = {
            "Remote - USA +1": "country:US",
            "Remote - Boston, MA +3": "country:US",
            "Remote - Hong Kong +2": "country:HK",
        }
        for location, expected in cases.items():
            self.assertEqual(scope_of(location), expected, location)

    def test_plus_n_matches_the_bare_form(self):
        for bare, suffixed in (("Remote - USA", "Remote - USA +1"),
                               ("Remote - Hong Kong", "Remote - Hong Kong +2")):
            self.assertEqual(scope_of(suffixed), scope_of(bare), suffixed)


class Census(unittest.TestCase):
    """Exact counts come off the FROZEN fixtures; the live corpus gets shapes.

    The live census used to be pinned here as
    `{global: 9, country:US: 14, country:CA: 2, country:DE: 2, country:IN: 1}`.
    The cron rewrites engine/data/jobs.json every morning and the workflow runs
    this suite before it mails, so that assertion was a scheduled red: the first
    real fetch would have failed the job and killed the mail. The property it
    was really defending -- every remote listing gets a readable scope, and the
    census adds up -- is below, and survives the corpus changing.
    """

    def test_shipped_corpus_census_keys_are_well_formed(self):
        census = scope_census(corpus_records())
        for scope, count in census.items():
            self.assertRegex(scope, r"^(global|unknown|country:[A-Z]{2})$", scope)
            self.assertGreaterEqual(count, 0, scope)

    def test_every_remote_shipped_record_gets_a_scope(self):
        """Not "most". A remote listing with no scope is an unreadable record.

        Deliberately NOT "at least one global listing": a morning where nothing
        on earth is globally remote is a legitimate corpus, and match.py already
        exits 1 and names the dead end for it. Asserting a floor on live data is
        the same mistake as asserting a count on it.
        """
        for job in corpus_records():
            if job["remote"]:
                self.assertIsNotNone(remote_scope(job), job["location"])

    def test_frozen_fixtures_census_is_exact(self):
        self.assertEqual(scope_census(fixture_records()), {
            "global": 3,
            "country:US": 14,
            "country:CA": 1,
            "country:BE": 1,
            "country:DE": 1,
            "country:HK": 1,
            "unknown": 0,
        })

    def test_census_total_equals_the_remote_count(self):
        for jobs in (corpus_records(), fixture_records()):
            self.assertEqual(sum(scope_census(jobs).values()),
                             sum(1 for j in jobs if j["remote"]))

    def test_census_always_names_unknown_even_at_zero(self):
        """A silent default is how "remote" broke in the first place."""
        self.assertIn("unknown", scope_census(corpus_records()))
        self.assertIn("unknown", scope_census([]))

    def test_census_counts_synthetic_unknowns(self):
        jobs = [{"remote": True, "location": loc}
                for loc in ("Remote", "Remote - LATAM", "Remote - USA")]
        jobs.append({"remote": False, "location": "Boston, MA"})
        self.assertEqual(scope_census(jobs),
                         {"global": 1, "country:US": 1, "unknown": 1})


class DerivedNotStored(unittest.TestCase):
    def test_schema_has_no_scope_field(self):
        self.assertNotIn("remote_scope", FIELDS)
        self.assertEqual(len(FIELDS), 13)

    def test_no_corpus_record_carries_a_scope_field(self):
        for job in corpus_records():
            self.assertEqual(list(job), FIELDS)

    def test_remote_scope_does_not_mutate_its_input(self):
        job = {"remote": True, "location": "Remote - USA"}
        before = dict(job)
        remote_scope(job)
        self.assertEqual(job, before)


if __name__ == "__main__":
    unittest.main()
