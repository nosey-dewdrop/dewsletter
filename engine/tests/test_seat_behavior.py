#!/usr/bin/env python3
"""The seat rules, executed by a real PostgreSQL, not read as text.

test_seat_schema proves the advisory lock LINE is in the file. This file proves
the line does something: with it, 199 filled seats plus twenty simultaneous
signups end at exactly 200; with the line deleted the same run ends at 219.
Nothing short of twenty concurrent server sessions can tell those two schemas
apart, which is why the harness builds a throwaway cluster.

It is a throwaway. initdb into a temp dir, a unix socket in that same dir, and
`pg_ctl stop` plus rmtree on the way out. The production Supabase is never
contacted, and there is no code path here that could.

If postgres is not installed everything below skips, so a CI runner without it
still reports green rather than red.

Winding the clock: the 48 hour rules are all of the form
`created_at > now() - interval '48 hours'`, which depends on nothing but the
DIFFERENCE between the two. There is no way to move a running server's clock
without libfaketime, so these tests move the row instead -- pushing created_at
49 hours into the past is arithmetically the same event as the clock advancing
49 hours, and it is deterministic where a sleeping test would not be.

Run: python3 -m unittest discover engine/tests
"""
import unittest

import pg_harness as H

CAP = 200

# sightstone_run_invites now takes the day's mail budget (S9b), so the calls
# below pass 10000: everything in THIS file is about seats, not about the mail
# cap, and the seat arithmetic has to come out exactly as it did before the
# parameter existed. A limit that cannot bind is how that is held still. The
# cap's own behaviour is measured in test_invite_delivery.py.


def sql_str(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


class ClusterCase(unittest.TestCase):
    """One cluster for the whole class; tables emptied between tests."""

    schema_text = None          # None means "the real schema.sql"
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
        self.pg.run("truncate sightstone_subscribers, sightstone_waitlist;")

    # -- helpers -----------------------------------------------------------
    def fill(self, n: int, confirmed: bool = True, prefix: str = "s") -> None:
        """n seats occupied, one INSERT so the cap trigger sees every row."""
        conf = "now()" if confirmed else "null"
        self.pg.run(
            "insert into sightstone_subscribers"
            "(email, mail_consent, kvkk_accepted_at, confirmed_at) "
            f"select {sql_str(prefix)}||g||'@example.test', true, now(), {conf} "
            f"from generate_series(1,{n}) g;")

    def taken(self) -> int:
        return self.pg.count("select sightstone_seats_taken();")

    def live_rows(self) -> int:
        return self.pg.count(
            "select count(*) from sightstone_subscribers "
            "where unsubscribed_at is null;")

    def age_subscriber(self, email: str, hours: int) -> None:
        """Wind the clock forward by pushing one row's created_at back."""
        self.pg.run(
            "update sightstone_subscribers "
            f"set created_at = created_at - interval '{hours} hours' "
            f"where email = {sql_str(email)};")

    def wait(self, email: str) -> None:
        self.pg.run(
            "insert into sightstone_waitlist(email, mail_consent, kvkk_accepted_at) "
            f"values ({sql_str(email)}, true, now());")


class Concurrency(ClusterCase):
    """The measurement the advisory lock exists for."""

    def test_199_seats_plus_20_simultaneous_signups_lands_on_exactly_200(self):
        self.fill(199)
        self.assertEqual(self.taken(), 199)

        # Twenty separate OS processes. Each holds its transaction open across
        # a half-second sleep, so every one of them overlaps every other; this
        # is the window an unlocked count reads stale data through.
        procs = [self.pg.spawn(
            "begin; "
            "insert into sightstone_subscribers"
            "(email, mail_consent, kvkk_accepted_at, confirmed_at) "
            f"values ('race{i}@example.test', true, now(), now()); "
            "select pg_sleep(0.5); commit;") for i in range(20)]
        # communicate() drains AND closes the pipes; a bare wait() leaks them.
        for p in procs:
            p.communicate()
        codes = [p.returncode for p in procs]

        seats = self.live_rows()
        self.assertEqual(seats, CAP,
                         f"cap breached: {seats} rows for {CAP} seats "
                         f"({codes.count(0)} of 20 inserts committed)")
        self.assertLessEqual(seats, CAP)
        self.assertEqual(codes.count(0), 1,
                         "exactly one of the twenty should win the last seat")

    def test_the_201st_signup_is_refused_outright(self):
        self.fill(CAP)
        proc = self.pg.run(
            "insert into sightstone_subscribers"
            "(email, mail_consent, kvkk_accepted_at, confirmed_at) "
            "values ('over@example.test', true, now(), now());", check=False)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("no seats left", proc.stderr)


class UnlockedControl(ClusterCase):
    """MUTATION 1, nailed down as a test instead of a claim in a report.

    The same cluster, the same twenty sessions, one line removed. If deleting
    the advisory lock did NOT break the cap, the lock would be decoration and
    the test above would be passing for some unrelated reason.
    """

    @classmethod
    def setUpClass(cls):
        text = H.schema_text()
        stripped = "\n".join(
            ln for ln in text.splitlines()
            if "pg_advisory_xact_lock" not in ln)
        assert stripped != text, "no advisory lock line to remove"
        cls.schema_text = stripped
        super().setUpClass()

    def test_without_the_lock_the_same_run_overshoots_the_cap(self):
        self.fill(199)
        procs = [self.pg.spawn(
            "begin; "
            "insert into sightstone_subscribers"
            "(email, mail_consent, kvkk_accepted_at, confirmed_at) "
            f"values ('race{i}@example.test', true, now(), now()); "
            "select pg_sleep(0.5); commit;") for i in range(20)]
        for p in procs:
            p.communicate()
        seats = self.live_rows()
        self.assertGreater(seats, CAP,
                           "removing the lock did not break the cap, so the "
                           "lock is not what is holding it")


class FortyEightHours(ClusterCase):
    """An unconfirmed signup rents the seat. It does not own it."""

    def test_unconfirmed_signup_holds_its_seat_before_48_hours(self):
        self.fill(1, confirmed=False, prefix="u")
        self.assertEqual(self.taken(), 1)

    def test_unconfirmed_signup_releases_the_seat_after_48_hours(self):
        self.fill(1, confirmed=False, prefix="u")
        self.assertEqual(self.taken(), 1)
        self.age_subscriber("u1@example.test", 49)
        self.assertEqual(self.taken(), 0,
                         "a typo'd address still holds the seat after 48h")
        # The row is still there; it just stopped counting.
        self.assertEqual(self.live_rows(), 1)

    def test_a_confirmed_signup_never_expires(self):
        self.fill(1, confirmed=True, prefix="c")
        self.age_subscriber("c1@example.test", 24 * 400)
        self.assertEqual(self.taken(), 1)

    def test_the_released_seat_is_reusable(self):
        self.fill(CAP, confirmed=False, prefix="u")
        self.age_subscriber("u1@example.test", 49)
        self.assertEqual(self.taken(), CAP - 1)
        self.pg.run(
            "insert into sightstone_subscribers"
            "(email, mail_consent, kvkk_accepted_at, confirmed_at) "
            "values ('late@example.test', true, now(), now());")
        self.assertEqual(self.taken(), CAP)

    def test_confirming_inside_the_window_makes_the_seat_permanent(self):
        self.fill(1, confirmed=False, prefix="u")
        token = self.pg.scalar(
            "select confirm_token from sightstone_subscribers "
            "where email = 'u1@example.test';")
        self.assertEqual(
            self.pg.scalar(f"select sightstone_confirm('{token}');"), "t")
        self.age_subscriber("u1@example.test", 49)
        self.assertEqual(self.taken(), 1)

    def test_confirming_after_the_window_is_refused(self):
        self.fill(1, confirmed=False, prefix="u")
        token = self.pg.scalar(
            "select confirm_token from sightstone_subscribers "
            "where email = 'u1@example.test';")
        self.age_subscriber("u1@example.test", 49)
        self.assertEqual(
            self.pg.scalar(f"select sightstone_confirm('{token}');"), "f")


class HardBounce(ClusterCase):
    def test_hard_bounce_frees_the_seat_immediately(self):
        self.fill(CAP)
        self.assertEqual(self.taken(), CAP)
        self.assertEqual(
            self.pg.scalar("select sightstone_mark_bounce('s7@example.test');"),
            "t")
        self.assertEqual(self.taken(), CAP - 1)
        self.assertIsNotNone(self.pg.scalar(
            "select unsubscribed_at from sightstone_subscribers "
            "where email = 's7@example.test';"))

    def test_bouncing_the_same_address_twice_frees_only_one_seat(self):
        self.fill(CAP)
        self.pg.scalar("select sightstone_mark_bounce('s7@example.test');")
        self.assertEqual(
            self.pg.scalar("select sightstone_mark_bounce('s7@example.test');"),
            "f")
        self.assertEqual(self.taken(), CAP - 1)


class WaitlistAndInvites(ClusterCase):
    """Seat frees up, oldest waiter gets it, and only the oldest waiter."""

    def full_house_with_two_waiters(self):
        self.fill(CAP)
        self.wait("first@example.test")
        self.wait("second@example.test")

    def invited(self) -> list[str]:
        out = self.pg.scalar(
            "select coalesce(string_agg(email, ',' order by invited_at, email), '') "
            "from sightstone_waitlist "
            "where invited_at is not null and accepted_at is null "
            "and dropped_at is null;")
        return [e for e in out.split(",") if e]

    def test_d8_nobody_may_wait_while_a_seat_is_free(self):
        self.fill(CAP - 1)
        proc = self.pg.run(
            "insert into sightstone_waitlist"
            "(email, mail_consent, kvkk_accepted_at) "
            "values ('early@example.test', true, now());", check=False)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("seats available", proc.stderr)

    def test_waitlist_opens_only_once_the_house_is_full(self):
        self.fill(CAP)
        self.wait("first@example.test")
        self.assertEqual(
            self.pg.count("select count(*) from sightstone_waitlist;"), 1)

    def test_no_invite_goes_out_while_the_house_is_full(self):
        self.full_house_with_two_waiters()
        self.assertEqual(
            self.pg.count("select sightstone_run_invites(10000);"), 0)
        self.assertEqual(self.invited(), [])

    def test_a_freed_seat_invites_the_oldest_waiter_only(self):
        self.full_house_with_two_waiters()
        self.pg.run("select sightstone_mark_bounce('s3@example.test');")
        self.assertEqual(self.pg.count("select sightstone_run_invites(10000);"), 1)
        self.assertEqual(self.invited(), ["first@example.test"])

    def test_three_term_count_stops_the_same_seat_being_invited_twice(self):
        """MUTATION 2's target, from the other side.

        One seat frees. The loop invites `first`. On the next daily run the
        seat is still not occupied by anyone -- `first` has not answered yet --
        so a two-term count would call it free and invite `second` to the very
        same seat. The third term is what makes the second run send nothing.
        """
        self.full_house_with_two_waiters()
        self.pg.run("select sightstone_mark_bounce('s3@example.test');")

        self.assertEqual(self.pg.count("select sightstone_run_invites(10000);"), 1)
        self.assertEqual(self.pg.count("select sightstone_run_invites(10000);"), 0)
        self.assertEqual(self.pg.count("select sightstone_run_invites(10000);"), 0)

        self.assertEqual(self.invited(), ["first@example.test"],
                         "one seat, more than one live invite")
        self.assertEqual(
            self.pg.count("select count(*) from sightstone_waitlist "
                          "where invited_at is not null;"), 1)

    def test_an_open_invite_is_counted_as_an_occupied_seat(self):
        self.full_house_with_two_waiters()
        self.pg.run("select sightstone_mark_bounce('s3@example.test');")
        self.assertEqual(self.taken(), CAP - 1)
        self.pg.run("select sightstone_run_invites(10000);")
        self.assertEqual(self.taken(), CAP,
                         "the reserved seat is not being counted")

    def test_an_unanswered_invite_expires_and_passes_to_the_next_in_line(self):
        self.full_house_with_two_waiters()
        self.pg.run("select sightstone_mark_bounce('s3@example.test');")
        self.pg.run("select sightstone_run_invites(10000);")
        self.assertEqual(self.invited(), ["first@example.test"])

        # 48 hours pass with no answer.
        self.pg.run("update sightstone_waitlist set "
                    "invited_at = invited_at - interval '49 hours', "
                    "invite_expires_at = invite_expires_at - interval '49 hours' "
                    "where email = 'first@example.test';")
        self.assertEqual(self.pg.count("select sightstone_run_invites(10000);"), 1)
        self.assertEqual(self.invited(), ["second@example.test"])
        self.assertIsNotNone(self.pg.scalar(
            "select dropped_at from sightstone_waitlist "
            "where email = 'first@example.test';"))

    def test_accepting_an_invite_turns_the_waiter_into_a_confirmed_subscriber(self):
        self.full_house_with_two_waiters()
        self.pg.run("select sightstone_mark_bounce('s3@example.test');")
        self.pg.run("select sightstone_run_invites(10000);")
        token = self.pg.scalar(
            "select invite_token from sightstone_waitlist "
            "where email = 'first@example.test';")
        self.assertEqual(
            self.pg.scalar(f"select sightstone_accept_invite('{token}');"), "t")

        self.assertEqual(self.taken(), CAP)
        self.assertEqual(self.pg.count(
            "select count(*) from sightstone_subscribers "
            "where email = 'first@example.test' "
            "and confirmed_at is not null;"), 1)
        # And the seat is not handed out a second time.
        self.assertEqual(self.pg.count("select sightstone_run_invites(10000);"), 0)

    def test_an_expired_invite_cannot_be_accepted(self):
        self.full_house_with_two_waiters()
        self.pg.run("select sightstone_mark_bounce('s3@example.test');")
        self.pg.run("select sightstone_run_invites(10000);")
        token = self.pg.scalar(
            "select invite_token from sightstone_waitlist "
            "where email = 'first@example.test';")
        self.pg.run("update sightstone_waitlist set "
                    "invite_expires_at = invite_expires_at - interval '49 hours' "
                    "where email = 'first@example.test';")
        self.assertEqual(
            self.pg.scalar(f"select sightstone_accept_invite('{token}');"), "f")
        self.assertEqual(self.pg.count(
            "select count(*) from sightstone_subscribers "
            "where email = 'first@example.test';"), 0)

    def test_a_random_token_accepts_nothing(self):
        self.full_house_with_two_waiters()
        self.assertEqual(self.pg.scalar(
            "select sightstone_accept_invite("
            "'00000000-0000-0000-0000-000000000000');"), "f")


class TwoTermControl(ClusterCase):
    """MUTATION 2 as a test: drop the third term, watch the double invite.

    The waitlist half of sightstone_seats_taken() is cut out, leaving the
    two-term count the draft assumed was enough.
    """

    @classmethod
    def setUpClass(cls):
        text = H.schema_text()
        start = text.index("create or replace function sightstone_seats_taken(")
        end = text.index("$$;", text.index("$$", start) + 2) + 3
        two_term = (
            "create or replace function sightstone_seats_taken() returns int\n"
            "language sql security definer stable as $$\n"
            "  select (select count(*)::int from sightstone_subscribers\n"
            "           where unsubscribed_at is null\n"
            "             and (confirmed_at is not null\n"
            "                  or created_at > now() - interval '48 hours'));\n"
            "$$;")
        cls.schema_text = text[:start] + two_term + text[end:]
        assert "sightstone_waitlist\n           where invited_at" not in \
            cls.schema_text[start:start + len(two_term)]
        super().setUpClass()

    def test_a_two_term_count_invites_two_people_to_one_seat(self):
        self.fill(CAP)
        self.wait("first@example.test")
        self.wait("second@example.test")
        self.pg.run("select sightstone_mark_bounce('s3@example.test');")

        self.pg.run("select sightstone_run_invites(10000);")
        self.pg.run("select sightstone_run_invites(10000);")

        live = self.pg.count(
            "select count(*) from sightstone_waitlist "
            "where invited_at is not null and accepted_at is null "
            "and dropped_at is null;")
        self.assertGreater(live, 1,
                           "dropping the third term did not cause a double "
                           "invite, so the third term is not what prevents it")


class RlsRegression(ClusterCase):
    """A lock on today's behaviour, not a fix for it.

    anon was measured working correctly before this card; these tests exist so
    a later edit cannot quietly open it. Supabase grants anon table privileges
    by default and relies on RLS to hold the line, so the harness reproduces
    that grant -- otherwise the test would pass on a plain permission error and
    prove nothing about the policies.
    """

    def setUp(self):
        super().setUp()
        self.pg.run(
            "grant usage on schema public to anon; "
            "grant select, insert, update, delete on sightstone_subscribers "
            "to anon; "
            "grant select, insert, update, delete on sightstone_waitlist to anon;")

    def as_anon(self, sql: str):
        return self.pg.run(f"set role anon; {sql}", check=False)

    def anon_scalar(self, sql: str) -> str:
        return self.pg.scalar(f"set role anon; {sql}")

    def test_anon_selects_nothing_from_subscribers(self):
        self.fill(3)
        self.assertEqual(
            self.anon_scalar("select count(*) from sightstone_subscribers;"), "0")

    def test_anon_selects_nothing_from_the_waitlist(self):
        self.fill(CAP)
        self.wait("first@example.test")
        self.assertEqual(
            self.anon_scalar("select count(*) from sightstone_waitlist;"), "0")

    def test_anon_cannot_read_a_single_email_or_token(self):
        self.fill(3)
        # cv_text is gone (A3). Nothing ever wrote it, but a column standing
        # ready to hold CV text made "the CV never leaves your browser" a
        # matter of nobody having written the insert yet rather than the schema
        # refusing to hold one. schema.sql drops it; there is no column left
        # here to protect.
        for col in ("email", "unsubscribe_token", "confirm_token"):
            with self.subTest(col=col):
                self.assertEqual(
                    self.anon_scalar(
                        f"select count({col}) from sightstone_subscribers;"), "0")

    def test_anon_updates_zero_rows(self):
        self.fill(3)
        self.as_anon("update sightstone_subscribers set name = 'pwned';")
        self.assertEqual(self.pg.count(
            "select count(*) from sightstone_subscribers "
            "where name = 'pwned';"), 0)

    def test_anon_deletes_zero_rows(self):
        self.fill(3)
        self.as_anon("delete from sightstone_subscribers;")
        self.assertEqual(self.live_rows(), 3)

    def test_anon_cannot_unsubscribe_someone_by_writing_the_column(self):
        self.fill(3)
        self.as_anon("update sightstone_subscribers set unsubscribed_at = now();")
        self.assertEqual(self.taken(), 3)

    def test_insert_without_mail_consent_is_refused_by_rls(self):
        proc = self.as_anon(
            "insert into sightstone_subscribers"
            "(email, mail_consent, kvkk_accepted_at) "
            "values ('nc@example.test', false, now());")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("row-level security", proc.stderr)
        self.assertEqual(self.live_rows(), 0)

    def test_insert_without_kvkk_is_refused_by_rls(self):
        proc = self.as_anon(
            "insert into sightstone_subscribers"
            "(email, mail_consent, kvkk_accepted_at) "
            "values ('nk@example.test', true, null);")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("row-level security", proc.stderr)
        self.assertEqual(self.live_rows(), 0)

    def test_a_proper_consented_signup_still_goes_through(self):
        proc = self.as_anon(
            "insert into sightstone_subscribers"
            "(email, mail_consent, kvkk_accepted_at) "
            "values ('ok@example.test', true, now());")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.live_rows(), 1)

    def test_waitlist_insert_without_consent_is_refused_by_rls(self):
        self.fill(CAP)
        proc = self.as_anon(
            "insert into sightstone_waitlist"
            "(email, mail_consent, kvkk_accepted_at) "
            "values ('w@example.test', false, now());")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("row-level security", proc.stderr)

    def test_anon_cannot_run_the_invite_loop_or_the_bounce_hook(self):
        """Neither is granted to anon: one hands out seats, the other evicts."""
        for call in ("sightstone_run_invites(10000)",
                     "sightstone_mark_bounce('s1@example.test')"):
            with self.subTest(call=call):
                proc = self.as_anon(f"select {call};")
                self.assertNotEqual(proc.returncode, 0)
                self.assertIn("permission denied", proc.stderr)

    def test_anon_may_still_read_the_public_seat_counter(self):
        """The counter is the one thing anon is supposed to see."""
        self.fill(5)
        out = self.anon_scalar("select sightstone_seats();")
        self.assertIn(f'"capacity" : {CAP}', out)
        self.assertIn('"taken" : 5', out)


if __name__ == "__main__":
    unittest.main()
