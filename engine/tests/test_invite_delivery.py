#!/usr/bin/env python3
"""S9b -- "seats open at the speed of the quota".

The sentence this file defends: I am on the waiting list, and when my turn
comes the invitation actually lands in my inbox.

Two measured holes sit behind that sentence, and they are not the same hole.

HOLE 1, in the SQL. sightstone_run_invites() took no argument and stamped
invited_at on every free seat in one shot. That stamp is a PROMISE with a 48
hour clock on it, and the only way the promise is ever delivered is a mail.
S9a caps the day at 90 mails. So 200 free seats meant 200 stamps, 90 mails, and
110 people marked dropped_at two days later having never heard a word. The
seats were "opened" and nobody was told. TheCapIsTheMailBudget below plays
exactly that out on a real PostgreSQL: 200 waiting, limit 90, and the answer
has to be 90 stamps -- not 200.

HOLE 2, worse, in the wiring. NOTHING CALLED THE FUNCTION. Not a workflow step,
not a pg_cron row -- the only caller in the whole repository was a test, while
the comment at the head of schema.sql said it ran once a day. It ran zero times
a day. TheLoopHasARealCaller reads send_mail.py's syntax tree and fails if the
call site is not there, so deleting the caller again cannot pass.

THE FORBIDDEN STATE, the one line everything here is arranged around:
A ROW THAT IS STAMPED AND NOT MAILED MUST NOT EXIST. Quota is one way to make
one; a provider softfail on a single address is another, so a send that is not
ACCEPTED hands the stamp back and the person keeps their place in line.

NOTHING HERE TOUCHES THE NETWORK. socket.socket is replaced for the whole
module, so an accidental urlopen raises instead of dialling. The database half
runs on the throwaway cluster from pg_harness -- initdb into a temp dir, a unix
socket in that same dir, torn down on the way out. The production Supabase has
no path into this file. The PostgREST implementation is still exercised, but
against a fake transport that records the request and answers from a script.

Run: python3 -m unittest discover engine/tests
"""
import ast
import io
import json
import socket
import sys
import unittest
from contextlib import redirect_stdout, redirect_stderr
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

HERE = Path(__file__).parent
ENGINE = HERE.parent
sys.path.insert(0, str(ENGINE))

import pg_harness as H          # noqa: E402
import send_mail                # noqa: E402

SEND_MAIL_SRC = (ENGINE / "send_mail.py").read_text()
SCHEMA = (ENGINE / "schema.sql").read_text()

CAP = 200
DAILY = 90                      # send_mail.DAILY_MAIL_CAP, asserted below

T0 = datetime(2026, 9, 15, 9, 0, tzinfo=timezone.utc)

_REAL_SOCKET = socket.socket


def _no_network(*a, **kw):
    raise AssertionError("a test opened a socket; these tests must be hermetic")


def setUpModule():
    socket.socket = _no_network


def tearDownModule():
    socket.socket = _REAL_SOCKET


# ============================================================ static: the SQL

class TheFunctionTakesTheBudget(unittest.TestCase):
    """Read out of schema.sql. No server needed, so it runs everywhere."""

    def body(self) -> str:
        start = SCHEMA.index("create or replace function sightstone_run_invites(")
        return SCHEMA[start:].split("$$")[1]

    def test_the_signature_names_a_daily_limit(self):
        self.assertIn(
            "create or replace function sightstone_run_invites(daily_limit int)",
            SCHEMA,
            "the invite loop still takes no argument, so it cannot be told how "
            "many mails today can carry")

    def test_the_limit_binds_the_loop_not_just_the_signature(self):
        """An accepted-and-ignored parameter would pass the test above."""
        body = self.body()
        self.assertRegex(body, r"limit\s+greatest\(\s*least\(\s*free\s*,")
        self.assertIn("daily_limit", body.split("limit greatest")[1][:80])

    def test_a_null_limit_means_zero_not_unlimited(self):
        """least(5, null) is 5 in PostgreSQL. Without the coalesce a null
        argument would read as "no ceiling" -- the exact old behaviour, reached
        by passing nothing useful."""
        self.assertIn("coalesce(daily_limit, 0)", self.body())

    def test_the_advisory_lock_is_still_the_first_thing_it_does(self):
        self.assertIn("pg_advisory_xact_lock(hashtext('sightstone_seats'))",
                      self.body())
        self.assertLess(self.body().index("pg_advisory_xact_lock"),
                        self.body().index("free :="))

    def test_the_48_hour_expiry_is_untouched(self):
        self.assertIn("invite_expires_at = now() + interval '48 hours'",
                      self.body())

    def test_the_parameterless_version_is_dropped_not_left_behind(self):
        """create or replace makes a NEW function for a new signature and
        leaves the old one sitting there. Running schema.sql twice would
        otherwise keep an uncapped sightstone_run_invites() alive."""
        drop = SCHEMA.index("drop function if exists sightstone_run_invites();")
        create = SCHEMA.index(
            "create or replace function sightstone_run_invites(daily_limit int)")
        self.assertLess(drop, create)

    def test_the_head_comment_matches_reality(self):
        """It used to claim a daily run that never happened."""
        head = SCHEMA[:SCHEMA.index("create extension")]
        self.assertIn("sightstone_run_invites", head)
        self.assertIn("send_mail.py", head,
                      "the file still does not say who runs the invite loop")


# ========================================================= static: the caller

def caller_is_wired(source: str) -> bool:
    """True when main() actually invokes the invite loop.

    Read from the syntax tree: a mention inside a comment or a docstring must
    not count, because a comment is exactly what hole 2 was made of.
    """
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "main":
            for sub in ast.walk(node):
                if (isinstance(sub, ast.Call)
                        and isinstance(sub.func, ast.Name)
                        and sub.func.id == "run_invite_loop"):
                    return True
    return False


def budget_reaches_the_database(source: str) -> bool:
    """True when run_invite_loop takes remaining_today() and hands THAT to
    run_invites -- not a literal, not a constant."""
    tree = ast.parse(source)
    for node in tree.body:
        if not (isinstance(node, ast.FunctionDef)
                and node.name == "run_invite_loop"):
            continue
        names = {n.func.id for n in ast.walk(node)
                 if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
        if "remaining_today" not in names:
            return False
        for sub in ast.walk(node):
            if (isinstance(sub, ast.Call)
                    and isinstance(sub.func, ast.Attribute)
                    and sub.func.attr == "run_invites"):
                # the single argument must be a variable, never a literal
                if len(sub.args) == 1 and isinstance(sub.args[0], ast.Name):
                    return True
        return False
    return False


class TheLoopHasARealCaller(unittest.TestCase):
    """MUTATION 2 lives here: cut the call site, this class goes red."""

    def test_main_calls_the_invite_loop(self):
        self.assertTrue(caller_is_wired(SEND_MAIL_SRC),
                        "nothing in the shipped code runs the invite loop -- "
                        "this is hole 2, exactly as it was found")

    def test_removing_the_call_site_is_caught(self):
        """The mutation, applied to a copy of the source. If this passed with
        the call site deleted, the test above would be proving nothing."""
        mutated = SEND_MAIL_SRC.replace(
            "invites = run_invite_loop(SupabaseSeats(service_key), provider)",
            "invites = None")
        self.assertNotEqual(mutated, SEND_MAIL_SRC, "the call site moved")
        self.assertFalse(caller_is_wired(mutated))

    def test_the_caller_is_not_a_test_file(self):
        """The only caller used to be engine/tests. Shipped code has to have
        one of its own."""
        shipped = [p for p in ENGINE.rglob("*.py")
                   if "tests" not in p.parts and "__pycache__" not in p.parts]
        callers = [p.name for p in shipped
                   if "run_invites" in p.read_text()]
        self.assertIn("send_mail.py", callers)

    def test_the_daily_budget_is_what_gets_passed(self):
        self.assertTrue(budget_reaches_the_database(SEND_MAIL_SRC))

    def test_a_hardcoded_limit_would_be_caught(self):
        """MUTATION 1 from the caller's side: freeze the number and the proof
        that remaining_today() reaches the database disappears."""
        mutated = SEND_MAIL_SRC.replace(
            'tally["opened"] = opened = seats.run_invites(budget)',
            'tally["opened"] = opened = seats.run_invites(90)')
        self.assertNotEqual(mutated, SEND_MAIL_SRC)
        self.assertFalse(budget_reaches_the_database(mutated))

    def test_the_invite_mail_declares_its_kind(self):
        self.assertIn('kind="invite"', SEND_MAIL_SRC)
        self.assertIn("invite", send_mail.MAIL_KINDS)

    def test_the_daily_cap_is_still_ninety(self):
        self.assertEqual(send_mail.DAILY_MAIL_CAP, DAILY)


# ================================================= the PostgREST calls, faked

class FakeHTTP:
    """A transport that answers from a script and records what it was asked.

    This is how the real SupabaseSeats code is exercised without a socket: the
    URLs, methods and bodies it builds are the thing under test.
    """

    def __init__(self, answers):
        self.answers = list(answers)
        self.calls = []

    def __call__(self, req, timeout=None):
        body = req.data.decode() if req.data else None
        self.calls.append((req.get_method(), req.full_url, body))
        payload = self.answers.pop(0) if self.answers else None

        class Resp:
            def read(self_inner):
                return json.dumps(payload).encode() if payload is not None else b""

            def __enter__(self_inner):
                return self_inner

            def __exit__(self_inner, *a):
                return False
        return Resp()


class TheRestCallsAreShaped(unittest.TestCase):
    def seats(self, answers):
        self.http = FakeHTTP(answers)
        patch = mock.patch.object(send_mail.urllib.request, "urlopen", self.http)
        patch.start()
        self.addCleanup(patch.stop)
        return send_mail.SupabaseSeats("sb_secret_test")

    def test_run_invites_posts_the_daily_limit_to_the_rpc(self):
        seats = self.seats([90])
        self.assertEqual(seats.run_invites(90), 90)
        method, url, body = self.http.calls[0]
        self.assertEqual(method, "POST")
        self.assertTrue(url.endswith("/rest/v1/rpc/sightstone_run_invites"), url)
        self.assertEqual(json.loads(body), {"daily_limit": 90})

    def test_fresh_invites_asks_for_the_newest_live_invites_only(self):
        seats = self.seats([[{"email": "a@b.c", "invite_token": "t"}]])
        rows = seats.fresh_invites(1)
        self.assertEqual(rows[0]["email"], "a@b.c")
        method, url, _ = self.http.calls[0]
        self.assertEqual(method, "GET")
        for fragment in ("invited_at=not.is.null", "accepted_at=is.null",
                         "dropped_at=is.null", "order=invited_at.desc",
                         "limit=1"):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, url)

    def test_fresh_invites_does_not_call_out_for_zero_rows(self):
        seats = self.seats([])
        self.assertEqual(seats.fresh_invites(0), [])
        self.assertEqual(self.http.calls, [])

    def test_releasing_clears_both_stamp_columns_for_that_token_alone(self):
        seats = self.seats([None])
        seats.release_invite("tok-1")
        method, url, body = self.http.calls[0]
        self.assertEqual(method, "PATCH")
        self.assertIn("invite_token=eq.tok-1", url)
        self.assertEqual(json.loads(body),
                         {"invited_at": None, "invite_expires_at": None})

    def test_a_jwt_key_gets_a_bearer_header_and_a_secret_key_does_not(self):
        self.assertIn("Authorization",
                      send_mail.SupabaseSeats("eyJabc")._headers())
        self.assertNotIn("Authorization",
                         send_mail.SupabaseSeats("sb_secret_x")._headers())

    def test_an_empty_service_key_is_refused(self):
        with self.assertRaises(RuntimeError):
            send_mail.SupabaseSeats("")


class ADryRunOpensNoSeat(unittest.TestCase):
    """A rehearsal spends no quota -- DryRunProvider sees to that -- but the
    invite loop writes to the DATABASE, which no flag on the provider can
    undo. So --dry-run must not reach the loop at all: otherwise a rehearsal
    stamps real people with a real 48 hour clock and mails none of them.
    """

    def run_main_dry(self):
        import os
        import shutil
        import tempfile
        data = Path(tempfile.mkdtemp(prefix="s9b-dry-")) / "data"
        data.mkdir(parents=True)
        self.addCleanup(shutil.rmtree, data.parent, ignore_errors=True)
        shutil.copy(ENGINE / "data" / "jobs.json", data / "jobs.json")
        built = []

        class Tripwire(send_mail.SeatBackend):
            def __init__(self, *a, **kw):
                built.append(1)
                raise AssertionError("a dry run reached the seat backend")

        with mock.patch.object(send_mail, "DATA", data), \
                mock.patch.object(send_mail, "STATE_FILE",
                                  data / "mail_state.json"), \
                mock.patch.object(send_mail, "SupabaseSeats", Tripwire), \
                mock.patch.object(send_mail, "fetch_subscribers",
                                  lambda k: [{"email": "a@b.c", "name": "a",
                                              "level": "bs", "interests": ["ml"],
                                              "location": "",
                                              "unsubscribe_token": None}]), \
                mock.patch.dict(os.environ, {"SUPABASE_SERVICE_KEY": "x"},
                                clear=True), \
                mock.patch.object(sys, "argv", ["send_mail.py", "--dry-run"]), \
                redirect_stdout(io.StringIO()) as out, \
                redirect_stderr(io.StringIO()):
            send_mail.main()
        send_mail.reset_ledger()
        return out.getvalue(), built

    def test_a_dry_run_never_touches_the_seat_backend(self):
        out, built = self.run_main_dry()
        self.assertEqual(built, [], "a dry run built a live seat backend")
        self.assertIn("invites: skipped", out)

    def test_the_skip_is_a_branch_not_an_accident(self):
        """Reachable proof that the guard is the --dry-run flag itself, so a
        later reorder cannot leave the loop running under a rehearsal."""
        tree = ast.parse(SEND_MAIL_SRC)
        main = next(n for n in tree.body
                    if isinstance(n, ast.FunctionDef) and n.name == "main")
        guards = [n for n in ast.walk(main)
                  if isinstance(n, ast.If)
                  and any(isinstance(s, ast.Attribute) and s.attr == "dry_run"
                          for s in ast.walk(n.test))
                  and any(isinstance(c, ast.Call) and isinstance(c.func, ast.Name)
                          and c.func.id == "run_invite_loop"
                          for c in ast.walk(n))]
        self.assertEqual(len(guards), 1,
                         "the invite loop is not behind a --dry-run branch")


# ====================================================== behaviour: a real cluster

class Clock:
    def __init__(self, start=T0):
        self.now = start

    def __call__(self):
        return self.now

    def advance(self, **kw):
        self.now = self.now + timedelta(**kw)
        return self.now


class PgSeats(send_mail.SeatBackend):
    """The same three operations, against the throwaway cluster.

    Every query mirrors SupabaseSeats one for one -- same filter, same
    newest-first ordering, same limit -- so the loop being measured here is the
    loop that ships. TheRestCallsAreShaped is what pins the HTTP side to these
    same strings.
    """

    def __init__(self, pg):
        self.pg = pg
        self.released = []

    def run_invites(self, daily_limit: int) -> int:
        return self.pg.count(
            f"select sightstone_run_invites({int(daily_limit)});")

    def fresh_invites(self, count: int) -> list[dict]:
        if count <= 0:
            return []
        out = self.pg.scalar(
            "select coalesce(string_agg(email || ' ' || invite_token, ','), '') "
            "from (select email, invite_token from sightstone_waitlist "
            "where invited_at is not null and accepted_at is null "
            "and dropped_at is null "
            f"order by invited_at desc, email asc limit {int(count)}) q;")
        rows = []
        for chunk in out.split(","):
            if not chunk.strip():
                continue
            email, token = chunk.split(" ")
            rows.append({"email": email, "invite_token": token})
        return rows

    def release_invite(self, token: str) -> None:
        self.released.append(token)
        self.pg.run("update sightstone_waitlist "
                    "set invited_at = null, invite_expires_at = null "
                    f"where invite_token = '{token}';")


class RecordingProvider(send_mail.Provider):
    """On the real account -- it costs quota -- but nothing leaves the process."""

    consumes_quota = True

    def __init__(self, from_addr="the engine <test@example.test>"):
        super().__init__(from_addr)
        self.mailed = []

    def deliver(self, payload):
        self.mailed.append(payload["to"][0])
        return send_mail.MessageId(f"fake-{len(self.mailed)}")


class RefusingProvider(RecordingProvider):
    """The provider rejects every address, so no stamp may survive."""

    def deliver(self, payload):
        return send_mail.SoftFail("nope", 422, "invalid_parameter")


class InviteClusterCase(unittest.TestCase):
    """One cluster per class; a private data dir and a hand-wound clock."""

    schema_text = None
    pg = None

    @classmethod
    def setUpClass(cls):
        if not H.available():
            raise unittest.SkipTest("no local postgres (initdb/pg_ctl/psql)")
        cls.pg = H.Cluster()
        try:
            cls.pg.start()
            cls.pg.load_schema(cls.schema_text)
        except Exception:
            cls.pg.stop()
            raise

    @classmethod
    def tearDownClass(cls):
        if cls.pg is not None:
            cls.pg.stop()
            cls.pg = None

    def setUp(self):
        import shutil
        import tempfile
        self.pg.run("truncate sightstone_subscribers, sightstone_waitlist;")
        self.data = Path(tempfile.mkdtemp(prefix="s9b-")) / "data"
        self.data.mkdir(parents=True)
        self.addCleanup(shutil.rmtree, self.data.parent, ignore_errors=True)
        self.clock = Clock()
        real_data = send_mail.DATA
        for patch in (mock.patch.object(send_mail, "DATA", self.data),
                      mock.patch.object(send_mail, "_now", self.clock)):
            patch.start()
            self.addCleanup(patch.stop)
        self.addCleanup(lambda: (setattr(send_mail, "DATA", real_data),
                                 send_mail.reset_ledger()))
        self.book = send_mail.reset_ledger()
        self.seats = PgSeats(self.pg)

    # -- fixtures ----------------------------------------------------------
    def full_house_then_empty_it(self, waiters: int = CAP):
        """CAP seats filled so the waitlist gate opens, `waiters` people queue,
        then every seat is vacated. Result: CAP free seats, `waiters` waiting.
        """
        self.pg.run(
            "insert into sightstone_subscribers"
            "(email, mail_consent, kvkk_accepted_at, confirmed_at) "
            "select 's'||g||'@example.test', true, now(), now() "
            f"from generate_series(1,{CAP}) g;")
        # created_at is written EXPLICITLY and one second apart. A bulk insert
        # takes now() from the transaction, so every row would share an instant
        # and `order by created_at, id` would fall through to a random uuid --
        # the queue would look shuffled and the test would be measuring the
        # fixture, not the ordering. Real signups arrive at distinct times.
        self.pg.run(
            "insert into sightstone_waitlist"
            "(email, mail_consent, kvkk_accepted_at, created_at) "
            "select 'w'||lpad(g::text,3,'0')||'@example.test', true, now(), "
            f"now() - (interval '1 second' * ({waiters} - g)) "
            f"from generate_series(1,{waiters}) g;")
        # everyone leaves; no trigger is involved in an unsubscribe
        self.pg.run("update sightstone_subscribers set unsubscribed_at = now();")
        self.assertEqual(self.pg.count("select sightstone_seats_taken();"), 0)
        self.assertEqual(
            self.pg.count("select count(*) from sightstone_waitlist;"), waiters)

    # -- measurements ------------------------------------------------------
    def stamped(self) -> int:
        return self.pg.count(
            "select count(*) from sightstone_waitlist "
            "where invited_at is not null;")

    def live_stamped_emails(self) -> set:
        out = self.pg.scalar(
            "select coalesce(string_agg(email, ','), '') from sightstone_waitlist "
            "where invited_at is not null and accepted_at is null "
            "and dropped_at is null;")
        return {e for e in out.split(",") if e}

    def loop(self, provider):
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            return send_mail.run_invite_loop(self.seats, provider)


class TheCapIsTheMailBudget(InviteClusterCase):
    """The card's number, measured: 200 waiting, 90 mails, 90 stamps."""

    def test_two_hundred_waiting_and_a_limit_of_ninety_stamps_exactly_ninety(self):
        self.full_house_then_empty_it()
        self.assertEqual(self.pg.count(f"select sightstone_run_invites({DAILY});"),
                         DAILY)
        self.assertEqual(self.stamped(), DAILY,
                         "the stamp count is not the mail count; somebody was "
                         "promised a seat nobody can tell them about")

    def test_the_oldest_waiters_are_the_ones_stamped(self):
        self.full_house_then_empty_it()
        self.pg.run(f"select sightstone_run_invites({DAILY});")
        self.assertEqual(self.live_stamped_emails(),
                         {f"w{i:03d}@example.test" for i in range(1, DAILY + 1)})

    def test_the_opening_spreads_over_three_days(self):
        """90 + 90 + 20. The queue drains; it is not truncated."""
        self.full_house_then_empty_it()
        days = []
        for _ in range(3):
            days.append(
                self.pg.count(f"select sightstone_run_invites({DAILY});"))
            # the day's invites are accepted, so their seats stop being free
            self.pg.run("update sightstone_waitlist set accepted_at = now() "
                        "where invited_at is not null and accepted_at is null;")
        self.assertEqual(days, [90, 90, 20])
        self.assertEqual(sum(days), CAP)
        self.assertEqual(self.stamped(), CAP, "somebody never got their turn")

    def test_a_limit_bigger_than_the_free_seats_does_not_invent_seats(self):
        self.full_house_then_empty_it(waiters=CAP)
        self.assertEqual(
            self.pg.count("select sightstone_run_invites(10000);"), CAP)

    def test_a_limit_of_zero_opens_nothing(self):
        self.full_house_then_empty_it()
        self.assertEqual(self.pg.count("select sightstone_run_invites(0);"), 0)
        self.assertEqual(self.stamped(), 0)

    def test_a_null_limit_opens_nothing_rather_than_everything(self):
        self.full_house_then_empty_it()
        self.assertEqual(
            self.pg.count("select sightstone_run_invites(null);"), 0)
        self.assertEqual(self.stamped(), 0)


class NobodyIsStampedWithoutBeingMailed(InviteClusterCase):
    """The forbidden state, checked end to end: database, loop, provider."""

    def stamped_but_unmailed(self, provider) -> set:
        return self.live_stamped_emails() - set(provider.mailed)

    def test_ninety_stamps_ninety_mails_and_nobody_left_silent(self):
        self.full_house_then_empty_it()
        p = RecordingProvider()
        tally = self.loop(p)
        self.assertEqual(tally["budget"], DAILY)
        self.assertEqual(tally["opened"], DAILY)
        self.assertEqual(tally["mailed"], DAILY)
        self.assertEqual(tally["missing"], 0)
        self.assertEqual(self.stamped(), DAILY)
        self.assertEqual(len(p.mailed), DAILY)
        self.assertEqual(self.stamped_but_unmailed(p), set(),
                         "somebody holds a 48 hour promise nobody mailed")
        # SEATS OPENED == INVITATIONS DELIVERED, and no stamp had to be clawed
        # back to make that true. The release path is REPAIR; needing it means
        # the database was told to open more seats than the day could mail.
        self.assertEqual(tally["opened"], tally["mailed"])
        self.assertEqual(tally["released"], 0,
                         "seats had to be un-stamped, so the limit handed to "
                         "the database was not the mail budget")

    def test_the_three_day_opening_mails_all_two_hundred(self):
        self.full_house_then_empty_it()
        p = RecordingProvider()
        opened = []
        for _ in range(3):
            opened.append(self.loop(p)["opened"])
            self.pg.run("update sightstone_waitlist set accepted_at = now() "
                        "where invited_at is not null and accepted_at is null;")
            self.clock.advance(hours=24, minutes=1)   # the quota window rolls
        self.assertEqual(opened, [90, 90, 20])
        self.assertEqual(len(p.mailed), CAP)
        self.assertEqual(len(set(p.mailed)), CAP, "somebody was mailed twice")

    def test_a_second_run_on_the_same_day_opens_nothing_more(self):
        """The budget is spent, so no further promise may be made."""
        self.full_house_then_empty_it()
        p = RecordingProvider()
        self.loop(p)
        again = self.loop(p)
        self.assertEqual(again["budget"], 0)
        self.assertEqual(again["opened"], 0)
        self.assertEqual(self.stamped(), DAILY)

    def test_the_budget_is_read_live_not_assumed(self):
        """60 mails already spent today leaves 30, so 30 seats open -- not 90.
        This is the proof that remaining_today() is really what is passed."""
        self.full_house_then_empty_it()
        self.book.record("bulletin", 60, self.clock.now)
        p = RecordingProvider()
        tally = self.loop(p)
        self.assertEqual(tally["budget"], 30)
        self.assertEqual(tally["opened"], 30)
        self.assertEqual(self.stamped(), 30)
        self.assertEqual(len(p.mailed), 30)

    def test_an_exhausted_budget_stamps_nobody_at_all(self):
        self.full_house_then_empty_it()
        self.book.record("bulletin", DAILY, self.clock.now)
        p = RecordingProvider()
        tally = self.loop(p)
        self.assertEqual(tally["budget"], 0)
        self.assertEqual(self.stamped(), 0,
                         "a seat was opened on a day with no mail left")
        self.assertEqual(p.mailed, [])

    def test_a_refused_send_gives_the_stamp_back(self):
        """Quota is not the only way to strand somebody. One softfailing
        address must not sit on a reserved seat in silence for 48 hours."""
        self.full_house_then_empty_it()
        p = RefusingProvider()
        tally = self.loop(p)
        self.assertEqual(tally["opened"], DAILY)
        self.assertEqual(tally["mailed"], 0)
        self.assertEqual(tally["released"], DAILY)
        self.assertEqual(self.live_stamped_emails(), set(),
                         "a stamp survived a send that never arrived")
        self.assertEqual(self.pg.count("select sightstone_seats_taken();"), 0,
                         "released seats are still being counted as occupied")

    def test_a_released_waiter_is_invited_again_next_run(self):
        self.full_house_then_empty_it()
        self.loop(RefusingProvider())
        self.clock.advance(hours=24, minutes=1)
        p = RecordingProvider()
        self.assertEqual(self.loop(p)["opened"], DAILY)
        self.assertEqual(sorted(p.mailed)[0], "w001@example.test",
                         "the head of the queue lost their place")

    def test_the_invite_mail_carries_the_token_and_a_way_out(self):
        self.full_house_then_empty_it(waiters=1)
        p = RecordingProvider()
        self.loop(p)
        payload = p.payloads[0]
        token = self.pg.scalar(
            "select invite_token from sightstone_waitlist limit 1;")
        self.assertIn(token, payload["text"])
        self.assertIn("List-Unsubscribe", payload["headers"])
        self.assertNotIn("List-Unsubscribe-Post", payload["headers"])

    def test_every_invite_is_charged_to_the_quota_as_a_mail(self):
        self.full_house_then_empty_it()
        self.loop(RecordingProvider())
        self.assertEqual(self.book.used_today(self.clock.now), DAILY)
        self.assertEqual(send_mail.remaining_today(self.clock.now), 0)
        self.assertTrue(all(r["kind"] == "invite" for r in self.book.sends))

    def test_an_empty_waitlist_is_a_quiet_no_op(self):
        p = RecordingProvider()
        tally = self.loop(p)
        self.assertEqual(tally["opened"], 0)
        self.assertEqual(p.mailed, [])
        self.assertEqual(self.book.sends, [])


class UncappedControl(InviteClusterCase):
    """MUTATION 1, run rather than asserted.

    The schema is loaded with the daily_limit ignored -- `limit greatest(free,
    0)`, the shape the function had before this card. Everything else is
    identical. If the delivery test above still passed under this schema, the
    parameter would be decoration.
    """

    @classmethod
    def setUpClass(cls):
        text = H.schema_text()
        mutated = text.replace(
            "limit greatest(least(free, coalesce(daily_limit, 0)), 0)",
            "limit greatest(free, 0)")
        assert mutated != text, "the limit line moved; the mutation missed"
        cls.schema_text = mutated
        super().setUpClass()

    def test_without_the_limit_two_hundred_are_stamped_for_ninety_mails(self):
        self.full_house_then_empty_it()
        opened = self.pg.count(f"select sightstone_run_invites({DAILY});")
        self.assertEqual(opened, CAP,
                         "ignoring daily_limit did not overshoot, so the limit "
                         "is not what is holding the line")
        self.assertGreater(opened, DAILY)

    def test_without_the_limit_a_hundred_and_ten_promises_have_to_be_taken_back(self):
        """The forbidden state, produced on purpose -- and then measured at the
        right place.

        MEASURED, and it changed this test: with the limit ignored the loop
        does NOT end up with stranded rows, because the release path catches
        all 110 and un-stamps them. The forbidden state is repaired rather than
        reached. That is defence in depth working, and it is exactly why the
        assertion cannot be "somebody is left stranded" -- it would be green
        for the wrong reason and the parameter would look like decoration.

        The line that actually separates the two schemas is OPENED == MAILED.
        With the limit, 90 seats open and 90 mails go out and nothing is
        clawed back. Without it, 200 seats open, 90 mails go out, and 110
        people are promised a seat and then quietly un-promised inside the same
        run -- 110 write-backs that only did not become 110 stranded people
        because a second mechanism happened to hold.
        """
        self.full_house_then_empty_it()
        p = RecordingProvider()
        tally = self.loop(p)
        self.assertEqual(tally["opened"], CAP)
        self.assertEqual(tally["mailed"], DAILY)
        self.assertNotEqual(tally["opened"], tally["mailed"],
                            "ignoring daily_limit still opened exactly what it "
                            "could mail, so the limit is not what does that")
        self.assertEqual(tally["released"], CAP - DAILY)
        # the repair held, which is the only reason nobody is stranded here
        self.assertEqual(self.live_stamped_emails() - set(p.mailed), set())


if __name__ == "__main__":
    unittest.main()
