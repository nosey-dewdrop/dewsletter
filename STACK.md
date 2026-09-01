# dewsletter, technically

Written 1 September 2026. Every number here was measured on that day by running
the command written beside it, not recalled.

## Shape of the thing

A static site and a cron. There is no server, no framework and no build step
beyond one Python script that writes HTML.

```
engine/          the whole product, plain Python, standard library only
  fetch/         the only code that touches the network
  match.py       pure scoring, no I/O
  build_site.py  writes docs/
  send_mail.py   composes and sends, one throat
  schema.sql     the database, applied by hand in the Supabase editor
  tests/         454 tests
tools/measure.py the measuring instrument, frozen
docs/            the published site, served straight from the repo
.github/         two workflows
```

Eleven Python modules in `engine/`, seventeen test modules. No `requirements.txt`,
because there are no requirements.

## Dependencies

There are none in the engine. Not a stylistic preference: `--invariants` scans
`engine/` for imports of any known model or HTTP client library and exits
non zero if it finds one.

The browser gets two vendored files, `pdf.js` and its worker, for reading a CV
locally. They are committed, not fetched from a CDN at runtime, so the CV
report has no third party in the path.

The one runtime dependency of any kind is the Latin Modern web font, which is
now unused after the restyle, and the two hosted services below.

## Services

| What | Why | Free tier limit that binds |
|---|---|---|
| GitHub Pages | serves `docs/` | none that matters here |
| GitHub Actions | the daily run and the confirmation run | none that matters here |
| Supabase (Postgres) | subscribers, waitlist, seats | 500 MB, and a pause after 7 idle days |
| Resend | sending | 100 mails a day, 3000 a month |

Supabase is shared with other projects, which is why every table and function
carries a `sightstone_` prefix. The prefix is older than the name dewsletter
and stays: renaming live tables to match a brand would mean a migration and a
window where the site cannot write, for nothing a user can see.

## The mail path

```
form -> sightstone_subscribers (confirmed_at null)
     -> confirmation mail, every 15 minutes
     -> confirm.html calls sightstone_confirm(token)
     -> bulletins, once a day at most
     -> unsubscribe.html calls sightstone_unsubscribe(token)
```

Delivery goes through one method, `Provider.send(to, subject, html, kind=...)`.
Nothing else in the repo speaks to a mail transport, so swapping providers is
one class and the signature does not move.

`kind` is required and closed: `bulletin`, `confirm`, `invite`. The three share
one budget but not one stop line, which is why the caller has to say which it
is rather than be guessed for.

### Quota accounting

The provider's caps are 100 a day and 3000 a month. The ledger enforces less:

- `DAILY_MAIL_CAP = 90`, ten mails of margin.
- `MONTHLY_BULLETIN_CAP = 2550`, a fifteen percent reserve. The provider's own
  docs say received mail counts against the same quota, and the ledger cannot
  see inbound, so every number it holds is a lower bound on real consumption.
- `DAILY_CONFIRM_CAP = 45`, half the day. A bot that takes every seat generates
  a confirmation for each one; without a per kind cap that is the whole day's
  budget spent on a bot while real subscribers get nothing.

The daily window is a rolling 24 hours, never a calendar day. The runner is UTC
and Damla is UTC+3, so a run triggered at 01:00 local would otherwise open a
second bucket for the same real day.

## Scoring

```
interest keyword in title    +4 each, capped at 12
skill keyword in title       +2 each, capped at 6
title prefers MS, BS profile -3
everything else               0
```

Geography, freshness and salary score nothing. They are filters and ordering.
The elimination block runs first and is separate: PhD only, MBA, US work
authorisation, and the geo rule, which runs on declared constraints only and
refuses to run half declared.

`--min-score` defaults to 4, which is exactly "at least one interest hit".

### The send order

When the budget cannot cover everyone, the order decides who is dropped, and
an unordered loop drops the same people every morning while every run still
reports success.

```
P = best_score + 1.2 * waiting_days + 0.5 * freshness + 0.3 * min(count, 5)
```

Waiting is the only uncapped term, so nobody can be outbid forever. The
crossover against the best possible rival (12 + 3.5 + 1.5 = 17.0) is 17.0 / 1.2,
about 15 days. Simulated over 53 real snapshots of the board with 200
subscribers: worst wait 2 days, miss rate 0.7 percent. The same simulation with
a fixed weekly cohort instead: worst wait 35 days, miss rate 6.7 percent.

## Database rules that are not in Python

The seat arithmetic is a trigger, not application code, because two signups
arriving together must not both read the same stale count.

- `sightstone_enforce_cap` holds the 200 seat cap under `pg_advisory_xact_lock`.
  Without the lock, 199 filled seats plus 20 simultaneous inserts end at 219.
  That measurement is a test.
- `sightstone_seats_taken` counts three things, not one: confirmed subscribers,
  unconfirmed ones inside their 48 hour window, and outstanding invitations.
  Dropping the third term invites two people to one seat.
- `sightstone_waitlist_cap` bounds the queue at 2000. Measured: queue rows are
  about 198 bytes, so an unbounded queue fills the free 500 MB at roughly 2.65
  million rows.
- Row level security gives `anon` insert and nothing else. Measured against a
  real cluster: anon cannot read a single address, cannot mass unsubscribe and
  cannot delete.

## Testing

```
python3 -m unittest discover engine/tests     # 454 tests, 0 skipped
```

No network, no keys, no production file written. Four things are worth naming:

**A real PostgreSQL.** `pg_harness` runs `initdb` into a temp directory and
listens on a unix socket inside it. A test that reads `schema.sql` as a string
can prove the lock line is present; only twenty real sessions prove it works.
CI puts postgres on `PATH` and fails if `initdb` is missing, because for a long
time it was absent and 52 tests were silently not collected.

**Python and JavaScript agree.** The signup form counts matching listings live,
and that count is a promise. `build_site` ships the titles already normalised by
`match.norm_title` plus the matcher's own expansion table, so the browser only
splits and substring tests. `test_reach_parity` runs both under node and Python
over 14 inputs and fails if they disagree.

**Every shipped script parses.** This generator is Python writing JavaScript, so
a single wrong backslash turns a whole inline script into a syntax error while
the HTML still looks perfect. That shipped once and lived for 36 days.
`test_inline_js_valid` runs `node --check` over every inline script and every
generated `.js`.

**Byte frozen surfaces.** Each page is pinned by size and sha256 against frozen
fixtures. A template edit, a stray space or a reworded sentence turns it red,
and the diff has to be explained before the pin moves.

## The measuring instrument

`tools/measure.py` is frozen. No phase may edit it, because the thing being
measured must not be allowed to write its own report card. It reads the git
history of `engine/data/jobs.json` to derive listing lifetime and miss rates,
and it exits non zero when an invariant is red so that it is a gate and not a
readout.

One known false positive is recorded rather than patched around: the D2 line
greps the source for a URL parameter and cannot see that the confirmation
filter now lives in code.

## Workflows

`daily.yml`, cron `0 6 * * *`: fetch, test, build, mail, commit. Full history
checkout, because the priority simulation replays it as its input data.

`confirm.yml`, every 15 minutes: confirmations only, and by construction it
cannot send a bulletin.

Both share one concurrency group. They commit the same directory, and two runs
racing over one ledger lose one of them.

The commit step runs whenever the tests passed, whatever the mailer did. It is
gated on the tests and not on success, because `mail_state.json` is written per
subscriber precisely so a half finished run remembers what it already sent, and
a skipped commit threw that away and re-sent everything the next morning.

## Sending identity

`news@mail.noseydewdrop.com`, on a subdomain so the apex site keeps its own DNS.
DKIM, SPF (MX and TXT) and DMARC are published and aligned. `List-Unsubscribe`
is on every mail. `List-Unsubscribe-Post` is deliberately absent: one click
unsubscribe is a POST, and a static page answers POST with 405, so claiming it
would be a promise the page cannot keep.

Resend sits behind Cloudflare, which rejects urllib's default agent with a 403.
The provider therefore sends a named `User-Agent`, and a test pins it, because
the failure mode was a soft fail and a bulletin that silently never arrived.
