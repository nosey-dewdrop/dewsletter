#!/usr/bin/env python3
"""Static site generator: jobs.json -> dewsletter's site. No LLM.

Design source of truth: site-mock/ (Damla-iterated, 26 Jul 2026).
Laws: LaTeX paper aesthetic, Latin Modern, flat white, NO horizontal rules
except booktabs table anatomy, question headings end with "?", per-letter
rainbow on important lines, real numbers only.

Output (docs/, served by GitHub Pages):
  docs/index.html          front page: pitch, why?, how?, form, data, matches
  docs/cv.html             sample CV report generated live by cv_critique
  docs/jobs/index.html     full listing, every row
  docs/jobs/<slug>.html    one page per listing (SEO surface)
  docs/sitemap.xml, robots.txt
"""
import html
import json
import re
import unicodedata
from datetime import date
from pathlib import Path

import cv_critique
import match

BASE_URL = "https://nosey-dewdrop.github.io/dewsletter"
SUPABASE_URL = "https://xjtmqncfhuidctxgthhv.supabase.co"
SUPABASE_ANON = ("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inhqd"
                 "G1xbmNmaHVpZGN0eGd0aGh2Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODM4OTQ5NTcsImV4cCI6"
                 "MjA5OTQ3MDk1N30.xQ2-SY7gT1BsI7isodRgKtaqyDSIzjDbgHyjOYMt_8g")  # public by design, RLS protects
ROOT = Path(__file__).parent.parent / "docs"

# Measured 2026-09-01 over every schedule-triggered run of daily.yml
# (`gh run list --workflow=daily.yml --json event,createdAt`, event == schedule).
# The cron asks for 06:00 UTC; GitHub's scheduler is best-effort and says so.
# Hardcoded because build_site must stay hermetic -- it may not call the GitHub
# API to render a page. Re-measure with the command above if it drifts.
SCHEDULE_RUNS = 37
SCHEDULE_MEDIAN_LATE_MIN = 78      # median actual build: 10:18 TRT
SCHEDULE_WORST_LATE = "12 hours late, at 21:06"
TODAY = date.today().strftime("%B %d, %Y")
TODAY_ISO = date.today().isoformat()
VERSION = f"v2 · built {TODAY_ISO}"

FONTS = """
@font-face { font-family:'Latin Modern'; src:url('https://cdn.jsdelivr.net/gh/vincentdoerig/latex-css@1.10.0/fonts/LM-regular.woff2') format('woff2'); font-weight:normal; font-style:normal; font-display:swap; }
@font-face { font-family:'Latin Modern'; src:url('https://cdn.jsdelivr.net/gh/vincentdoerig/latex-css@1.10.0/fonts/LM-bold.woff2') format('woff2'); font-weight:bold; font-style:normal; font-display:swap; }
@font-face { font-family:'Latin Modern'; src:url('https://cdn.jsdelivr.net/gh/vincentdoerig/latex-css@1.10.0/fonts/LM-italic.woff2') format('woff2'); font-weight:normal; font-style:italic; font-display:swap; }
"""

CSS = FONTS + """
:root { --ink:#111; --paper:#fff; --link:#0b4fa8;
  --red:#c22a1e; --orange:#d2600a; --ochre:#b8860b;
  --green:#1a7a3c; --blue:#0b4fa8; --violet:#6b2fa8; }
* { margin:0; padding:0; box-sizing:border-box; }
html { background:var(--paper); scroll-behavior:smooth; }
body { font-family:'Latin Modern','Computer Modern',Georgia,serif; color:var(--ink);
  background:var(--paper); font-size:15.5px; line-height:1.52; }
a { color:var(--link); text-decoration:none; }
a:hover { text-decoration:underline; }
u { text-decoration-thickness:1px; text-underline-offset:2.5px; }
#why u { text-decoration-color:var(--red); }
#how u { text-decoration-color:var(--orange); }
.rb1{color:var(--red)} .rb2{color:var(--orange)} .rb3{color:var(--ochre)}
.rb4{color:var(--green)} .rb5{color:var(--blue)} .rb6{color:var(--violet)}

nav.runhead { position:sticky; top:0; z-index:10; background:var(--paper); font-size:13.5px; }
.rh-inner { max-width:1080px; margin:0 auto; padding:.8rem 24px .6rem 24px;
  display:flex; justify-content:space-between; align-items:baseline; gap:1rem; }
.rh-left .wordmark { font-variant:small-caps; font-size:15px; color:var(--ink); letter-spacing:.02em; }
.rh-left .rh-sub { font-style:italic; color:#333; margin-left:.7rem; }
.rh-links { display:flex; gap:1.15rem; align-items:baseline; }
.rh-links a { color:var(--ink); font-variant:small-caps;
  border-bottom:1.5px solid transparent; padding-bottom:.1rem; transition:border-color 150ms ease; }
.rh-links a:hover { text-decoration:none; border-bottom-color:var(--ink); }
.rh-links a.active { border-bottom-color:var(--ink); }
.rh-links a.rh-join { background:var(--ink); color:var(--paper);
  padding:.12rem .8rem .18rem .8rem; border-bottom:none; transition:background 150ms ease; }
.rh-links a.rh-join:hover { background:#000; }

.sheet { max-width:1080px; margin:0 auto; padding:2.6rem 24px 3rem 24px; }

.maketitle { text-align:center; margin-bottom:2.2rem; }
.maketitle h1 { font-size:25px; font-weight:bold; line-height:1.3; margin-bottom:.9rem; }
.maketitle .author { font-size:15.5px; margin-bottom:.25rem; }
.maketitle .date { font-style:italic; font-size:14px; }

.pitch { font-size:17.5px; line-height:1.55; text-align:justify; hyphens:auto; margin:0 0 2.6rem 0; }

.grid { display:grid; grid-template-columns:1.02fr .98fr; column-gap:16mm; row-gap:3rem; align-items:start; }
.grid > section, .grid > .algo { margin-bottom:0; }
section { margin-bottom:2rem; }
h3.sec { font-size:17px; font-weight:bold; margin-bottom:.7rem; }
h1.page { font-size:23px; font-weight:bold; margin-bottom:.6rem; }
p { text-align:justify; hyphens:auto; margin-bottom:.7rem; }
.lede { font-size:16.5px; max-width:68ch; margin-bottom:2rem; }

.algo { margin-bottom:2.4rem; }
/* The form is the page's job, so it sits right under the pitch at full measure
   instead of being one cell of a three-cell grid. Centred as a BLOCK with the
   text still left-aligned: a centred headline over two buttons is the SaaS
   hero this site is deliberately not. No border, no box -- separation is
   whitespace, same as everywhere else here. */
.algo#join { max-width:62ch; margin:0 auto 3.4rem auto; }
.algo#join .algo-cap { font-size:17px; }
.algo-cap { font-size:15px; margin-bottom:.5rem; }
.seatline { font-size:13.5px; margin-bottom:1.1rem; }
.seatline b { font-weight:bold; }
.algo-cap b { font-weight:bold; }
.field { display:grid; grid-template-columns:30mm 1fr; align-items:baseline; margin-bottom:.9rem; }
.field label { font-style:italic; font-size:14.5px; }
.field input[type=text], .field input[type=email], .field select {
  font-family:inherit; font-size:14.5px; color:var(--ink);
  border:none; border-bottom:.8px solid #b5b5b5; background:transparent;
  padding:.1rem 0; width:100%; border-radius:0; outline:none; transition:border-color 150ms ease; }
.field input:focus, .field select:focus { border-bottom-color:var(--link); }
.cvline { margin:.9rem 0; font-size:14px; }
.cvline .tex, .tex { font-family:monospace; font-size:12.5px; }
.consent { font-size:13px; margin-top:.9rem; }
.consent input { margin-right:.45rem; }
button.submit { font-family:inherit; font-size:14.5px; font-variant:small-caps;
  background:var(--ink); color:var(--paper); border:none; border-radius:0;
  padding:.4rem 1.5rem; margin-top:1rem; cursor:pointer; transition:background 150ms ease; }
button.submit:hover { background:#000; }

table { border-collapse:collapse; margin:.3rem 0 .4rem 0; font-size:14px; }
th { font-weight:bold; }
th, td { padding:.3rem 0 .3rem 3rem; text-align:right; }
td:first-child, th:first-child { padding-left:0; text-align:left; }
thead tr { border-top:1px solid var(--ink); border-bottom:.6px solid var(--ink); }
tbody tr:last-child { border-bottom:1px solid var(--ink); }
.tabnote { font-size:13px; margin-top:.6rem; }

table.wide { width:100%; font-size:13.8px; }
table.wide th, table.wide td { padding:.3rem 1.1rem .3rem 0; text-align:left; vertical-align:baseline; }
table.wide th:last-child, table.wide td:last-child { padding-right:0; }
td.co { font-variant:small-caps; white-space:nowrap; }
td.pos { font-style:italic; }
td.num { white-space:nowrap; }

.twocol { column-count:2; column-gap:16mm; margin-top:.6rem; }
.bib { list-style:none; counter-reset:bib; font-size:13.8px; }
.bib li { counter-increment:bib; padding-left:2.1em; text-indent:-2.1em;
  margin-bottom:.75rem; break-inside:avoid; }
.bib li::before { content:"[" counter(bib) "]"; margin-right:.7em; }
.bib li:nth-child(6n+1)::before { color:var(--red); }
.bib li:nth-child(6n+2)::before { color:var(--orange); }
.bib li:nth-child(6n+3)::before { color:var(--ochre); }
.bib li:nth-child(6n+4)::before { color:var(--green); }
.bib li:nth-child(6n+5)::before { color:var(--blue); }
.bib li:nth-child(6n+6)::before { color:var(--violet); }
.bib .co { font-variant:small-caps; }
.bib .pos { font-style:italic; }
.bib .meta { color:#333; }

.scoreline { font-size:30px; font-weight:bold; margin-bottom:.3rem; }
.reachline { font-size:15px; font-style:italic; margin-bottom:1.2rem; }
.flagline { font-size:14.5px; margin-bottom:2.4rem; }
.flagline .opt { font-variant:small-caps; margin-right:1.1rem; color:var(--ink);
  border-bottom:1.5px solid transparent; padding-bottom:.1rem; cursor:pointer; }
.flagline .opt.on { border-bottom-color:var(--ink); font-weight:bold; }
.heartnote { margin-top:2.4rem; width:60%; font-size:13.5px; }
.heartnote .star { color:var(--red); }

.footnote { margin-top:2.4rem; width:55%; font-size:12.5px; color:#222; }
.pagenum { text-align:center; margin-top:2.2rem; font-size:13px; }
.version { text-align:center; font-size:11.5px; color:#666; margin-top:.4rem; }

@media (max-width:860px) {
  .grid { grid-template-columns:1fr; }
  .twocol { column-count:1; }
  .rh-inner { flex-wrap:wrap; }
  .rh-left .rh-sub { display:none; }
  .footnote, .heartnote { width:100%; }
  td.pos { font-size:13px; }
}
"""

RAINBOW_JS = """
document.querySelectorAll('.rainbow').forEach(el => {
  let i = 0;
  el.innerHTML = [...el.textContent].map(ch =>
    ch === ' ' ? ' ' : `<span class="rb${(i++ % 6) + 1}">${ch}</span>`
  ).join('');
});
"""


def esc(s):
    return html.escape(str(s) if s is not None else "", quote=True)


def json_in_html(data) -> str:
    """json.dumps for a <script> block. The four characters that can end the
    element or break a JS string literal leave as \\uXXXX escapes; JSON stays
    lossless because \\uXXXX is the same string to any JSON reader.
    '&' is deliberately untouched: HTML never entity-decodes inside <script>."""
    return (json.dumps(data)
            .replace("<", "\\u003c")
            .replace(">", "\\u003e")
            .replace(" ", "\\u2028")
            .replace(" ", "\\u2029"))


def safe_url(u) -> str:
    """Only http(s) survives. javascript:, data:, vbscript: and every other
    scheme (including a scheme-relative //host) become the empty string, so a
    dropped link is indistinguishable from a listing that never had one."""
    s = str(u or "").strip()
    return s if re.match(r"https?://", s, re.I) else ""


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:80]


def nav(root: str, active: str) -> str:
    def link(href, label, key, cls=""):
        c = ("active " if key == active else "") + cls
        attr = f' class="{c.strip()}"' if c.strip() else ""
        return f'<a href="{href}"{attr}>{label}</a>'
    return f"""<nav class="runhead"><div class="rh-inner">
<div class="rh-left"><a class="wordmark" href="{root}index.html">dewsletter</a><span class="rh-sub">deterministic internship matching</span></div>
<div class="rh-links">
{link(root + 'index.html#why', 'why', 'why')}
{link(root + 'index.html#how', 'how', 'how')}
{link(root + 'index.html#data', 'data', 'data')}
{link(root + 'cv.html', 'cv report', 'cv')}
{link(root + 'jobs/index.html', 'all listings', 'jobs')}
{link(root + 'index.html#join', 'join', 'join', 'rh-join')}
</div></div></nav>"""


def page(title, description, canonical, root, active, body, extra_head="", script=""):
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(description)}">
<link rel="canonical" href="{canonical}">
<link rel="stylesheet" href="{root}style.css">
{extra_head}
</head>
<body>
{nav(root, active)}
<div class="sheet">
{body}
</div>
<script>{RAINBOW_JS}{script}</script>
</body>
</html>"""


FORM_HTML = """<div class="algo" id="join">
  <div class="algo-cap"><b class="rainbow">Submit a profile, receive matches.</b></div>
  <div class="seatline">membership is capped at <b>{capacity}</b> people, so every mail
  stays personally scored. <b id="seats-left">{left} seats left</b>. one person leaves, one seat opens.</div>
  <form id="join-form">
    <div class="field"><label>name</label><input id="f-name" type="text" autocomplete="name"></div>
    <div class="field"><label>e-mail</label><input id="f-email" type="email" autocomplete="email" required></div>
    <div class="field"><label>level</label>
      <select id="f-level"><option value="bs">BS student</option><option value="ms">MS student</option><option value="phd">PhD student</option></select>
    </div>
    <div class="field"><label>interests</label><input id="f-interests" type="text" placeholder="ai infra, agents, devtools, &hellip;"></div>
    <div class="cvline">or upload a CV and the profile fills itself:
      <span class="tex">\\includegraphics{{your_cv.pdf}}</span> <a href="cv.html">see what it reads</a></div>
    <div class="consent"><label><input id="f-consent" type="checkbox"> I consent to receiving match mails.
      One mail comes first, to confirm this address is yours; nothing else is sent until you click it.
      Leaving takes one click on the page linked in every mail. Data stays in the EU region,
      deletable any time (KVKK/GDPR).</label></div>
    <button class="submit" type="submit">submit profile</button>
    <div id="join-msg" class="tabnote"></div>
  </form>
</div>"""

JOIN_JS = """
const SB = '%(url)s';
const SBK = '%(key)s';
const sbHeaders = {apikey: SBK, Authorization: 'Bearer ' + SBK, 'Content-Type': 'application/json'};

fetch(SB + '/rest/v1/rpc/sightstone_seats', {method: 'POST', headers: sbHeaders, body: '{}'})
  .then(r => r.json())
  .then(j => { const el = document.getElementById('seats-left');
    if (el && j.capacity) el.textContent = (j.capacity - j.taken) + ' seats left'; })
  .catch(() => {});

document.getElementById('join-form').addEventListener('submit', async e => {
  e.preventDefault();
  const msg = document.getElementById('join-msg');
  const email = document.getElementById('f-email').value.trim();
  if (!document.getElementById('f-consent').checked) {
    msg.textContent = 'the consent box is not decoration; dewsletter cannot mail you without it.';
    return;
  }
  if (!email) { msg.textContent = 'an e-mail address is the one thing dewsletter cannot infer.'; return; }
  const body = {
    email: email,
    name: document.getElementById('f-name').value.trim() || null,
    level: document.getElementById('f-level').value,
    interests: document.getElementById('f-interests').value.split(',').map(s => s.trim()).filter(Boolean),
    mail_consent: true,
    kvkk_accepted_at: new Date().toISOString()
  };
  msg.textContent = 'submitting…';
  const r = await fetch(SB + '/rest/v1/sightstone_subscribers', {
    method: 'POST', headers: sbHeaders, body: JSON.stringify(body)});
  if (r.status === 201) {
    msg.textContent = 'saved. the confirming mail goes out with the next morning run — one link in it and the seat is yours. nothing else is sent until you click it.';
    document.querySelector('#join-form .submit').disabled = true;
    const el = document.getElementById('seats-left');
    const m = el.textContent.match(/\\d+/);
    if (m) el.textContent = (parseInt(m[0]) - 1) + ' seats left';
  } else {
    const t = await r.text();
    if (r.status === 409) msg.textContent = 'this address is already signed up. if you never clicked the confirm link, it is in your mail.';
    else if (t.includes('no seats left')) {
      // The waitlist had no door. The table, the D8 guard, run_invites, the
      // invite mail and accept.html all existed and none of them could ever
      // fire, because nothing on this page ever wrote a waitlist row. The old
      // message told a full-house visitor to wait for somebody else to leave
      // and gave them nothing to do -- a dead end on the only screen that
      // matters.
      msg.textContent = 'every seat is taken. putting you in the queue…';
      const w = await fetch(SB + '/rest/v1/sightstone_waitlist', {
        method: 'POST', headers: sbHeaders,
        body: JSON.stringify({email: body.email, mail_consent: true,
                              kvkk_accepted_at: body.kvkk_accepted_at})});
      if (w.status === 201) {
        msg.textContent = 'you are in the queue. the moment a seat opens the oldest waiting address is mailed, and you have 48 hours to take it.';
        document.querySelector('#join-form .submit').disabled = true;
      } else if (w.status === 409) {
        msg.textContent = 'you are already in the queue. the next free seat goes to whoever has waited longest.';
      } else {
        const wt = await w.text();
        // D8: the guard rejects a queue row while seats are free. If we land
        // here a seat opened between the two requests, so say that and not
        // "error".
        msg.textContent = wt.includes('seats available')
          ? 'a seat just opened. submit again.'
          : 'could not reach the queue (' + w.status + '). try again in a minute.';
      }
    }
    else msg.textContent = 'could not save (' + r.status + '). try again in a minute.';
  }
});
"""


def bib_entry(r: dict, href: str) -> str:
    reason = "; ".join(r["reasons"][:4]).replace(" in title", " in title")
    reason = re.sub(r"(interest|skill) '([^']+)' in title", r"\2 in title", reason)
    link = (f'<a href="{esc(safe_url(href))}">apply</a>' if safe_url(r.get("link"))
            else "<i>link not found, search it yourself</i>")
    return (f'<li><span class="co">{esc(r["company"])}</span>. '
            f'<span class="pos">{esc(r["position"])}.</span> '
            f'{esc(r.get("location") or "location unlisted")}. {link}. '
            f'<span class="meta">score {r["score"]}: {esc(reason)}.</span></li>')


def build_index(jobs, results, stats, dupes_removed, seats):
    usa = sum(1 for j in jobs if j["source"].endswith("usa"))
    intl = sum(1 for j in jobs if j["source"].endswith("intl"))
    remote = sum(1 for j in jobs if j["remote"])
    n = len(jobs)
    # Straight off match.run's own census, never a second guess: how many
    # listings the geo rule removed before scoring, and how many were left for
    # scoring to look at. Without these two the page shows "matched: 1" against
    # 613 listings and reads as a broken engine rather than a hard profile.
    geo_cut = sum(stats.get(b, 0) for b in match.GEO_BUCKETS)
    reachable = n - geo_cut
    matches_html = "".join(bib_entry(r, r.get("link") or "") for r in results[:6])
    form_html = FORM_HTML.format(capacity=seats["capacity"],
                                 left=seats["capacity"] - seats["taken"])

    body = f"""
<div class="maketitle">
  <h1>Deterministic Matching of Student Profiles<br>to Startup Internships</h1>
  <div class="author">dewsletter, <a href="https://noseydewdrop.com">noseydewdrop.com</a></div>
  <div class="date">{TODAY} &middot; rebuilt once a day</div>
</div>

<p class="pitch">You write down what you can do. Every morning dewsletter reads
<b>{n} live AI/ML internship listings</b>, scores each one against your profile, and
<b>mails you only the new matches</b>. Every match carries its <u>named reasons</u>, so
you can see exactly why it was sent. When nothing new fits, no mail is sent.</p>

{form_html}

<div class="grid">
  <section id="why">
    <h3 class="sec rainbow">Why should this exist?</h3>
    <p>Listings are scattered, stale and noisy ({dupes_removed} duplicates deleted just this
    morning), but that is not the real problem. The real problem:
    <b>people still fail to find internships</b>. The one who wins is usually not the best
    candidate. It is <u>the most alert one</u>, the one who saw the posting first, the one
    with <u>the most connections</u>. This site exists to <b>delete that advantage</b>.
    Dewsletter reads every listing every morning, for everyone, so nobody wins just by
    watching job boards harder than you.</p>
  </section>

  <section id="how">
    <h3 class="sec rainbow">How does it work?</h3>
    <p>Sources are parsed into <b>a single schema</b> every morning. Each listing carries
    company, position, location, remote flag, salary when public, and the application link.
    A listing with no link still enters, marked <i>link not found, search it yourself</i>.
    Your profile (interests, skills, level, location) is scored against every listing;
    <b>a point is never awarded without a reason string attached</b>. <u>No black box, no
    language model.</u></p>
  </section>

  <section id="data">
    <h3 class="sec rainbow">The dataset today</h3>
    <table>
      <thead><tr><th>segment</th><th>count</th></tr></thead>
      <tbody>
        <tr><td>USA internships</td><td>{usa}</td></tr>
        <tr><td>International internships</td><td>{intl}</td></tr>
        <tr><td>remote positions</td><td>{remote}</td></tr>
        <tr><td>duplicates removed this morning</td><td>{dupes_removed}</td></tr>
        <tr><td>reachable for the sample profile</td><td>{reachable}</td></tr>
        <tr><td>matched for the sample profile below</td><td>{stats["matched"]}</td></tr>
      </tbody>
    </table>
    <p class="tabnote">The full listing is public: <a href="jobs/index.html">all {n} rows</a>, refreshed daily.</p>
  </section>
</div>

<section id="matches">
  <h3 class="sec"><span class="rainbow">Sample matches</span>
  <span style="font-weight:normal;font-size:13.5px">(profile: AI infra / agents, BS, in Turkey, not relocating)</span></h3>
  <p class="tabnote">This sample is deliberately the hardest case on the board: someone who
  cannot move countries and cannot take a US-only remote role. {geo_cut} of today's {n} listings
  are unreachable for her before a single word is scored, which is why so few survive. A profile
  that can relocate reaches all {n}. Dewsletter would rather show one listing with a reason than
  twenty without.</p>
  <div class="twocol"><ol class="bib">{matches_html}</ol></div>
</section>

<div class="footnote">* The dataset is public; your profile is not. Mails are sent only
when a new listing matches your profile. The rebuild is asked for at 09:00 UTC+3,
but the scheduler running it is best-effort and does not promise a time: measured
over {SCHEDULE_RUNS} scheduled runs, the median build landed {SCHEDULE_MEDIAN_LATE_MIN} minutes late and the
latest landed {SCHEDULE_WORST_LATE}. So: once a day, most often in the morning, never guaranteed
to the minute.</div>
<div class="pagenum">1</div>
<div class="version">{VERSION}</div>
"""
    return page("Deterministic student internship matching",
                f"Curated, daily-refreshed dataset of {n} AI/ML student internships with deterministic profile matching and named reasons.",
                f"{BASE_URL}/", "", "index", body,
                script=JOIN_JS % {"url": SUPABASE_URL, "key": SUPABASE_ANON})


def build_cv_page(total_jobs: int):
    fixture = (Path(__file__).parent / "tests" / "cv_strong.txt").read_text()
    v = cv_critique.critique_text(fixture, found_job=False)
    score_rows = ""
    for part in v["score_parts"]:
        m = re.match(r"(.+?) (-?\d+/\d+|-\d+) ?(?:\((.+)\))?$", part)
        if m:
            name, pts, evid = m.group(1), m.group(2), m.group(3) or "present"
            score_rows += f"<tr><td>{esc(name)}</td><td>{esc(evid)}</td><td>{esc(pts)}</td></tr>"
    demand_rows = "".join(f"<tr><td>{esc(t)}</td><td>{c}</td></tr>" for t, c in v["demand_top"])
    findings = "".join(f"<li>{esc(line)}</li>" for line in v["lines"])
    note = esc(v["note"] or "")

    body = f"""
<h1 class="page rainbow">Can your CV even be seen?</h1>
<p class="lede">Upload a CV and dewsletter reads it the way the market does: against
every live internship title, counting what it finds. No taste, no vibes, no model.
Every sentence below carries a measured number, and every gap comes with the exact
move that closes it. It is blunt because the market is blunt; it is useful because
the market is not.</p>

<div class="cvline"><span class="tex">\\includegraphics{{your_cv.pdf}}</span>
  <label style="cursor:pointer"><u>choose a .pdf / .txt / .md file</u><input id="cv-file" type="file"
    accept=".pdf,.txt,.md,application/pdf,text/plain" style="display:none"></label>
  &ensp;or paste the text below. <i>the file is read inside your browser; nothing is uploaded.</i></div>
<textarea id="cv-input" rows="7" placeholder="paste your CV text here. it never leaves this page: no upload, no server, no model reads it."
  style="width:100%; font-family:inherit; font-size:14px; color:var(--ink); background:transparent;
  border:none; border-bottom:.8px solid #b5b5b5; outline:none; resize:vertical; padding:.3rem 0"></textarea>
<div style="margin:.7rem 0 1.2rem 0">
  <button class="submit" id="cv-run" type="button" style="background:var(--ink); color:var(--paper);
    border:none; border-radius:0; padding:.4rem 1.5rem; font-family:inherit; font-size:14.5px;
    font-variant:small-caps; cursor:pointer">read my cv</button>
</div>
<div class="flagline">after reading, tell it one thing:
  <span class="opt" data-found="true" data-note="for once, both the CV and the network did their job.">i found a job</span>
  <span class="opt on" data-found="false" data-note="{note}">i did not find a job</span>
</div>

<div class="grid">
  <section>
    <p style="font-style:italic; font-size:13.5px; margin-bottom:1rem" id="cv-samplenote">below:
    a sample report, generated by dewsletter from a student CV against this morning's dataset.
    paste yours above to replace it.</p>
    <h3 class="sec rainbow">The score</h3>
    <div class="scoreline" id="cv-score">{v["score"]} / 100</div>
    <div class="reachline" id="cv-reach">your vocabulary reaches {v["matched"]} of {v["total"]} live
    internships. the other {v["total"] - v["matched"]} cannot even see you.</div>
    <table>
      <thead><tr><th>component</th><th>evidence counted</th><th>points</th></tr></thead>
      <tbody id="cv-parts">{score_rows}</tbody>
    </table>
  </section>
  <section>
    <h3 class="sec rainbow">What the market wants right now</h3>
    <p>Counted over {v["total"]} live internship titles this morning. This column is why
    the findings are not opinions.</p>
    <table>
      <thead><tr><th>term</th><th>live titles</th></tr></thead>
      <tbody>{demand_rows}</tbody>
    </table>
  </section>
</div>

<section style="margin-top:3rem">
  <h3 class="sec rainbow">Findings</h3>
  <ol class="bib" id="cv-findings">{findings}</ol>
</section>

<div class="heartnote"><span class="star">*</span> <span id="heartnote-text">{note}</span></div>
<div class="pagenum">3</div>
<div class="version">{VERSION}</div>
"""
    script = """
let lastScore = null;

function currentFound() {
  const on = document.querySelector('.flagline .opt.on');
  return on ? on.dataset.found === 'true' : false;
}

document.querySelectorAll('.flagline .opt').forEach(o => o.addEventListener('click', () => {
  document.querySelectorAll('.flagline .opt').forEach(x => x.classList.remove('on'));
  o.classList.add('on');
  document.getElementById('heartnote-text').textContent =
    lastScore !== null ? (heartsNote(o.dataset.found === 'true', lastScore) || '') : o.dataset.note;
}));

function renderReport(v) {
  lastScore = v.score;
  document.getElementById('cv-samplenote').textContent =
    'your report, generated in your browser just now. nothing was uploaded anywhere.';
  document.getElementById('cv-score').textContent = v.score + ' / 100';
  document.getElementById('cv-reach').textContent =
    'your vocabulary reaches ' + v.matched + ' of ' + v.total +
    ' live internships. the other ' + (v.total - v.matched) + ' cannot even see you.';
  const tb = document.getElementById('cv-parts');
  tb.innerHTML = '';
  for (const [name, evd, pts] of v.parts) {
    const tr = document.createElement('tr');
    for (const val of [name, evd, pts]) {
      const td = document.createElement('td');
      td.textContent = val;
      tr.appendChild(td);
    }
    tb.appendChild(tr);
  }
  const ol = document.getElementById('cv-findings');
  ol.innerHTML = '';
  for (const line of v.lines) {
    const li = document.createElement('li');
    li.textContent = line;
    ol.appendChild(li);
  }
  document.getElementById('heartnote-text').textContent = v.note || '';
}

document.getElementById('cv-run').addEventListener('click', () => {
  const text = document.getElementById('cv-input').value;
  if (text.trim().length < 40) {
    document.getElementById('cv-samplenote').textContent =
      'that is not a CV yet. paste the whole text, then hit read.';
    return;
  }
  renderReport(critique(text, currentFound()));
  document.getElementById('cv-score').scrollIntoView({behavior: 'smooth', block: 'center'});
});

function loadScript(src) {
  return new Promise((res, rej) => {
    const s = document.createElement('script');
    s.src = src; s.onload = res; s.onerror = rej;
    document.head.appendChild(s);
  });
}

async function extractPdf(file) {
  if (!window.pdfjsLib) {
    await loadScript('vendor/pdf.min.js');
    pdfjsLib.GlobalWorkerOptions.workerSrc = 'vendor/pdf.worker.min.js';
  }
  const doc = await pdfjsLib.getDocument({data: await file.arrayBuffer()}).promise;
  const lines = [];
  let cur = [];
  for (let i = 1; i <= doc.numPages; i++) {
    const tc = await (await doc.getPage(i)).getTextContent();
    let lastY = null;
    for (const it of tc.items) {
      const y = it.transform[5];
      if (lastY !== null && Math.abs(y - lastY) > 2) { lines.push(cur.join('')); cur = []; }
      cur.push(it.str);
      if (it.hasEOL) { lines.push(cur.join('')); cur = []; lastY = null; } else lastY = y;
    }
    lines.push(cur.join('')); cur = [];
  }
  return lines.join('\n');
}

document.getElementById('cv-file').addEventListener('change', async e => {
  const f = e.target.files[0];
  if (!f) return;
  const note = document.getElementById('cv-samplenote');
  let text;
  if (f.name.toLowerCase().endsWith('.pdf') || f.type === 'application/pdf') {
    note.textContent = 'reading the pdf inside your browser…';
    try { text = await extractPdf(f); }
    catch (err) { note.textContent = 'could not parse this pdf. paste the text instead.'; return; }
    if (text.trim().length < 40) {
      note.textContent = 'this pdf has no text layer (a scanned image?). paste the text instead.';
      return;
    }
  } else {
    text = await f.text();
  }
  document.getElementById('cv-input').value = text;
  document.getElementById('cv-run').click();
});
"""
    return page("Can your CV even be seen? · dewsletter",
                f"Deterministic CV critique against {total_jobs} live internships: measured gaps, concrete moves, no black box. Runs in your browser; the CV is never uploaded.",
                f"{BASE_URL}/cv.html", "", "cv", body,
                extra_head='<script src="cv-engine.js"></script>', script=script)


def build_unsubscribe():
    body = """
<h1 class="page rainbow">Leaving?</h1>
<p class="lede" id="unsub-msg">one moment, dewsletter is checking your link&hellip;</p>
<p class="tabnote"><a href="index.html">back to the paper</a> &middot; a seat opens the moment you leave.</p>
<div class="version">""" + VERSION + """</div>
"""
    script = f"""
const SB = '{SUPABASE_URL}';
const SBK = '{SUPABASE_ANON}';
const token = new URLSearchParams(location.search).get('token');
const msg = document.getElementById('unsub-msg');
if (!token) {{ msg.textContent = 'no token in the link. use the link from your mail.'; }}
else fetch(SB + '/rest/v1/rpc/sightstone_unsubscribe', {{
  method: 'POST',
  headers: {{apikey: SBK, Authorization: 'Bearer ' + SBK, 'Content-Type': 'application/json'}},
  body: JSON.stringify({{token: token}})
}}).then(r => r.json()).then(ok => {{
  msg.textContent = ok
    ? 'done. no more mail, and your seat just opened for someone else.'
    : 'this link was already used or never existed.';
}}).catch(() => {{ msg.textContent = 'could not reach the database. try again in a minute.'; }});
"""
    # NOT "one-click": this is static GitHub Pages and POST answers 405, so
    # RFC 8058 one-click is impossible here. Measured live 2026-09-01.
    return page("Unsubscribe · dewsletter", "Leave in one click, on this page.",
                f"{BASE_URL}/unsubscribe.html", "", "", body,
                extra_head='<meta name="robots" content="noindex">', script=script)


def build_confirm():
    """S10. Without this page nobody new can ever be mailed.

    D2 made send_mail drop every row whose confirmed_at is null. That closed
    the consent hole and, on its own, also closed the front door: a stranger
    signs up, has no way to say "yes that is me", and is held back forever.
    This is the other half -- the link in the confirmation mail lands here.
    """
    body = """
<h1 class="page rainbow">Is that you?</h1>
<p class="lede" id="confirm-msg">one moment, dewsletter is checking your link&hellip;</p>
<p class="tabnote"><a href="index.html">back to the paper</a> &middot; you only ever do this once.</p>
<div class="version">""" + VERSION + """</div>
"""
    script = f"""
const SB = '{SUPABASE_URL}';
const SBK = '{SUPABASE_ANON}';
const token = new URLSearchParams(location.search).get('token');
const msg = document.getElementById('confirm-msg');
if (!token) {{ msg.textContent = 'no token in the link. use the link from your mail.'; }}
else fetch(SB + '/rest/v1/rpc/sightstone_confirm', {{
  method: 'POST',
  headers: {{apikey: SBK, Authorization: 'Bearer ' + SBK, 'Content-Type': 'application/json'}},
  body: JSON.stringify({{token: token}})
}}).then(r => r.json()).then(ok => {{
  msg.textContent = ok
    ? 'confirmed. the seat is yours, and the next listing that matches comes to you.'
    : 'this link was already used, or it expired after 48 hours. sign up again.';
}}).catch(() => {{ msg.textContent = 'could not reach the database. try again in a minute.'; }});
"""
    return page("Confirm · dewsletter", "Confirm your address, once.",
                f"{BASE_URL}/confirm.html", "", "", body,
                extra_head='<meta name="robots" content="noindex">', script=script)


def build_accept():
    """S9b left this hole and S10 closes it: the invite had nowhere to land.

    sightstone_accept_invite(token) has been in the schema, granted to anon,
    since S9b. Nothing ever called it. The invite mail pointed at the home
    page, which reads no token at all -- so the promised seat could be offered,
    clicked, and still expire 48 hours later without the person being able to
    take it. A promise nobody could accept.
    """
    body = """
<h1 class="page rainbow">Your seat?</h1>
<p class="lede" id="accept-msg">one moment, dewsletter is checking your invite&hellip;</p>
<p class="tabnote"><a href="index.html">back to the paper</a> &middot; an invite is held for 48 hours.</p>
<div class="version">""" + VERSION + """</div>
"""
    script = f"""
const SB = '{SUPABASE_URL}';
const SBK = '{SUPABASE_ANON}';
const token = new URLSearchParams(location.search).get('token');
const msg = document.getElementById('accept-msg');
if (!token) {{ msg.textContent = 'no token in the link. use the link from your invite mail.'; }}
else fetch(SB + '/rest/v1/rpc/sightstone_accept_invite', {{
  method: 'POST',
  headers: {{apikey: SBK, Authorization: 'Bearer ' + SBK, 'Content-Type': 'application/json'}},
  body: JSON.stringify({{token: token}})
}}).then(r => r.json()).then(ok => {{
  msg.textContent = ok
    ? 'the seat is yours. nothing else to confirm -- the next listing that matches comes to you.'
    : 'this invite was already used, or it expired after 48 hours and passed to the next person.';
}}).catch(() => {{ msg.textContent = 'could not reach the database. try again in a minute.'; }});
"""
    return page("Your seat · dewsletter", "Accept the seat you were offered.",
                f"{BASE_URL}/accept.html", "", "", body,
                extra_head='<meta name="robots" content="noindex">', script=script)


def write_accept(root):
    """Owns the filename too, so main() gains a call and not a literal."""
    (root / "accept.html").write_text(build_accept())


def write_confirm(root):
    """Owns the filename too, so main() gains a call and not a literal."""
    (root / "confirm.html").write_text(build_confirm())


def build_jobs_index(jobs):
    n = len(jobs)
    rows = ""
    for i, j in enumerate(jobs, 1):
        loc = esc(j["location"] or "")
        link = (f'<a href="{slugify(j["company"] + "-" + j["position"])}.html">details</a>'
                if True else "")
        apply_ = (f'<a href="{esc(safe_url(j["link"]))}" rel="nofollow">apply</a>'
                  if safe_url(j.get("link")) else "<i>link not found</i>")
        rows += (f'<tr><td class="num">{i}</td><td class="co">{esc(j["company"])}</td>'
                 f'<td class="pos">{esc(j["position"])}</td><td>{loc}</td>'
                 f'<td class="num">{esc(j["salary"] or "")}</td><td class="num">{esc(j["age"] or "")}</td>'
                 f'<td>{link} &middot; {apply_}</td></tr>')
    body = f"""
<h1 class="page rainbow">The full listing</h1>
<p class="lede">All {n} live internships, refreshed daily at 09:00 UTC+3. A listing with
no application link is kept and marked, not dropped.</p>
<table class="wide">
  <caption>live listings, {TODAY}</caption>
  <thead><tr><th>#</th><th>company</th><th>position</th><th>location</th><th>salary</th><th>age</th><th></th></tr></thead>
  <tbody>{rows}</tbody>
</table>
<div class="tabnote" style="margin-top:1.4rem"><a href="../index.html#join">&larr; back to the paper, submit a profile</a></div>
<div class="pagenum">2</div>
<div class="version">{VERSION}</div>
"""
    return page(f"All {n} listings · dewsletter",
                f"{n} curated AI/ML student internships, one page per listing, refreshed daily.",
                f"{BASE_URL}/jobs/", "../", "jobs", body)


def job_jsonld(job, canonical):
    data = {"@context": "https://schema.org/", "@type": "JobPosting",
            "title": job["position"], "datePosted": TODAY_ISO, "employmentType": "INTERN",
            "hiringOrganization": {"@type": "Organization", "name": job["company"],
                                   "sameAs": safe_url(job.get("company_url")) or None},
            "jobLocation": {"@type": "Place", "address": job.get("location") or "unspecified"},
            "directApply": bool(safe_url(job.get("link"))), "url": canonical}
    if job.get("remote"):
        data["jobLocationType"] = "TELECOMMUTE"
    return '<script type="application/ld+json">' + json_in_html(data) + "</script>"


def build_job_page(job, slug):
    canonical = f"{BASE_URL}/jobs/{slug}.html"
    apply_html = (f'<a href="{esc(safe_url(job["link"]))}" rel="nofollow">apply at the source &rarr;</a>'
                  if safe_url(job.get("link")) else
                  f'link not found, search it yourself: <i>{esc(job["company"])} {esc(job["position"])}</i>')
    rows = "".join(f"<tr><td>{k}</td><td>{esc(v)}</td></tr>" for k, v in [
        ("company", job["company"]), ("location", job.get("location") or "unlisted"),
        ("remote", "yes" if job.get("remote") else "no"),
        ("salary", job.get("salary") or "not public"),
        ("listed", job.get("age") or "?"), ("source", job["source"])])
    body = f"""
<div class="tabnote" style="margin:0 0 1.4rem 0"><a href="../index.html">index</a> &middot; <a href="index.html">all listings</a></div>
<div class="grid">
  <section>
    <h1 class="page">{esc(job["position"])}</h1>
    <div style="font-size:17px; margin-bottom:1rem"><span class="co" style="font-variant:small-caps">{esc(job["company"])}</span></div>
    <p style="font-size:16.5px">{apply_html}</p>
    <p style="font-size:13.5px; color:#333">internship listing &middot; retrieved {TODAY}</p>
  </section>
  <section>
    <table>
      <thead><tr><th>field</th><th>value</th></tr></thead>
      <tbody>{rows}</tbody>
    </table>
  </section>
</div>
<div class="version">{VERSION}</div>
"""
    title = f'{job["company"]} - {job["position"]} (internship)'
    desc = f'{job["position"]} internship at {job["company"]}, {job.get("location") or "location unlisted"}. Student-suitable, refreshed {TODAY_ISO}.'
    return page(title, desc, canonical, "../", "jobs", body, extra_head=job_jsonld(job, canonical))


def robots_extra() -> str:
    """The extra robots.txt group that closes /u/ to crawlers.

    Returned as a suffix, never as a rewrite: the existing group (Allow: /,
    Sitemap:) is untouched, a second group for the same user-agent is appended.
    Both groups merge, and for /u/anything the longer rule wins."""
    return "\nUser-agent: *\nDisallow: /u/\n"


def job_slug_map(jobs: list) -> dict:
    """(company, position) -> the slug main() writes to disk.

    Same base slug, same collision counter, same order. The frozen corpus has
    16 base-slug collisions, so a page that linked to the base slug alone would
    send 16 listings to another listing's page."""
    taken, out = {}, {}
    for j in jobs:
        base = slugify(f'{j["company"]}-{j["position"]}')
        slug, k = base, 2
        while slug in taken:
            slug, k = f"{base}-{k}", k + 1
        taken[slug] = True
        out[(j["company"].strip().lower(), j["position"].strip().lower())] = slug
    return out


def slugs_on_disk(root, jobs: list) -> dict:
    """job_slug_map filtered down to pages that actually exist on disk.

    A link is never written on faith: if the file is not there, the row says so
    instead of pointing at a 404."""
    out = {}
    for key, slug in job_slug_map(jobs).items():
        if (root / "jobs" / f"{slug}.html").exists():
            out[key] = slug
    return out


def result_key(r: dict) -> tuple:
    """The identity match.dedupe collapses on, so a result finds its page."""
    return (r["company"].strip().lower(), r["position"].strip().lower())


def xml_text(s) -> str:
    """esc() plus the characters XML 1.0 cannot carry in any form.

    esc() makes the text safe for markup; it does not make it well-formed XML.
    A raw \\x0b in a job title parses as HTML and kills the feed, so the
    control range and the surrogates are dropped before escaping."""
    dead = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff]")
    return dead.sub("", esc(s))


def user_row_html(r: dict, slug) -> str:
    """One match: who, where, its page here, the source link, score, reasons."""
    detail = (f'<a href="../jobs/{slug}.html">details</a>' if slug
              else "<i>no page for this listing</i>")
    apply_ = (f'<a href="{esc(safe_url(r["link"]))}" rel="nofollow">apply</a>'
              if safe_url(r.get("link")) else "<i>link not found, search it yourself</i>")
    return (f'<li><span class="co">{esc(r["company"])}</span>. '
            f'<span class="pos">{esc(r["position"])}.</span> '
            f'{esc(r.get("location") or "location unlisted")}. '
            f'{detail} &middot; {apply_}. '
            f'<span class="meta">score {r["score"]}: '
            f'{esc("; ".join(r["reasons"]))}.</span></li>')


def user_page_html(results: list, smap: dict) -> str:
    """Every match the matcher returned, with no score threshold at all."""
    rows = "".join(user_row_html(r, smap.get(result_key(r))) for r in results)
    scores = [r["score"] for r in results]
    span = f"{min(scores)} to {max(scores)}" if scores else "none"
    body = f"""
<h1 class="page rainbow">Your matches, all of them</h1>
<p class="lede">Built from <span class="tex">profile.json</span> in this repository against
this morning's listing set, by the same matcher the rest of the site runs. It holds
{len(results)} records, scores {span}, and applies <b>no minimum score</b>: a match worth one
point is on this page.</p>
<p class="tabnote">The daily mail is a different surface. It carries its own cut-off and its
own, smaller profile, so this page is not a copy of what was mailed and does not claim to be.
Nothing here is read from the database; the only input is the profile file and the listings.</p>
<p class="tabnote">Machine-readable copy: <a href="matches.xml">atom feed</a>.</p>
<ol class="bib" id="all-matches">{rows}</ol>
<div class="version">{VERSION}</div>
"""
    return page("Your matches, all of them", "Every match, no score threshold.",
                f"{BASE_URL}/u/matches.html", "../", "", body,
                extra_head=('<meta name="robots" content="noindex">'
                            '<link rel="alternate" type="application/atom+xml" '
                            'title="matches" href="matches.xml">'))


def user_feed_xml(results: list, smap: dict) -> str:
    """The same records as an Atom feed. Same set, same order, same absence of
    a threshold; only the syntax differs."""
    entries = ""
    for r in results:
        slug = smap.get(result_key(r))
        ident = slug or slugify(f'{r["company"]}-{r["position"]}')
        target = (f"{BASE_URL}/jobs/{slug}.html" if slug
                  else safe_url(r.get("link")) or f"{BASE_URL}/u/matches.html")
        title = xml_text(f'{r["company"]} - {r["position"]}')
        summary = xml_text(f'score {r["score"]}: ' + "; ".join(r["reasons"]))
        entries += (f"<entry><title>{title}</title>"
                    f"<id>urn:dewsletter:{ident}</id>"
                    f"<updated>{TODAY_ISO}T00:00:00Z</updated>"
                    f'<link rel="alternate" href="{xml_text(safe_url(target))}"/>'
                    f"<summary>{summary}</summary></entry>")
    return ('<?xml version="1.0" encoding="UTF-8"?>'
            '<feed xmlns="http://www.w3.org/2005/Atom">'
            "<title>your matches, all of them</title>"
            f"<id>{BASE_URL}/u/matches.xml</id>"
            f"<updated>{TODAY_ISO}T00:00:00Z</updated>"
            f'<link rel="self" href="{xml_text(safe_url(BASE_URL + "/u/matches.xml"))}"/>'
            + entries + "</feed>")


def write_user_pages(root, jobs: list, results: list) -> None:
    """docs/u/: one fixed pair of files, no token, no per-person page.

    docs/ is a public git repository pushed every morning, so a page named
    after a per-person token would publish that token to the world. There is
    exactly one page here and it is built from the profile file alone."""
    out = root / "u"
    out.mkdir(parents=True, exist_ok=True)
    smap = slugs_on_disk(root, jobs)
    (out / "matches.html").write_text(user_page_html(results, smap))
    (out / "matches.xml").write_text(user_feed_xml(results, smap))


def main() -> None:
    data_dir = Path(__file__).parent / "data"
    jobs = json.loads((data_dir / "jobs.json").read_text())
    jobs, build_dupes = match.dedupe(jobs)
    meta_file = data_dir / "fetch_meta.json"
    dupes_removed = (json.loads(meta_file.read_text())["duplicates_removed"]
                     if meta_file.exists() else build_dupes)
    profile = json.loads((Path(__file__).parent.parent / "profile.json").read_text())
    results, stats = match.run(profile, jobs)

    seats_file = data_dir / "seats.json"
    seats = (json.loads(seats_file.read_text()) if seats_file.exists()
             else {"capacity": 200, "taken": 1})

    (ROOT / "jobs").mkdir(parents=True, exist_ok=True)
    (ROOT / "style.css").write_text(CSS)
    (ROOT / "index.html").write_text(build_index(jobs, results, stats, dupes_removed, seats))
    (ROOT / "cv.html").write_text(build_cv_page(len(jobs)))
    (ROOT / "unsubscribe.html").write_text(build_unsubscribe())
    write_confirm(ROOT)
    write_accept(ROOT)
    import cv_engine_js
    cv_engine_js.emit(ROOT / "cv-engine.js")
    (ROOT / "jobs" / "index.html").write_text(build_jobs_index(jobs))

    slugs, urls = set(), [f"{BASE_URL}/", f"{BASE_URL}/cv.html", f"{BASE_URL}/jobs/"]
    for job in jobs:
        base = slugify(f'{job["company"]}-{job["position"]}')
        slug, k = base, 2
        while slug in slugs:
            slug, k = f"{base}-{k}", k + 1
        slugs.add(slug)
        (ROOT / "jobs" / f"{slug}.html").write_text(build_job_page(job, slug))
        urls.append(f"{BASE_URL}/jobs/{slug}.html")

    sitemap = ['<?xml version="1.0" encoding="UTF-8"?>',
               '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    sitemap += [f"<url><loc>{esc(u)}</loc><lastmod>{TODAY_ISO}</lastmod></url>" for u in urls]
    sitemap.append("</urlset>")
    (ROOT / "sitemap.xml").write_text("\n".join(sitemap))
    write_user_pages(ROOT, jobs, results)
    (ROOT / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {BASE_URL}/sitemap.xml\n"
                                     + robots_extra())
    (ROOT / ".nojekyll").write_text("")

    n_files = sum(1 for _ in ROOT.rglob("*.html"))
    print(f"jobs: {len(jobs)} (dupes removed: {dupes_removed}) | matches: {stats['matched']} | "
          f"html pages: {n_files} | sitemap urls: {len(urls)}")


if __name__ == "__main__":
    main()
