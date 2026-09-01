#!/usr/bin/env python3
"""S8a -- "the mail comes from somewhere real, and it can be escaped".

Everything here is hermetic: socket.socket is replaced module-wide, so a test
that reaches the network dies instead of sending mail. No request ever leaves
this process, and no production file is written.

What is nailed:

1. ONE THROAT. Delivery goes through Provider.send(to, subject, html). smtplib
   is gone from send_mail.py, send() is defined on Provider and nowhere else,
   every call site is in send_mail.py, and every call site names its kind.
   (S9b: the rule is one throat, not one caller -- the invite loop is a second
   legitimate caller through the same method. See OneThroat's note.)
2. RESEND PROVIDER. urllib POST to https://api.resend.com/emails with a Bearer
   token, body fields per the provider's docs, `id` from the response body ->
   MessageId. No pip package.
3. A31 CLASSIFICATION. The table comes from
   https://resend.com/docs/api-reference/errors, transcribed row by row below
   and diffed against the module's own copy, so no name can be invented. Not a
   single documented error is permanent for the RECIPIENT -- account, domain,
   quota, key, rate limit, server and our own malformed request all leave the
   subscriber alive -- so classify() returns SoftFail for every documented row,
   for `None`, and for any unknown name at ANY status, 422 included.
4. A32 DRY-RUN. --dry-run binds a provider with no transport, not None, and
   makes zero network calls.
5. A25 ISOLATION. One subscriber's HardBounce/SoftFail/exception cannot stop or
   skip the others: 10 subscribers, the 5th fails -> 9 delivered, 0 unprocessed.
6. LIST-UNSUBSCRIBE on EVERY generated mail, checked across all of them, and
   List-Unsubscribe-Post on NONE (the unsubscribe page answers POST with 405).
7. A28. No teardown in the send path that can mask the original exception.

Run: python3 -m unittest discover engine/tests -v
"""
import io
import hashlib
import json
import os
import re
import shutil
import socket
import sys
import tempfile
import unittest
import urllib.error
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from unittest import mock

HERE = Path(__file__).parent
ENGINE = HERE.parent
sys.path.insert(0, str(ENGINE))

import send_mail  # noqa: E402

SRC = (ENGINE / "send_mail.py").read_text()
LIVE_DATA = ENGINE / "data"
LIVE_STATE = LIVE_DATA / "mail_state.json"
LIVE_JOBS = LIVE_DATA / "jobs.json"

SIM_SUBS = 10
FAIL_AT = 5          # the 5th delivery is the one that goes wrong

# sha of the live state BEFORE any test ran. ProductionIsUntouched asks "did
# the SUITE write to engine/data", not "is production frozen forever" -- a
# literal here goes red the first morning the cron actually mails something.
LIVE_STATE_SHA_AT_IMPORT = hashlib.sha256(LIVE_STATE.read_bytes()).hexdigest()

_REAL_SOCKET = socket.socket
_REAL_DATA = send_mail.DATA
_MODULE_SANDBOX: Path | None = None


def _no_network(*args, **kwargs):
    raise AssertionError("a test opened a socket; these tests must be hermetic")


def setUpModule():
    global _MODULE_SANDBOX
    socket.socket = _no_network
    # S9a: the quota ledger's path is derived from send_mail.DATA, so pointing
    # DATA at something disposable for the whole module means no test in here
    # can write engine/data/quota_state.json even by accident.
    _MODULE_SANDBOX = Path(tempfile.mkdtemp(prefix="s8a-data-"))
    send_mail.DATA = _MODULE_SANDBOX
    send_mail.reset_ledger()


def tearDownModule():
    socket.socket = _REAL_SOCKET
    send_mail.DATA = _REAL_DATA
    send_mail.reset_ledger()
    if _MODULE_SANDBOX is not None:
        shutil.rmtree(_MODULE_SANDBOX, ignore_errors=True)


# ------------------------------------------------------------------- fake wire

class RecordingProvider(send_mail.Provider):
    """A provider with no transport. Optionally fails the Nth delivery."""

    payloads_all: list[dict] = []
    delivered: list[str] = []
    outcomes: list[object] = []
    fail_at: int | None = None
    fail_with: object = None     # HardBounce / SoftFail instance, or an Exception
    attempts: int = 0

    def __init__(self, *args, **kwargs):
        super().__init__("the engine <test@example.test>")

    @classmethod
    def reset(cls, fail_at=None, fail_with=None):
        cls.payloads_all = []
        cls.delivered = []
        cls.outcomes = []
        cls.fail_at = fail_at
        cls.fail_with = fail_with
        cls.attempts = 0

    def deliver(self, payload):
        RecordingProvider.attempts += 1
        RecordingProvider.payloads_all.append(payload)
        if RecordingProvider.attempts == RecordingProvider.fail_at:
            if isinstance(RecordingProvider.fail_with, BaseException):
                raise RecordingProvider.fail_with
            RecordingProvider.outcomes.append(RecordingProvider.fail_with)
            return RecordingProvider.fail_with
        out = send_mail.MessageId(f"fake-{RecordingProvider.attempts}")
        RecordingProvider.outcomes.append(out)
        RecordingProvider.delivered.append(payload["to"][0])
        return out


def subscriber(email: str, interests=("machine learning",), token=None) -> dict:
    return {"email": email, "name": email.split("@")[0], "level": "bs",
            "interests": list(interests), "location": "",
            "unsubscribe_token": token}


def sandbox() -> Path:
    data = Path(tempfile.mkdtemp(prefix="s8a-")) / "data"
    data.mkdir(parents=True)
    shutil.copy(LIVE_JOBS, data / "jobs.json")
    return data


def sid(email: str) -> str:
    import hashlib
    return hashlib.sha1(email.encode()).hexdigest()[:12]


class StubSeats(send_mail.SeatBackend):
    """S9b: main() also drives the invite loop, which speaks PostgREST.

    Stubbed rather than left to fail, because a real urlopen would hit this
    module's socket trap and put an exception in the middle of every run --
    noise on top of the isolation and List-Unsubscribe measurements these tests
    exist for. There is no waitlist in these fixtures, so the honest answer is
    zero seats and no mail; the invite loop's own behaviour is measured in
    test_invite_delivery.py against a real cluster.
    """

    def __init__(self, key, *a, **kw):
        pass

    def run_invites(self, daily_limit):
        return 0

    def fresh_invites(self, count):
        return []

    def release_invite(self, token):
        raise AssertionError("nothing was stamped, nothing to release")


def run_main(data: Path, subs: list[dict], argv=("send_mail.py",),
             env_extra=None, provider=RecordingProvider) -> tuple[str, str]:
    env = {"SUPABASE_SERVICE_KEY": "x", "RESEND_API_KEY": "re_test",
           "MAIL_FROM": "the engine <test@example.test>"}
    env.update(env_extra or {})
    with mock.patch.object(send_mail, "DATA", data), \
            mock.patch.object(send_mail, "STATE_FILE", data / "mail_state.json"), \
            mock.patch.object(send_mail, "fetch_subscribers", lambda k: subs), \
            mock.patch.object(send_mail, "ResendProvider", provider), \
            mock.patch.object(send_mail, "SupabaseSeats", StubSeats), \
            mock.patch.dict(os.environ, env, clear=True), \
            mock.patch.object(sys, "argv", list(argv)), \
            redirect_stdout(io.StringIO()) as out, \
            redirect_stderr(io.StringIO()) as err:
        send_mail.main()
    # main() re-read the ledger from the sandbox it was given; put the process
    # back on the module's own throwaway ledger so nothing leaks between tests.
    send_mail.reset_ledger()
    return out.getvalue(), err.getvalue()


def read_state(data: Path) -> dict:
    p = data / "mail_state.json"
    return json.loads(p.read_text()) if p.exists() else {}


# ----------------------------------------------------------------- one throat

class OneThroat(unittest.TestCase):
    """All delivery goes through a single interface, and smtplib is gone."""

    def test_smtplib_appears_on_zero_lines(self):
        hits = [i + 1 for i, l in enumerate(SRC.splitlines()) if "smtplib" in l]
        self.assertEqual(hits, [], f"smtplib still in send_mail.py at {hits}")
        self.assertFalse(hasattr(send_mail, "smtplib"))

    def test_no_smtp_api_survives_anywhere_in_the_module(self):
        for token in ("SMTP_SSL", "send_message", "starttls", "SMTP_PASS",
                      "smtp.gmail.com", "MIMEText"):
            self.assertNotIn(token, SRC, f"{token} still in the send path")

    def send_call_sites(self) -> list:
        sites = []
        for py in sorted(ENGINE.glob("*.py")):
            for i, line in enumerate(py.read_text().splitlines(), 1):
                if re.search(r"\bprovider\.send\(|\.send\(", line) and \
                        not line.strip().startswith("#"):
                    sites.append((py.name, i, line))
        return sites

    # S9b added a SECOND caller -- the invite loop -- and this gate was re-read
    # rather than relaxed. It used to count call sites and demand exactly one.
    # That count was never the guarantee: the guarantee is that every mail
    # leaves through Provider.send and nothing else in the codebase touches a
    # transport. ONE THROAT, not one caller. Keeping the count would have meant
    # the second kind of mail this product owes people could only ship by
    # widening the interface, which is the opposite of what the rule is for.
    # The three things that actually carry the rule are asserted directly
    # below, and together they are stricter than the number was.

    def test_every_send_call_site_lives_in_send_mail(self):
        """No other engine module may talk to a mail transport at all."""
        sites = self.send_call_sites()
        self.assertTrue(sites, "no send call site found at all")
        offenders = [f"{n}:{i}" for n, i, _ in sites if n != "send_mail.py"]
        self.assertEqual(offenders, [],
                         f"delivery escaped the single throat: {offenders}")

    def test_every_send_call_site_names_its_kind(self):
        """A caller that will not say which budget it spends cannot be guessed
        for. The throat raises on a missing kind; this catches it earlier.

        Read from the syntax tree, not the line: a call that wraps puts its
        keywords on a later line, and a text check would have called the live
        bulletin site nameless.
        """
        import ast
        calls = [n for n in ast.walk(ast.parse(SRC))
                 if isinstance(n, ast.Call)
                 and isinstance(n.func, ast.Attribute)
                 and n.func.attr == "send"
                 and isinstance(n.func.value, ast.Name)
                 and n.func.value.id in ("provider", "p", "self")]
        self.assertTrue(calls, "no send call found in the syntax tree")
        for call in calls:
            with self.subTest(line=call.lineno):
                kinds = [k for k in call.keywords if k.arg == "kind"]
                self.assertEqual(len(kinds), 1,
                                 f"send at line {call.lineno} names no kind")
                self.assertIsInstance(kinds[0].value, ast.Constant)
                self.assertIn(kinds[0].value.value, send_mail.MAIL_KINDS)

    def test_send_is_defined_on_the_throat_and_nowhere_else(self):
        """Subclasses override deliver(), never send(). An override of send()
        would skip the quota check and the kind gate in one move."""
        import ast
        definers = [n.name for n in ast.walk(ast.parse(SRC))
                    if isinstance(n, ast.ClassDef)
                    and any(isinstance(b, ast.FunctionDef) and b.name == "send"
                            for b in n.body)]
        self.assertEqual(definers, ["Provider"],
                         f"send() is defined outside the throat: {definers}")

    def test_send_signature_is_to_subject_html(self):
        import inspect
        params = list(inspect.signature(send_mail.Provider.send).parameters)
        self.assertEqual(params[:4], ["self", "to", "subject", "html"])

    def test_send_returns_one_of_the_three_outcomes(self):
        p = RecordingProvider()
        RecordingProvider.reset()
        self.assertIsInstance(p.send("a@b.c", "s", "<p>h</p>", kind="bulletin"),
                              send_mail.MessageId)

    def test_no_third_party_package_is_imported(self):
        banned = ("requests", "resend", "sendgrid", "httpx", "aiohttp",
                  "boto3", "urllib3")
        imports = re.findall(r"^\s*(?:import|from)\s+([a-zA-Z0-9_.]+)", SRC, re.M)
        for name in imports:
            self.assertNotIn(name.split(".")[0], banned, f"pip dependency: {name}")

    def test_no_masking_teardown_in_the_send_path(self):
        """A28: a `finally` that calls something on the transport can swallow the
        original exception. There is no transport object to tear down at all."""
        self.assertNotIn(".quit()", SRC)
        main_src = SRC.split("def main()", 1)[1]
        self.assertNotIn("finally", main_src,
                         "main() has a finally block again; it can mask the error "
                         "that actually killed the run")


# ------------------------------------------------------------- resend provider

class FakeHTTPResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def http_error(code: int, body: dict | str) -> urllib.error.HTTPError:
    raw = json.dumps(body) if isinstance(body, dict) else body
    return urllib.error.HTTPError("https://api.resend.com/emails", code, "err",
                                  {}, io.BytesIO(raw.encode()))


class ResendWire(unittest.TestCase):
    """The exact request the provider puts on the wire, without a wire."""

    def deliver(self, response=None, error=None):
        seen = {}

        def fake_urlopen(req, timeout=None):
            seen["req"] = req
            seen["timeout"] = timeout
            if error is not None:
                raise error
            return FakeHTTPResponse(json.dumps(response).encode())

        p = send_mail.ResendProvider("the engine <hi@example.test>", "re_abc123")
        with mock.patch.object(send_mail.urllib.request, "urlopen", fake_urlopen):
            out = p.send("who@example.test", "subject line", "<p>body</p>",
                         kind="bulletin", text="body",
                         unsub_url="https://x.test/u?token=t")
        return out, seen, p

    def test_post_to_the_documented_endpoint_with_a_bearer_token(self):
        out, seen, _ = self.deliver({"id": "49a3999c-0ce1-4ea6-ab68-afcd6dc2e794"})
        req = seen["req"]
        self.assertEqual(req.full_url, "https://api.resend.com/emails")
        self.assertEqual(req.get_method(), "POST")
        self.assertEqual(req.get_header("Authorization"), "Bearer re_abc123")
        self.assertEqual(req.get_header("Content-type"), "application/json")

    def test_body_carries_the_documented_fields(self):
        _, seen, _ = self.deliver({"id": "x"})
        body = json.loads(seen["req"].data.decode())
        self.assertEqual(body["from"], "the engine <hi@example.test>")
        self.assertEqual(body["to"], ["who@example.test"])
        self.assertEqual(body["subject"], "subject line")
        self.assertEqual(body["html"], "<p>body</p>")
        self.assertEqual(body["text"], "body")
        self.assertEqual(body["headers"],
                         {"List-Unsubscribe": "<https://x.test/u?token=t>"})
        self.assertEqual(set(body) - {"from", "to", "subject", "html", "text",
                                      "headers"}, set())

    def test_response_id_becomes_the_message_id(self):
        out, _, _ = self.deliver({"id": "49a3999c-0ce1-4ea6-ab68-afcd6dc2e794"})
        self.assertEqual(out, send_mail.MessageId("49a3999c-0ce1-4ea6-ab68-afcd6dc2e794"))

    def test_a_response_without_an_id_is_a_soft_fail_not_a_success(self):
        out, _, _ = self.deliver({"ok": True})
        self.assertIsInstance(out, send_mail.SoftFail)

    def test_transport_error_is_a_soft_fail(self):
        out, _, _ = self.deliver(error=urllib.error.URLError("connection refused"))
        self.assertIsInstance(out, send_mail.SoftFail)
        self.assertIn("URLError", out.reason)

    def test_timeout_is_a_soft_fail_never_a_hard_bounce(self):
        out, _, _ = self.deliver(error=TimeoutError("timed out"))
        self.assertIsInstance(out, send_mail.SoftFail)

    def test_missing_api_key_raises_a_named_error(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(RuntimeError) as cm:
                send_mail.ResendProvider("x <a@b.c>", os.environ.get("RESEND_API_KEY"))
        self.assertIn("RESEND_API_KEY", str(cm.exception))

    def test_more_than_fifty_recipients_is_refused_before_the_wire(self):
        p = send_mail.ResendProvider("x <a@b.c>", "re_k")
        with mock.patch.object(send_mail.urllib.request, "urlopen",
                               mock.Mock(side_effect=AssertionError("wire touched"))):
            with self.assertRaises(ValueError):
                p.send([f"a{i}@b.c" for i in range(51)], "s", "<p>h</p>",
                       kind="bulletin")
            p_ok = send_mail.build_payload("x <a@b.c>",
                                           [f"a{i}@b.c" for i in range(50)],
                                           "s", "<p>h</p>", None, "https://x/u")
            self.assertEqual(len(p_ok["to"]), 50)

    def test_empty_subject_is_refused(self):
        with self.assertRaises(ValueError):
            send_mail.build_payload("x <a@b.c>", "a@b.c", "", "<p>h</p>", None,
                                    "https://x/u")


#: Every row of https://resend.com/docs/api-reference/errors, transcribed by
#: hand from the page on 2026-08-30 (name, status, first words of the doc's own
#: Message). validation_error appears four times on the page: once at 400 and
#: three times at 403. This list is the evidence; send_mail's table is checked
#: against it, so a name that is not on the page cannot survive here.
RESEND_DOC_ROWS = [
    ("invalid_idempotency_key", 400, "Idempotency keys, if present, must have"),
    ("validation_error", 400, "An error was found with one or more fields"),
    ("missing_api_key", 401, "Missing API key in the authorization header."),
    ("restricted_api_key", 401, "This API key is restricted to only send emails."),
    ("email_above_quota", 403, "You can't retrieve this email's content"),
    ("invalid_permission", 403, "Access token is missing required scopes."),
    ("restricted_api_key", 403, "API key is not active"),
    ("suspended_api_key", 403, "This API key is suspended"),
    ("validation_error", 403, "You can only send testing emails to your own email address"),
    ("validation_error", 403, "The domain.com domain is not verified."),
    ("validation_error", 403, "The example.com domain has been registered already."),
    ("not_found", 404, "The requested endpoint does not exist."),
    ("method_not_allowed", 405, "Method is not allowed for the requested path."),
    ("concurrent_idempotent_requests", 409, "There is another request in progress"),
    ("invalid_idempotent_request", 409, "This idempotency key has been used"),
    ("resource_locked", 409, "Another request is already updating this resource."),
    ("invalid_attachment", 422, "Attachment must have either a content or path."),
    ("invalid_parameter", 422, "The parameter must be a valid UUID."),
    ("missing_required_field", 422, "The request body is missing one or more required fields."),
    ("missing_required_parameter", 422, "The request is missing one or more required parameters."),
    ("daily_quota_exceeded", 429, "You have exceeded your daily email sending quota."),
    ("monthly_quota_exceeded", 429, "You have exceeded your monthly email sending quota."),
    ("rate_limit_exceeded", 429, "Too many requests."),
    ("application_error", 500, "An unexpected error occurred."),
    ("service_unavailable", 503, "API is temporarily unavailable"),
]


class A31Classification(unittest.TestCase):
    """Read from https://resend.com/docs/api-reference/errors, not invented.

    One rule: HardBounce is only for an error that says something PERMANENT
    about THIS RECIPIENT, because HardBounce is what marks a person dead. The
    doc has no such error -- every row is about the account (key, plan, domain,
    quota), about our own request (missing field, bad UUID, wrong path), or
    plainly temporary (rate limit, 5xx). Resend reports real bounces
    asynchronously, not in this response. So every documented row is a SoftFail,
    and so is everything undocumented.

    The 403 rows matter most: `validation_error` at 403 is "The domain.com
    domain is not verified" / "You can only send testing emails to your own
    email address". Classifying that as a HardBounce would mark EVERY
    subscriber permanently dead the first morning the sending domain's DNS
    record went missing. test_validation_error_at_403_* pins that shut.
    """

    #: doc rows, deduplicated to the (status, name) pairs classify() can see
    DOCUMENTED = sorted({(status, name) for name, status, _ in RESEND_DOC_ROWS})

    # -------------------------------------------------- the table is the doc's

    def test_every_classified_name_appears_in_the_resend_doc(self):
        """No invented entry: the module's table equals the doc transcript."""
        documented_names = {name for name, _, _ in RESEND_DOC_ROWS}
        self.assertEqual(set(send_mail.RESEND_ERROR_DOC), documented_names)
        for name, (statuses, scope) in send_mail.RESEND_ERROR_DOC.items():
            with self.subTest(name=name):
                doc_statuses = {s for n, s, _ in RESEND_DOC_ROWS if n == name}
                self.assertEqual(set(statuses), doc_statuses)
                self.assertIn(scope, {"account", "request", "temporary"})
        # and the destructive set is a subset of it, so it cannot hold a name
        # that is not on the page either
        self.assertTrue(
            send_mail.RESEND_RECIPIENT_PERMANENT <= documented_names)

    def test_no_documented_error_is_permanent_for_the_recipient(self):
        """The doc's own scopes: account / our request / temporary. No recipient."""
        self.assertEqual(send_mail.RESEND_RECIPIENT_PERMANENT, frozenset())

    # ------------------------------------------------------- documented errors

    def test_every_documented_error_leaves_the_subscriber_alive(self):
        for code, name in self.DOCUMENTED:
            with self.subTest(code=code, name=name):
                out = send_mail.classify(code, name, "m")
                self.assertIsInstance(out, send_mail.SoftFail)
                self.assertEqual((out.code, out.name), (code, name))

    def test_validation_error_at_403_is_a_soft_fail_not_a_dead_subscriber(self):
        """Unverified domain is an ACCOUNT fault. It must not kill anyone."""
        for message in (
            "The domain.com domain is not verified. Please, add and verify your domain.",
            "You can only send testing emails to your own email address "
            "(youremail@domain.com).",
            "The example.com domain has been registered already.",
        ):
            with self.subTest(message=message[:30]):
                self.assertIsInstance(
                    send_mail.classify(403, "validation_error", message),
                    send_mail.SoftFail)

    def test_validation_error_at_400_is_also_a_soft_fail(self):
        """400 is "an error was found with one or more fields in the request" --
        our payload, not the person on the other end."""
        self.assertIsInstance(
            send_mail.classify(400, "validation_error",
                               "An error was found with one or more fields in the request."),
            send_mail.SoftFail)

    # ----------------------------------------------------- unknown / no name

    def test_an_unknown_error_name_never_kills_a_subscriber(self):
        """ANY status, 422 included -- the status is not evidence about a person.

        Every status the doc uses, plus statuses it does not, plus the whole
        4xx/5xx range so no single code can hide a HardBounce branch again.
        """
        doc_statuses = sorted({s for _, s, _ in RESEND_DOC_ROWS})
        self.assertIn(422, doc_statuses)
        codes = sorted(set(doc_statuses)
                       | {200, 202, 300, 301, 402, 406, 410, 418, 421, 422, 423,
                          424, 425, 426, 428, 431, 451, 501, 502, 504, 507, 599}
                       | set(range(400, 600)))
        for code in codes:
            for name in ("brand_new_unknown_error", "xyz", "validation", "",
                         "HardBounce", "invalid_to_address"):
                with self.subTest(code=code, name=name):
                    self.assertIsInstance(
                        send_mail.classify(code, name, "m"), send_mail.SoftFail)

    def test_a_missing_error_name_is_a_soft_fail_at_every_status(self):
        """classify(422, None) was the hole. None is not evidence either."""
        self.assertIsInstance(send_mail.classify(422, None, "m"), send_mail.SoftFail)
        for code in sorted(set(range(400, 600)) | {418, 0, -1}):
            with self.subTest(code=code):
                self.assertIsInstance(send_mail.classify(code, None, "m"),
                                      send_mail.SoftFail)

    def test_nothing_at_all_classifies_as_a_hard_bounce(self):
        """The sweep, stated as one sentence: no (status, name) reachable from
        the provider produces a HardBounce."""
        names = ([n for n, _, _ in RESEND_DOC_ROWS]
                 + [None, "", "unknown_name", "bounce", "hard_bounce"])
        hard = [(c, n) for c in range(200, 600) for n in names
                if isinstance(send_mail.classify(c, n, "m"), send_mail.HardBounce)]
        self.assertEqual(hard, [])

    def test_the_wire_path_classifies_a_real_http_error_body(self):
        p = send_mail.ResendProvider("x <a@b.c>", "re_k")
        cases = [(422, "missing_required_field", send_mail.SoftFail),
                 (403, "validation_error", send_mail.SoftFail),
                 (422, "brand_new_unknown_error", send_mail.SoftFail),
                 (429, "rate_limit_exceeded", send_mail.SoftFail),
                 (503, "service_unavailable", send_mail.SoftFail)]
        for code, name, expected in cases:
            with self.subTest(name=name):
                err = http_error(code, {"statusCode": code, "name": name,
                                        "message": "from the provider"})
                with mock.patch.object(send_mail.urllib.request, "urlopen",
                                       mock.Mock(side_effect=err)):
                    out = p.send("a@b.c", "s", "<p>h</p>", kind="bulletin")
                self.assertIsInstance(out, expected)
                self.assertEqual(out.code, code)
                self.assertEqual(out.name, name)
                self.assertEqual(out.reason, "from the provider")

    def test_an_unparsable_error_body_is_a_soft_fail(self):
        p = send_mail.ResendProvider("x <a@b.c>", "re_k")
        with mock.patch.object(send_mail.urllib.request, "urlopen",
                               mock.Mock(side_effect=http_error(500, "<html>502</html>"))):
            out = p.send("a@b.c", "s", "<p>h</p>", kind="bulletin")
        self.assertIsInstance(out, send_mail.SoftFail)


# ------------------------------------------------------------------ A32 dry run

class A32DryRun(unittest.TestCase):
    """--dry-run binds a provider that has no transport. Never None, never Resend."""

    def setUp(self):
        self.data = sandbox()

    def test_dry_run_makes_zero_network_calls(self):
        opened = []
        with mock.patch.object(send_mail.urllib.request, "urlopen",
                               lambda *a, **kw: opened.append(a) or (_ for _ in ()).throw(
                                   AssertionError("a network call in --dry-run"))):
            out, _ = run_main(self.data, [subscriber("dry@example.test")],
                              argv=("send_mail.py", "--dry-run"))
        self.assertEqual(opened, [])
        self.assertIn("DRY RUN", out)

    def test_dry_run_never_instantiates_the_real_provider(self):
        boom = mock.Mock(side_effect=AssertionError("ResendProvider built in dry-run"))
        out, _ = run_main(self.data, [subscriber("dry@example.test")],
                          argv=("send_mail.py", "--dry-run"), provider=boom)
        self.assertIn("DRY RUN", out)
        boom.assert_not_called()

    def test_dry_run_provider_is_not_none(self):
        """None is only safe while an early return stands in front of it."""
        seen = {}
        real = send_mail.process_subscriber

        def spy(*a, **kw):
            seen["provider"] = a[6]
            return real(*a, **kw)

        with mock.patch.object(send_mail, "process_subscriber", spy):
            run_main(self.data, [subscriber("dry@example.test")],
                     argv=("send_mail.py", "--dry-run"))
        self.assertIsNotNone(seen["provider"], "dry-run bound the provider to None")
        self.assertIsInstance(seen["provider"], send_mail.DryRunProvider)

    def test_the_dry_run_provider_cannot_reach_a_transport(self):
        p = send_mail.DryRunProvider("x <a@b.c>")
        with mock.patch.object(send_mail.urllib.request, "urlopen",
                               mock.Mock(side_effect=AssertionError("wire touched"))):
            out = p.send("a@b.c", "s", "<p>h</p>", kind="bulletin")
        self.assertIsInstance(out, send_mail.MessageId)
        self.assertEqual(out.id, "dry-run")

    def test_dry_run_writes_no_state(self):
        run_main(self.data, [subscriber("dry@example.test")],
                 argv=("send_mail.py", "--dry-run"))
        self.assertEqual(read_state(self.data), {},
                         "a dry run marked listings as already mailed")

    def test_dry_run_needs_no_api_key(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            out, _ = run_main(self.data, [subscriber("dry@example.test")],
                              argv=("send_mail.py", "--dry-run"),
                              env_extra={"RESEND_API_KEY": "", "MAIL_FROM": ""})
        self.assertIn("DRY RUN", out)


class RealSendRefusesToRunWithoutCredentials(unittest.TestCase):
    def test_missing_api_key_exits_with_a_named_message(self):
        data = sandbox()
        with self.assertRaises(SystemExit):
            _, err = run_main(data, [subscriber("a@example.test")],
                              env_extra={"RESEND_API_KEY": ""})

    def test_missing_from_address_exits(self):
        data = sandbox()
        with self.assertRaises(SystemExit):
            run_main(data, [subscriber("a@example.test")], env_extra={"MAIL_FROM": ""})


# ------------------------------------------------------------- A25 isolation

class A25SubscriberIsolation(unittest.TestCase):
    """10 subscribers, the 5th goes wrong three different ways. Same answer:
    9 delivered, 10 processed, nobody skipped."""

    def setUp(self):
        self.data = sandbox()
        self.subs = [subscriber(f"s{i}@example.test") for i in range(SIM_SUBS)]
        self.victim = self.subs[FAIL_AT - 1]["email"]

    def run_with(self, fail_with):
        RecordingProvider.reset(fail_at=FAIL_AT, fail_with=fail_with)
        return run_main(self.data, self.subs)

    def assert_nine_of_ten(self, out):
        state = read_state(self.data)
        delivered = RecordingProvider.delivered
        self.assertEqual(len(RecordingProvider.payloads_all), SIM_SUBS,
                         "not every subscriber was even attempted")
        self.assertEqual(len(delivered), SIM_SUBS - 1,
                         f"delivered {len(delivered)}/{SIM_SUBS}, isolation is broken")
        self.assertNotIn(self.victim, delivered)
        self.assertIn(f"processed {SIM_SUBS}/{SIM_SUBS}", out)
        self.assertEqual(len(state), SIM_SUBS - 1)
        self.assertNotIn(sid(self.victim), state,
                         "a failed subscriber was recorded as mailed")
        return state

    def test_a_hard_bounce_on_the_fifth_stops_nobody(self):
        out, _ = self.run_with(send_mail.HardBounce("dead address", 422,
                                                    "invalid_parameter"))
        self.assert_nine_of_ten(out)
        self.assertIn("hard bounce 1", out)
        self.assertIn("HARD BOUNCE", out)

    def test_a_soft_fail_on_the_fifth_stops_nobody(self):
        out, _ = self.run_with(send_mail.SoftFail("try later", 429,
                                                  "rate_limit_exceeded"))
        self.assert_nine_of_ten(out)
        self.assertIn("soft fail 1", out)

    def test_an_unexpected_exception_on_the_fifth_stops_nobody(self):
        out, err = self.run_with(RuntimeError("the transport exploded"))
        self.assert_nine_of_ten(out)
        self.assertIn("error 1", out)
        self.assertIn("the transport exploded", err,
                      "the swallowed exception was not reported anywhere")

    def test_a_soft_fail_subscriber_is_mailed_again_tomorrow(self):
        self.run_with(send_mail.SoftFail("try later", 503, "service_unavailable"))
        RecordingProvider.reset()
        run_main(self.data, self.subs)
        self.assertEqual([p["to"][0] for p in RecordingProvider.payloads_all],
                         [self.victim],
                         "the retryable subscriber was forgotten or double-mailed")

    def test_zero_subscribers_go_unprocessed_when_every_send_fails(self):
        RecordingProvider.reset(fail_at=None)
        with mock.patch.object(RecordingProvider, "deliver",
                               lambda self, payload: send_mail.SoftFail("down", 503,
                                                                        "service_unavailable")):
            out, _ = run_main(self.data, self.subs)
        self.assertIn(f"processed {SIM_SUBS}/{SIM_SUBS}", out)
        self.assertIn(f"soft fail {SIM_SUBS}", out)
        self.assertEqual(read_state(self.data), {})


class A25MutationWitness(unittest.TestCase):
    """Remove the isolation try and this evidence disappears -- which is the
    point: the isolation is what the tests above are measuring."""

    def test_the_send_loop_is_wrapped_in_a_per_subscriber_try(self):
        loop = SRC.split("for email, profile, token in targets:", 1)[1]
        head = loop.split("print(f\"done:", 1)[0]
        self.assertIn("try:", head, "the per-subscriber try is gone (A25)")
        self.assertIn("except Exception", head)
        self.assertIn("continue", head)


# ------------------------------------------------------- list-unsubscribe

class ListUnsubscribeOnEveryMail(unittest.TestCase):
    """Not one sample mail: every mail the run generates."""

    def setUp(self):
        self.data = sandbox()
        # a mix: half with a token, half without, so both header shapes appear
        self.subs = [subscriber(f"u{i}@example.test",
                                token=(f"tok{i}" if i % 2 == 0 else None))
                     for i in range(SIM_SUBS)]

    def generated(self) -> list[dict]:
        RecordingProvider.reset()
        run_main(self.data, self.subs)
        return list(RecordingProvider.payloads_all)

    def test_every_generated_mail_has_a_list_unsubscribe_header(self):
        mails = self.generated()
        self.assertEqual(len(mails), SIM_SUBS, "not every subscriber produced a mail")
        missing = [m["to"][0] for m in mails
                   if "List-Unsubscribe" not in (m.get("headers") or {})]
        self.assertEqual(missing, [], f"mails without List-Unsubscribe: {missing}")
        for m in mails:
            value = m["headers"]["List-Unsubscribe"]
            self.assertTrue(value.startswith("<https://") and value.endswith(">"),
                            f"malformed header: {value!r}")
            self.assertIn("/unsubscribe.html", value)

    def test_the_header_carries_the_subscribers_own_token_when_there_is_one(self):
        for m in self.generated():
            who = m["to"][0]
            i = int(who[1:who.index("@")])
            value = m["headers"]["List-Unsubscribe"]
            if i % 2 == 0:
                self.assertIn(f"token=tok{i}", value)
            else:
                self.assertNotIn("token=", value)

    def test_list_unsubscribe_post_appears_in_zero_mails(self):
        """The unsubscribe page is static GitHub Pages: POST answers 405. A
        one-click claim we cannot honour burns sender reputation (A29 -> S10)."""
        mails = self.generated()
        with_post = [m["to"][0] for m in mails
                     if any(k.lower() == "list-unsubscribe-post"
                            for k in (m.get("headers") or {}))]
        self.assertEqual(with_post, [], f"one-click claimed for: {with_post}")
        # and it is not set anywhere in the source either (comments explaining
        # WHY it is absent are allowed; a header key is not)
        code_lines = [l for l in SRC.splitlines()
                      if re.search(r"""['"]List-Unsubscribe-Post""", l)]
        self.assertEqual(code_lines, [],
                         f"the source advertises one-click unsubscribe: {code_lines}")

    def test_the_header_survives_whatever_the_caller_forgets(self):
        """build_payload is the only assembler, so it cannot be bypassed."""
        p = RecordingProvider()
        RecordingProvider.reset()
        p.send("nobody@example.test", "s", "<p>h</p>", kind="bulletin")  # no unsub_url
        self.assertIn("List-Unsubscribe", RecordingProvider.payloads_all[0]["headers"])

    def test_the_body_still_carries_a_visible_way_out(self):
        for m in self.generated():
            i = int(m["to"][0][1:m["to"][0].index("@")])
            if i % 2 == 0:
                self.assertIn("unsubscribe", m["text"].lower())


class ProductionIsUntouched(unittest.TestCase):
    def test_live_state_file_hash_is_unchanged(self):
        """The SUITE did not write to engine/data. Compared to import time."""
        self.assertEqual(hashlib.sha256(LIVE_STATE.read_bytes()).hexdigest(),
                         LIVE_STATE_SHA_AT_IMPORT,
                         "a test wrote to the live mail_state.json")

    def test_the_subscriber_query_still_excludes_the_unsubscribed(self):
        self.assertIn("unsubscribed_at=is.null", SRC)

    # S8a's gate was "no quota constant may appear at all", which was right
    # while the counter did not exist and is impossible now that it does. It is
    # INVERTED here, not deleted: the danger it guarded against was a quota
    # number appearing loose in the code, and that danger is unchanged. Every
    # one of these values must appear on EXACTLY ONE line of send_mail.py, and
    # that line must be its own named module constant. A magic 90 in the middle
    # of a comparison, or a second copy of 2550 that drifts from the first, is
    # the same failure the original test was written to catch.
    QUOTA_CONSTANTS = {
        "RESEND_DAILY_QUOTA": 100,
        "DAILY_MAIL_CAP": 90,
        "MONTHLY_BULLETIN_CAP": 2550,
        "RESEND_MONTHLY_QUOTA": 3000,
    }

    def test_every_quota_constant_lives_on_exactly_one_named_line(self):
        lines = SRC.splitlines()
        for name, value in self.QUOTA_CONSTANTS.items():
            with self.subTest(constant=name):
                hits = [(i + 1, l) for i, l in enumerate(lines)
                        if re.search(rf"(?<![\d.]){value}(?![\d.])", l)]
                self.assertEqual(
                    len(hits), 1,
                    f"{value} must appear on exactly one line of send_mail.py, "
                    f"found {[n for n, _ in hits]}")
                ln, line = hits[0]
                self.assertRegex(
                    line, rf"^{name}\s*=\s*{value}\b",
                    f"line {ln} uses {value} without naming it {name}: {line.strip()}")
                self.assertEqual(getattr(send_mail, name), value)

    def test_the_quota_constants_are_actually_the_ones_in_force(self):
        """Named but unused would be the same lie as unnamed."""
        self.assertEqual(send_mail.DAILY_MAIL_CAP,
                         send_mail.RESEND_DAILY_QUOTA - 10,
                         "the ten-mail safety margin is gone")
        self.assertLess(send_mail.MONTHLY_BULLETIN_CAP,
                        send_mail.RESEND_MONTHLY_QUOTA)
        self.assertEqual(
            send_mail.RESEND_MONTHLY_QUOTA - send_mail.MONTHLY_BULLETIN_CAP,
            round(send_mail.RESEND_MONTHLY_QUOTA * 0.15),
            "the reserve is 15%, not 5%: inbound mail eats the same quota and "
            "this ledger cannot see it")


if __name__ == "__main__":
    unittest.main()
