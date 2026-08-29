#!/usr/bin/env python3
"""measure.py - sightstone olcum araci. OLCER, ONARMAZ.

Bu arac motoru degistirmez. Sadece repo'daki gercek veriyi (git gecmisi,
jobs.json, mail_state.json, seats.json, schema.sql, kaynak dosyalar) okur ve
sayi basar. Basilan her sayinin yaninda nereden geldigi yazar.

Kural: kaynagi olmayan sayi burada uretilmez. Bir sey olculemiyorsa
"OLCULEMEDI" yazar ve nedenini soyler; tahmin uydurmaz.

Alt komutlar:
  --lifetime         git'teki jobs.json anlik goruntulerinden ilan omru dagilimi
  --miss <gun>       verilen gonderim araligi icin beklenen kacirma orani
  --budget <koltuk>  aylik 3.000 -> kisi basi siklik -> kacirma projeksiyonu
  --double-send      mail_state.json'da tekrar eden anahtar (D1)
  --unconfirmed      onaysiz adrese gonderim (D2)
  --invariants       D4/D5/D6/D9 kaynak taramasi

Stdlib + git disinda bagimlilik yok.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import statistics
import subprocess
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENGINE = ROOT / "engine"
DATA = ENGINE / "data"
DOCS = ROOT / "docs"

JOBS_PATH_REL = "engine/data/jobs.json"

# --- KOSU-v4.md'den alinan sabitler. Kaynak satirlari yazili, uydurma yok. ---
QUOTA_MONTHLY = 3000       # KOSU-v4.md:113 (D3) ve :151 (Resend bedava katman)
QUOTA_DAILY = 100          # KOSU-v4.md:113 (D3) ve :151
USABLE_SEATS_DOC = 2550    # KOSU-v4.md:156 (KOLTUK karari gerekcesi)
USABLE_S9_DOC = 2850       # KOSU-v4.md:504 (S9 durdurma esigi)
DAYS_PER_MONTH = 30        # KOLTUK gerekcesindeki 2550/200 -> 2,4 gun ile tutarli

# ZEMIN'de (KOSU-v4.md:186-191) ilan edilen omur dagilimi. OLCUM DEGIL, HIPOTEZ.
# Sadece duyarlilik analizi icin kullanilir, asla olculmus deger diye basilmaz.
ZEMIN_LIFETIME_CDF = {1: 0.116, 2: 0.190, 3: 0.265, 4: 0.312, 5: 0.413,
                      6: 0.481, 7: 0.545}
ZEMIN_LIFETIME_MEDIAN = 7

US_STATES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID", "IL",
    "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT",
    "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI",
    "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY", "DC", "PR",
}

AGE_RE = re.compile(r"^\s*(\d+)\s*(h|d|w|mo|y)\s*$", re.I)
AGE_UNIT_DAYS = {"h": 0, "d": 1, "w": 7, "mo": 30, "y": 365}


# ---------------------------------------------------------------- yardimcilar

def pct(x: float) -> str:
    return f"{100 * x:.1f}%"


def head(title: str) -> None:
    print()
    print(f"== {title} " + "=" * max(0, 62 - len(title)))


def git(*args: str) -> str:
    res = subprocess.run(["git", "-C", str(ROOT), *args],
                         capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {res.stderr.strip()}")
    return res.stdout


def age_days(age: str | None) -> int | None:
    if not age:
        return None
    m = AGE_RE.match(age)
    if not m:
        return None
    n, unit = int(m.group(1)), m.group(2).lower()
    return 0 if unit == "h" else n * AGE_UNIT_DAYS[unit]


def job_identity(job: dict) -> str:
    """send_mail.job_key ile ayni kimlik: link varsa link, yoksa sirket|pozisyon."""
    return job.get("link") or f'{job["company"]}|{job["position"]}'


def dedupe(jobs: list[dict]) -> list[dict]:
    """engine/match.py:43 dedupe ile birebir ayni kural."""
    seen, out = set(), []
    for j in jobs:
        k = (j["company"].strip().lower(), j["position"].strip().lower())
        if k in seen:
            continue
        seen.add(k)
        out.append(j)
    return out


def country_of(location: str | None) -> str:
    """Konum metninden ulke cikarir. Kural acik: son virgul parcasi."""
    if not location:
        return "(bos)"
    s = re.sub(r"\s*\+\d+\s*$", "", location.strip())
    s = re.sub(r"^remote\s*[-–]\s*", "", s, flags=re.I)
    if s.strip().lower() in {"remote", "worldwide", "anywhere", ""}:
        return "(dunya geneli remote)"
    parts = [p.strip() for p in s.split(",") if p.strip()]
    if not parts:
        return "(bos)"
    last = parts[-1]
    if last.upper() in US_STATES or last.upper() in {"USA", "US", "U.S.", "UNITED STATES"}:
        return "USA"
    if last.lower() in {"uk", "united kingdom", "england", "scotland", "wales"}:
        return "United Kingdom"
    if last.lower().startswith("the "):
        last = last[4:]
    return last


def load_jobs() -> list[dict]:
    return json.loads((DATA / "jobs.json").read_text())


# ------------------------------------------------------------- git anlik goru.

def snapshots() -> list[dict]:
    """jobs.json'un git'teki her anlik goruntusu, eskiden yeniye."""
    log = git("log", "--format=%H %cI", "--reverse", "--", JOBS_PATH_REL).strip()
    out = []
    if not log:
        return out
    for line in log.splitlines():
        sha, ts = line.split()
        blob = git("show", f"{sha}:{JOBS_PATH_REL}")
        try:
            jobs = json.loads(blob)
        except json.JSONDecodeError:
            continue
        deduped = dedupe(jobs)
        out.append({
            "sha": sha,
            "when": datetime.fromisoformat(ts),
            "raw": len(jobs),
            "n": len(deduped),
            "keys": {job_identity(j): j for j in deduped},
        })
    return out


def lifetimes_from_git(snaps: list[dict]) -> tuple[list[float], int]:
    """(tamamlanmis omurler [gun], sansurlu sayisi).

    Yontem, hakemin elle tekrarlayabilmesi icin acik:
      1. jobs.json'a dokunan her commit bir anlik goruntudur.
      2. Her goruntu match.py kurallariyla dedupe edilir.
      3. Ilan kimligi = link, link yoksa "sirket|pozisyon".
      4. Bir ilan i. goruntude VAR, sonraki bir goruntude YOK ise olmustur.
         omur = (son gorulme zamani - ilk gorulme zamani), gun cinsinden.
      5. Son goruntude hala duran ilan SANSURLUDUR, omru bilinmez, sayilmaz.
    """
    if len(snaps) < 2:
        return [], sum(s["n"] for s in snaps[:1])
    first_seen: dict[str, datetime] = {}
    last_seen: dict[str, datetime] = {}
    for s in snaps:
        for k in s["keys"]:
            first_seen.setdefault(k, s["when"])
            last_seen[k] = s["when"]
    alive_at_end = set(snaps[-1]["keys"])
    completed = []
    for k, last in last_seen.items():
        if k in alive_at_end:
            continue
        completed.append((last - first_seen[k]).total_seconds() / 86400.0)
    return completed, len(alive_at_end)


# ------------------------------------------------------------------ --lifetime

def cmd_lifetime() -> dict:
    head("KORPUS (calisma agacindaki engine/data/jobs.json)")
    jobs_raw = load_jobs()
    jobs = dedupe(jobs_raw)
    print(f"ham satir            : {len(jobs_raw)}")
    print(f"dedupe sonrasi ilan  : {len(jobs)}")
    meta_path = DATA / "fetch_meta.json"
    if meta_path.exists():
        meta = json.loads(meta_path.read_text())
        print(f"fetch_meta.json      : raw_rows={meta.get('raw_rows')} "
              f"duplicates_removed={meta.get('duplicates_removed')} "
              f"fetched_at={meta.get('fetched_at')}")
    countries = Counter(country_of(j.get("location")) for j in jobs)
    real = {k: v for k, v in countries.items() if not k.startswith("(")}
    print(f"farkli ulke          : {len(real)} (+ {sum(v for k, v in countries.items() if k.startswith('('))} "
          f"ulkesiz satir)")
    for name, n in countries.most_common(6):
        print(f"  {name:<24} {n}")
    tr = countries.get("Turkey", 0) + countries.get("Türkiye", 0) + countries.get("Turkiye", 0)
    print(f"  {'Turkiye':<24} {tr}")
    srcs = Counter(j["source"] for j in jobs)
    print(f"kaynak               : {dict(srcs)}")

    head("REMOTE")
    rem = [j for j in jobs if j.get("remote")]
    loc_ctr = Counter((j.get("location") or "").strip() for j in rem)
    plain = loc_ctr.get("Remote", 0)
    print(f"remote=true ilan     : {len(rem)} ({pct(len(rem) / len(jobs))})")
    print(f"duz 'Remote'         : {plain}   (ulkeye/sehre civili: {len(rem) - plain})")
    for name, n in loc_ctr.most_common():
        if name != "Remote":
            print(f"  {name:<32} {n}")

    head("OMUR (git anlik goruntuleri)")
    snaps = snapshots()
    print(f"jobs.json'a dokunan commit : {len(snaps)}")
    for s in snaps:
        print(f"  {s['sha'][:8]}  {s['when'].isoformat()}  ham={s['raw']:<4} dedupe={s['n']}")
    if len(snaps) >= 2:
        span = (snaps[-1]["when"] - snaps[0]["when"]).total_seconds() / 86400.0
        days = len({s["when"].date() for s in snaps})
        print(f"kapsanan sure              : {span:.2f} gun, {days} farkli takvim gunu")
        births = deaths = 0
        for a, b in zip(snaps, snaps[1:]):
            births += len(set(b["keys"]) - set(a["keys"]))
            deaths += len(set(a["keys"]) - set(b["keys"]))
        print(f"goruntuler arasi YENI ilan : {births}")
        print(f"goruntuler arasi KAYBOLAN  : {deaths}")
    else:
        span = 0.0

    completed, censored = lifetimes_from_git(snaps)
    print(f"omru TAMAMLANMIS ilan      : {len(completed)}")
    print(f"SANSURLU (hala yasayan)    : {censored}")
    result = {"completed": completed, "censored": censored, "span": span,
              "snapshots": len(snaps), "jobs": len(jobs)}
    if completed:
        completed.sort()
        med = statistics.median(completed)
        print(f"medyan omur                : {med:.2f} gun")
        print(f"ortalama omur              : {statistics.mean(completed):.2f} gun")
        for d in (1, 3, 7):
            k = sum(1 for x in completed if x <= d)
            print(f"  <= {d} gunde olen          : {k} ({pct(k / len(completed))})")
        result["median"] = med
    else:
        result["median"] = None
        print("medyan omur                : OLCULEMEDI")
        print("  neden: hicbir ilan hicbir goruntude kaybolmadi. Tamamlanmis omur")
        print("  ornegi 0. Sansur orani %100. Bu veriden omur dagilimi cikmaz.")

    head("AKIS (yeni ilan hizi)")
    if span > 0:
        print(f"olculen: {births} yeni ilan / {span:.2f} gun = {births / span:.2f} ilan/gun")
    else:
        print("olculen: OLCULEMEDI, iki goruntu arasi olcumlu sure yok")
    print("not: korpus tek bir fetch'in tekrari. Yeni ilan akisi git'te GORUNMUYOR.")

    head("YAS ALANI (tek goruntu, olum degil)")
    ages = [age_days(j.get("age")) for j in jobs]
    parsed = [a for a in ages if a is not None]
    print(f"okunabilen 'age' alani     : {len(parsed)}/{len(jobs)}")
    if parsed:
        print(f"medyan yas (fetch aninda)  : {statistics.median(parsed):.1f} gun")
        hist = Counter(parsed)
        young = sum(v for k, v in hist.items() if k <= 1)
        peak_d, peak_n = hist.most_common(1)[0]
        print(f"yas<=1 gun olan ilan       : {young}")
        print(f"histogram tepesi           : {peak_d} gun ({peak_n} ilan)")
        print("durgunluk (stationarity) testi: sabit ilan akisi olsaydi yas histogrami")
        print(f"  monoton azalirdi. Gercek: yas<=1 -> {young}, yas={peak_d} -> {peak_n}.")
        print("  Durgunluk YOK. Yas alanindan omur dagilimi TURETILEMEZ.")

    head("ESLESME (profile.json, engine/match.py)")
    sys.path.insert(0, str(ENGINE))
    import match as match_mod  # noqa: E402
    profile = json.loads((ROOT / "profile.json").read_text())
    results, stats = match_mod.run(profile, jobs_raw)
    score_ctr = Counter(r["score"] for r in results)
    print(f"eslesme                    : {stats['matched']}")
    print(f"  skor 1                   : {score_ctr.get(1, 0)}")
    print(f"  skor 2                   : {score_ctr.get(2, 0)}")
    print(f"  skor >= 5                : {sum(v for k, v in score_ctr.items() if k >= 5)}")
    print(f"eleme: no_signal {stats['no_signal']} · phd_only {stats['phd_only']} · "
          f"mba {stats['mba']} · us_work_auth {stats['us_work_auth']}")
    result["matched"] = stats["matched"]
    result["ge5"] = sum(v for k, v in score_ctr.items() if k >= 5)
    return result


# ---------------------------------------------------------------------- --miss

def miss_uniform_phase(cdf: dict[int, float], interval: float) -> float:
    """Gonderim araligi d icin beklenen kacirma orani.

    Model: ilan rastgele bir fazda dogar. Omru L olan ilan, sonraki gonderime
    kadar yasamazsa kacirilir. Duzgun (uniform) faz varsayimiyla
    P(kacirma | L) = max(0, (d - L) / d). Beklenen deger omur dagiliminda
    integre edilir; burada dagilim ayrik CDF olarak verilir.
    """
    d = interval
    grid = sorted(cdf)
    prev_c = 0.0
    prev_l = 0.0
    total = 0.0
    for l in grid:
        p = cdf[l] - prev_c          # P(prev_l < L <= l)
        mid = (prev_l + l) / 2.0     # kova temsilcisi
        total += p * max(0.0, (d - mid) / d)
        prev_c, prev_l = cdf[l], l
    return total


def miss_crude(cdf: dict[int, float], interval: float) -> float:
    """Kaba ust sinir: araliktan kisa yasayan her ilan kacirilmis sayilir."""
    grid = sorted(cdf)
    val = 0.0
    for l in grid:
        if l <= interval:
            val = cdf[l]
    return val


def cmd_miss(interval: float, quiet: bool = False) -> dict:
    if not quiet:
        head(f"KACIRMA · gonderim araligi {interval:g} gun")
    snaps = snapshots()
    completed, censored = lifetimes_from_git(snaps)
    print(f"olculmus omur ornegi       : {len(completed)} tamamlanmis, {censored} sansurlu")
    if completed:
        emp = {}
        completed.sort()
        for d in range(1, 31):
            emp[d] = sum(1 for x in completed if x <= d) / len(completed)
        lo = miss_uniform_phase(emp, interval)
        crude = miss_crude(emp, interval)
        print(f"OLCULEN kacirma (uniform)  : {pct(lo)}")
        print(f"OLCULEN kacirma (kaba ust) : {pct(crude)}")
        measured = lo
    else:
        measured = None
        print("OLCULEN kacirma            : OLCULEMEDI")
        print("  Gozlenen olum 0. Alt sinir %0,0 (hicbir ilan olmedigi gozlendi),")
        print("  ust sinir belirsiz (omurlerin %100'u sansurlu). Bu iki sinir")
        print("  arasinda tek bir sayi secmek uydurma olurdu.")

    print()
    print("DUYARLILIK - KOSU-v4.md:186-191 ZEMIN dagilimi DOGRU OLSAYDI:")
    print("  (bu bir HIPOTEZ. Bu repoda olculmedi, kanit degildir.)")
    print(f"  uniform-faz kacirma      : {pct(miss_uniform_phase(ZEMIN_LIFETIME_CDF, interval))}")
    print(f"  kaba ust sinir           : {pct(miss_crude(ZEMIN_LIFETIME_CDF, interval))}")
    return {"measured": measured, "completed": len(completed),
            "hypo": miss_uniform_phase(ZEMIN_LIFETIME_CDF, interval),
            "hypo_crude": miss_crude(ZEMIN_LIFETIME_CDF, interval)}


# -------------------------------------------------------------------- --budget

def cmd_budget(seats: int) -> dict:
    head(f"BUTCE · {seats} koltuk")
    print(f"kota (KOSU-v4.md:113,151)  : aylik {QUOTA_MONTHLY}, gunluk {QUOTA_DAILY}")
    print(f"belgede iki farkli 'kullanilabilir' sayi var:")
    print(f"  KOSU-v4.md:156 (KOLTUK)  : {USABLE_SEATS_DOC}/ay")
    print(f"  KOSU-v4.md:504 (S9)      : {USABLE_S9_DOC}/ay")
    print("  CELISKI: ayni kotadan iki ayri rezerv turetilmis (450 vs 150).")
    rows = []
    for label, usable in (("KOLTUK karari", USABLE_SEATS_DOC), ("S9 esigi", USABLE_S9_DOC),
                          ("rezervsiz", QUOTA_MONTHLY)):
        per_person = usable / seats
        interval = DAYS_PER_MONTH / per_person if per_person else float("inf")
        rows.append((label, usable, per_person, interval))
    print()
    print(f"{'kaynak':<16}{'kullanilabilir':>15}{'mail/kisi/ay':>15}{'aralik (gun)':>15}")
    for label, usable, pp, iv in rows:
        print(f"{label:<16}{usable:>15}{pp:>15.2f}{iv:>15.2f}")
    daily_cap_interval = seats / QUOTA_DAILY
    print()
    print(f"gunluk 100 siniri          : {seats} kisi -> en sik {daily_cap_interval:.2f} gunde bir")
    binding = max(rows[0][3], daily_cap_interval)
    print(f"baglayici aralik (KOLTUK)  : {binding:.2f} gun")

    print()
    print("kacirma projeksiyonu bu aralikta:")
    print(f"  OLCULEN                  : {'OLCULEMEDI (omur ornegi 0)' if not lifetimes_from_git(snapshots())[0] else ''}")
    print(f"  ZEMIN hipotezi olsaydi   : {pct(miss_uniform_phase(ZEMIN_LIFETIME_CDF, binding))} "
          f"(kaba ust {pct(miss_crude(ZEMIN_LIFETIME_CDF, binding))})")

    head("ABONE / KOLTUK durumu")
    seats_file = DATA / "seats.json"
    if seats_file.exists():
        sj = json.loads(seats_file.read_text())
        print(f"seats.json                 : {json.dumps(sj)}")
    else:
        print("seats.json                 : YOK")
    state_file = DATA / "mail_state.json"
    if state_file.exists():
        st = json.loads(state_file.read_text())
        total_sent = sum(len(v.get("sent_keys", [])) for v in st.values())
        print(f"mail_state.json abone      : {len(st)}")
        print(f"mail_state.json gonderilen : {total_sent} ilan")
        for sid, v in st.items():
            print(f"  {sid}: {len(v.get('sent_keys', []))} ilan, son gonderim {v.get('last_sent')}")
    return {"binding": binding}


# --------------------------------------------------------------- --double-send

def cmd_double_send() -> int:
    head("D1 · AYNI ILAN AYNI ABONEYE IKI KEZ (mail_state.json)")
    state_file = DATA / "mail_state.json"
    if not state_file.exists():
        print("mail_state.json YOK, olcum yapilamaz")
        return 0
    state = json.loads(state_file.read_text())
    dup_total = 0
    for sid, v in state.items():
        keys = v.get("sent_keys", [])
        ctr = Counter(keys)
        dups = {k: n for k, n in ctr.items() if n > 1}
        dup_total += sum(n - 1 for n in dups.values())
        print(f"abone {sid}: {len(keys)} anahtar, {len(set(keys))} tekil, "
              f"{len(dups)} tekrar eden")
        for k, n in dups.items():
            print(f"    TEKRAR: {k} x{n}")
    print(f"TEKRAR EDEN ANAHTAR TOPLAMI: {dup_total}")

    head("D1 · yapisal risk taramasi (engine/send_mail.py)")
    src = (ENGINE / "send_mail.py").read_text().splitlines()
    findings = []
    write_lines = [i + 1 for i, l in enumerate(src) if "STATE_FILE.write_text" in l]
    loop_lines = [i + 1 for i, l in enumerate(src) if re.match(r"\s*for email, profile", l)]
    send_lines = [i + 1 for i, l in enumerate(src) if "send_message" in l]
    for w in write_lines:
        if loop_lines and w > max(loop_lines):
            findings.append(
                f"send_mail.py:{w} state yaziliyor, ama gonderim dongusu satir "
                f"{loop_lines[0]}'de bitmis. Donguden SONRA tek seferde yaziliyor: "
                f"gonderim (satir {send_lines[0] if send_lines else '?'}) basarili olup "
                f"surec cokerse ayni ilan yarin tekrar gider.")
    guard = [i + 1 for i, l in enumerate(src) if "if mailed:" in l]
    for g in guard:
        findings.append(
            f"send_mail.py:{g} state yalnizca mailed>0 iken yaziliyor; kismi "
            f"basarida (bir abone gitti, sonraki patladi) yazma hic olmayabilir.")
    for f in findings:
        print(f"  BULGU: {f}")
    print(f"YAPISAL BULGU SAYISI: {len(findings)}")
    return dup_total


# ---------------------------------------------------------------- --unconfirmed

def cmd_unconfirmed() -> int:
    head("D2 · ONAYSIZ ADRESE GONDERIM")
    schema = (ENGINE / "schema.sql").read_text()
    schema_lines = schema.splitlines()
    has_confirmed = [i + 1 for i, l in enumerate(schema_lines)
                     if re.search(r"confirmed_at|confirmation_token|verified_at", l)]
    print(f"schema.sql onay sutunu     : {len(has_confirmed)} adet "
          f"{'satir ' + str(has_confirmed) if has_confirmed else '(YOK)'}")

    mail_src = (ENGINE / "send_mail.py").read_text()
    m = re.search(r"sightstone_subscribers\"?\s*\n?\s*\"?([^\"]*)", mail_src)
    filt = re.findall(r"\?([a-z_]+)=is\.null", mail_src)
    print(f"fetch_subscribers filtresi : {filt if filt else '(filtre yok)'}")
    confirms_in_query = any("confirmed" in f for f in filt)
    print(f"sorguda onay filtresi      : {'VAR' if confirms_in_query else 'YOK'}")

    state_file = DATA / "mail_state.json"
    state = json.loads(state_file.read_text()) if state_file.exists() else {}
    mailed_people = len(state)
    unconfirmed = 0 if confirms_in_query else mailed_people
    print(f"mail GITMIS abone sayisi   : {mailed_people} (mail_state.json)")
    print(f"ONAYSIZ ADRESE GONDERIM    : {unconfirmed}")
    if not confirms_in_query:
        print("  neden: sema onay sutunu tanimlamiyor ve fetch_subscribers yalniz")
        print("  unsubscribed_at=is.null suzuyor. Onay kavrami kodda YOK; dolayisiyla")
        print("  mail gitmis her adres tanim geregi onaysiz.")

    head("D2 · sema kapasitesi")
    cap_lines = [(i + 1, l.strip()) for i, l in enumerate(schema_lines)
                 if re.search(r"\b100\b", l) and not l.strip().startswith("--")]
    print(f"schema.sql'de sabit 100 (yorum haric): {len(cap_lines)} yerde")
    for n, l in cap_lines:
        print(f"  satir {n}: {l}")

    head("D2 · gonderim yolu")
    prov = []
    for name, pat in (("smtplib (Gmail)", r"smtplib"), ("Resend", r"resend|api\.resend\.com"),
                      ("SendGrid", r"sendgrid"), ("Supabase", r"supabase")):
        hits = [i + 1 for i, l in enumerate(mail_src.splitlines()) if re.search(pat, l, re.I)]
        if hits:
            prov.append((name, hits))
    for name, hits in prov:
        print(f"  {name:<18} send_mail.py satir {hits[:4]}")
    return unconfirmed


# ---------------------------------------------------------------- --invariants

LLM_PKGS = ["openai", "anthropic", "groq", "cohere", "mistralai", "litellm",
            "google.generativeai", "google_genai", "transformers", "llama_cpp",
            "ollama", "replicate", "together", "huggingface_hub", "langchain"]
LLM_HOSTS = ["api.openai.com", "api.anthropic.com", "api.groq.com",
             "generativelanguage.googleapis.com", "api.mistral.ai",
             "api.cohere.ai", "api.cohere.com", "openrouter.ai",
             "api.together.xyz", "api.deepseek.com", "api-inference.huggingface.co",
             "api.replicate.com", "localhost:11434"]
PAID_MARKERS = ["stripe", "paddle.com", "lemonsqueezy", "api.openai.com",
                "twilio", "sendgrid.net", "mailgun", "postmark", "algolia",
                "amazonaws.com", "cloudinary"]


def scan_files(patterns: list[Path]) -> list[tuple[Path, int, str]]:
    out = []
    for p in patterns:
        try:
            for i, line in enumerate(p.read_text(errors="replace").splitlines(), 1):
                out.append((p, i, line))
        except OSError:
            continue
    return out


def engine_sources() -> list[Path]:
    return sorted(ENGINE.glob("*.py"))


def repo_web_sources() -> list[Path]:
    files = []
    for pat in ("*.html", "*.js"):
        files += [p for p in DOCS.glob(pat)]
    files += [p for p in DOCS.glob("*.py")]
    return sorted(files)


def cmd_invariants() -> dict:
    counts = {}

    head("D4 · MOTORDA LLM YOK (engine/)")
    hits = []
    for p in engine_sources():
        tree = ast.parse(p.read_text())
        for node in ast.walk(tree):
            mods = []
            if isinstance(node, ast.Import):
                mods = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                mods = [node.module or ""]
            for mod in mods:
                for pkg in LLM_PKGS:
                    if mod == pkg or mod.startswith(pkg + "."):
                        hits.append((p, node.lineno, f"import {mod}"))
    for p, ln, line in scan_files(engine_sources()):
        for host in LLM_HOSTS:
            if host in line:
                hits.append((p, ln, f"LLM sunucusuna cagri: {host}"))
    print(f"taranan dosya              : {len(engine_sources())}")
    for p, ln, why in hits:
        print(f"  IHLAL {p.relative_to(ROOT)}:{ln} {why}")
    print(f"D4 IHLAL SAYISI            : {len(hits)}")
    counts["D4"] = len(hits)

    head("D5 · CV TARAYICIDAN CIKMAZ")
    d5 = []
    net_re = re.compile(r"fetch\s*\(|XMLHttpRequest|sendBeacon|new WebSocket|\.submit\s*\(")
    cv_re = re.compile(r"\bcv\b|resume|pdf_?text|cvText|cv_text", re.I)
    for p, ln, line in scan_files(repo_web_sources() + engine_sources()):
        if net_re.search(line) and cv_re.search(line):
            d5.append((p, ln, line.strip()[:110]))
    for p, ln, line in scan_files(engine_sources()):
        if "cv_text" in line and re.search(r"insert|post|upload|payload", line, re.I):
            d5.append((p, ln, line.strip()[:110]))
    for p, ln, why in d5:
        print(f"  IHLAL {p.relative_to(ROOT)}:{ln} {why}")
    print(f"D5 IHLAL SAYISI            : {len(d5)}")
    schema_cv = [i + 1 for i, l in enumerate((ENGINE / "schema.sql").read_text().splitlines())
                 if "cv_text" in l]
    print(f"D5 GIZLI RISK              : schema.sql'de cv_text sutunu satir {schema_cv} "
          f"(yazan kod yok, ama sema CV'yi sunucuda saklamaya HAZIR)")
    counts["D5"] = len(d5)

    head("D6 · UCRETLI SERVIS YOK")
    all_src = engine_sources() + repo_web_sources() + [ENGINE / "schema.sql"]
    wf = ROOT / ".github" / "workflows"
    if wf.exists():
        all_src += sorted(wf.glob("*.yml"))
    paid = []
    for p, ln, line in scan_files(all_src):
        for marker in PAID_MARKERS:
            if marker in line.lower():
                paid.append((p, ln, marker))
    for p, ln, marker in paid:
        print(f"  IHLAL {p.relative_to(ROOT)}:{ln} {marker}")
    print(f"D6 IHLAL SAYISI            : {len(paid)}")
    hosts = Counter()
    host_re = re.compile(r"https?://([A-Za-z0-9.\-]+)")
    for p, ln, line in scan_files(all_src):
        for h in host_re.findall(line):
            if "schema.org" in h or "sitemaps.org" in h or "w3.org" in h:
                continue
            hosts[h] += 1
    print(f"repoda gecen dis host      : {len(hosts)}")
    for h, n in hosts.most_common():
        print(f"  {h:<44} {n}")
    counts["D6"] = len(paid)

    head("D9 · HAM DIS METIN HTML'E BASILAMAZ")
    d9 = []
    safe = []
    bs = ENGINE / "build_site.py"
    src_lines = bs.read_text().splitlines()
    tree = ast.parse(bs.read_text())
    ext_re = re.compile(r"\b(job|j|r|sub|row)\b\s*(\[|\.get\()")
    # kacisi gerektirmeyenler: sanitize eden sarmalayicilar ve motorun urettigi sayilar
    safe_wrapper_re = re.compile(r"^\s*(esc|html\.escape|slugify|int|len|bool|round)\s*\(")
    numeric_field_re = re.compile(r"\[[\"'](score|age_days)[\"']\]\s*$")
    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr):
            raw = "".join(v.value for v in node.values if isinstance(v, ast.Constant))
            if "<" not in raw and ">" not in raw:
                continue
            for v in node.values:
                if not isinstance(v, ast.FormattedValue):
                    continue
                expr = ast.unparse(v.value)
                if not ext_re.search(expr):
                    continue
                if "esc(" in expr or "html.escape" in expr:
                    continue
                if safe_wrapper_re.match(expr) or numeric_field_re.search(expr):
                    safe.append((node.lineno, expr))
                    continue
                d9.append((node.lineno, expr))
    for node in ast.walk(tree):
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            txt = ast.unparse(node)
            if "<script" in txt and "json.dumps" in txt:
                d9.append((node.lineno, "json.dumps -> <script> (</script> kacisi yok)"))
    seen = set()
    uniq = []
    for ln, why in d9:
        if (ln, why) in seen:
            continue
        seen.add((ln, why))
        uniq.append((ln, why))
    for ln, why in uniq:
        print(f"  IHLAL build_site.py:{ln} {why}")
        print(f"      {src_lines[ln - 1].strip()[:110]}")
    esc_count = sum(1 for _, _, l in scan_files([bs]) if "esc(" in l)
    print(f"esc() gecen satir          : {esc_count}")
    print(f"kacissiz ama GUVENLI       : {len(safe)} (slugify/int gibi sanitize eden "
          f"sarmalayici ya da motorun urettigi sayi)")
    for ln, expr in safe:
        print(f"    build_site.py:{ln} {expr}")
    print(f"D9 IHLAL SAYISI            : {len(uniq)}")
    counts["D9"] = len(uniq)

    head("OZET")
    for k in ("D4", "D5", "D6", "D9"):
        print(f"  {k}: {counts[k]} ihlal  {'YESIL' if counts[k] == 0 else 'KIRMIZI'}")
    return counts


# ------------------------------------------------------------------------ main

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lifetime", action="store_true")
    ap.add_argument("--miss", type=float, metavar="GUN")
    ap.add_argument("--budget", type=int, metavar="KOLTUK")
    ap.add_argument("--double-send", action="store_true")
    ap.add_argument("--unconfirmed", action="store_true")
    ap.add_argument("--invariants", action="store_true")
    args = ap.parse_args()

    if not any([args.lifetime, args.miss is not None, args.budget is not None,
                args.double_send, args.unconfirmed, args.invariants]):
        ap.print_help()
        sys.exit(2)

    if args.lifetime:
        cmd_lifetime()
    if args.miss is not None:
        cmd_miss(args.miss)
    if args.budget is not None:
        cmd_budget(args.budget)
    if args.double_send:
        cmd_double_send()
    if args.unconfirmed:
        cmd_unconfirmed()
    if args.invariants:
        cmd_invariants()


if __name__ == "__main__":
    main()
