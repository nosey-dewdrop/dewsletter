#!/usr/bin/env python3
"""D9: nothing a listing carries can become code on the site.

The listing text is not ours. It arrives from speedyapply markdown, so a job
title is attacker-controlled input that the generator prints into five
different contexts: body text, an attribute value, a <script> JSON block, a URL
attribute, and (by accident, if escaping fails) inline JavaScript.

Every assertion here goes through a REAL HTML parser (html.parser). Searching
the generated string with `in` is banned in this file: `</SCRIPT >` closes a
script element in any browser and slips straight past a string search, so a
string-based test would pass on a page that executes alert(2).

Run: python3 -m unittest discover engine/tests
"""
import json
import sys
import unittest
from html.parser import HTMLParser
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))

import build_site  # noqa: E402

CANONICAL = "https://nosey-dewdrop.github.io/dewsletter/jobs/x.html"

# Five payloads plus one lossless-escaping probe. Each one is a real technique,
# not a decoration: script break-out, case/space variant end tag, URL scheme,
# svg event handler, quote+ampersand+markup, and the JS line terminator that
# breaks a JavaScript string literal without breaking JSON.
PAYLOADS = [
    "</script><script>alert(1)</script>",
    "</SCRIPT ><img src=x onerror=alert(2)>",
    "javascript:alert(3)",
    "<svg onload=alert(5)>",
    'Ev"il & <b>Co</b>',
    "line sep",
]
EXEC_MARKERS = ("alert(", "onerror", "onload")


class Collector(HTMLParser):
    """Walks the emitted HTML the way a browser tokenizer does."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tags = []            # [(tagname, {attr: value})]
        self.scripts = []         # [(type attribute, body text)]
        self.text = []            # data outside <script>
        self._script = None

    def handle_starttag(self, tag, attrs):
        d = {k: (v if v is not None else "") for k, v in attrs}
        self.tags.append((tag, d))
        if tag == "script":
            self._script = [d.get("type", ""), []]

    def handle_startendtag(self, tag, attrs):
        self.tags.append((tag, {k: (v if v is not None else "") for k, v in attrs}))

    def handle_endtag(self, tag):
        if tag == "script" and self._script is not None:
            self.scripts.append((self._script[0], "".join(self._script[1])))
            self._script = None

    def handle_data(self, data):
        if self._script is not None:
            self._script[1].append(data)
        else:
            self.text.append(data)

    # ---- readers -----------------------------------------------------------
    def tag_names(self):
        return [t for t, _ in self.tags]

    def event_attrs(self):
        return [(t, k) for t, d in self.tags for k in d if k.lower().startswith("on")]

    def url_attrs(self):
        out = []
        for _, d in self.tags:
            for k, v in d.items():
                if k.lower() in ("href", "src", "action"):
                    out.append(v)
        return out

    def dangerous_urls(self):
        bad = ("javascript:", "data:", "vbscript:")
        return [u for u in self.url_attrs()
                if u.strip().lower().replace("\t", "").replace("\n", "").startswith(bad)]

    def executable_scripts(self):
        """Script elements a browser would run: no type, or a JS type."""
        return [body for typ, body in self.scripts
                if typ == "" or "javascript" in typ.lower() or typ.lower() == "module"]

    def ld_json(self):
        return [body for typ, body in self.scripts
                if typ.lower() == "application/ld+json"]

    def joined_text(self):
        return "".join(self.text)


def parse(html_text: str) -> Collector:
    c = Collector()
    c.feed(html_text)
    c.close()
    return c


def job(**over) -> dict:
    j = {"source": "speedyapply-intern-usa", "company": "Clean Co",
         "company_url": "https://clean.example", "position": "AI Intern",
         "location": "Berlin, Germany", "remote": True, "salary": "$40/hr",
         "link": "https://clean.example/apply", "link_missing": False,
         "age": "2d", "student_ok": True, "deadline": None}
    j.update(over)
    return j


def result(j: dict) -> dict:
    return {**j, "score": 7, "reasons": ["interest 'ai' in title", "remote"]}


def index_of(jobs):
    stats = {"matched": len(jobs), "no_signal": 0, "phd_only": 0, "mba": 0,
             "us_work_auth": 0}
    return build_site.build_index(jobs, [result(j) for j in jobs], stats, 0,
                                  {"capacity": 100, "taken": 1})


def all_surfaces(jobs) -> dict:
    """Every page a listing reaches. cv.html carries no listing text."""
    return {"index": index_of(jobs),
            "jobs_index": build_site.build_jobs_index(jobs),
            "job_page": build_site.build_job_page(jobs[0], "x")}


BASELINE = {name: parse(html) for name, html in all_surfaces([job()]).items()}


class BodyTextContext(unittest.TestCase):
    """Payload in the visible prose: company, position, location, salary."""

    def test_payload_in_body_text_makes_no_new_element(self):
        for p in PAYLOADS:
            for field in ("company", "position", "location", "salary"):
                jobs = [job(**{field: p})]
                for name, html_text in all_surfaces(jobs).items():
                    with self.subTest(payload=p, field=field, surface=name):
                        got = parse(html_text)
                        base = BASELINE[name]
                        self.assertEqual(got.event_attrs(), [])
                        self.assertEqual(len(got.scripts), len(base.scripts))
                        for tag in ("img", "svg", "b", "iframe", "object"):
                            self.assertEqual(got.tag_names().count(tag),
                                             base.tag_names().count(tag), tag)

    def test_payload_text_survives_verbatim(self):
        """Escaped, not stripped: the parser hands the original back."""
        for p in PAYLOADS:
            with self.subTest(payload=p):
                page = build_site.build_job_page(job(position=p), "x")
                self.assertIn(p, parse(page).joined_text())


class AttributeContext(unittest.TestCase):
    """Payload inside an attribute value (meta description, title)."""

    def test_payload_cannot_close_the_attribute(self):
        for p in PAYLOADS:
            with self.subTest(payload=p):
                got = parse(build_site.build_job_page(job(position=p), "x"))
                self.assertEqual(got.event_attrs(), [])
                metas = [d for t, d in got.tags
                         if t == "meta" and d.get("name") == "description"]
                self.assertEqual(len(metas), 1)
                self.assertIn(p, metas[0]["content"])


class ScriptJsonContext(unittest.TestCase):
    """The ld+json block: no break-out, and the JSON stays lossless."""

    def test_json_block_is_one_data_script_and_round_trips(self):
        for p in PAYLOADS:
            with self.subTest(payload=p):
                frag = build_site.job_jsonld(job(position=p, company=p), CANONICAL)
                got = parse(frag)
                self.assertEqual(len(got.scripts), 1)
                self.assertEqual(got.executable_scripts(), [])
                data = json.loads(got.ld_json()[0])
                self.assertEqual(data["title"], p)
                self.assertEqual(data["hiringOrganization"]["name"], p)

    def test_json_block_inside_the_whole_page_round_trips(self):
        for p in PAYLOADS:
            with self.subTest(payload=p):
                got = parse(build_site.build_job_page(job(position=p), "x"))
                blocks = got.ld_json()
                self.assertEqual(len(blocks), 1)
                self.assertEqual(json.loads(blocks[0])["title"], p)

    def test_ampersand_is_left_alone(self):
        """& must NOT be escaped here; the byte freeze depends on it."""
        frag = build_site.job_jsonld(job(position="a & b"), CANONICAL)
        body = parse(frag).ld_json()[0]
        self.assertEqual(json.loads(body)["title"], "a & b")
        self.assertEqual(body.count("&amp;"), 0)
        self.assertEqual(build_site.json_in_html({"t": "a & b"}).count("&"), 1)


class UrlSchemeContext(unittest.TestCase):
    """A link is a URL, not a string: esc() escapes quotes, not schemes."""

    HOSTILE = ["javascript:alert(3)", "JaVaScRiPt:alert(3)",
               "  javascript:alert(3)", "data:text/html,<script>alert(3)</script>",
               "vbscript:msgbox(3)", "//evil.example/x"]

    def test_no_dangerous_scheme_reaches_any_url_attribute(self):
        for u in self.HOSTILE:
            jobs = [job(link=u, company_url=u)]
            for name, html_text in all_surfaces(jobs).items():
                with self.subTest(url=u, surface=name):
                    self.assertEqual(parse(html_text).dangerous_urls(), [])

    def test_dropped_link_is_reported_as_missing_and_stays_consistent(self):
        frag = build_site.job_jsonld(job(link="javascript:alert(3)",
                                         company_url="javascript:alert(3)"),
                                     CANONICAL)
        data = json.loads(parse(frag).ld_json()[0])
        self.assertIs(data["directApply"], False)
        self.assertIsNone(data["hiringOrganization"]["sameAs"])

    def test_real_links_are_untouched(self):
        good = "https://boards.greenhouse.io/x/jobs/1?src=a&b=2"
        got = parse(build_site.build_job_page(job(link=good), "x"))
        self.assertIn(good, got.url_attrs())


class InlineJsIsolation(unittest.TestCase):
    """Listing text never lands inside a script a browser would execute."""

    def test_no_listing_text_leaks_into_executable_script(self):
        leaks = 0
        for p in PAYLOADS:
            jobs = [job(company=p, position=p, location=p, salary=p,
                        link="javascript:alert(3)", company_url=p)]
            for html_text in all_surfaces(jobs).values():
                for body in parse(html_text).executable_scripts():
                    if any(m in body for m in EXEC_MARKERS) or p in body:
                        leaks += 1
        self.assertEqual(leaks, 0)


if __name__ == "__main__":
    unittest.main()
