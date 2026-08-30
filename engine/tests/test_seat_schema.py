#!/usr/bin/env python3
"""Seat arithmetic, read straight out of the source. No server needed.

This is the layer that runs everywhere, CI included. It cannot prove the
advisory lock stops a race -- only a real cluster can, and test_seat_behavior
does that -- but it CAN prove the things a race test would silently pass
without: that the lock is the FIRST statement in the trigger rather than a line
somewhere after the count, that the count has all three terms, and that the
capacity number is the same in all four places it is written down.

The four places are not a style complaint. Capacity lives in schema.sql twice
(the cap trigger and the seats() json), in engine/data/seats.json, and in the
build_site.py fallback. Three of them agreeing and one disagreeing is a site
that advertises a number the database will not honour, so each one is parsed
separately here and then compared.

Run: python3 -m unittest discover engine/tests
"""
import ast
import json
import re
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).parent
ENGINE = HERE.parent
sys.path.insert(0, str(ENGINE))

SCHEMA = (ENGINE / "schema.sql").read_text()
SEATS_JSON = ENGINE / "data" / "seats.json"
BUILD_SITE = ENGINE / "build_site.py"

CAPACITY = 200


def sql_function(name: str, body: str = SCHEMA) -> str:
    """The body of one create-or-replace function, dollar-quote to dollar-quote.

    Splitting on `$$` is safe here because schema.sql uses exactly one dollar
    quoting style and never nests it.
    """
    # The trailing "(" matters: sightstone_seats is a prefix of
    # sightstone_seats_taken, and the taken one is declared first.
    marker = f"create or replace function {name}("
    start = body.index(marker)
    chunks = body[start:].split("$$")
    if len(chunks) < 3:
        raise AssertionError(f"{name} has no dollar-quoted body")
    return chunks[1]


def strip_sql_comments(text: str) -> str:
    return "\n".join(line.split("--")[0] for line in text.splitlines())


def statements(body: str) -> list[str]:
    """Executable statements of a plpgsql body, comments and blanks removed.

    `begin` carries no semicolon of its own, so it is peeled off first --
    otherwise it would ride along glued to the statement after it and hide
    which statement really comes first.
    """
    inner = strip_sql_comments(body).strip()
    if inner.startswith("declare"):
        inner = inner[inner.index("begin"):]
    self_begin = re.match(r"begin\b", inner)
    if self_begin:
        inner = inner[self_begin.end():]
    return [s.strip() for s in inner.split(";") if s.strip()]


class CapacityIsOneNumber(unittest.TestCase):
    """All four writings of the capacity, parsed apart, then compared."""

    def cap_from_trigger(self) -> int:
        body = sql_function("sightstone_enforce_cap")
        m = re.search(r"sightstone_seats_taken\(\)\s*>=\s*(\d+)", body)
        self.assertIsNotNone(m, "cap trigger no longer compares against a number")
        return int(m.group(1))

    def cap_from_seats_fn(self) -> int:
        body = sql_function("sightstone_seats")
        m = re.search(r"'capacity'\s*,\s*(\d+)", body)
        self.assertIsNotNone(m, "seats() no longer reports a capacity literal")
        return int(m.group(1))

    def cap_from_seats_json(self) -> int:
        return json.loads(SEATS_JSON.read_text())["capacity"]

    def cap_from_build_site(self) -> int:
        """The fallback dict in build_site, found by parsing the module, not by
        grepping for a number that also appears in CSS widths and CV scores."""
        tree = ast.parse(BUILD_SITE.read_text())
        found = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Dict):
                continue
            keys = [k.value for k in node.keys
                    if isinstance(k, ast.Constant) and isinstance(k.value, str)]
            if sorted(keys) == ["capacity", "taken"]:
                idx = keys.index("capacity")
                value = node.values[idx]
                self.assertIsInstance(value, ast.Constant)
                found.append(value.value)
        self.assertEqual(len(found), 1,
                         f"expected exactly one seats fallback dict, got {found}")
        return found[0]

    def test_all_four_places_agree(self):
        places = {
            "schema.sql cap trigger": self.cap_from_trigger(),
            "schema.sql seats() json": self.cap_from_seats_fn(),
            "engine/data/seats.json": self.cap_from_seats_json(),
            "build_site.py fallback": self.cap_from_build_site(),
        }
        self.assertEqual(len(set(places.values())), 1,
                         f"capacity disagrees across places: {places}")
        self.assertEqual(set(places.values()), {CAPACITY}, places)

    def test_comments_do_not_still_say_the_old_number(self):
        """The two prose lines that name the seat count are part of the six
        places the number is written. A comment saying 100 over a trigger
        saying 200 is a lie left in the file for the next reader."""
        stale = [ln.strip() for ln in SCHEMA.splitlines()
                 if ln.strip().startswith("--") and re.search(r"\b100 koltuk\b", ln)]
        self.assertEqual(stale, [], f"comments still advertise 100 seats: {stale}")
        self.assertTrue(
            any("200 koltuk" in ln for ln in SCHEMA.splitlines()),
            "no comment states the seat count at all")


class LockIsFirst(unittest.TestCase):
    """The lock has to be taken BEFORE the count, or it locks nothing."""

    def test_advisory_lock_is_the_first_statement_of_the_cap_trigger(self):
        stmts = statements(sql_function("sightstone_enforce_cap"))
        self.assertIn("pg_advisory_xact_lock", stmts[0],
                      f"first executable statement is {stmts[0]!r}, not the lock")
        self.assertIn("hashtext('sightstone_seats')", stmts[0])

    def test_lock_precedes_the_count_textually(self):
        body = sql_function("sightstone_enforce_cap")
        self.assertLess(body.index("pg_advisory_xact_lock"),
                        body.index("sightstone_seats_taken"),
                        "the count is read before the lock is held")

    def test_every_seat_mutating_function_takes_the_same_lock(self):
        """One function skipping the lock reopens the race through a side door."""
        for fn in ("sightstone_enforce_cap", "sightstone_waitlist_guard",
                   "sightstone_accept_invite", "sightstone_run_invites"):
            with self.subTest(fn=fn):
                body = sql_function(fn)
                self.assertIn("pg_advisory_xact_lock(hashtext('sightstone_seats'))",
                              body, f"{fn} does not serialise on the seat lock")


class ThreeTermCount(unittest.TestCase):
    """free = capacity - confirmed - (unconfirmed under 48h) - (open invites)."""

    def setUp(self):
        self.body = strip_sql_comments(sql_function("sightstone_seats_taken"))

    def test_first_term_confirmed_and_not_unsubscribed(self):
        self.assertIn("unsubscribed_at is null", self.body)
        self.assertIn("confirmed_at is not null", self.body)

    def test_second_term_unconfirmed_but_inside_the_48_hour_grace(self):
        self.assertRegex(
            self.body,
            r"created_at\s*>\s*now\(\)\s*-\s*interval\s*'48 hours'")

    def test_third_term_counts_invites_still_awaiting_an_answer(self):
        self.assertIn("sightstone_waitlist", self.body,
                      "seat count ignores the waitlist entirely: an outstanding "
                      "invite would leave its seat looking free")
        self.assertIn("invited_at is not null", self.body)
        self.assertIn("accepted_at is null", self.body)
        self.assertRegex(self.body, r"invite_expires_at\s*>\s*now\(\)")

    def test_count_is_summed_not_picked(self):
        """Two subqueries added together, not one subquery with the waitlist
        mentioned in passing."""
        self.assertEqual(self.body.count("select count(*)"), 2, self.body)
        self.assertIn("+", self.body)


class SchemaShape(unittest.TestCase):
    def test_confirmed_at_column_exists_and_is_added_idempotently(self):
        self.assertRegex(
            SCHEMA,
            r"add column if not exists confirmed_at timestamptz")

    def test_waitlist_table_exists_with_an_ordering_column(self):
        self.assertIn("create table if not exists sightstone_waitlist", SCHEMA)
        for col in ("invite_token", "invited_at", "invite_expires_at",
                    "accepted_at", "dropped_at", "created_at"):
            with self.subTest(col=col):
                self.assertIn(col, SCHEMA)

    def test_invites_go_to_the_oldest_waiter(self):
        body = sql_function("sightstone_run_invites")
        self.assertRegex(body, r"order by created_at")

    def test_hard_bounce_releases_the_seat(self):
        body = sql_function("sightstone_mark_bounce")
        self.assertIn("set unsubscribed_at = now()", body)

    def test_privileged_functions_are_revoked_from_public(self):
        """Withholding a grant is NOT enough, and this was measured.

        PostgreSQL hands EXECUTE to PUBLIC on every new function, so a
        security-definer function with no grant line was still callable by
        anon: anon could evict any subscriber by address, or drive the invite
        loop on demand. The revoke is what actually closes it.
        """
        for fn in ("sightstone_mark_bounce(text)", "sightstone_run_invites()",
                   "sightstone_seats_taken()"):
            with self.subTest(fn=fn):
                self.assertIn(f"revoke execute on function {fn} from public",
                              SCHEMA)
                self.assertNotIn(f"grant execute on function {fn} to anon",
                                 SCHEMA)

    def test_rls_is_on_for_both_tables(self):
        for table in ("sightstone_subscribers", "sightstone_waitlist"):
            with self.subTest(table=table):
                self.assertIn(f"alter table {table} enable row level security",
                              SCHEMA)

    def test_anon_policies_are_insert_only(self):
        for policy in ("sightstone_anon_signup", "sightstone_anon_waitlist"):
            with self.subTest(policy=policy):
                start = SCHEMA.index(f"create policy {policy}")
                block = SCHEMA[start:start + 240]
                self.assertIn("for insert to anon", block)
                self.assertIn("mail_consent = true", block)
                self.assertIn("kvkk_accepted_at is not null", block)

    def test_the_nightly_window_is_written_down_not_hidden(self):
        """D8's known gap is disclosed at the head of the file."""
        head = SCHEMA[:SCHEMA.index("create extension")]
        self.assertIn("24 saat", head)
        self.assertIn("sightstone_run_invites", head)


if __name__ == "__main__":
    unittest.main()
