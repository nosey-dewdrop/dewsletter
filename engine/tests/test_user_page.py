#!/usr/bin/env python3
"""S5b: docs/u/ -- the page that exists on the days no mail arrives.

Three things are being locked here.

1. It is PUBLIC. docs/ is a public git repository and daily.yml pushes it every
   morning, so there is no token in the path and no per-person page. The name is
   fixed, the only input is profile.json plus the listings, and nothing from the
   database is printed. A page named after unsubscribe_token would have shipped
   every subscriber's one-click-leave link to the world.

2. It has NO THRESHOLD. The mail cuts at --min-score 5 (send_mail.py:135). This
   page prints the whole of match.run(). On the frozen corpus that is the
   difference between 1 record and 3.

3. Its links are real. build_jobs_index() links to the BASE slug, which on the
   frozen corpus collides 16 times; the page here resolves through the slug map
   main() actually writes and drops any link whose file is not on disk.

Every HTML assertion goes through html.parser and every feed assertion through
xml.etree. `in` against the raw string is not evidence: `</SCRIPT >` closes a
script element and slips past a string search.

Run: python3 -m unittest discover engine/tests
"""
import json
import shutil
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

import build_site  # noqa: E402
import fetch  # noqa: E402
import match  # noqa: E402
from test_d9_escape import job, parse  # noqa: E402

MAIL_MIN_SCORE = 5          # engine/send_mail.py:135, the mail's cut-off
FIXTURE_COLLISIONS = 16     # measured on engine/tests/fixtures
ATOM = "{http://www.w3.org/2005/Atom}"
DB_TOKENS = ("supabase", "subscriber", "mail_state", "send_mail")
NEW_FUNCS = ("robots_extra", "job_slug_map", "slugs_on_disk", "result_key",
             "xml_text", "user_row_html", "user_page_html", "user_feed_xml",
             "write_user_pages")


def fixture_jobs() -> list:
    texts = {m.NAME: (HERE / "fixtures" / m.FIXTURE).read_text(encoding="utf-8")
             for m in fetch.SOURCES}
    per = fetch.parse_all(texts, "2026-08-30T09:00:00+00:00")
    deduped, _ = fetch.dedupe([j for _, rows in per for j in rows])
    jobs, _ = match.dedupe(deduped)
    return jobs


def profile() -> dict:
    return json.loads((ROOT / "profile.json").read_text())


def build_into(tmp: Path, jobs: list) -> tuple:
    """Write the job pages the way main() does, then the user pages."""
    (tmp / "jobs").mkdir(parents=True, exist_ok=True)
    for key, slug in build_site.job_slug_map(jobs).items():
        j = next(x for x in jobs
                 if (x["company"].strip().lower(), x["position"].strip().lower()) == key)
        (tmp / "jobs" / f"{slug}.html").write_text(build_site.build_job_page(j, slug))
    results, _ = match.run(profile(), jobs)
    build_site.write_user_pages(tmp, jobs, results)
    return results, (tmp / "u" / "matches.html").read_text(), (tmp / "u" / "matches.xml").read_text()


def li_count(html_text: str) -> int:
    return parse(html_text).tag_names().count("li")


class RecordLinks(HTMLParser):
    """Only the hrefs inside <ol id="all-matches">. The run-head nav also points
    at ../jobs/index.html; that link is not a record and is not evidence."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hrefs = []
        self._depth = 0

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if tag == "ol" and d.get("id") == "all-matches":
            self._depth = 1
            return
        if self._depth:
            if tag == "ol":
                self._depth += 1
            if tag == "a" and d.get("href"):
                self.hrefs.append(d["href"])

    def handle_endtag(self, tag):
        if tag == "ol" and self._depth:
            self._depth -= 1


def record_hrefs(html_text: str) -> list:
    p = RecordLinks()
    p.feed(html_text)
    p.close()
    return p.hrefs


def jobs_hrefs(html_text: str) -> list:
    return [u for u in record_hrefs(html_text) if u.startswith("../jobs/")]


class Surface(unittest.TestCase):
    """What lands in docs/u/, and what deliberately does not."""

    @classmethod
    def setUpClass(cls):
        cls.jobs = fixture_jobs()
        cls._tmp = tempfile.TemporaryDirectory()
        cls.tmp = Path(cls._tmp.name)
        cls.results, cls.html, cls.xml = build_into(cls.tmp, cls.jobs)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_exactly_two_files_and_neither_name_carries_a_token(self):
        names = sorted(p.name for p in (self.tmp / "u").iterdir())
        self.assertEqual(names, ["matches.html", "matches.xml"])
        for n in names:
            self.assertNotRegex(n, r"[0-9a-f]{8}-[0-9a-f]{4}")

    def test_page_is_noindex(self):
        metas = [d for t, d in parse(self.html).tags
                 if t == "meta" and d.get("name") == "robots"]
        self.assertEqual([d["content"] for d in metas], ["noindex"])

    def test_record_count_equals_the_whole_matcher_output(self):
        expected, _ = match.run(profile(), self.jobs)
        self.assertEqual(li_count(self.html), len(expected))
        self.assertEqual(len([e for e in ET.fromstring(self.xml)
                              if e.tag == ATOM + "entry"]), len(expected))

    def test_records_below_the_mail_cutoff_are_on_the_page(self):
        """The proof that there is no threshold: the mail would drop these."""
        below = [r for r in self.results if r["score"] < MAIL_MIN_SCORE]
        self.assertGreater(len(below), 0)
        text = parse(self.html).joined_text()
        for r in below:
            self.assertIn(r["position"], text)

    def test_page_names_its_own_data_source(self):
        text = parse(self.html).joined_text()
        self.assertIn("profile.json", text)

    def test_no_database_surface_in_the_new_code_or_its_output(self):
        src = (HERE.parent / "build_site.py").read_text()
        tree = __import__("ast").parse(src)
        for node in __import__("ast").walk(tree):
            if getattr(node, "name", None) in NEW_FUNCS:
                body = __import__("ast").get_source_segment(src, node).lower()
                for tok in DB_TOKENS:
                    self.assertNotIn(tok, body, f"{node.name} touches {tok}")
        for out in (self.html.lower(), self.xml.lower()):
            for tok in DB_TOKENS:
                self.assertNotIn(tok, out)


class Robots(unittest.TestCase):
    """robots.txt grows, it is not rewritten."""

    def test_extra_group_disallows_u_and_keeps_the_old_line_intact(self):
        old = f"User-agent: *\nAllow: /\nSitemap: {build_site.BASE_URL}/sitemap.xml\n"
        combined = old + build_site.robots_extra()
        self.assertTrue(combined.startswith(old))
        self.assertIn("Disallow: /u/", combined)
        self.assertEqual(combined.count("Allow: /\n"), 1)


class FullBuild(unittest.TestCase):
    """main() itself, against the live corpus, into a throwaway docs root."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.tmp = Path(cls._tmp.name)
        cls._old = build_site.ROOT
        build_site.ROOT = cls.tmp
        try:
            build_site.main()
        finally:
            build_site.ROOT = cls._old

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_u_holds_exactly_two_files(self):
        self.assertEqual(len(list((self.tmp / "u").iterdir())), 2)

    def test_sitemap_never_mentions_u(self):
        self.assertNotIn("/u/", (self.tmp / "sitemap.xml").read_text())

    def test_robots_disallows_u(self):
        self.assertIn("Disallow: /u/", (self.tmp / "robots.txt").read_text())

    def test_no_page_anywhere_links_to_the_user_page(self):
        linkers = []
        for p in self.tmp.rglob("*.html"):
            if p.parent.name == "u":
                continue
            for u in parse(p.read_text()).url_attrs():
                if "u/matches" in u:
                    linkers.append(p.name)
        self.assertEqual(linkers, [])

    def test_the_helper_map_is_the_map_main_wrote_to_disk(self):
        jobs = json.loads((HERE.parent / "data" / "jobs.json").read_text())
        jobs, _ = match.dedupe(jobs)
        expected = set(build_site.job_slug_map(jobs).values())
        on_disk = {p.stem for p in (self.tmp / "jobs").glob("*.html")} - {"index"}
        self.assertEqual(on_disk, expected)

    def test_every_jobs_link_on_the_page_resolves(self):
        html_text = (self.tmp / "u" / "matches.html").read_text()
        hrefs = jobs_hrefs(html_text)
        self.assertGreater(len(hrefs), 0)
        for u in hrefs:
            self.assertTrue((self.tmp / "u" / u).resolve().exists(), u)


class Collisions(unittest.TestCase):
    """16 listings share a base slug. None of them may get the wrong page."""

    def test_fixture_collision_count(self):
        jobs = fixture_jobs()
        bases = [build_site.slugify(f'{j["company"]}-{j["position"]}') for j in jobs]
        self.assertEqual(len(bases) - len(set(bases)), FIXTURE_COLLISIONS)

    def test_every_link_resolves_on_a_collision_forced_corpus(self):
        twins = [job(company="Same Co", position="AI Intern", location="Berlin"),
                 job(company="same co", position="ai intern ", location="Paris"),
                 job(company="Same Co.", position="AI  Intern", location="Rome")]
        jobs = fixture_jobs() + twins
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            _, html_text, _ = build_into(tmp, jobs)
            hrefs = jobs_hrefs(html_text)
            for u in hrefs:
                self.assertTrue((tmp / "u" / u).resolve().exists(), u)

    def test_a_listing_with_no_page_on_disk_gets_no_link(self):
        jobs = [job(company="Ghost Co", position="AI Intern")]
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            (tmp / "jobs").mkdir()
            smap = build_site.slugs_on_disk(tmp, jobs)
            self.assertEqual(smap, {})
            r = {**jobs[0], "score": 3, "reasons": ["x"]}
            self.assertEqual(jobs_hrefs(build_site.user_page_html([r], smap)), [])


class Hostile(unittest.TestCase):
    """A job title is attacker-controlled text. It reaches this page too."""

    PAYLOADS = ["<script>alert(1)</script>",
                "</script><script>alert(1)</script>",
                "</SCRIPT ><img src=x onerror=alert(2)>",
                "<svg onload=alert(5)>",
                'Ev"il & <b>Co</b>']

    def rows(self, **over):
        j = job(**over)
        return [{**j, "score": 4, "reasons": ["interest 'ai' in title"]}]

    def test_no_executable_script_and_no_event_handler(self):
        for p in self.PAYLOADS:
            for field in ("company", "position", "location"):
                with self.subTest(payload=p, field=field):
                    page = build_site.user_page_html(self.rows(**{field: p}), {})
                    got = parse(page)
                    self.assertEqual(got.event_attrs(), [])
                    for body in got.executable_scripts():
                        for marker in ("alert(", "onerror", "onload"):
                            self.assertNotIn(marker, body)
                    base = parse(build_site.user_page_html(self.rows(), {}))
                    for tag in ("img", "svg", "b", "iframe", "script"):
                        self.assertEqual(got.tag_names().count(tag),
                                         base.tag_names().count(tag), tag)

    def test_payload_text_survives_verbatim(self):
        for p in self.PAYLOADS:
            with self.subTest(payload=p):
                page = build_site.user_page_html(self.rows(position=p), {})
                self.assertIn(p, parse(page).joined_text())

    def test_no_dangerous_scheme_reaches_a_url_attribute(self):
        for u in ("javascript:alert(3)", "JaVaScRiPt:alert(3)",
                  " javascript:alert(3)", "data:text/html,<script>alert(3)</script>",
                  "//evil.example/x"):
            with self.subTest(url=u):
                page = build_site.user_page_html(self.rows(link=u), {})
                self.assertEqual(parse(page).dangerous_urls(), [])

    def test_feed_parses_with_markup_and_a_control_character_in_the_title(self):
        for p in self.PAYLOADS + ["bell\x0bhere", "null\x00here"]:
            with self.subTest(payload=p):
                xml = build_site.user_feed_xml(self.rows(position=p), {})
                root = ET.fromstring(xml)
                titles = [e.findtext(ATOM + "title")
                          for e in root if e.tag == ATOM + "entry"]
                self.assertEqual(len(titles), 1)
                self.assertIn(p.replace("\x0b", "").replace("\x00", ""), titles[0])

    def test_feed_link_of_a_hostile_url_is_dropped_not_printed(self):
        xml = build_site.user_feed_xml(self.rows(link="javascript:alert(3)"), {})
        root = ET.fromstring(xml)
        for e in root:
            if e.tag != ATOM + "entry":
                continue
            for ln in e.findall(ATOM + "link"):
                self.assertNotIn("javascript:", ln.get("href"))


class XmlFilter(unittest.TestCase):
    """xml_text() = esc() plus the characters XML 1.0 cannot hold."""

    def test_markup_is_escaped(self):
        self.assertEqual(build_site.xml_text("<b>&\"x\"</b>"),
                         "&lt;b&gt;&amp;&quot;x&quot;&lt;/b&gt;")

    def test_forbidden_control_characters_are_dropped(self):
        for ch in ("\x00", "\x08", "\x0b", "\x0c", "\x1f", chr(0xD800)):
            with self.subTest(ch=repr(ch)):
                self.assertEqual(build_site.xml_text("a" + ch + "b"), "ab")

    def test_legal_whitespace_is_kept(self):
        self.assertEqual(build_site.xml_text("a\tb\nc\rd"), "a\tb\nc\rd")


if __name__ == "__main__":
    unittest.main()
