# dewsletter

A listing reaches you with the reason it concerns you, or it does not reach you.

Live: https://nosey-dewdrop.github.io/dewsletter/

Every morning dewsletter reads the day's AI/ML internship board, scores each
listing against your profile, and mails you only the ones that are new to you.
Every match arrives with the reason it was sent, in words. Nothing new, no mail.

There is no language model anywhere in it. A point is never awarded without a
reason string attached, so any number on the site can be reproduced by running
the same code over the same file.

## The flow, in the order a person meets it

1. You write down what you are looking for, or you hand it a CV and it fills
   that in for you. The CV is read in your own browser tab and is never
   uploaded.
2. As you type, the page tells you how many of today's listings would match.
   If the answer is zero it says so, plainly, instead of letting you sign up
   for silence.
3. One mail arrives to confirm the address is yours. Nothing else is sent
   until you click it.
4. From then on you get a bulletin when, and only when, something new matches.
   One a day at most, however many times the pipeline happens to run.
5. Every mail carries a link that ends it. Leaving frees your seat for the
   next person.

Membership is capped, so the queue is real: when the seats are full you join a
waiting list, and when a seat opens the oldest waiting address is invited and
has 48 hours to take it.

## Why should this exist?

The person who gets the internship is usually not the best candidate. It is
the one who saw the posting first. Measured on this repo's own history of the
board, a listing lives a median of 9.77 days and roughly a fifth of them are
gone within three. Watching job boards harder is a real advantage, and it is
the advantage this deletes.

## How does the scoring work?

Only interest, skill and role fit earn points. Geography, freshness and salary
earn nothing at all.

That is not a detail. Those three used to score, and the result was that two
of three matches sent to the sample profile were there because the listing
said "remote" and for no other reason. "Remote" is not a reason you should
read next to a job. It is the filter that failed to eliminate it. So the
filters stayed filters: they can still remove a listing you could never take,
but they can no longer put one in front of you.

A listing whose only distinction is that it is remote now scores zero and is
not a match.

## The numbers on the site

Every figure the site prints comes from the engine, on the corpus of the day.
Today, for the sample profile:

```
630   listings on the board
486   removed before scoring: onsite in a country the profile cannot move to
 95   removed: PhD only
  1   match
```

One match out of 630 is not a broken engine. The sample profile is deliberately
the hardest case on the board, somebody who cannot change countries and cannot
take a US only remote role. The site prints the reach number next to the match
number so that one is readable.

## Running it

```
python3 -m unittest discover engine/tests    # 454 tests, no network, no keys
python3 engine/fetch_speedyapply.py          # refresh the board
python3 engine/build_site.py                 # rebuild docs/
python3 engine/send_mail.py --dry-run        # see the bulletin without sending
python3 tools/measure.py --lifetime          # measure the corpus from git history
```

The test suite needs no secrets and touches no network. The SQL tests build a
throwaway PostgreSQL cluster in a temp directory; if `initdb` is missing they
are skipped locally, and CI fails rather than skipping them quietly.

## Deliberately not here

**No language model.** Not in the matcher, not in the CV report, not in the
mail. A rule that cannot be read is a rule that cannot be argued with.

**No tracking.** The dataset is public, your profile is not. There is no
analytics script on any page.

**No CV upload.** The CV report runs entirely in your browser. The engine has
no code that sends CV text anywhere, and the database has no column that could
hold it.

**No guessing.** When the source ships a listing with no location, the engine
declines to guess and says so in its own census. Twenty six listings sit in
that bucket today.

## Known limits, written down rather than implied

- The confirmation mail rides a job that runs every fifteen minutes, so it
  arrives in minutes rather than instantly. Instant would need a server side
  hook on the insert, which a static site and a cron cannot give.
- The daily rebuild is asked for at 09:00 UTC+3, but the scheduler running it
  is best effort. Measured over 37 scheduled runs the median build landed 78
  minutes late and the latest landed 12 hours late.
- A determined bot can still take the seats one signup at a time. It heals by
  itself, because an unconfirmed seat is released after 48 hours, and it can no
  longer exhaust the mail budget or the database. Closing it properly needs a
  captcha, and validating a captcha needs a server this project does not have.
- Two addresses that differ only in capitals are two rows, two seats and two
  mails. The unique constraint is case sensitive.
- An address that unsubscribes cannot sign up again with the same address.

## Licence

See LICENSE.
