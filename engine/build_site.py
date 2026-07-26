#!/usr/bin/env python3
"""Static site generator: jobs.json -> hundreds of plain HTML pages.

LaTeX flavor (Latin Modern, numbered sections, booktabs tables) on a real
site skeleton: navbar, columns, footer. No framework, no LLM.

Output:
  site/dist/index.html            front page (journal masthead + columns)
  site/dist/jobs/index.html       full listing, three-column bibliography
  site/dist/jobs/<slug>.html      one page PER listing (SEO surface)
  site/dist/style.css, sitemap.xml, robots.txt
"""
import html
import json
import re
import unicodedata
from datetime import date
from pathlib import Path

BASE_URL = "https://jobs.noseydewdrop.com"  # placeholder until domain is chosen
BRAND = "the engine 👾"                      # placeholder until Damla names it
ROOT = Path(__file__).parent.parent / "site" / "dist"
TODAY = date.today().isoformat()

CSS = """
@font-face { font-family:'Latin Modern'; src:url('https://cdn.jsdelivr.net/gh/vincentdoerig/latex-css@1.10.0/fonts/LM-regular.woff2') format('woff2'); font-weight:normal; font-style:normal; font-display:swap; }
@font-face { font-family:'Latin Modern'; src:url('https://cdn.jsdelivr.net/gh/vincentdoerig/latex-css@1.10.0/fonts/LM-bold.woff2') format('woff2'); font-weight:bold; font-style:normal; font-display:swap; }
@font-face { font-family:'Latin Modern'; src:url('https://cdn.jsdelivr.net/gh/vincentdoerig/latex-css@1.10.0/fonts/LM-italic.woff2') format('woff2'); font-weight:normal; font-style:italic; font-display:swap; }
:root { --ink:#111; --paper:#fff; --link:#0b4fa8; --hair:#111; }
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family:'Latin Modern','Computer Modern',Georgia,serif; color:var(--ink); background:var(--paper); font-size:15.5px; line-height:1.45; }
a { color:var(--link); text-decoration:none; }
a:hover { text-decoration:underline; }
.wrap { max-width:1100px; margin:0 auto; padding:0 24px; }

/* navbar */
nav { border-bottom:1.5px solid var(--hair); }
nav .wrap { display:flex; align-items:baseline; gap:1.6rem; padding:.7rem 24px; }
nav .brand { font-weight:bold; font-size:18px; margin-right:auto; }
nav a.item { color:var(--ink); font-size:14.5px; }
nav a.item:hover { text-decoration:underline; color:var(--link); }
nav .count { color:#444; font-size:13px; }
nav .stamp { font-style:italic; font-size:13px; color:#333; }

/* masthead (front page) */
.masthead { text-align:center; padding:2.2rem 0 1.4rem; border-bottom:.8px solid var(--hair); }
.masthead h1 { font-size:34px; line-height:1.2; margin-bottom:.5rem; }
.masthead .sub { font-style:italic; font-size:15px; }

/* column grids */
.grid { display:grid; gap:0 34px; padding:1.4rem 0; }
.grid.two { grid-template-columns:1.4fr 1fr; }
.colrule { border-left:.8px solid var(--hair); padding-left:34px; }
@media (max-width:760px){ .grid.two { grid-template-columns:1fr; } .colrule { border-left:none; padding-left:0; } }

h3.sec { font-size:17px; margin:0 0 .55rem; }
h3.sec .no { margin-right:.9rem; }
p { text-align:justify; hyphens:auto; margin-bottom:.55rem; }
.block { margin-bottom:1.5rem; }

/* bibliography entries */
.threecol { column-count:3; column-gap:30px; }
@media (max-width:1000px){ .threecol { column-count:2; } }
@media (max-width:660px){ .threecol { column-count:1; } }
.bib { list-style:none; counter-reset:bib; font-size:13.6px; }
.bib li { counter-increment:bib; padding-left:2em; text-indent:-2em; margin-bottom:.5rem; break-inside:avoid; }
.bib li::before { content:"[" counter(bib) "]"; margin-right:.6em; }
.co { font-variant:small-caps; }
.pos { font-style:italic; }
.meta { color:#333; }

/* tables, booktabs */
table { border-collapse:collapse; margin:.4rem 0; font-size:14px; width:100%; }
caption { caption-side:top; font-size:13.5px; margin-bottom:.35rem; text-align:left; }
th,td { padding:.2rem .9rem .2rem 0; text-align:left; }
thead tr { border-top:1.5px solid var(--ink); border-bottom:.8px solid var(--ink); }
tbody tr:last-child { border-bottom:1.5px solid var(--ink); }

.crumb { font-size:13px; margin:1rem 0; }
.applyline { margin:.9rem 0; font-size:16.5px; }
.pill-not-a-pill { font-variant:small-caps; }

/* footer */
footer { border-top:1.5px solid var(--hair); margin-top:2.5rem; }
footer .wrap { display:flex; gap:1.6rem; padding:.8rem 24px; font-size:13px; }
footer .right { margin-left:auto; font-style:italic; }
"""

PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="description" content="{description}">
<link rel="canonical" href="{canonical}">
<link rel="stylesheet" href="{csspath}">
{extra_head}
</head>
<body>
<nav><div class="wrap">
  <span class="brand"><a href="{rootpath}index.html" style="color:var(--ink)">{brand}</a></span>
  <a class="item" href="{rootpath}jobs/index.html">listings <span class="count">({njobs})</span></a>
  <a class="item" href="{rootpath}index.html#method">method 👩🏻‍💻</a>
  <a class="item" href="{rootpath}index.html#join">join</a>
  <span class="stamp">refreshed {today}</span>
</div></nav>
<div class="wrap">
{body}
</div>
<footer><div class="wrap">
  <span>🐞 curated for students &middot; single-applicant &middot; no referral required</span>
  <span class="right">updated daily &middot; deterministic engine, no black box</span>
</div></footer>
</body>
</html>
"""


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return text[:80]


def esc(s):
    return html.escape(s or "", quote=True)


def render(title, description, canonical, csspath, rootpath, body, njobs, extra_head=""):
    return PAGE.format(title=esc(title), description=esc(description), canonical=canonical,
                       csspath=csspath, rootpath=rootpath, body=body, njobs=njobs,
                       brand=BRAND, today=TODAY, extra_head=extra_head)


def job_jsonld(job: dict, canonical: str) -> str:
    data = {
        "@context": "https://schema.org/",
        "@type": "JobPosting",
        "title": job["position"],
        "datePosted": job.get("first_seen") or TODAY,
        "employmentType": "INTERN",
        "hiringOrganization": {"@type": "Organization", "name": job["company"],
                               "sameAs": job.get("company_url")},
        "jobLocation": {"@type": "Place", "address": job.get("location") or "unspecified"},
        "directApply": bool(job.get("link")),
        "url": canonical,
    }
    if job.get("remote"):
        data["jobLocationType"] = "TELECOMMUTE"
    return '<script type="application/ld+json">' + json.dumps(data) + "</script>"


def bib_entry(job: dict, href: str) -> str:
    loc = esc(job.get("location") or "location unlisted")
    sal = f' <span class="meta">{esc(job["salary"])}.</span>' if job.get("salary") else ""
    return (f'<li><span class="co">{esc(job["company"])}</span>. '
            f'<span class="pos"><a href="{href}">{esc(job["position"])}</a>.</span> '
            f'<span class="loc">{loc}.</span>{sal}</li>')


def job_page(job: dict, slug: str, njobs: int) -> str:
    canonical = f"{BASE_URL}/jobs/{slug}.html"
    apply_html = (f'<a href="{esc(job["link"])}" rel="nofollow">apply at the source &rarr;</a>'
                  if job.get("link") else
                  f'link not found &mdash; search it yourself: <i>{esc(job["company"])} {esc(job["position"])}</i>')
    rows = "".join(
        f"<tr><td>{k}</td><td>{esc(str(v))}</td></tr>"
        for k, v in [("company", job["company"]), ("location", job.get("location") or "unlisted"),
                     ("remote", "yes" if job.get("remote") else "no"),
                     ("salary", job.get("salary") or "not public"), ("listed", job.get("age") or "?"),
                     ("source", job["source"])] )
    body = f"""
<div class="crumb"><a href="../index.html">index</a> &middot; <a href="index.html">all listings</a></div>
<div class="grid two">
  <div>
    <h1 style="font-size:26px; line-height:1.25; margin-bottom:.4rem">{esc(job["position"])}</h1>
    <div style="font-size:17px; margin-bottom:1rem"><span class="co">{esc(job["company"])}</span></div>
    <p class="applyline">{apply_html}</p>
    <p style="font-size:13.5px; color:#333">internship listing &middot; retrieved {TODAY}</p>
  </div>
  <div class="colrule">
    <table>
    <caption><b>Table 1:</b> listing facts</caption>
    <thead><tr><th>field</th><th>value</th></tr></thead>
    <tbody>{rows}</tbody>
    </table>
  </div>
</div>
"""
    title = f'{job["company"]} — {job["position"]} (internship)'
    desc = f'{job["position"]} internship at {job["company"]}, {job.get("location") or "location unlisted"}. Student-suitable, refreshed {TODAY}.'
    return render(title, desc, canonical, "../style.css", "../", body, njobs,
                  extra_head=job_jsonld(job, canonical))


def main() -> None:
    jobs = json.loads((Path(__file__).parent / "data" / "jobs.json").read_text())
    n = len(jobs)
    (ROOT / "jobs").mkdir(parents=True, exist_ok=True)
    (ROOT / "style.css").write_text(CSS)

    slugs, entries, urls = set(), [], []
    for job in jobs:
        base = slugify(f'{job["company"]}-{job["position"]}')
        slug, k = base, 2
        while slug in slugs:
            slug, k = f"{base}-{k}", k + 1
        slugs.add(slug)
        (ROOT / "jobs" / f"{slug}.html").write_text(job_page(job, slug, n))
        entries.append(bib_entry(job, f"{slug}.html"))
        urls.append(f"{BASE_URL}/jobs/{slug}.html")

    listing_body = f"""
<div class="crumb"><a href="../index.html">index</a></div>
<h1 style="font-size:26px; margin:.4rem 0 .2rem">All Listings 👾</h1>
<p style="font-size:14px; font-style:italic; margin-bottom:1.1rem">{n} student internships &middot; refreshed {TODAY}</p>
<div class="threecol"><ol class="bib">{''.join(entries)}</ol></div>
"""
    (ROOT / "jobs" / "index.html").write_text(render(
        f"All listings ({n}) — student internships",
        f"{n} curated AI/ML student internships, one page per listing, refreshed {TODAY}.",
        f"{BASE_URL}/jobs/", "../style.css", "../", listing_body, n))

    remote = sum(1 for j in jobs if j.get("remote"))
    fresh = [j for j in jobs if (j.get("age") or "99d").rstrip("d").isdigit()
             and int((j.get("age") or "99d").rstrip("d")) <= 7]
    fresh_entries = "".join(bib_entry(j, f'jobs/{slugify(j["company"] + "-" + j["position"])}.html')
                            for j in sorted(fresh, key=lambda x: int(x["age"].rstrip("d")))[:12])
    cover_body = f"""
<div class="masthead">
  <h1>Deterministic Matching of Student Profiles<br>to Startup Internships</h1>
  <div class="sub">a curated, daily-refreshed map of {n} AI/ML internships &middot; <a href="https://noseydewdrop.com">noseydewdrop.com</a></div>
</div>
<div class="grid two">
  <div>
    <div class="block" id="method">
      <h3 class="sec"><span class="no">1</span>Method 👩🏻‍💻</h3>
      <p>Sources are parsed into a single schema every morning; each listing gets its own page.
      Profiles are matched with a fully deterministic engine &mdash; every point carries a named
      reason, no black box, no language model. A listing with no application link still enters,
      marked <i>link not found, search it yourself</i>.</p>
    </div>
    <div class="block" id="join">
      <h3 class="sec"><span class="no">2</span>Join</h3>
      <p>Fill a profile or upload a CV; interests are extracted and matched nightly.
      Mail arrives only when a new listing matches you &mdash; nothing new, no mail.
      <i>Membership opens with the next release.</i></p>
    </div>
    <div class="block">
      <h3 class="sec"><span class="no">3</span>Dataset 🐞</h3>
      <table style="max-width:340px">
      <caption><b>Table 1:</b> live inventory</caption>
      <thead><tr><th>segment</th><th>count</th></tr></thead>
      <tbody>
      <tr><td><a href="jobs/index.html">all listings</a></td><td>{n}</td></tr>
      <tr><td>remote positions</td><td>{remote}</td></tr>
      <tr><td>added last 7 days</td><td>{len(fresh)}</td></tr>
      </tbody>
      </table>
    </div>
  </div>
  <div class="colrule">
    <h3 class="sec">Fresh this week</h3>
    <ol class="bib">{fresh_entries}</ol>
    <p style="font-size:13.5px"><a href="jobs/index.html">all {n} listings &rarr;</a></p>
  </div>
</div>
"""
    (ROOT / "index.html").write_text(render(
        "Deterministic student internship matching",
        f"Curated, daily-refreshed dataset of {n} AI/ML student internships with deterministic profile matching.",
        f"{BASE_URL}/", "style.css", "", cover_body, n))

    urls = [f"{BASE_URL}/", f"{BASE_URL}/jobs/"] + urls
    sitemap = ['<?xml version="1.0" encoding="UTF-8"?>',
               '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    sitemap += [f"<url><loc>{esc(u)}</loc><lastmod>{TODAY}</lastmod></url>" for u in urls]
    sitemap.append("</urlset>")
    (ROOT / "sitemap.xml").write_text("\n".join(sitemap))
    (ROOT / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {BASE_URL}/sitemap.xml\n")

    n_files = sum(1 for _ in ROOT.rglob("*.html"))
    print(f"html pages: {n_files} | sitemap urls: {len(urls)} | fresh this week: {len(fresh)}")


if __name__ == "__main__":
    main()
