#!/usr/bin/env python3
"""Can this profile actually APPLY to what the engine sends it?

`us_work_auth` reads a TITLE for "citizen"/"clearance". Real listings rarely
spell that out, so on the shipped corpus it fires zero times: a rule that
excludes nothing. Meanwhile 133 of the 142 listings the engine sent were
unreachable -- onsite in another country, or remote fenced to one foreign
country.

WHERE THE NUMBERS COME FROM
---------------------------
Every EXACT count in this file is measured against the FROZEN fixtures in
tests/fixtures/, never against engine/data/jobs.json. jobs.json is rewritten by
the cron every morning, and .github/workflows/daily.yml runs this suite BEFORE
it mails: a count pinned to the live corpus turns the first real fetch into a
red suite, a failed job, and a mail that never goes out.

The live corpus is still tested -- in `LiveCorpusInvariants` -- but only with
statements that survive the corpus changing under them: buckets partition the
input, nothing is negative, and every survivor is reachable.

Run: python3 -m unittest discover engine/tests -v
"""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

HERE = Path(__file__).parent
FIXTURES = HERE / "fixtures"
ENGINE = HERE.parent
ROOT = ENGINE.parent
sys.path.insert(0, str(ENGINE))
import fetch  # noqa: E402
import match  # noqa: E402
from fetch.common import COUNTRY_CODES, listing_country, remote_scope  # noqa: E402

PROFILE = json.loads((ROOT / "profile.json").read_text())

FROZEN_AT = "2026-08-30T09:00:00+00:00"


def fixture_jobs() -> list[dict]:
    """The frozen fixtures, parsed and deduped exactly as the pipeline does.

    No socket, no clock: `fetch.parse_all` is pure and `FROZEN_AT` is a literal.
    """
    texts = {m.NAME: (FIXTURES / m.FIXTURE).read_text(encoding="utf-8")
             for m in fetch.SOURCES}
    flat = [job for _, rows in fetch.parse_all(texts, FROZEN_AT) for job in rows]
    deduped, _ = fetch.dedupe(flat)
    return deduped


JOBS = fixture_jobs()
FIXTURE_TOTAL = 599  # measured off the frozen fixtures; moves only if they move

LIVE_JOBS = json.loads((ENGINE / "data" / "jobs.json").read_text())

GEO_BUCKETS = ["onsite_abroad", "remote_scope_country_mismatch",
               "remote_scope_unknown", "location_country_unknown"]
ALL_BUCKETS = ["phd_only", "mba", "us_work_auth", *GEO_BUCKETS, "no_signal"]

# The four listings a US-immobile profile reaches geographically and then drops
# for lack of signal. Named, not counted, because "4 fell out" is a number and
# "THESE four fell out" is a fact: if scoring drifts and a different four start
# failing, a count stays green and this list goes red.
US_NO_SIGNAL = [
    ("TikTok",
     "Data Science Project Intern - TikTok Shop-Supply Chain & Logistics "
     "- 2026 Start - BS/MS"),
    ("Wells Fargo",
     "2027 Quantitative Analytics Summer Internship Risk Analytics and "
     "Decision Sciences - RADS Masters - Early Careers"),
    ("Capital One",
     "Current Master's - Data Science Internship - Summer 2027"),
    ("Susquehanna International Group",
     "Quantitative Research Internship - Master's: Summer 2027"),
]


def profile_with(**constraints) -> dict:
    """The real profile with its constraints overridden. Nothing else moves."""
    out = deepcopy(PROFILE)
    out.setdefault("constraints", {}).update(constraints)
    return out


def run_cli(profile: dict, jobs=None) -> subprocess.CompletedProcess:
    """Drive match.py as a process, so --stats text and exit code are real.

    When `jobs` is given the whole engine is copied into a sandbox, because
    match.py reads data/jobs.json next to itself and the shipped corpus is
    frozen for this phase.
    """
    tmp = Path(tempfile.mkdtemp())
    engine = ENGINE
    if jobs is not None:
        engine = tmp / "engine"
        engine.mkdir()
        shutil.copy(ENGINE / "match.py", engine / "match.py")
        shutil.copytree(ENGINE / "fetch", engine / "fetch")
        (engine / "data").mkdir()
        (engine / "data" / "jobs.json").write_text(json.dumps(jobs))
    path = tmp / "profile.json"
    path.write_text(json.dumps(profile))
    return subprocess.run(
        [sys.executable, str(engine / "match.py"), str(path), "--stats", "--top", "0"],
        capture_output=True, text=True)


def synthetic(locations: list[str]) -> list[dict]:
    """Listings that differ only in where they are."""
    return [
        {"source": "s", "company": f"company {i}", "company_url": None,
         "position": "Agentic AI Infrastructure Intern", "location": loc,
         "remote": "remote" in loc.lower(), "salary": None,
         "link": "https://example.invalid", "link_missing": False, "age": "3d",
         "student_ok": True, "deadline": None, "fetched_at": "2026-08-30"}
        for i, loc in enumerate(locations)
    ]


class FrozenInput(unittest.TestCase):
    """The exact numbers below are only meaningful if the input cannot move."""

    def test_fixture_corpus_size_is_the_number_every_count_is_measured_against(self):
        self.assertEqual(len(JOBS), FIXTURE_TOTAL)

    def test_the_frozen_corpus_is_not_the_live_one(self):
        """Same object would mean the counts below are live-pinned after all."""
        self.assertIsNot(JOBS, LIVE_JOBS)
        self.assertEqual(len(JOBS), FIXTURE_TOTAL)


class Declaration(unittest.TestCase):
    """The rule runs on what the profile SAYS, never on a scraped guess."""

    def test_real_profile_declares_it_cannot_relocate(self):
        self.assertIs(PROFILE["constraints"].get("relocation"), False,
                      "profile.json must declare constraints.relocation: false")

    def test_real_profile_declares_a_two_letter_home_country(self):
        home = PROFILE["constraints"].get("home_country")
        self.assertIsInstance(home, str)
        self.assertRegex(home, r"^[A-Z]{2}$",
                         "home_country must be an ISO 3166-1 alpha-2 code")

    def test_relocation_false_without_home_country_is_a_named_error(self):
        """Half a declaration is not a licence to guess, and not a silent pass."""
        broken = deepcopy(PROFILE)
        broken.setdefault("constraints", {}).pop("home_country", None)
        broken["constraints"]["relocation"] = False
        with self.assertRaises(SystemExit) as caught:
            match.run(broken, JOBS[:1])
        message = str(caught.exception)
        self.assertIn("home_country", message)
        self.assertIn("relocation", message)

    def test_relocation_true_turns_the_rule_off(self):
        self.assertIsNone(match.home_country(profile_with(relocation=True)))

    def test_undeclared_relocation_turns_the_rule_off(self):
        self.assertIsNone(match.home_country({"identity": {"location": "Ankara, Turkey"}}))

    def test_home_country_is_never_read_from_the_identity_string(self):
        """Living in Ankara is not a constraint. Saying you cannot leave is."""
        loose = profile_with(relocation=True, home_country="TR")
        self.assertIsNone(match.home_country(loose))


class ListingCountryRule(unittest.TestCase):
    """`listing_country` reads a country code, or admits it could not."""

    def test_country_name_wins(self):
        self.assertEqual(listing_country("Bengaluru, India"), "IN")
        self.assertEqual(listing_country("Ankara, Turkey"), "TR")

    def test_us_state_code_means_us(self):
        self.assertEqual(listing_country("San Jose, CA"), "US")
        self.assertEqual(listing_country("Washington, DC"), "US")

    def test_plus_n_names_no_place(self):
        self.assertEqual(listing_country("New York, NY +3"), "US")

    def test_unreadable_is_unknown_never_a_guess(self):
        for raw in ["", None, "Remote", "Anywhere", "Bilkent"]:
            self.assertEqual(listing_country(raw), "unknown", repr(raw))

    def test_turkey_is_in_the_country_table(self):
        self.assertEqual(COUNTRY_CODES["turkey"], "TR")


class DamlaProfile(unittest.TestCase):
    """The real profile against the FROZEN corpus. Every number measured."""

    @classmethod
    def setUpClass(cls):
        cls.results, cls.stats = match.run(PROFILE, JOBS)

    def test_matched_is_exactly_three(self):
        self.assertEqual(self.stats["matched"], 3)

    def test_every_survivor_is_globally_remote(self):
        scopes = [remote_scope(r) for r in self.results]
        self.assertEqual(scopes, ["global"] * 3, scopes)

    def test_bucket_census_is_exact(self):
        self.assertEqual({b: self.stats[b] for b in ALL_BUCKETS}, {
            "phd_only": 92,
            "mba": 1,
            "us_work_auth": 0,
            "onsite_abroad": 461,
            "remote_scope_country_mismatch": 17,
            "remote_scope_unknown": 0,
            "location_country_unknown": 25,
            "no_signal": 0,
        })

    def test_buckets_plus_matched_account_for_every_listing(self):
        self.assertEqual(
            sum(self.stats[b] for b in ALL_BUCKETS) + self.stats["matched"],
            FIXTURE_TOTAL)

    def test_the_new_rule_actually_fires(self):
        """us_work_auth excludes 0. A rule worth adding has to beat that."""
        fired = sum(self.stats[b] for b in GEO_BUCKETS)
        self.assertEqual(fired, 503)
        self.assertGreater(fired, self.stats["us_work_auth"])

    def test_us_work_auth_rule_is_still_there_and_still_first(self):
        """The inherited rule keeps its key and keeps running before the geo rule."""
        job = dict(JOBS[0], company="x", location="Remote", remote=True,
                   position="AI Intern - US Citizenship Required")
        _, stats = match.run(PROFILE, [job])
        self.assertEqual(stats["us_work_auth"], 1)
        self.assertEqual(sum(stats[b] for b in GEO_BUCKETS), 0,
                         "a globally-remote listing must die of us_work_auth, not geo")


class CounterProfiles(unittest.TestCase):
    """Move the home country and the answer has to move with it."""

    @classmethod
    def setUpClass(cls):
        cls.us = match.run(profile_with(relocation=False, home_country="US"), JOBS)
        cls.zz = match.run(profile_with(relocation=False, home_country="ZZ"), JOBS)
        cls.free = match.run(profile_with(relocation=True), JOBS)

    def test_us_immobile_profile_reaches_us_work(self):
        # This assertion used to read `matched == 144` against the live corpus,
        # and 144 was a bad derivation: it is the number that SURVIVES the geo
        # elimination (453 - 309), not the number that survives SCORING.
        # `matched` is counted after scoring, and on the live corpus four TikTok
        # "Machine Learning Engineer Intern" listings score to zero and land in
        # `no_signal` -- as they already did BEFORE the geo phase existed
        # (verified by running a9b66ba, the pre-S4 commit, in a git worktree).
        # Correcting a threshold downward is a loosening on its own, so the
        # test was tightened in the same move: `no_signal` is now pinned too,
        # and the listings in it are named one by one below.
        _, stats = self.us
        self.assertEqual(stats["matched"], 210)
        self.assertEqual(stats["onsite_abroad"], 263)
        self.assertEqual(stats["remote_scope_country_mismatch"], 4)

    def test_us_immobile_profile_drops_exactly_four_for_lack_of_signal(self):
        _, stats = self.us
        self.assertEqual(stats["no_signal"], 4)
        self.assertEqual(len(US_NO_SIGNAL), 4)

    def test_the_four_no_signal_listings_are_these_four_by_name(self):
        """A count says "four died". This says WHICH four, and proves it."""
        by_name = {(j["company"], j["position"]): j for j in JOBS}
        victims = []
        for key in US_NO_SIGNAL:
            self.assertIn(key, by_name, key)
            victims.append(by_name[key])

        # each named listing, alone, is exactly one `no_signal` and zero matches
        for job in victims:
            _, one = match.run(profile_with(relocation=False, home_country="US"),
                               [job])
            self.assertEqual(one["no_signal"], 1, job["position"])
            self.assertEqual(one["matched"], 0, job["position"])
            self.assertEqual(sum(one[b] for b in GEO_BUCKETS), 0,
                             f"{job['position']} died of geo, not of no_signal")

        # ...and together they are the WHOLE bucket: nothing else fell in
        _, four = match.run(profile_with(relocation=False, home_country="US"),
                            victims)
        self.assertEqual(four["no_signal"], 4)
        _, whole = self.us
        self.assertEqual(whole["no_signal"], four["no_signal"])

    def test_every_us_survivor_is_global_or_in_the_us(self):
        results, _ = self.us
        for r in results:
            reachable = (remote_scope(r) == "global"
                         or remote_scope(r) == "country:US"
                         or listing_country(r.get("location")) == "US")
            self.assertTrue(reachable, f"{r['company']} / {r.get('location')!r}")

    def test_nonexistent_country_still_gets_the_global_three(self):
        """ZZ is no country: the 3 come from `global`, not from being Turkish."""
        results, stats = self.zz
        self.assertEqual(stats["matched"], 3)
        self.assertEqual([remote_scope(r) for r in results], ["global"] * 3)

    def test_zz_buckets_equal_tr_buckets(self):
        _, tr = match.run(PROFILE, JOBS)
        _, zz = self.zz
        self.assertEqual({b: tr[b] for b in ALL_BUCKETS},
                         {b: zz[b] for b in ALL_BUCKETS})

    def test_portable_profile_keeps_the_old_reach(self):
        _, stats = self.free
        self.assertEqual(stats["matched"], 221)
        for bucket in GEO_BUCKETS:
            self.assertEqual(stats[bucket], 0, bucket)

    def test_home_country_scores_location_fits(self):
        jobs = synthetic(["Ankara, Turkey"])
        results, _ = match.run(PROFILE, jobs)
        self.assertEqual(len(results), 1)
        self.assertIn("location fits (Ankara, Turkey)", results[0]["reasons"])


class LiveCorpusInvariants(unittest.TestCase):
    """The live, cron-rewritten corpus. Properties only -- never a count.

    Tomorrow morning the cron replaces engine/data/jobs.json and this suite runs
    before the mailer. Everything here has to stay green through that.
    """

    @classmethod
    def setUpClass(cls):
        cls.results, cls.stats = match.run(PROFILE, LIVE_JOBS)

    def test_buckets_and_matched_partition_the_deduped_input(self):
        self.assertEqual(
            sum(self.stats[b] for b in ALL_BUCKETS) + self.stats["matched"],
            self.stats["considered"])

    def test_dedupe_accounts_for_every_raw_record(self):
        self.assertEqual(self.stats["considered"] + self.stats["duplicates_removed"],
                         len(LIVE_JOBS))
        self.assertEqual(self.stats["total_raw"], len(LIVE_JOBS))

    def test_no_bucket_is_negative(self):
        for bucket in ALL_BUCKETS:
            self.assertGreaterEqual(self.stats[bucket], 0, bucket)

    def test_matched_is_not_negative(self):
        self.assertGreaterEqual(self.stats["matched"], 0)

    def test_every_single_survivor_is_reachable_from_home(self):
        """100%, not "most": the mail may not carry one unreachable listing."""
        home = PROFILE["constraints"]["home_country"]
        unreachable = [
            (r["company"], r.get("location"))
            for r in self.results
            if not (remote_scope(r) == "global"
                    or listing_country(r.get("location")) == home)
        ]
        self.assertEqual(unreachable, [])

    def test_the_geo_rule_is_on_for_the_shipped_profile(self):
        self.assertEqual(self.stats["geo_rule"], "on")
        self.assertEqual(self.stats["home_country"],
                         PROFILE["constraints"]["home_country"])


class StatsOutput(unittest.TestCase):
    """--stats has to report the rule and every bucket, zeros included."""

    def test_stats_names_every_bucket_even_at_zero(self):
        out = run_cli(PROFILE, jobs=JOBS).stdout
        for bucket in ALL_BUCKETS:
            self.assertIn(f"{bucket} ", out, bucket)
        self.assertIn("us_work_auth 0", out)
        self.assertIn("remote_scope_unknown 0", out)

    def test_stats_reports_the_rule_is_on_and_says_where_home_is(self):
        out = run_cli(PROFILE, jobs=JOBS).stdout
        self.assertIn("geo rule: on, home TR", out)
        self.assertIn("matched: 3", out)

    def test_stats_reports_the_rule_is_off_for_a_portable_profile(self):
        out = run_cli(profile_with(relocation=True), jobs=JOBS).stdout
        self.assertIn("geo rule: off, profile declares no relocation constraint", out)
        self.assertIn("matched: 221", out)


class DeadEnd(unittest.TestCase):
    """Reaching nobody is a failure, and it has to say so out loud."""

    JOBS = None

    @classmethod
    def setUpClass(cls):
        # no globally-remote listing anywhere: this profile can reach none of them
        cls.JOBS = synthetic(["San Jose, CA", "Remote - USA", "Bengaluru, India",
                              "Remote - Germany", "Somewhere", "New York, NY"])

    def test_nothing_matches(self):
        results, stats = match.run(PROFILE, self.JOBS)
        self.assertEqual(results, [])
        self.assertEqual(stats["matched"], 0)

    def test_cli_exits_one_and_names_the_largest_bucket(self):
        proc = run_cli(PROFILE, jobs=self.JOBS)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("dead end", proc.stdout)
        self.assertIn("onsite_abroad (3)", proc.stdout)

    def test_a_reachable_corpus_still_exits_zero(self):
        self.assertEqual(run_cli(PROFILE, jobs=JOBS).returncode, 0)


if __name__ == "__main__":
    unittest.main()
