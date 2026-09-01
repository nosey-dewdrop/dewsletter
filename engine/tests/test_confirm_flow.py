#!/usr/bin/env python3
"""S10 -- "it does not arrive unless I said yes".

D2 made send_mail drop every row whose confirmed_at is null. On its own that
also shut the front door: a stranger signs up and can never be mailed, because
nothing ever offers them a way to say "yes, that is me". This file measures the
other half -- the confirmation mail and the page its link lands on.

Hermetic: no socket, no provider, no production file written.

Run: python3 -m unittest discover engine/tests -v
"""
import json
import shutil
import socket
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).parent
ENGINE = HERE.parent
sys.path.insert(0, str(ENGINE))

import build_site  # noqa: E402
import send_mail  # noqa: E402

_REAL_SOCKET = socket.socket
_REAL_DATA = send_mail.DATA


def _no_network(*a, **k):
    raise AssertionError("a test opened a socket; these tests must be hermetic")


def setUpModule():
    socket.socket = _no_network


def tearDownModule():
    socket.socket = _REAL_SOCKET
    send_mail.DATA = _REAL_DATA


class Recorder(send_mail.Provider):
    """No transport. Records what it was asked to send."""

    def __init__(self, outcome=None):
        super().__init__("the engine <test@example.test>")
        self.calls = []
        self._outcome = outcome

    def deliver(self, payload):
        self.calls.append(payload)
        if self._outcome is not None:
            return self._outcome
        return send_mail.MessageId(f"fake-{len(self.calls)}")


class ConfirmMailBody(unittest.TestCase):
    def test_the_link_points_at_the_confirm_page_with_the_token(self):
        text = send_mail.compose_confirm("tok-123")
        self.assertIn(f"{send_mail.SITE}/confirm.html?token=tok-123", text)

    def test_it_tells_a_stranger_that_doing_nothing_is_safe(self):
        """The address may not belong to whoever typed it."""
        text = send_mail.compose_confirm("t").lower()
        self.assertIn("if it was not you", text)
        self.assertIn("48 hours", text)

    def test_it_never_claims_they_already_subscribed(self):
        text = send_mail.compose_confirm("t").lower()
        for lie in ("you subscribed", "welcome aboard", "your subscription is active"):
            self.assertNotIn(lie, text)


class ConfirmSending(unittest.TestCase):
    def setUp(self):
        self.data = Path(tempfile.mkdtemp(prefix="s10-")) / "data"
        self.data.mkdir(parents=True)
        send_mail.DATA = self.data
        send_mail.reset_ledger()

    def tearDown(self):
        send_mail.DATA = _REAL_DATA
        send_mail.reset_ledger()
        shutil.rmtree(self.data.parent, ignore_errors=True)

    def rows(self, n):
        return [{"email": f"p{i}@example.test", "confirm_token": f"tok{i}"}
                for i in range(n)]

    def test_every_pending_address_is_mailed_once(self):
        prov = Recorder()
        tally = send_mail.send_confirmations(self.rows(3), prov)
        self.assertEqual(tally["sent"], 3)
        self.assertEqual(len(prov.calls), 3)

    def test_a_second_run_mails_nobody_again(self):
        """A confirmation is not a reminder campaign. Once, ever."""
        send_mail.send_confirmations(self.rows(3), Recorder())
        prov = Recorder()
        tally = send_mail.send_confirmations(self.rows(3), prov)
        self.assertEqual(prov.calls, [])
        self.assertEqual(tally["already"], 3)

    def test_the_ledger_is_written_per_address_not_at_the_end(self):
        """A crash halfway must not re-mail the people who already got theirs."""
        prov = Recorder()
        original = prov.deliver

        def die_on_third(payload):
            if len(prov.calls) == 2:
                raise RuntimeError("transport died")
            return original(payload)

        prov.deliver = die_on_third
        with self.assertRaises(RuntimeError):
            send_mail.send_confirmations(self.rows(5), prov)
        written = json.loads((self.data / send_mail.CONFIRM_FILENAME).read_text())
        self.assertEqual(sorted(written), ["p0@example.test", "p1@example.test"])

    def test_a_quota_halt_does_not_mark_them_as_mailed(self):
        """Deferred is not delivered: they must be mailed by a later run."""
        prov = Recorder(outcome=send_mail.QuotaHalt("daily", 1))
        prov.consumes_quota = False   # force the halt through deliver(), not the book
        tally = send_mail.send_confirmations(self.rows(2), prov)
        self.assertEqual(tally["sent"], 0)
        self.assertFalse((self.data / send_mail.CONFIRM_FILENAME).exists())

    def test_a_failed_send_does_not_mark_them_as_mailed_either(self):
        prov = Recorder(outcome=send_mail.SoftFail("boom"))
        tally = send_mail.send_confirmations(self.rows(2), prov)
        self.assertEqual(tally["sent"], 0)
        self.assertEqual(tally["failed"], 2)
        self.assertFalse((self.data / send_mail.CONFIRM_FILENAME).exists())

    def test_the_mail_is_booked_as_a_confirm_not_a_bulletin(self):
        """confirm and bulletin share a budget but not a stop line."""
        prov = Recorder()
        seen = {}
        real_send = prov.send

        def spy(to, subject, html, *, kind, **kw):
            seen["kind"] = kind
            return real_send(to, subject, html, kind=kind, **kw)

        prov.send = spy
        send_mail.send_confirmations(self.rows(1), prov)
        self.assertEqual(seen["kind"], "confirm")


class ConfirmPage(unittest.TestCase):
    def setUp(self):
        self.html = build_site.build_confirm()

    def test_it_calls_the_confirm_rpc_and_not_the_unsubscribe_one(self):
        self.assertIn("rpc/sightstone_confirm", self.html)
        self.assertNotIn("sightstone_unsubscribe", self.html)

    def test_it_reads_the_token_from_the_query_string(self):
        self.assertIn("URLSearchParams", self.html)
        self.assertIn("'token'", self.html)

    def test_a_missing_token_is_explained_not_swallowed(self):
        self.assertIn("no token in the link", self.html)

    def test_an_expired_link_says_so_instead_of_pretending(self):
        self.assertIn("expired", self.html)

    def test_it_is_not_indexed(self):
        """A page keyed by somebody's token has no business in a search index."""
        self.assertIn('name="robots" content="noindex"', self.html)

    def test_the_heading_is_a_question_and_ends_with_one(self):
        """Damla's law: a heading in question form takes a question mark."""
        head = self.html.split('<h1 class="page rainbow">')[1].split("</h1>")[0]
        self.assertTrue(head.strip().endswith("?"), head)

    def test_write_confirm_puts_it_where_the_mail_link_points(self):
        out = Path(tempfile.mkdtemp())
        build_site.write_confirm(out)
        self.assertTrue((out / "confirm.html").exists())
        shutil.rmtree(out, ignore_errors=True)


class LandingPageTellsTheTruth(unittest.TestCase):
    """The front page is where the promise is made. S10 changed the promise."""

    @classmethod
    def setUpClass(cls):
        cls.form = build_site.FORM_HTML
        cls.js = build_site.JOIN_JS

    def test_the_form_says_a_confirmation_mail_comes_first(self):
        self.assertIn("confirm this address", self.form.lower())

    def test_it_no_longer_claims_you_are_in_on_submit(self):
        """D2 holds the row back until it is confirmed, so 'you are in' was a
        lie the moment the insert returned 201."""
        self.assertNotIn("you are in", self.js.lower())

    def test_the_success_message_sends_them_to_their_inbox(self):
        self.assertIn("check your mail", self.js.lower())

    def test_nothing_on_the_landing_page_promises_one_click_unsubscribe(self):
        """POST to the unsubscribe page answers 405; measured 2026-09-01."""
        for surface in (self.form, self.js):
            self.assertNotIn("one click, ", surface.lower())
            self.assertNotIn("one-click", surface.lower())

    def test_an_already_registered_address_is_pointed_at_the_confirm_link(self):
        """'already in' hid the real case: signed up, never confirmed."""
        self.assertIn("already signed up", self.js.lower())


class ScheduleClaimIsMeasured(unittest.TestCase):
    """S13 -- the shop window tells the truth about when it opens."""

    @classmethod
    def setUpClass(cls):
        import json as _json
        jobs = _json.loads((ENGINE / "data" / "jobs.json").read_text())
        import match
        profile = _json.loads((ENGINE.parent / "profile.json").read_text())
        results, stats = match.run(profile, jobs)
        cls.html = build_site.build_index(jobs, results, stats, 0,
                                          {"capacity": 200, "taken": 1})

    def test_the_page_no_longer_promises_a_clock_time(self):
        """It said 'updated daily at 09:00 UTC+3'. Measured over 37 scheduled
        runs the median build was 78 minutes late and one was 12 hours late,
        so that sentence was false roughly every single morning."""
        self.assertNotIn("updated daily at 09:00", self.html)

    def test_the_lateness_it_admits_to_is_the_measured_number(self):
        self.assertIn(str(build_site.SCHEDULE_MEDIAN_LATE_MIN), self.html)
        self.assertIn(build_site.SCHEDULE_WORST_LATE, self.html)
        self.assertIn(str(build_site.SCHEDULE_RUNS), self.html)

    def test_the_cron_still_asks_for_the_hour_the_page_names(self):
        """If the cron moves, the footnote's '09:00 UTC+3' becomes a lie."""
        wf = (ENGINE.parent / ".github" / "workflows" / "daily.yml").read_text()
        self.assertIn('cron: "0 6 * * *"', wf)
        self.assertIn("09:00 UTC+3", self.html)


class InviteHasSomewhereToLand(unittest.TestCase):
    """S9b measured the hole and left it open: the RPC existed, the page did not."""

    def setUp(self):
        self.html = build_site.build_accept()

    def test_the_invite_mail_points_at_the_accept_page(self):
        """It used to point at the home page, which reads no token at all: the
        seat was offered, the link was clicked, and it still expired."""
        link = send_mail.compose_invite("tok9")
        self.assertIn(f"{send_mail.SITE}/accept.html?token=tok9", link)
        self.assertNotIn("/?invite=", link)

    def test_the_page_calls_the_accept_rpc(self):
        self.assertIn("rpc/sightstone_accept_invite", self.html)

    def test_an_expired_invite_says_it_passed_to_someone_else(self):
        self.assertIn("expired", self.html)
        self.assertIn("next person", self.html)

    def test_it_does_not_ask_them_to_confirm_a_second_time(self):
        """accept_invite inserts with confirmed_at set, so they are already in."""
        self.assertIn("nothing else to confirm", self.html)

    def test_it_is_not_indexed(self):
        self.assertIn('name="robots" content="noindex"', self.html)

    def test_the_heading_is_a_question_and_ends_with_one(self):
        head = self.html.split('<h1 class="page rainbow">')[1].split("</h1>")[0]
        self.assertTrue(head.strip().endswith("?"), head)

    def test_write_accept_puts_it_where_the_mail_link_points(self):
        out = Path(tempfile.mkdtemp())
        build_site.write_accept(out)
        self.assertTrue((out / "accept.html").exists())
        shutil.rmtree(out, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
