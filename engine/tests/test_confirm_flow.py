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


if __name__ == "__main__":
    unittest.main()
