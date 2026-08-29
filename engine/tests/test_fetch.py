#!/usr/bin/env python3
"""Tests for the fetch pipeline, the listing ledger, and the death gate.

Every test here runs off FROZEN fixtures in tests/fixtures/. No test may open a
socket: setUpModule replaces socket.socket with a raiser, so a test that reaches
for the network fails instead of passing on live data.

Run: python3 -m unittest discover engine/tests -v
"""
import importlib.util
import io
import json
import os
import shutil
import socket
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

HERE = Path(__file__).parent
FIXTURES = HERE / "fixtures"
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE.parent))

import fetch  # noqa: E402
import send_mail  # noqa: E402

sys.path.insert(0, str(ROOT / "tools"))
import measure  # noqa: E402

FROZEN = datetime(2026, 8, 30, 9, 0, 0, tzinfo=timezone.utc)
DAY1, DAY2, DAY3 = "2026-08-01", "2026-08-02", "2026-08-03"

# A real listing from the frozen corpus that WOULD be mailed if it were alive.
# It used to be TikTok's "AI Infra Engineer Intern", San Jose CA. profile.json
# now declares `relocation: false` / `home_country: TR`, so an onsite-US listing
# is excluded before scoring (onsite_abroad) and proves nothing about the death
# gate: it stays out of the mail whether it is alive or dead, and the "does
# carry it while alive" half of the mutation goes vacuous. The victim has to be
# a listing this profile can actually take -- globally remote, and scoring at or
# above send_mail's --min-score default of 5.
VICTIM_COMPANY = "Astreya"
VICTIM_POSITION = "AI Infrastructure DC Design Intern"
VICTIM_KEY = f"{VICTIM_COMPANY.lower()}|{VICTIM_POSITION.lower()}"

_REAL_SOCKET = socket.socket


def _no_network(*args, **kwargs):
    raise AssertionError("a test opened a socket; these tests must be hermetic")


def setUpModule():
    socket.socket = _no_network


def tearDownModule():
    socket.socket = _REAL_SOCKET


def fixture_texts() -> dict[str, str]:
    return {m.NAME: (FIXTURES / m.FIXTURE).read_text(encoding="utf-8")
            for m in fetch.SOURCES}


def frozen_records() -> list[dict]:
    """Today's deduped records, straight off the frozen fixtures."""
    per = fetch.parse_all(fixture_texts(), FROZEN.isoformat(timespec="seconds"))
    flat = [job for _, rows in per for job in rows]
    deduped, _ = fetch.dedupe(flat)
    return deduped


def fake_urlopen(by_url: dict[str, str]):
    """urlopen stand-in that serves frozen text, so no socket is ever needed."""
    class Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            self.close()
            return False

    def opener(url, *a, **kw):
        return Resp(by_url[url].encode("utf-8"))
    return opener


class Fixtures(unittest.TestCase):
    def test_fixtures_are_frozen_on_disk(self):
        """The tests read markdown from disk, never from GitHub."""
        for m in fetch.SOURCES:
            path = FIXTURES / m.FIXTURE
            self.assertTrue(path.exists(), path)
            self.assertIn("| Company |", path.read_text(encoding="utf-8"))

    def test_network_is_blocked_inside_tests(self):
        with self.assertRaises(AssertionError):
            socket.socket()
        with self.assertRaises(Exception):
            fetch.fetch_texts(timeout=1)


class Replay(unittest.TestCase):
    """The new engine/fetch/ line must reproduce the old line byte for byte."""

    def legacy_bytes(self, texts: dict[str, str]) -> bytes:
        tmp = Path(tempfile.mkdtemp())
        legacy_path = tmp / "legacy_fetch.py"
        shutil.copy(FIXTURES / "legacy_fetch_speedyapply.py", legacy_path)
        spec = importlib.util.spec_from_file_location("legacy_fetch", legacy_path)
        legacy = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(legacy)

        by_url = {url: texts[name] for name, url in legacy.SOURCES}

        class FakeDT:
            @staticmethod
            def now(tz=None):
                return FROZEN

        with mock.patch("urllib.request.urlopen", fake_urlopen(by_url)), \
                mock.patch.object(legacy, "datetime", FakeDT), \
                redirect_stdout(io.StringIO()):
            legacy.main()
        return (tmp / "data" / "jobs.json").read_bytes()

    def new_bytes(self, texts: dict[str, str]) -> bytes:
        tmp = Path(tempfile.mkdtemp()) / "data"
        fetch.run(texts, tmp, FROZEN, verbose=False)
        return (tmp / "jobs.json").read_bytes()

    def test_replay_is_byte_identical(self):
        texts = fixture_texts()
        self.assertEqual(self.new_bytes(texts), self.legacy_bytes(texts))

    def test_replay_dedupe_order_is_identical(self):
        """Byte equality already implies order, but name the property."""
        texts = fixture_texts()
        old = json.loads(self.legacy_bytes(texts))
        new = json.loads(self.new_bytes(texts))
        self.assertEqual([(j["company"], j["position"], j["source"]) for j in new],
                         [(j["company"], j["position"], j["source"]) for j in old])


class CrossSourceDedupe(unittest.TestCase):
    def test_listing_in_both_sources_appears_once_owned_by_first_source(self):
        per = fetch.parse_all(fixture_texts(), FROZEN.isoformat(timespec="seconds"))
        keys = [{fetch.job_key(j) for j in rows} for _, rows in per]
        overlap = keys[0] & keys[1]
        self.assertGreater(len(overlap), 0, "fixtures carry no cross-source duplicate")
        records = frozen_records()
        for key in overlap:
            hits = [j for j in records if fetch.job_key(j) == key]
            self.assertEqual(len(hits), 1, key)
            self.assertEqual(hits[0]["source"], fetch.SOURCES[0].NAME, key)


class EmptyFetchIsAFailure(unittest.TestCase):
    def sandbox(self) -> Path:
        """A data dir that already holds yesterday's jobs.json and ledger."""
        tmp = Path(tempfile.mkdtemp()) / "data"
        tmp.mkdir(parents=True)
        (tmp / "jobs.json").write_text('[{"marker": "untouched"}]', encoding="utf-8")
        (tmp / "jobs_seen.json").write_text(json.dumps(
            {"marker|untouched": {"first_seen": DAY1, "last_seen": DAY1, "alive": True}}),
            encoding="utf-8")
        return tmp

    def run_main(self, texts: dict[str, str], data: Path) -> int:
        by_url = {m.URL: texts[m.NAME] for m in fetch.SOURCES}
        with mock.patch("urllib.request.urlopen", fake_urlopen(by_url)), \
                mock.patch.object(fetch, "DATA", data), \
                redirect_stdout(io.StringIO()):
            return fetch.main()

    def test_total_zero_rows_exits_nonzero_and_writes_nothing(self):
        data = self.sandbox()
        before = {p.name: p.read_bytes() for p in data.iterdir()}
        code = self.run_main({m.NAME: "" for m in fetch.SOURCES}, data)
        self.assertNotEqual(code, 0)
        self.assertEqual({p.name: p.read_bytes() for p in data.iterdir()}, before)

    def test_single_source_zero_rows_exits_nonzero_and_writes_nothing(self):
        data = self.sandbox()
        before = {p.name: p.read_bytes() for p in data.iterdir()}
        texts = fixture_texts()
        texts[fetch.SOURCES[1].NAME] = "# the source changed its format\n"
        code = self.run_main(texts, data)
        self.assertNotEqual(code, 0)
        self.assertEqual({p.name: p.read_bytes() for p in data.iterdir()}, before)

    def test_healthy_fetch_exits_zero_and_writes(self):
        data = self.sandbox()
        code = self.run_main(fixture_texts(), data)
        self.assertEqual(code, 0)
        self.assertGreater(len(json.loads((data / "jobs.json").read_text())), 400)
        self.assertTrue((data / "jobs_seen.json").exists())


class Ledger(unittest.TestCase):
    def test_first_seen_and_last_seen_are_recorded(self):
        records = frozen_records()
        ledger = fetch.update_ledger({}, records, DAY1)
        self.assertEqual(len(ledger), len(records))
        entry = ledger[VICTIM_KEY]
        self.assertEqual(entry, {"first_seen": DAY1, "last_seen": DAY1, "alive": True})

    def test_missing_listing_dies_and_keeps_its_last_seen(self):
        records = frozen_records()
        day1 = fetch.update_ledger({}, records, DAY1)
        survivors = [j for j in records if fetch.job_key(j) != VICTIM_KEY]

        day2 = fetch.update_ledger(day1, survivors, DAY2)
        self.assertFalse(day2[VICTIM_KEY]["alive"])
        self.assertEqual(day2[VICTIM_KEY]["last_seen"], DAY1)
        self.assertEqual(day2[VICTIM_KEY]["first_seen"], DAY1)

        day3 = fetch.update_ledger(day2, survivors, DAY3)
        self.assertEqual(day3[VICTIM_KEY]["last_seen"], DAY1,
                         "a dead listing's last_seen must never move")
        self.assertEqual(day3["cotiviti|intern ai engineer - early-career - "
                              "llm context & data layer - healthcare"]["last_seen"], DAY3)

    def test_returning_listing_revives_without_losing_first_seen(self):
        records = frozen_records()
        day1 = fetch.update_ledger({}, records, DAY1)
        day2 = fetch.update_ledger(
            day1, [j for j in records if fetch.job_key(j) != VICTIM_KEY], DAY2)
        day3 = fetch.update_ledger(day2, records, DAY3)
        self.assertTrue(day3[VICTIM_KEY]["alive"])
        self.assertEqual(day3[VICTIM_KEY]["first_seen"], DAY1)
        self.assertEqual(day3[VICTIM_KEY]["last_seen"], DAY3)

    def test_ledger_survives_a_json_round_trip(self):
        ledger = fetch.update_ledger({}, frozen_records(), DAY1)
        self.assertEqual(json.loads(fetch.dumps_ledger(ledger)), ledger)


def mutated_ledger(records: list[dict]) -> dict:
    """Ledger where ONE listing has been hand-marked as no longer open."""
    ledger = fetch.update_ledger({}, records, DAY1)
    ledger[VICTIM_KEY]["alive"] = False
    return ledger


def mail_body(data_dir: Path) -> str:
    """Run send_mail --dry-run against a sandbox data dir, return the mail text."""
    seen = []
    real_compose = send_mail.compose

    def spy(*a, **kw):
        body = real_compose(*a, **kw)
        seen.append(body)
        return body

    argv = ["send_mail.py", "--dry-run"]
    with mock.patch.object(send_mail, "DATA", data_dir), \
            mock.patch.object(send_mail, "STATE_FILE", data_dir / "mail_state.json"), \
            mock.patch.object(send_mail, "compose", spy), \
            mock.patch.dict(os.environ, {}, clear=True), \
            mock.patch.object(sys, "argv", argv), \
            redirect_stdout(io.StringIO()) as out:
        send_mail.main()
    return "\n".join(seen) + "\n" + out.getvalue()


class DeathGate(unittest.TestCase):
    """MUTATION tests: a listing marked dead must be structurally unreachable."""

    @classmethod
    def setUpClass(cls):
        cls.records = frozen_records()
        cls.ledger = mutated_ledger(cls.records)

    def sandbox(self, live: list[dict]) -> Path:
        data = Path(tempfile.mkdtemp()) / "data"
        data.mkdir(parents=True)
        (data / "jobs.json").write_text(fetch.dumps_jobs(live), encoding="utf-8")
        (data / "mail_state.json").write_text("{}", encoding="utf-8")
        return data

    def check_data(self, live: list[dict]):
        """MUTATION 2: the dead listing is absent, and jobs.json == alive set."""
        keys = [fetch.job_key(j) for j in live]
        assert VICTIM_KEY not in keys, "dead listing entered jobs.json"
        alive = {k for k, v in self.ledger.items() if v["alive"]}
        assert set(keys) == alive, "jobs.json keys != ledger alive=true keys"

    def check_mail(self, live: list[dict]):
        """MUTATION 1: the dead listing appears zero times in the mail."""
        body = mail_body(self.sandbox(live))
        assert body.count(VICTIM_POSITION) == 0, "dead listing reached the mail"

    def test_mail_never_carries_a_dead_listing(self):
        self.check_mail(fetch.build_jobs(self.records, self.ledger))

    def test_mail_does_carry_the_same_listing_while_it_is_alive(self):
        """Without this, MUTATION 1 would pass vacuously."""
        alive_ledger = fetch.update_ledger({}, self.records, DAY1)
        body = mail_body(self.sandbox(fetch.build_jobs(self.records, alive_ledger)))
        self.assertGreaterEqual(body.count(VICTIM_POSITION), 1)

    def test_jobs_json_is_exactly_the_alive_set(self):
        self.check_data(fetch.build_jobs(self.records, self.ledger))

    def test_gate_removal_breaks_both_mutations(self):
        """MUTATION 3: delete the alive filter and the two checks above must fail."""
        def gateless(jobs, ledger):
            return list(jobs)

        live = gateless(self.records, self.ledger)
        with self.assertRaises(AssertionError):
            self.check_data(live)
        with self.assertRaises(AssertionError):
            self.check_mail(live)


class FrozenCorpusCounts(unittest.TestCase):
    """Exact counts, measured off the FROZEN fixtures. These cannot drift.

    They used to be measured off engine/data/jobs.json: 453 records, 41
    duplicates removed, 42 countries. The cron rewrites that file every morning
    and daily.yml runs this suite BEFORE send_mail.py, so the first real fetch
    would have turned all three red, failed the job, and stopped the mail. The
    fixtures are the input that is allowed to carry a number.
    """

    @classmethod
    def setUpClass(cls):
        cls.records = frozen_records()

    def test_record_count(self):
        self.assertEqual(len(self.records), 599)

    def test_dedupe_count(self):
        flat = [job for _, rows in
                fetch.parse_all(fixture_texts(), FROZEN.isoformat(timespec="seconds"))
                for job in rows]
        _, removed = fetch.dedupe(flat)
        self.assertEqual(removed, 59)
        self.assertEqual(len(flat) - removed, len(self.records))

    def test_country_count(self):
        countries = {measure.country_of(j.get("location")) for j in self.records}
        self.assertEqual(len({c for c in countries if not c.startswith("(")}), 43)


class ShippedCorpusInvariants(unittest.TestCase):
    """The live corpus, checked only for things a new fetch cannot break."""

    @classmethod
    def setUpClass(cls):
        cls.jobs = json.loads((HERE.parent / "data" / "jobs.json").read_text())
        cls.meta = json.loads((HERE.parent / "data" / "fetch_meta.json").read_text())

    def test_corpus_is_not_empty(self):
        """An empty jobs.json is the one corpus shape that IS a failure."""
        self.assertGreater(len(self.jobs), 0)

    def test_dedupe_count_is_never_negative(self):
        self.assertGreaterEqual(self.meta["duplicates_removed"], 0)

    def test_no_listing_is_carried_twice(self):
        keys = [fetch.job_key(j) for j in self.jobs]
        self.assertEqual(len(keys), len(set(keys)))

    def test_every_country_is_read_or_openly_unread(self):
        """`country_of` either names a country or brackets its own ignorance."""
        for job in self.jobs:
            country = measure.country_of(job.get("location"))
            self.assertTrue(country, repr(job.get("location")))

    def test_no_new_field_leaked_into_the_corpus(self):
        for job in self.jobs:
            self.assertEqual(list(job), fetch.common.FIELDS)

    def test_shipped_ledger_matches_the_shipped_corpus(self):
        """D7 on the live data: jobs.json keys == ledger alive=true keys."""
        ledger = json.loads((HERE.parent / "data" / "jobs_seen.json").read_text())
        alive = {k for k, v in ledger.items() if v["alive"]}
        self.assertEqual({fetch.job_key(j) for j in self.jobs}, alive)


if __name__ == "__main__":
    unittest.main()
