#!/usr/bin/env python3
"""S7 -- "the same listing never arrives twice".

Four things are nailed here, all hermetic (no socket, no SMTP, no Supabase, no
production files written):

1. CRASH DURABILITY. A run that hits a failure must leave every already-sent
   subscriber recorded on disk. Ten subscribers, the fifth send raises: the
   other nine are delivered and persisted (S8a/A25 isolation), and a re-run
   mails only the one that failed.
2. ATOMICITY. A write that dies mid-serialisation must leave mail_state.json as
   valid JSON with the PREVIOUS content, so load_state() cannot die on a
   truncated file. No temp file is left behind either.
3. PROFILE EDITS DO NOT UN-SEND. Rescoring after an interests change keeps
   sent_keys lossless -- every key in is a key out.
4. IDENTITY NAIL. job_key and sub_id derivation are pinned against the LIVE
   engine/data/mail_state.json (subscriber bd235c29a8fc) and against literal
   hashes. Later phases cannot quietly redefine either without turning this
   file red -- redefining them means mass double-mail.

COUNTS ARE READ, NOT PINNED. daily.yml runs this suite BEFORE the mailer, and
the cron rewrites jobs.json and mail_state.json every morning. Every literal
count in here has already gone stale once (22 -> 89, 12 -> 55 -> 53) and each
time it meant a red suite and a morning with no mail. Derivations and shapes
are asserted hard; the sizes are read off the files at import.

Run: python3 -m unittest discover engine/tests -v
"""
import io
import hashlib
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

# The one real subscriber in the live state file. THIS stays a literal: it is
# the anchor sub_id identity is measured against, and it only changes if the
# derivation breaks -- which is the whole point of pinning it.
LIVE_SUB_ID = "bd235c29a8fc"

# The key COUNT is read from the file, never pinned. It was 22, then 89, and it
# grows by one every time the cron mails a new listing. A literal here is a
# time bomb: daily.yml runs this suite BEFORE the mailer, so a stale count
# means a red suite, a failed job, and a morning with no mail. The shape of
# these keys is still asserted hard (unique, 16 hex chars, one subscriber).
LIVE_KEY_COUNT = len(json.loads(LIVE_STATE.read_text())[LIVE_SUB_ID]["sent_keys"])

# sha of the live state as it was BEFORE any test ran. ProductionIsUntouched
# compares against this, not against a literal: the question it asks is "did
# the SUITE write to engine/data", not "is production frozen forever".
LIVE_STATE_SHA_AT_IMPORT = hashlib.sha256(LIVE_STATE.read_bytes()).hexdigest()

SIM_INTERESTS = ["machine learning"]
SIM_SUBS = 10
CRASH_AT = 5  # the 5th delivery raises

_REAL_SOCKET = socket.socket


def _no_network(*args, **kwargs):
    raise AssertionError("a test opened a socket; these tests must be hermetic")


def setUpModule():
    socket.socket = _no_network


def tearDownModule():
    socket.socket = _REAL_SOCKET


def live_state() -> dict:
    return json.loads(LIVE_STATE.read_text())


class FakeProvider(send_mail.Provider):
    """Stand-in for ResendProvider. Counts sends, optionally dies on the Nth.

    No transport, no socket: deliver() never leaves the process.
    """

    sent: list[str] = []
    die_on: int | None = None
    state_seen: list[int] = []
    attempts: int = 0

    def __init__(self, *args, **kwargs):
        super().__init__("the engine <test@example.test>")

    @classmethod
    def reset(cls, die_on=None):
        cls.sent = []
        cls.die_on = die_on
        cls.state_seen = []
        cls.attempts = 0

    def deliver(self, payload):
        FakeProvider.attempts += 1
        n = FakeProvider.attempts
        # how many subscribers are already durable on disk at this moment
        p = Path(str(send_mail.STATE_FILE))
        FakeProvider.state_seen.append(
            len(json.loads(p.read_text())) if p.exists() else 0)
        if FakeProvider.die_on is not None and n == FakeProvider.die_on:
            raise RuntimeError(f"transport died on send #{FakeProvider.die_on}")
        FakeProvider.sent.append(payload["to"][0])
        return send_mail.MessageId(f"fake-{n}")


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


class StubSeats(send_mail.SeatBackend):
    """S9b: main() also drives the invite loop, which speaks PostgREST.

    No waitlist exists in these fixtures, so the honest answer is zero seats
    and no mail. Stubbed rather than left to raise, because this file is about
    mail_state idempotence and a live urlopen in the middle of it is noise.
    The invite loop is measured in test_invite_delivery.py.
    """

    def __init__(self, key, *a, **kw):
        pass

    def run_invites(self, daily_limit):
        return 0

    def fresh_invites(self, count):
        return []

    def release_invite(self, token):
        raise AssertionError("nothing was stamped, nothing to release")


def run_send_mail(data: Path, subs: list[dict], die_on=None) -> str:
    """Run send_mail.main() end to end on the real send path (no --dry-run)."""
    FakeProvider.reset(die_on=die_on)
    env = {"SUPABASE_SERVICE_KEY": "x", "RESEND_API_KEY": "re_test",
           "MAIL_FROM": "the engine <test@example.test>"}
    with mock.patch.object(send_mail, "DATA", data), \
            mock.patch.object(send_mail, "STATE_FILE", data / "mail_state.json"), \
            mock.patch.object(send_mail, "fetch_subscribers", lambda k: subs), \
            mock.patch.object(send_mail, "pending_confirmations", lambda k: []), \
            mock.patch.object(send_mail, "ResendProvider", FakeProvider), \
            mock.patch.object(send_mail, "SupabaseSeats", StubSeats), \
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
    """A run that hits a failure must not forget what it already sent -- and,
    since S8a, must not stop either (A25)."""

    def setUp(self):
        self.data = sandbox()
        self.subs = [subscriber(f"s{i}@example.test") for i in range(SIM_SUBS)]

    def test_failure_on_fifth_send_does_not_stop_the_other_nine(self):
        out = run_send_mail(self.data, self.subs, die_on=CRASH_AT)

        state = read_state(self.data)
        self.assertEqual(len(FakeProvider.sent), SIM_SUBS - 1,
                         "isolation broken: a single failure cost more than one mail")
        self.assertEqual(len(state), SIM_SUBS - 1,
                         "sends happened but subscribers are missing from disk")
        victim = self.subs[CRASH_AT - 1]["email"]
        self.assertNotIn(sid(victim), state, "a failed send was recorded as sent")
        self.assertEqual(set(state),
                         {sid(s["email"]) for s in self.subs if s["email"] != victim})
        # Every survivor got the SAME number of keys, and that number is not
        # pinned to a literal: these subscribers share one filter, so whatever
        # today's corpus offers them, they all get it. A literal here was a
        # live-corpus pin -- the cron rewrites jobs.json every morning, the
        # count moved 55 -> 53 overnight, and the red suite blocked the mail.
        counts = {len(v["sent_keys"]) for v in state.values()}
        self.assertEqual(len(counts), 1, f"survivors got different key counts: {counts}")
        per_sub = counts.pop()
        self.assertGreater(per_sub, 0, "every survivor was mailed an empty list")
        total = sum(len(v["sent_keys"]) for v in state.values())
        self.assertEqual(total, (SIM_SUBS - 1) * per_sub)
        self.assertIn(f"processed {SIM_SUBS}/{SIM_SUBS}", out)
        self.assertIn("error 1", out)

    def test_rerun_after_failure_mails_only_the_one_that_failed(self):
        run_send_mail(self.data, self.subs, die_on=CRASH_AT)
        already = {s["email"] for s in self.subs
                   if s["email"] != self.subs[CRASH_AT - 1]["email"]}

        out = run_send_mail(self.data, self.subs)  # clean re-run, nothing dies

        self.assertEqual(FakeProvider.sent, [self.subs[CRASH_AT - 1]["email"]],
                         "re-run did not mail exactly the subscriber that failed")
        self.assertEqual(already & set(FakeProvider.sent), set(),
                         "a subscriber who already had mail got it a SECOND time")
        self.assertIn("done: 1 mail(s) sent", out)

    def test_third_run_sends_nothing_at_all(self):
        run_send_mail(self.data, self.subs)
        self.assertEqual(len(FakeProvider.sent), SIM_SUBS)
        run_send_mail(self.data, self.subs)
        self.assertEqual(FakeProvider.sent, [], "a fully mailed corpus was mailed again")

    def test_state_is_on_disk_before_the_next_subscriber_is_touched(self):
        """At send #N, exactly N-1 subscribers are already durable on disk."""
        run_send_mail(self.data, self.subs)
        self.assertEqual(FakeProvider.state_seen, list(range(SIM_SUBS)),
                         "state is not flushed before the next subscriber is touched")
        state = read_state(self.data)
        self.assertEqual(len(state), SIM_SUBS)
        counts = {len(v["sent_keys"]) for v in state.values()}
        self.assertEqual(len(counts), 1, f"subscribers got different counts: {counts}")
        self.assertGreater(counts.pop(), 0)


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
        # seed with the 89 keys the LIVE state carries, under a test identity
        seeded = {self.sid: {"sent_keys": list(live_state()[LIVE_SUB_ID]["sent_keys"]),
                             "last_sent": "2026-07-27"}}
        (self.data / "mail_state.json").write_text(json.dumps(seeded, indent=1))

    def test_89_keys_stay_89_when_the_new_filter_finds_nothing_new(self):
        # measured on the 599-listing corpus: every listing "software engineering"
        # is eligible for is already inside the seeded 89 -> no mail, no key movement
        run_send_mail(self.data, [subscriber(self.email, ["software engineering"])])
        after = read_state(self.data)[self.sid]["sent_keys"]
        self.assertEqual(FakeProvider.sent, [], "a rescored profile re-sent old listings")
        self.assertEqual(len(after), LIVE_KEY_COUNT)
        self.assertEqual(sorted(after),
                         sorted(live_state()[LIVE_SUB_ID]["sent_keys"]))

    def test_a_wider_filter_adds_keys_and_loses_none(self):
        before = set(live_state()[LIVE_SUB_ID]["sent_keys"])
        run_send_mail(self.data, [subscriber(self.email, ["machine learning"])])
        after = set(read_state(self.data)[self.sid]["sent_keys"])
        self.assertTrue(before <= after, "sent_keys shrank after a profile edit")
        # STRICTLY wider, but the width is not a literal. "+53" was a live-corpus
        # pin: the cron rewrites jobs.json nightly, it became +51, and the red
        # suite stopped the mail. The claim is "adds keys and loses none", and
        # that is exactly what the two assertions around this comment say.
        self.assertGreater(len(after), len(before),
                           "a wider filter found nothing new at all")
        self.assertEqual(len(FakeProvider.sent), 1)

    def test_history_is_never_reset_to_empty(self):
        run_send_mail(self.data, [subscriber(self.email, [])])
        after = read_state(self.data)[self.sid]["sent_keys"]
        self.assertGreaterEqual(len(after), LIVE_KEY_COUNT)


class IdentityNail(unittest.TestCase):
    """job_key and sub_id are pinned to the LIVE state file. Do not redefine."""

    def test_live_keys_still_reproduce_from_the_live_corpus(self):
        """The nail is the DERIVATION, not the corpus.

        This used to demand that EVERY mailed key reproduce from jobs.json.
        That premise died when the corpus started moving: a listing we mailed
        can be taken down, and then it is legitimately absent from jobs.json.
        Measured 2026-08-30 over 89 mailed keys: 46 still live, 43 dead.
        All 89 DO reproduce from the corpus history (40 snapshots, 1135 keys),
        so nothing was lost -- but that walk shells out to git and does not
        belong in a unit test.

        A job_key drift is still caught here, and caught hard: it would push
        the overlap to exactly 0. The exact derivation is pinned separately by
        test_job_key_literal_witnesses. The overlap COUNT is deliberately not
        pinned -- it drops every day a mailed listing is taken down.
        """
        keys = set(live_state()[LIVE_SUB_ID]["sent_keys"])
        self.assertEqual(len(keys), LIVE_KEY_COUNT)
        derived = {send_mail.job_key(r) for r in json.loads(LIVE_JOBS.read_text())}
        self.assertGreater(len(keys & derived), 0,
                           "job_key reproduces NONE of the live mail_state.json "
                           "keys; the derivation drifted and every subscriber "
                           "would be re-mailed everything")

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
        """The SUITE did not write to engine/data. Compared to import time."""
        self.assertEqual(hashlib.sha256(LIVE_STATE.read_bytes()).hexdigest(),
                         LIVE_STATE_SHA_AT_IMPORT,
                         "a test wrote to the live mail_state.json")

    def test_no_stray_temp_files_in_the_live_data_dir(self):
        strays = [p.name for p in LIVE_DATA.iterdir()
                  if p.name.startswith(".mail_state.")]
        self.assertEqual(strays, [], f"save_state leaked into engine/data: {strays}")

    def test_unsubscribed_filter_still_in_the_subscriber_query(self):
        src = (HERE.parent / "send_mail.py").read_text()
        self.assertIn("unsubscribed_at=is.null", src)


if __name__ == "__main__":
    unittest.main()
