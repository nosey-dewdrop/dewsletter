#!/usr/bin/env python3
"""S9a -- "the quota does not blow up".

The failure this file exists to make impossible: 200 people sign up on launch
day, the provider's free tier cuts off at 100 mails, and person 101 never gets
a confirmation mail. Their account dies unconfirmed and nobody finds out,
because a run that sent 100 of 200 mails looks exactly like a run that sent all
of them.

What is nailed:

1. THE UNIT IS A MAIL. One call carrying 50 addresses spends 50, not 1.
2. THE WINDOWS ROLL. Daily is the last 24 HOURS. date.today() would give the
   same real day two buckets across the UTC / UTC+3 boundary; there is a test
   for exactly that midnight.
3. 2.550 IS THE MONTHLY LINE, not 2.850: inbound mail eats the same quota and
   this ledger cannot see it, so every count here is a lower bound.
4. KIND IS MANDATORY AND CLOSED. bulletin stops at 2.550 so that confirm and
   invite still have room to 3.000 -- a person who cannot confirm is lost, a
   person who misses one digest is not.
5. A PLANNED STOP NEVER ATTEMPTS THE SEND, always writes `halted`, and exits 0.
   Being TOLD about the quota by the provider, or a backlog that grew, exits
   non-zero.
6. A DRY RUN SPENDS NOTHING. 500 rehearsals leave an empty ledger.

Everything is hermetic: no socket, no live data file, a fake clock.

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
from contextlib import redirect_stdout, redirect_stderr
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

HERE = Path(__file__).parent
ENGINE = HERE.parent
sys.path.insert(0, str(ENGINE))

import send_mail  # noqa: E402

SRC = (ENGINE / "send_mail.py").read_text()
LIVE_DATA = ENGINE / "data"
LIVE_JOBS = LIVE_DATA / "jobs.json"

# A fixed instant with a nasty property: 22:00 UTC is 01:00 the NEXT day in
# Damla's timezone, which is where a calendar-day counter breaks.
T0 = datetime(2026, 9, 15, 9, 0, tzinfo=timezone.utc)

_REAL_SOCKET = socket.socket
_REAL_DATA = send_mail.DATA


def _no_network(*args, **kwargs):
    raise AssertionError("a test opened a socket; these tests must be hermetic")


def setUpModule():
    socket.socket = _no_network


def tearDownModule():
    socket.socket = _REAL_SOCKET
    send_mail.DATA = _REAL_DATA
    send_mail.reset_ledger()


# ----------------------------------------------------------------- scaffolding

class Clock:
    """A hand-wound UTC clock. The quota path may read no other one."""

    def __init__(self, start: datetime = T0):
        self.now = start

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kw) -> datetime:
        self.now = self.now + timedelta(**kw)
        return self.now


class CountingProvider(send_mail.Provider):
    """A provider on the real account: no transport, but it costs quota."""

    consumes_quota = True

    def __init__(self, from_addr="the engine <test@example.test>", *a, **kw):
        super().__init__(from_addr)
        self.attempts = 0

    def deliver(self, payload):
        self.attempts += 1
        return send_mail.MessageId(f"fake-{self.attempts}")


class RefusingProvider(CountingProvider):
    """Every call is rejected by the provider, so nothing is charged."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)

    def deliver(self, payload):
        self.attempts += 1
        return send_mail.SoftFail("nope", 422, "invalid_parameter")


class QuotaErrorProvider(CountingProvider):
    """The provider itself says we are over quota -- our counter was wrong."""

    error_name = "daily_quota_exceeded"

    def deliver(self, payload):
        self.attempts += 1
        return send_mail.SoftFail("You have reached your daily quota", 429,
                                  type(self).error_name)


class MonthlyQuotaErrorProvider(QuotaErrorProvider):
    error_name = "monthly_quota_exceeded"


class QuotaCase(unittest.TestCase):
    """Every test gets its own data dir, its own ledger and its own clock."""

    def setUp(self):
        self.data = Path(tempfile.mkdtemp(prefix="s9a-")) / "data"
        self.data.mkdir(parents=True)
        self.addCleanup(shutil.rmtree, self.data.parent, ignore_errors=True)
        self.clock = Clock()
        patch_data = mock.patch.object(send_mail, "DATA", self.data)
        patch_now = mock.patch.object(send_mail, "_now", self.clock)
        patch_data.start()
        patch_now.start()
        self.addCleanup(patch_data.stop)
        self.addCleanup(patch_now.stop)
        self.addCleanup(lambda: (setattr(send_mail, "DATA", _REAL_DATA),
                                 send_mail.reset_ledger()))
        self.book = send_mail.reset_ledger()

    # -- helpers ------------------------------------------------------------
    def provider(self, cls=CountingProvider):
        return cls()

    def burn(self, n: int, kind: str = "bulletin", at: datetime | None = None):
        """Put n mails into the ledger at a chosen instant, no provider needed."""
        self.book.record(kind, n, at or self.clock.now)

    def ledger_file(self) -> dict:
        return json.loads((self.data / "quota_state.json").read_text())


# ------------------------------------------------------------------ kind gate

class KindIsMandatoryAndClosed(QuotaCase):
    def test_send_without_a_kind_is_a_type_error(self):
        """No default: the three kinds share a budget but not a stop line, so a
        caller that will not say which one it is cannot be guessed for."""
        p = self.provider()
        with self.assertRaises(TypeError):
            p.send("a@b.c", "s", "<p>h</p>")

    def test_an_unknown_kind_is_a_value_error(self):
        p = self.provider()
        for bad in ("newsletter", "BULLETIN", "", None, "digest"):
            with self.subTest(kind=bad):
                with self.assertRaises(ValueError):
                    p.send("a@b.c", "s", "<p>h</p>", kind=bad)

    def test_the_three_documented_kinds_are_accepted(self):
        p = self.provider()
        for kind in ("bulletin", "confirm", "invite"):
            with self.subTest(kind=kind):
                out = p.send("a@b.c", "s", "<p>h</p>", kind=kind)
                self.assertIsInstance(out, send_mail.MessageId)
        self.assertEqual(send_mail.MAIL_KINDS,
                         frozenset({"bulletin", "confirm", "invite"}))

    def test_a_rejected_kind_never_reaches_the_transport(self):
        p = self.provider()
        with self.assertRaises(ValueError):
            p.send("a@b.c", "s", "<p>h</p>", kind="whatever")
        self.assertEqual(p.attempts, 0)
        self.assertEqual(self.book.sends, [])

    def test_the_live_bulletin_call_site_names_its_kind(self):
        self.assertIn('kind="bulletin"', SRC)


# --------------------------------------------------------------- the ledger

class TheLedgerRecordsMailsNotCalls(QuotaCase):
    def test_one_send_writes_one_stamped_record(self):
        p = self.provider()
        p.send("a@b.c", "s", "<p>h</p>", kind="confirm")
        self.assertEqual(len(self.book.sends), 1)
        rec = self.book.sends[0]
        self.assertEqual(rec["kind"], "confirm")
        self.assertEqual(rec["count"], 1)
        parsed = datetime.fromisoformat(rec["at"])
        self.assertIsNotNone(parsed.tzinfo, "the stamp is not timezone-aware")
        self.assertEqual(parsed.utcoffset(), timedelta(0), "the stamp is not UTC")

    def test_a_fifty_recipient_call_costs_fifty(self):
        """The provider charges per address. Counting the CALL would let one
        request spend fifty mails while the ledger reads 1."""
        p = self.provider()
        p.send([f"a{i}@b.c" for i in range(50)], "s", "<p>h</p>", kind="invite")
        self.assertEqual(self.book.sends[0]["count"], 50)
        self.assertEqual(self.book.used_today(self.clock.now), 50)
        self.assertEqual(send_mail.remaining_today(self.clock.now), 40)

    def test_two_bulk_calls_cannot_slip_past_the_daily_cap(self):
        p = self.provider()
        first = p.send([f"a{i}@b.c" for i in range(50)], "s", "<p>h</p>",
                       kind="invite")
        second = p.send([f"b{i}@b.c" for i in range(50)], "s", "<p>h</p>",
                        kind="invite")
        self.assertIsInstance(first, send_mail.MessageId)
        self.assertIsInstance(second, send_mail.QuotaHalt,
                              "100 mails went out under a 90 cap")
        self.assertEqual(p.attempts, 1)

    def test_only_an_accepted_call_is_charged(self):
        """A 4xx never reached the provider's counter, so it must not reach
        ours either -- otherwise a broken payload burns the day's budget."""
        p = self.provider(RefusingProvider)
        for _ in range(5):
            p.send("a@b.c", "s", "<p>h</p>", kind="bulletin")
        self.assertEqual(p.attempts, 5)
        self.assertEqual(self.book.sends, [])
        self.assertEqual(send_mail.remaining_today(self.clock.now),
                         send_mail.DAILY_MAIL_CAP)

    def test_remaining_today_is_exported_for_the_seat_opener(self):
        """S9b hands this straight to sightstone_run_invites(daily_limit)."""
        self.assertTrue(callable(send_mail.remaining_today))
        self.assertEqual(send_mail.remaining_today(self.clock.now), 90)
        self.burn(30)
        self.assertEqual(send_mail.remaining_today(self.clock.now), 60)
        self.burn(60)
        self.assertEqual(send_mail.remaining_today(self.clock.now), 0)

    def test_remaining_never_goes_negative(self):
        self.burn(500)
        self.assertEqual(send_mail.remaining_today(self.clock.now), 0)


# ------------------------------------------------------- the windows roll

class ConfirmationsCannotEatTheDay(QuotaCase):
    """Measured 1 Sep against a real cluster: a bot inserting one row at a time
    took 197 of the 200 seats. Every one of those rows is a pending
    confirmation, so unchecked they are a whole day's budget spent on a bot's
    addresses while real subscribers get nothing. The attack costs an afternoon
    and silences the product; the monthly split already reserved for this, the
    DAY did not."""

    def test_confirmations_halt_at_their_own_cap(self):
        p = self.provider()
        for _ in range(send_mail.DAILY_CONFIRM_CAP):
            self.assertIsInstance(p.send("a@b.c", "s", "h", kind="confirm"),
                                  send_mail.MessageId)
        self.assertIsInstance(p.send("a@b.c", "s", "h", kind="confirm"),
                              send_mail.QuotaHalt)

    def test_bulletins_still_go_out_after_confirmations_are_exhausted(self):
        """The whole point: a flood of signups must not silence the product."""
        p = self.provider()
        for _ in range(send_mail.DAILY_CONFIRM_CAP + 5):
            p.send("a@b.c", "s", "h", kind="confirm")
        self.assertIsInstance(p.send("real@b.c", "s", "h", kind="bulletin"),
                              send_mail.MessageId)

    def test_the_reserve_leaves_the_larger_half_to_bulletins(self):
        self.assertLessEqual(send_mail.DAILY_CONFIRM_CAP,
                             send_mail.DAILY_MAIL_CAP // 2)


class TheDailyWindowRolls(QuotaCase):
    def test_the_cap_is_ninety_not_a_hundred(self):
        self.assertEqual(send_mail.DAILY_MAIL_CAP, 90)
        self.assertEqual(send_mail.RESEND_DAILY_QUOTA
                         - send_mail.DAILY_MAIL_CAP, 10)

    def test_a_full_day_is_still_full_one_minute_before_the_window_ends(self):
        self.burn(90)
        self.clock.advance(hours=23, minutes=59)
        self.assertEqual(send_mail.remaining_today(self.clock.now), 0)
        p = self.provider()
        self.assertIsInstance(p.send("a@b.c", "s", "h", kind="confirm"),
                              send_mail.QuotaHalt)

    def test_capacity_returns_once_twenty_four_hours_have_passed(self):
        self.burn(90)
        self.clock.advance(hours=24, minutes=1)
        self.assertEqual(send_mail.remaining_today(self.clock.now), 90)
        p = self.provider()
        self.assertIsInstance(p.send("a@b.c", "s", "h", kind="confirm"),
                              send_mail.MessageId)

    def test_the_window_slides_it_does_not_jump(self):
        """Mails spread over a day expire one by one, not all at midnight."""
        for h in range(9):
            self.burn(10, at=self.clock.now + timedelta(hours=h))
        self.clock.advance(hours=8)
        self.assertEqual(self.book.used_today(self.clock.now), 90)
        self.clock.advance(hours=16, minutes=1)   # the first batch aged out
        self.assertEqual(self.book.used_today(self.clock.now), 80)
        self.clock.advance(hours=1)               # and now the second
        self.assertEqual(self.book.used_today(self.clock.now), 70)

    def test_utc_plus_three_midnight_is_one_bucket_not_two(self):
        """THE BUG: the runner is UTC, Damla is UTC+3. A run at 22:00 UTC is
        01:00 TRT the next day. A calendar counter -- date.today() -- hands the
        same real day a second fresh bucket and 180 mails go out under a cap of
        100. A rolling 24 hours cannot do that."""
        evening = datetime(2026, 9, 15, 22, 0, tzinfo=timezone.utc)
        self.clock.now = evening
        p = self.provider()
        # kind is "bulletin" because this test is about the WINDOW, not about
        # who may spend what. Confirmations now carry their own daily sub-cap
        # (DAILY_CONFIRM_CAP), so 60 of them would legitimately halt here and
        # the halt would say nothing about midnight.
        for _ in range(60):
            self.assertIsInstance(
                p.send("a@b.c", "s", "h", kind="bulletin"), send_mail.MessageId)

        # 01:00 TRT -- a NEW calendar day in Damla's timezone, and a new
        # calendar day in UTC three hours later too.
        self.clock.advance(hours=3, minutes=1)
        self.assertNotEqual(evening.date(), self.clock.now.date(),
                            "the fixture must actually cross UTC midnight")
        self.assertEqual(self.book.used_today(self.clock.now), 60,
                         "the earlier run fell out of the day's count")
        self.assertEqual(send_mail.remaining_today(self.clock.now), 30)

        out = [p.send("a@b.c", "s", "h", kind="confirm") for _ in range(40)]
        accepted = [o for o in out if isinstance(o, send_mail.MessageId)]
        halted = [o for o in out if isinstance(o, send_mail.QuotaHalt)]
        self.assertEqual(len(accepted), 30, "the second run got a fresh bucket")
        self.assertEqual(len(halted), 10)
        self.assertEqual(self.book.used_today(self.clock.now), 90)
        self.assertLess(self.book.used_today(self.clock.now),
                        send_mail.RESEND_DAILY_QUOTA)

    def test_the_quota_path_never_asks_for_a_calendar_day(self):
        """date.today() survives in the mail SUBJECT and in mail_state, where a
        human-readable day is all it is. On the quota path it is the bug: a
        calendar day gives the UTC/UTC+3 boundary two buckets.

        Read from the syntax tree, not from the text, so a comment mentioning
        date.today() cannot fail this and a real call cannot hide in one."""
        import ast
        tree = ast.parse(SRC)
        quota_nodes = []
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name in (
                    "_now", "quota_path", "remaining_today", "ledger",
                    "reset_ledger", "_atomic_write_json"):
                quota_nodes.append(node)
            if isinstance(node, ast.ClassDef) and node.name == "QuotaLedger":
                quota_nodes.append(node)
            if isinstance(node, ast.ClassDef) and node.name == "Provider":
                quota_nodes += [b for b in node.body
                                if isinstance(b, ast.FunctionDef)
                                and b.name == "send"]
        self.assertEqual(len(quota_nodes), 8, "the quota path moved")
        for top in quota_nodes:
            for n in ast.walk(top):
                if isinstance(n, ast.Attribute) and n.attr == "today":
                    self.fail(f"date.today() on the quota path: {top.name}")
        # and the one clock that IS allowed is UTC-aware
        self.assertEqual(send_mail._now().utcoffset(), timedelta(0))


class TheMonthlyWindowIsTheTighterOfTwo(QuotaCase):
    def test_the_rolling_thirty_days_can_be_the_binding_one(self):
        self.burn(1000, at=self.clock.now - timedelta(days=20))   # last month
        self.burn(1000, at=self.clock.now - timedelta(days=5))
        # calendar month sees only the 1000 from this month; rolling sees 2000
        self.assertEqual(self.book.used_month(self.clock.now), 2000)

    def test_the_calendar_month_can_be_the_binding_one(self):
        """A burst early in a long month is invisible to a 30-day window on the
        31st, but the provider's calendar month still remembers it."""
        self.clock.now = datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc)
        self.burn(1200, at=datetime(2026, 10, 1, 1, 0, tzinfo=timezone.utc))
        self.burn(500, at=datetime(2026, 10, 30, 1, 0, tzinfo=timezone.utc))
        rolling = self.book._sum(
            lambda w: w > self.clock.now - send_mail.MONTHLY_WINDOW)
        self.assertEqual(self.book.used_month(self.clock.now), 1700)
        self.assertGreaterEqual(self.book.used_month(self.clock.now), rolling)


# ----------------------------------------------- the bulletin stops first

class TheBulletinStopsBeforeTheOthers(QuotaCase):
    def seed_month(self, n: int):
        """n mails already spent this month, none of them in the last 24h."""
        for i in range(n // 100):
            self.burn(100, at=self.clock.now - timedelta(days=25 - (i % 20),
                                                         hours=i % 20))
        rest = n % 100
        if rest:
            self.burn(rest, at=self.clock.now - timedelta(days=25))
        # the day's window must be clear, or "daily" would mask "monthly"
        self.assertEqual(self.book.used_today(self.clock.now), 0)
        self.assertEqual(self.book.used_month(self.clock.now), n)

    def test_the_line_is_2550_not_2850(self):
        self.assertEqual(send_mail.MONTHLY_BULLETIN_CAP, 2550)
        self.assertEqual(send_mail.RESEND_MONTHLY_QUOTA, 3000)

    def test_the_bulletin_stops_at_2550(self):
        self.seed_month(2550)
        p = self.provider()
        out = p.send("a@b.c", "s", "h", kind="bulletin")
        self.assertIsInstance(out, send_mail.QuotaHalt)
        self.assertEqual(out.reason, "monthly")
        self.assertEqual(p.attempts, 0)

    def test_the_bulletin_still_runs_one_mail_below_the_line(self):
        self.seed_month(2549)
        p = self.provider()
        self.assertIsInstance(p.send("a@b.c", "s", "h", kind="bulletin"),
                              send_mail.MessageId)

    def test_confirm_and_invite_pass_the_bulletin_line(self):
        """The reserve exists FOR them. A person who cannot confirm is lost for
        good; a person who misses one digest is not."""
        self.seed_month(2550)
        p = self.provider()
        for kind in ("confirm", "invite"):
            with self.subTest(kind=kind):
                out = p.send("a@b.c", "s", "h", kind=kind)
                self.assertIsInstance(out, send_mail.MessageId)

    def test_confirm_runs_all_the_way_to_3000(self):
        self.seed_month(2999)
        p = self.provider()
        self.assertIsInstance(p.send("a@b.c", "s", "h", kind="confirm"),
                              send_mail.MessageId)
        self.assertEqual(self.book.used_month(self.clock.now), 3000)

    def test_at_3000_everything_stops(self):
        self.seed_month(3000)
        p = self.provider()
        for kind in ("bulletin", "confirm", "invite"):
            with self.subTest(kind=kind):
                out = p.send("a@b.c", "s", "h", kind=kind)
                self.assertIsInstance(out, send_mail.QuotaHalt)
                self.assertEqual(out.reason, "monthly")
        self.assertEqual(p.attempts, 0)

    def test_a_bulk_call_cannot_straddle_the_line(self):
        self.seed_month(2540)
        p = self.provider()
        out = p.send([f"a{i}@b.c" for i in range(20)], "s", "h", kind="bulletin")
        self.assertIsInstance(out, send_mail.QuotaHalt, "2560 > 2550")
        self.assertEqual(out.deferred, 20)


# ------------------------------------------------------ two hundred signups

class TwoHundredPeopleSignUpAtOnce(QuotaCase):
    """The launch-day scenario, played out on a fake clock."""

    def run_simulation(self, people: int = 200, days: int = 10):
        p = self.provider()
        pending = [f"person{i}@example.test" for i in range(people)]
        confirmed = []
        for _ in range(days * 2):          # two runs a day, 12 hours apart
            for addr in list(pending):
                out = p.send(addr, "confirm your seat", "<p>h</p>",
                             kind="confirm")
                if isinstance(out, send_mail.MessageId):
                    pending.remove(addr)
                    confirmed.append((self.clock.now, addr))
                else:
                    self.assertIsInstance(out, send_mail.QuotaHalt)
                    break
            self.clock.advance(hours=12)
        return confirmed, pending

    def test_no_rolling_day_ever_exceeds_ninety(self):
        confirmed, pending = self.run_simulation()
        stamps = [t for t, _ in confirmed]
        worst = 0
        for start in stamps:
            window = sum(1 for t in stamps
                         if start <= t < start + timedelta(hours=24))
            worst = max(worst, window)
        self.assertLessEqual(worst, send_mail.DAILY_MAIL_CAP,
                             f"a rolling 24h window carried {worst} mails")
        self.assertLess(worst, send_mail.RESEND_DAILY_QUOTA,
                        f"the provider's hard limit was touched: {worst}")
        self.worst = worst

    def test_everybody_is_eventually_confirmed_nobody_is_dropped(self):
        confirmed, pending = self.run_simulation()
        self.assertEqual(pending, [], "someone never got a confirmation mail")
        self.assertEqual(len(confirmed), 200)
        self.assertEqual(len({a for _, a in confirmed}), 200,
                         "somebody was mailed twice")

    def test_the_first_day_is_not_the_whole_two_hundred(self):
        """The point of the ledger: the burst is spread, not truncated."""
        confirmed, _ = self.run_simulation()
        first_day = [t for t, _ in confirmed if t < T0 + timedelta(hours=24)]
        self.assertLessEqual(len(first_day), send_mail.DAILY_MAIL_CAP)
        self.assertGreater(len(confirmed), len(first_day))


# ---------------------------------------------------------- the planned stop

class APlannedStopIsWrittenDown(QuotaCase):
    def subs(self, n=1):
        return [{"email": f"p{i}@example.test", "name": f"p{i}", "level": "bs",
                 "interests": ["machine learning"], "location": "",
                 "unsubscribe_token": None} for i in range(n)]

    def run_main(self, subs, provider=CountingProvider, argv=("send_mail.py",)):
        """A whole run, with the two outside worlds replaced.

        S9b: main() now also drives the seat/invite loop, which speaks
        PostgREST. It is stubbed here rather than allowed to fail, for two
        reasons. A real urlopen would hit the module-wide socket trap and turn
        every quota test into a run with an exception in the middle of it --
        noise that hides the thing under test. And the stub is a MEASUREMENT:
        self.seat_calls records the daily_limit main() handed the database, so
        this file pins the caller from its own side. Deleting the call site
        empties that list.
        """
        shutil.copy(LIVE_JOBS, self.data / "jobs.json")
        env = {"SUPABASE_SERVICE_KEY": "x", "RESEND_API_KEY": "re_test",
               "MAIL_FROM": "the engine <test@example.test>"}
        code = 0
        self.seat_calls = calls = []

        class StubSeats(send_mail.SeatBackend):
            def __init__(self, key, *a, **kw):
                pass

            def run_invites(self, daily_limit):
                calls.append(daily_limit)
                return 0            # no waitlist in these fixtures

            def fresh_invites(self, count):
                return []

            def release_invite(self, token):
                raise AssertionError("nothing was stamped, nothing to release")

        with mock.patch.object(send_mail, "STATE_FILE",
                               self.data / "mail_state.json"), \
                mock.patch.object(send_mail, "fetch_subscribers", lambda k: subs), \
                mock.patch.object(send_mail, "pending_confirmations", lambda k: []), \
                mock.patch.object(send_mail, "ResendProvider", provider), \
                mock.patch.object(send_mail, "SupabaseSeats", StubSeats), \
                mock.patch.dict(os.environ, env, clear=True), \
                mock.patch.object(sys, "argv", list(argv)), \
                redirect_stdout(io.StringIO()) as out, \
                redirect_stderr(io.StringIO()) as err:
            try:
                send_mail.main()
            except SystemExit as exc:
                code = exc.code or 0
        return out.getvalue(), err.getvalue(), code

    def test_main_hands_the_remaining_daily_budget_to_the_seat_opener(self):
        """S9b hole 2, locked from the quota side: a full run reaches the
        invite loop, and what it passes is what is LEFT of today, not a
        constant. One bulletin goes out first, so the number must be 89."""
        self.run_main(self.subs(1))
        self.assertEqual(self.seat_calls, [send_mail.DAILY_MAIL_CAP - 1],
                         "main() did not run the invite loop with the live "
                         "remaining budget")

    def test_a_run_with_no_budget_left_opens_no_seats(self):
        self.burn(send_mail.DAILY_MAIL_CAP)
        self.run_main(self.subs(1))
        self.assertEqual(self.seat_calls, [],
                         "a seat was opened on a day that cannot mail")

    def test_the_halted_key_is_present_even_when_nothing_halted(self):
        """Absence must never stand for a state: a missing key reads the same
        whether the run was clean or the writer died before reaching it."""
        self.run_main(self.subs(1))
        book = self.ledger_file()
        self.assertIn("halted", book)
        self.assertIsNone(book["halted"])

    def test_the_ledger_is_written_on_every_run(self):
        self.run_main(self.subs(1))
        self.assertTrue((self.data / "quota_state.json").exists())
        self.assertGreater(len(self.ledger_file()["sends"]), 0)

    def test_a_halt_names_its_reason_its_moment_and_its_backlog(self):
        self.burn(90)
        out, err, code = self.run_main(self.subs(3))
        halted = self.ledger_file()["halted"]
        self.assertIsNotNone(halted)
        self.assertEqual(halted["reason"], "daily")
        self.assertEqual(halted["deferred"], 3)
        self.assertEqual(datetime.fromisoformat(halted["at"]).utcoffset(),
                         timedelta(0))

    def test_a_halt_says_so_on_stderr(self):
        self.burn(90)
        out, err, code = self.run_main(self.subs(2))
        self.assertIn("QUOTA HALT", err)
        self.assertIn("reason=daily", err)
        self.assertIn("deferred=2", err)

    def test_a_halted_send_is_never_attempted(self):
        self.burn(90)
        seen = {}

        class Watched(CountingProvider):
            def deliver(self, payload):
                seen["called"] = True
                return super().deliver(payload)

        self.run_main(self.subs(3), provider=Watched)
        self.assertNotIn("called", seen,
                         "a send was attempted with the budget already gone")

    def test_a_halted_subscriber_keeps_their_listings_for_next_time(self):
        self.burn(90)
        self.run_main(self.subs(1))
        state = json.loads((self.data / "mail_state.json").read_text()) \
            if (self.data / "mail_state.json").exists() else {}
        self.assertEqual(state, {},
                         "listings were marked as mailed without being mailed")


class TheExitCodeSaysWhichOfTheFour(APlannedStopIsWrittenDown):
    def test_a_normal_run_exits_zero(self):
        _, _, code = self.run_main(self.subs(1))
        self.assertEqual(code, 0)

    def test_a_planned_stop_with_a_steady_backlog_exits_zero(self):
        """The budget ran out and the queue did not grow. Working as designed."""
        self.burn(90)
        self.run_main(self.subs(5))                     # first halt: 0 -> 5
        self.assertEqual(self.ledger_file()["halted"]["deferred"], 5)
        _, err, code = self.run_main(self.subs(5))      # again: 5 -> 5
        self.assertEqual(code, 0, err)
        self.assertIn("QUOTA HALT", err)

    def test_a_growing_backlog_exits_non_zero(self):
        """A queue that keeps growing cannot quietly look like a green run."""
        self.burn(90)
        self.run_main(self.subs(2))
        _, err, code = self.run_main(self.subs(7))
        self.assertNotEqual(code, 0)
        self.assertIn("deferred grew 2 -> 7", err)

    def test_the_provider_reporting_a_daily_quota_error_exits_non_zero(self):
        """Being TOLD we are over means our own counter was wrong. That is a
        fault, not a plan, however tidy the ledger looks."""
        _, err, code = self.run_main(self.subs(1), provider=QuotaErrorProvider)
        self.assertNotEqual(code, 0)
        self.assertIn("quota error", err.lower() + " ")

    def test_the_provider_reporting_a_monthly_quota_error_exits_non_zero(self):
        _, err, code = self.run_main(self.subs(1),
                                     provider=MonthlyQuotaErrorProvider)
        self.assertNotEqual(code, 0)

    def test_an_ordinary_soft_fail_is_not_a_quota_fault(self):
        _, err, code = self.run_main(self.subs(1), provider=RefusingProvider)
        self.assertEqual(code, 0)

    def test_both_quota_error_names_are_the_documented_ones(self):
        self.assertEqual(send_mail.PROVIDER_QUOTA_ERRORS,
                         frozenset({"daily_quota_exceeded",
                                    "monthly_quota_exceeded"}))
        for name in send_mail.PROVIDER_QUOTA_ERRORS:
            self.assertIn(name, send_mail.RESEND_ERROR_DOC)


# ------------------------------------------------------------ the dry run

class ADryRunSpendsNothing(QuotaCase):
    def test_the_flags_say_which_providers_cost_money(self):
        self.assertIs(send_mail.ResendProvider.consumes_quota, True)
        self.assertIs(send_mail.DryRunProvider.consumes_quota, False)
        self.assertIs(send_mail.Provider.consumes_quota, True,
                      "the default must be to COUNT; a subclass that forgets "
                      "to answer cannot be silently exempt")

    def test_five_hundred_rehearsals_leave_an_empty_ledger(self):
        p = send_mail.DryRunProvider("the engine <dry-run@invalid>")
        for i in range(500):
            out = p.send(f"a{i}@b.c", "s", "<p>h</p>", kind="bulletin")
            self.assertIsInstance(out, send_mail.MessageId)
        self.assertEqual(self.book.sends, [], "a dry run ate the real budget")
        self.assertEqual(send_mail.remaining_today(self.clock.now), 90)

    def test_a_dry_run_cannot_be_halted_either(self):
        """Spending nothing means the budget is never in its way, so a
        rehearsal shows the whole run, not the first 90 mails of it."""
        self.burn(90)
        p = send_mail.DryRunProvider("the engine <dry-run@invalid>")
        for i in range(50):
            self.assertIsInstance(
                p.send(f"a{i}@b.c", "s", "h", kind="bulletin"),
                send_mail.MessageId)


class TheLiveDataDirectoryIsUntouched(unittest.TestCase):
    def test_five_hundred_dry_sends_leave_engine_data_byte_identical(self):
        before = {p.name: p.read_bytes() for p in sorted(LIVE_DATA.iterdir())
                  if p.is_file()}

        def sweep():
            """If this test ever goes red it must not leave the evidence behind:
            a stray quota_state.json in engine/data would show up as an
            uncommitted file long after the run that made it."""
            for q in LIVE_DATA.iterdir():
                if q.is_file() and q.name not in before:
                    q.unlink()

        self.addCleanup(sweep)
        p = send_mail.DryRunProvider("the engine <dry-run@invalid>")
        for i in range(500):
            p.send(f"a{i}@b.c", "s", "<p>h</p>", kind="bulletin")
        after = {q.name: q.read_bytes() for q in sorted(LIVE_DATA.iterdir())
                 if q.is_file()}
        self.assertEqual(set(before), set(after),
                         "a dry run created or removed a file in engine/data")
        for name in before:
            self.assertEqual(before[name], after[name], f"{name} changed")

    def test_the_ledger_path_follows_data_so_a_sandbox_cannot_be_missed(self):
        self.assertEqual(send_mail.quota_path(),
                         send_mail.DATA / "quota_state.json")
        tmp = Path(tempfile.mkdtemp(prefix="s9a-path-"))
        try:
            with mock.patch.object(send_mail, "DATA", tmp):
                self.assertEqual(send_mail.quota_path(), tmp / "quota_state.json")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


# ------------------------------------------------------------ file discipline

class TheLedgerFileSurvivesAbuse(QuotaCase):
    def test_a_corrupt_ledger_does_not_kill_the_run(self):
        (self.data / "quota_state.json").write_text("{not json")
        book = send_mail.reset_ledger()
        self.assertEqual(book.sends, [])

    def test_records_older_than_every_window_are_pruned(self):
        self.burn(5, at=self.clock.now - timedelta(days=400))
        self.burn(5, at=self.clock.now - timedelta(days=2))
        self.book.save(self.clock.now)
        self.assertEqual(len(self.ledger_file()["sends"]), 1)

    def test_the_current_calendar_month_is_never_pruned(self):
        """A 30-day window would forget the 1st of a 31-day month; the
        provider's calendar month would not."""
        self.clock.now = datetime(2026, 10, 31, 23, 0, tzinfo=timezone.utc)
        self.burn(7, at=datetime(2026, 10, 1, 0, 30, tzinfo=timezone.utc))
        self.book.save(self.clock.now)
        self.assertEqual(len(self.ledger_file()["sends"]), 1)
        self.assertEqual(send_mail.reset_ledger().used_month(self.clock.now), 7)

    def test_the_ledger_is_written_whole_or_not_at_all(self):
        p = self.provider()
        p.send("a@b.c", "s", "h", kind="confirm")
        leftovers = [q.name for q in self.data.iterdir()
                     if q.name.endswith(".tmp")]
        self.assertEqual(leftovers, [])
        json.loads((self.data / "quota_state.json").read_text())


if __name__ == "__main__":
    unittest.main()
