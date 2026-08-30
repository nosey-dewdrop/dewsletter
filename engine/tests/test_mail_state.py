#!/usr/bin/env python3
"""S7 -- "the same listing never arrives twice".

Four things are nailed here, all hermetic (no socket, no SMTP, no Supabase, no
production files written):

1. CRASH DURABILITY. A run that dies halfway must leave every already-sent
   subscriber recorded on disk. Ten subscribers, the fifth send raises: the
   first four are persisted, and a re-run mails them nothing.
2. ATOMICITY. A write that dies mid-serialisation must leave mail_state.json as
   valid JSON with the PREVIOUS content, so load_state() cannot die on a
   truncated file. No temp file is left behind either.
3. PROFILE EDITS DO NOT UN-SEND. Rescoring after an interests change keeps
   sent_keys lossless -- 22 keys in, 22 keys out.
4. IDENTITY NAIL. job_key and sub_id derivation are pinned against the LIVE
   engine/data/mail_state.json (22 keys, subscriber bd235c29a8fc) and against
   literal hashes. Later phases cannot quietly redefine either without turning
   this file red -- redefining them means mass double-mail.

Run: python3 -m unittest discover engine/tests -v
"""
import io
import json
import os
import shutil
import socket
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

HERE = Path(__file__).parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE.parent))

import send_mail  # noqa: E402

LIVE_DATA = HERE.parent / "data"
LIVE_STATE = LIVE_DATA / "mail_state.json"
LIVE_JOBS = LIVE_DATA / "jobs.json"

# The one real subscriber in the live state file, and the count of listings
# already mailed to them. Both are literals on purpose: they are the anchor the
# identity of job_key/sub_id is measured against.
LIVE_SUB_ID = "bd235c29a8fc"
LIVE_KEY_COUNT = 22

# Measured against engine/data/jobs.json: this profile is eligible for exactly
# 12 listings at send_mail's default --min-score 5.
SIM_INTERESTS = ["machine learning"]
KEYS_PER_SUB = 12
SIM_SUBS = 10
CRASH_AT = 5  # the 5th send_message raises

_REAL_SOCKET = socket.socket


def _no_network(*args, **kwargs):
    raise AssertionError("a test opened a socket; these tests must be hermetic")


def setUpModule():
    socket.socket = _no_network


def tearDownModule():
    socket.socket = _REAL_SOCKET


def live_state() -> dict:
    return json.loads(LIVE_STATE.read_text())


class FakeSMTP:
    """Stand-in for smtplib.SMTP_SSL. Counts sends, optionally dies on the Nth."""

    instances: list["FakeSMTP"] = []
    sent: list[str] = []
    die_on: int | None = None

    def __init__(self, *args, **kwargs):
        FakeSMTP.instances.append(self)
        self.quit_calls = 0

    @classmethod
    def reset(cls, die_on=None):
        cls.instances = []
        cls.sent = []
        cls.die_on = die_on

    def login(self, user, password):
        return None

    def send_message(self, msg):
        if FakeSMTP.die_on is not None and len(FakeSMTP.sent) + 1 == FakeSMTP.die_on:
            raise RuntimeError(f"smtp died on send #{FakeSMTP.die_on}")
        FakeSMTP.sent.append(msg["To"])

    def quit(self):
        self.quit_calls += 1


def subscriber(email: str, interests=None) -> dict:
    return {"email": email, "name": email.split("@")[0], "level": "bs",
            "interests": list(interests if interests is not None else SIM_INTERESTS),
            "location": "", "unsubscribe_token": None}


def sandbox() -> Path:
    """A temp data dir carrying a COPY of the real jobs.json. Never the real dir."""
    data = Path(tempfile.mkdtemp(prefix="s7-")) / "data"
    data.mkdir(parents=True)
    shutil.copy(LIVE_JOBS, data / "jobs.json")
    return data


def run_send_mail(data: Path, subs: list[dict], die_on=None) -> str:
    """Run send_mail.main() end to end on the real send path (no --dry-run)."""
    FakeSMTP.reset(die_on=die_on)
    env = {"SUPABASE_SERVICE_KEY": "x", "SMTP_USER": "a@b.c", "SMTP_PASS": "p"}
    with mock.patch.object(send_mail, "DATA", data), \
            mock.patch.object(send_mail, "STATE_FILE", data / "mail_state.json"), \
            mock.patch.object(send_mail, "fetch_subscribers", lambda k: subs), \
            mock.patch.object(send_mail.smtplib, "SMTP_SSL", FakeSMTP), \
            mock.patch.dict(os.environ, env, clear=True), \
            mock.patch.object(sys, "argv", ["send_mail.py"]), \
            redirect_stdout(io.StringIO()) as out:
        send_mail.main()
    return out.getvalue()


def read_state(data: Path) -> dict:
    p = data / "mail_state.json"
    return json.loads(p.read_text()) if p.exists() else {}


def sid(email: str) -> str:
    """sub_id as send_mail derives it -- proven behaviourally in IdentityNail."""
    import hashlib
    return hashlib.sha1(email.encode()).hexdigest()[:12]


class CrashDurability(unittest.TestCase):
    """A run that dies must not forget what it already sent."""

    def setUp(self):
        self.data = sandbox()
        self.subs = [subscriber(f"s{i}@example.test") for i in range(SIM_SUBS)]

    def test_crash_on_fifth_send_persists_the_first_four(self):
        with self.assertRaises(RuntimeError):
            run_send_mail(self.data, self.subs, die_on=CRASH_AT)

        state = read_state(self.data)
        self.assertEqual(len(FakeSMTP.sent), CRASH_AT - 1, "wrong number of sends")
        self.assertEqual(len(state), CRASH_AT - 1,
                         "sends happened but subscribers are missing from disk")
        expected = {sid(s["email"]) for s in self.subs[:CRASH_AT - 1]}
        self.assertEqual(set(state), expected)
        total = sum(len(v["sent_keys"]) for v in state.values())
        self.assertEqual(total, (CRASH_AT - 1) * KEYS_PER_SUB,
                         f"expected {(CRASH_AT - 1) * KEYS_PER_SUB} keys on disk")

    def test_rerun_after_crash_sends_zero_to_the_first_four(self):
        with self.assertRaises(RuntimeError):
            run_send_mail(self.data, self.subs, die_on=CRASH_AT)
        already = {s["email"] for s in self.subs[:CRASH_AT - 1]}

        out = run_send_mail(self.data, self.subs)  # clean re-run, nothing dies

        self.assertEqual(len(FakeSMTP.sent), SIM_SUBS - (CRASH_AT - 1),
                         "re-run did not mail exactly the untouched subscribers")
        self.assertEqual(already & set(FakeSMTP.sent), set(),
                         "a subscriber who already had mail got it a SECOND time")
        self.assertEqual(set(FakeSMTP.sent),
                         {s["email"] for s in self.subs[CRASH_AT - 1:]})
        self.assertIn("done: 6 mail(s) sent", out)

    def test_third_run_sends_nothing_at_all(self):
        run_send_mail(self.data, self.subs)
        self.assertEqual(len(FakeSMTP.sent), SIM_SUBS)
        run_send_mail(self.data, self.subs)
        self.assertEqual(FakeSMTP.sent, [], "a fully mailed corpus was mailed again")

    def test_state_is_on_disk_before_the_next_subscriber_is_touched(self):
        """Fail on send #2 and the FIRST subscriber must already be durable."""
        with self.assertRaises(RuntimeError):
            run_send_mail(self.data, self.subs, die_on=2)
        state = read_state(self.data)
        self.assertEqual(set(state), {sid(self.subs[0]["email"])})
        self.assertEqual(len(state[sid(self.subs[0]["email"])]["sent_keys"]),
                         KEYS_PER_SUB)


class Atomicity(unittest.TestCase):
    """A half-finished write must never be visible to load_state()."""

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="s7-atomic-"))
        self.state_file = self.dir / "mail_state.json"
        self.previous = {"aaaaaaaaaaaa": {"sent_keys": ["ffff0000ffff0000"],
                                          "last_sent": "2026-08-01"}}
        self.state_file.write_text(json.dumps(self.previous, indent=1))

    def test_exception_mid_dump_leaves_previous_valid_json(self):
        def half_written_dump(obj, fh, **kw):
            fh.write('{"corrupt": ["aaaa", "bb')  # truncated on purpose
            fh.flush()
            raise RuntimeError("crashed mid json.dump")

        with mock.patch.object(send_mail, "STATE_FILE", self.state_file), \
                mock.patch.object(send_mail.json, "dump", half_written_dump):
            with self.assertRaises(RuntimeError):
                send_mail.save_state({"bbbbbbbbbbbb": {"sent_keys": []}})

            self.assertEqual(json.loads(self.state_file.read_text()), self.previous,
                             "a partial write reached mail_state.json")
            self.assertEqual(send_mail.load_state(), self.previous,
                             "load_state() saw a corrupted file")

    def test_no_temp_file_survives_a_failed_write(self):
        def boom(obj, fh, **kw):
            fh.write("{")
            raise RuntimeError("boom")

        with mock.patch.object(send_mail, "STATE_FILE", self.state_file), \
                mock.patch.object(send_mail.json, "dump", boom):
            with self.assertRaises(RuntimeError):
                send_mail.save_state({})
        leftovers = [p.name for p in self.dir.iterdir() if p.name != "mail_state.json"]
        self.assertEqual(leftovers, [], f"temp files left behind: {leftovers}")

    def test_successful_write_is_a_rename_not_an_in_place_truncate(self):
        """MUTATION 2 guard: with write_text() there is no os.replace to see."""
        seen = []
        real_replace = os.replace

        def spy(src, dst, *a, **kw):
            seen.append((str(src), str(dst)))
            return real_replace(src, dst, *a, **kw)

        payload = {"cccccccccccc": {"sent_keys": ["1111222233334444"]}}
        with mock.patch.object(send_mail, "STATE_FILE", self.state_file), \
                mock.patch.object(send_mail.os, "replace", spy):
            send_mail.save_state(payload)

        self.assertEqual(len(seen), 1, "save_state did not go through os.replace")
        src, dst = seen[0]
        self.assertEqual(dst, str(self.state_file))
        self.assertEqual(Path(src).parent, self.state_file.parent,
                         "temp file is on another directory; os.replace is not atomic "
                         "across filesystems")
        self.assertEqual(json.loads(self.state_file.read_text()), payload)

    def test_save_state_round_trips_through_load_state(self):
        payload = {"dddddddddddd": {"sent_keys": ["aaaa1111bbbb2222"],
                                    "last_sent": "2026-08-30"}}
        with mock.patch.object(send_mail, "STATE_FILE", self.state_file):
            send_mail.save_state(payload)
            self.assertEqual(send_mail.load_state(), payload)


class ProfileEditKeepsHistory(unittest.TestCase):
    """Changing a subscriber's filter rescores. It does not un-send."""

    def setUp(self):
        self.data = sandbox()
        self.email = "edited@example.test"
        self.sid = sid(self.email)
        # seed with the 22 keys the LIVE state carries, under a test identity
        seeded = {self.sid: {"sent_keys": list(live_state()[LIVE_SUB_ID]["sent_keys"]),
                             "last_sent": "2026-07-27"}}
        (self.data / "mail_state.json").write_text(json.dumps(seeded, indent=1))

    def test_22_keys_stay_22_when_the_new_filter_finds_nothing_new(self):
        # measured: "software engineering" is eligible for 3 listings, all 3
        # already inside the seeded 22 -> no mail, no key movement
        run_send_mail(self.data, [subscriber(self.email, ["software engineering"])])
        after = read_state(self.data)[self.sid]["sent_keys"]
        self.assertEqual(FakeSMTP.sent, [], "a rescored profile re-sent old listings")
        self.assertEqual(len(after), LIVE_KEY_COUNT)
        self.assertEqual(sorted(after),
                         sorted(live_state()[LIVE_SUB_ID]["sent_keys"]))

    def test_a_wider_filter_adds_keys_and_loses_none(self):
        before = set(live_state()[LIVE_SUB_ID]["sent_keys"])
        run_send_mail(self.data, [subscriber(self.email, ["machine learning"])])
        after = set(read_state(self.data)[self.sid]["sent_keys"])
        self.assertTrue(before <= after, "sent_keys shrank after a profile edit")
        self.assertEqual(len(after), LIVE_KEY_COUNT + 9)  # measured: 9 genuinely new
        self.assertEqual(len(FakeSMTP.sent), 1)

    def test_history_is_never_reset_to_empty(self):
        run_send_mail(self.data, [subscriber(self.email, [])])
        after = read_state(self.data)[self.sid]["sent_keys"]
        self.assertGreaterEqual(len(after), LIVE_KEY_COUNT)


class IdentityNail(unittest.TestCase):
    """job_key and sub_id are pinned to the LIVE state file. Do not redefine."""

    def test_all_22_live_keys_reproduce_from_live_jobs_json(self):
        keys = set(live_state()[LIVE_SUB_ID]["sent_keys"])
        self.assertEqual(len(keys), LIVE_KEY_COUNT)
        jobs = json.loads(LIVE_JOBS.read_text())
        derived = {send_mail.job_key(r) for r in jobs}
        missing = sorted(keys - derived)
        self.assertEqual(missing, [],
                         "job_key no longer reproduces live mail_state.json keys; "
                         "every subscriber would be re-mailed everything")

    def test_job_key_literal_witnesses(self):
        # each pair is (input record, the key sitting in the LIVE state file)
        witnesses = [
            ({"link": "https://www.jumptrading.com/hr/job?gh_jid=8052351",
              "company": "Jump Trading", "position": "Software Engineer Intern"},
             "5ce7cd2a22b03c93"),
            ({"link": "https://jobs.lever.co/equativ/43f7b6c8-476b-4226-bbec-1e1b3dfb35b2",
              "company": "Equativ", "position": "Intern"},
             "537d76cf38f0d773"),
            ({"link": "https://lifeattiktok.com/search/7664538232974559493",
              "company": "TikTok", "position": "Intern"},
             "e244e71533c7491a"),
        ]
        for record, expected in witnesses:
            with self.subTest(link=record["link"]):
                self.assertEqual(send_mail.job_key(record), expected)

    def test_job_key_is_the_link_alone_and_falls_back_to_company_position(self):
        record = {"link": "https://www.jumptrading.com/hr/job?gh_jid=8052351",
                  "company": "Jump Trading", "position": "Software Engineer Intern"}
        noisy = dict(record, score=9, location="Chicago", reasons=["x"])
        self.assertEqual(send_mail.job_key(noisy), send_mail.job_key(record),
                         "job_key depends on fields beyond the link")
        no_link = {"company": "Acme", "position": "Intern"}
        self.assertEqual(send_mail.job_key(no_link),
                         send_mail.job_key({"link": "", "company": "Acme",
                                            "position": "Intern"}))
        self.assertEqual(send_mail.job_key(no_link), "cf1d6586dbb13472")

    def test_sub_id_derivation_is_pinned(self):
        """Behavioural: the key send_mail writes for an address cannot drift."""
        data = sandbox()
        email = "su.bilge@ug.bilkent.edu.tr"
        run_send_mail(data, [subscriber(email)])
        self.assertEqual(list(read_state(data)), ["609be0e707e7"],
                         "sub_id derivation changed; every subscriber becomes a new "
                         "identity with an empty history -> mass double-mail")

    def test_live_state_shape_is_intact(self):
        state = live_state()
        self.assertEqual(list(state), [LIVE_SUB_ID])
        self.assertEqual(len(LIVE_SUB_ID), 12)
        self.assertTrue(all(c in "0123456789abcdef" for c in LIVE_SUB_ID))
        keys = state[LIVE_SUB_ID]["sent_keys"]
        self.assertEqual(len(keys), LIVE_KEY_COUNT)
        self.assertEqual(len(set(keys)), LIVE_KEY_COUNT, "duplicate key in live state")
        self.assertTrue(all(len(k) == 16 for k in keys))


class ProductionIsUntouched(unittest.TestCase):
    """No test in this file may write to engine/data or open a socket."""

    def test_live_state_file_hash_is_unchanged(self):
        import hashlib
        self.assertEqual(hashlib.sha256(LIVE_STATE.read_bytes()).hexdigest(),
                         "99d7660afdf9b3bb2eeb5afa308b19a3fdffb1f68abe79e8e8b2efd3"
                         "efe5e390")

    def test_no_stray_temp_files_in_the_live_data_dir(self):
        strays = [p.name for p in LIVE_DATA.iterdir()
                  if p.name.startswith(".mail_state.")]
        self.assertEqual(strays, [], f"save_state leaked into engine/data: {strays}")

    def test_unsubscribed_filter_still_in_the_subscriber_query(self):
        src = (HERE.parent / "send_mail.py").read_text()
        self.assertIn("unsubscribed_at=is.null", src)


if __name__ == "__main__":
    unittest.main()
