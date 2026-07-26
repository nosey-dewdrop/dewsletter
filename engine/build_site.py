#!/usr/bin/env python3
"""Static site generator: jobs.json -> hundreds of plain HTML pages.

No framework, no LLM. Deterministic output:
  site/dist/index.html            landing (paper cover)
  site/dist/jobs/index.html       full listing, two-column bibliography
  site/dist/jobs/<slug>.html      one page PER listing (SEO surface)
  site/dist/style.css             Latin Modern + article layout
  site/dist/sitemap.xml, robots.txt

BASE_URL is a placeholder until the domain is chosen.
"""
import html
import json
import re
import unicodedata
from datetime import date
from pathlib import Path

BASE_URL = "https://jobs.noseydewdrop.com"  # placeholder, single place to change
ROOT = Path(__file__).parent.parent / "site" / "dist"
TODAY = date.today().isoformat()

CSS = """
@font-face { font-family:'Latin Modern'; src:url('https://cdn.jsdelivr.net/gh/vincentdoerig/latex-css@1.10.0/fonts/LM-regular.woff2') format('woff2'); font-weight:normal; font-style:normal; font-display:swap; }
@font-face { font-family:'Latin Modern'; src:url('https://cdn.jsdelivr.net/gh/vincentdoerig/latex-css@1.10.0/fonts/LM-bold.woff2') format('woff2'); font-weight:bold; font-style:normal; font-display:swap; }
@font-face { font-family:'Latin Modern'; src:url('https://cdn.jsdelivr.net/gh/vincentdoerig/latex-css@1.10.0/fonts/LM-italic.woff2') format('woff2'); font-weight:normal; font-style:italic; font-display:swap; }
:root { --ink:#111; --paper:#fff; --link:#0b4fa8; }
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family:'Latin Modern','Computer Modern',Georgia,serif; color:var(--ink); background:var(--paper);
  max-width:210mm; margin:0 auto; padding:12mm 20mm 24mm; font-size:15.5px; line-height:1.42; }
a { color:var(--link); text-decoration:none; }
a:hover { text-decoration:underline; }
.maketitle { text-align:center; margin:1rem 0 1.5rem; }
.maketitle h1 { font-size:22px; line-height:1.3; margin-bottom:.7rem; }
.maketitle .author { font-size:15.5px; margin-bottom:.2rem; }
.maketitle .date { font-style:italic; font-size:14px; }
h3.sec { font-size:16.5px; margin:1.3rem 0 .5rem; }
h3.sec .no { margin-right:.9rem; }
p { text-align:justify; hyphens:auto; margin-bottom:.55rem; }
.twocol { column-count:2; column-gap:8mm; }
@media (max-width:700px){ .twocol { column-count:1; } body { padding:8mm 6mm 18mm; } }
.bib { list-style:none; counter-reset:bib; font-size:13.8px; }
.bib li { counter-increment:bib; padding-left:2.1em; text-indent:-2.1em; margin-bottom:.5rem; break-inside:avoid; }
.bib li::before { content:"[" counter(bib) "]"; margin-right:.7em; }
.co { font-variant:small-caps; }
.pos { font-style:italic; }
.meta { color:#333; }
table { border-collapse:collapse; margin:.5rem auto; font-size:14px; }
caption { caption-side:top; font-size:13.5px; margin-bottom:.35rem; }
th,td { padding:.18rem 1.1rem; text-align:left; }
thead tr { border-top:1.5px solid var(--ink); border-bottom:.8px solid var(--ink); }
tbody tr:last-child { border-bottom:1.5px solid var(--ink); }
.crumb { font-size:13px; margin-bottom:1rem; }
.applyline { margin:.9rem 0; font-size:16px; }
.footnote { margin-top:2.2rem; border-top:.6px solid var(--ink); padding-top:.4rem; width:60%; font-size:12.5px; }
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
{body}
</body>
</html>
"""


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return text[:80]


def esc(s):
    return html.escape(s or "", quote=True)


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
    return (f'<li><span class="co">{esc(job["company"])}</span>. '
            f'<span class="pos"><a href="{href}">{esc(job["position"])}</a>.</span> '
            f'<span class="loc">{loc}.</span> '
            f'<span class="meta">{esc(job.get("salary") or "")}</span></li>')


def job_page(job: dict, slug: str) -> str:
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
<div class="maketitle">
  <h1>{esc(job["position"])}</h1>
  <div class="author"><span class="co">{esc(job["company"])}</span></div>
  <div class="date">internship listing &middot; retrieved {TODAY}</div>
</div>
<table>
<caption><b>Table 1:</b> listing facts</caption>
<thead><tr><th>field</th><th>value</th></tr></thead>
<tbody>{rows}</tbody>
</table>
<p class="applyline">{apply_html}</p>
<div class="footnote">Curated for students: single-applicant positions, no referral required.
Matching engine and daily refresh: <a href="../index.html">about this site</a>.</div>
"""
    title = f'{job["company"]} — {job["position"]} (internship)'
    desc = f'{job["position"]} internship at {job["company"]}, {job.get("location") or "location unlisted"}. Student-suitable, refreshed {TODAY}.'
    return PAGE.format(title=esc(title), description=esc(desc), canonical=canonical,
                       csspath="../style.css", extra_head=job_jsonld(job, canonical), body=body)


def main() -> None:
    jobs = json.loads((Path(__file__).parent / "data" / "jobs.json").read_text())
    (ROOT / "jobs").mkdir(parents=True, exist_ok=True)
    (ROOT / "style.css").write_text(CSS)

    slugs, entries, urls = set(), [], []
    for job in jobs:
        base = slugify(f'{job["company"]}-{job["position"]}')
        slug, n = base, 2
        while slug in slugs:
            slug, n = f"{base}-{n}", n + 1
        slugs.add(slug)
        (ROOT / "jobs" / f"{slug}.html").write_text(job_page(job, slug))
        entries.append(bib_entry(job, f"{slug}.html"))
        urls.append(f"{BASE_URL}/jobs/{slug}.html")

    listing_body = f"""
<div class="crumb"><a href="../index.html">index</a></div>
<div class="maketitle">
  <h1>All Listings 👾</h1>
  <div class="date">{len(jobs)} student internships &middot; refreshed {TODAY}</div>
</div>
<div class="twocol"><ol class="bib">{''.join(entries)}</ol></div>
"""
    (ROOT / "jobs" / "index.html").write_text(PAGE.format(
        title=f"All listings ({len(jobs)}) — student internships",
        description=f"{len(jobs)} curated AI/ML student internships, one page per listing, refreshed {TODAY}.",
        canonical=f"{BASE_URL}/jobs/", csspath="../style.css", extra_head="", body=listing_body))

    remote = sum(1 for j in jobs if j.get("remote"))
    cover_body = f"""
<div class="maketitle">
  <h1>Deterministic Matching of Student Profiles<br>to Startup Internships</h1>
  <div class="author">the engine 👾 &middot; <a href="https://noseydewdrop.com">noseydewdrop.com</a></div>
  <div class="date">refreshed {TODAY}</div>
</div>
<h3 class="sec"><span class="no">1</span>Dataset 🐞</h3>
<table>
<caption><b>Table 1:</b> live inventory</caption>
<thead><tr><th>segment</th><th>count</th></tr></thead>
<tbody>
<tr><td><a href="jobs/index.html">all listings</a></td><td>{len(jobs)}</td></tr>
<tr><td>remote positions</td><td>{remote}</td></tr>
</tbody>
</table>
<h3 class="sec"><span class="no">2</span>Method 👩🏻‍💻</h3>
<p>Sources are parsed into a single schema every morning; each listing gets its own page.
Profiles are matched with a fully deterministic engine &mdash; every point has a named reason,
no black box, no language model. Signup and CV upload arrive with the membership release.</p>
"""
    (ROOT / "index.html").write_text(PAGE.format(
        title="Deterministic student internship matching",
        description=f"Curated, daily-refreshed dataset of {len(jobs)} AI/ML student internships with deterministic profile matching.",
        canonical=f"{BASE_URL}/", csspath="style.css", extra_head="", body=cover_body))

    urls = [f"{BASE_URL}/", f"{BASE_URL}/jobs/"] + urls
    sitemap = ['<?xml version="1.0" encoding="UTF-8"?>',
               '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    sitemap += [f"<url><loc>{esc(u)}</loc><lastmod>{TODAY}</lastmod></url>" for u in urls]
    sitemap.append("</urlset>")
    (ROOT / "sitemap.xml").write_text("\n".join(sitemap))
    (ROOT / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {BASE_URL}/sitemap.xml\n")

    n_files = sum(1 for _ in ROOT.rglob("*.html"))
    print(f"html pages: {n_files} | sitemap urls: {len(urls)} | out: {ROOT}")


if __name__ == "__main__":
    main()
