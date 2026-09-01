#!/usr/bin/env python3
"""S11 -- "my turn comes".

The daily budget is finite. Without an order the send loop serves whatever
order the database returned, which is stable, so the same tail is cut every
morning and never hears from us -- and every individual run still looks like a
success. This file measures that the aging queue fixes it, and measures it
against the REAL git history of jobs.json rather than invented data, because
the card says a simulation fed with made-up data fails the phase.

The card's acceptance command names `tools/measure.py --miss-simulated`. That
command cannot exist: measure.py is FROZEN by S1 and a phase may not add a
subcommand to it. The simulation lives here instead, inside engine/tests/,
which the card's own DOKUNULABILIR list allows.

Run: python3 -m unittest discover engine/tests -v
"""
import json
import subprocess
import sys
import unittest
from datetime import date
from pathlib import Path

HERE = Path(__file__).parent
ENGINE = HERE.parent
sys.path.insert(0, str(ENGINE))

import match  # noqa: E402
import send_mail  # noqa: E402

# Ten interest archetypes, twenty subscribers each: two hundred people, the
# capacity the seat cap is set to.
ARCHETYPES = [
    ["machine learning"], ["ai infrastructure"], ["data science"],
    ["computer vision"], ["software engineering"], ["nlp"],
    ["robotics"], ["security"], ["cloud"], ["analytics"],
]
PER_ARCHETYPE = 20
MIN_SCORE = 4

MAX_WAIT_DAYS = 8       # the card's threshold
MAX_MISS = 0.10         # the card's threshold


def profile_for(interests):
    return {"identity": {"location": "Ankara, Turkey"},
            "direction_and_motivation": {"target_field": "; ".join(interests)},
            "constraints": {"relocation": True},
            "education": "BS student"}


def load_snapshots():
    """Every committed state of jobs.json, oldest first. Real data only."""
    out = []
    log = subprocess.run(
        ["git", "-C", str(ENGINE.parent), "log", "--format=%H %cI", "--reverse",
         "--", "engine/data/jobs.json"],
        capture_output=True, text=True).stdout.split("\n")
    for line in filter(None, log):
        sha, ts = line.split()
        blob = subprocess.run(
            ["git", "-C", str(ENGINE.parent), "show", f"{sha}:engine/data/jobs.json"],
            capture_output=True, text=True).stdout
        try:
            jobs = json.loads(blob)
        except Exception:
            continue
        deduped, _ = match.dedupe(jobs)
        out.append((date.fromisoformat(ts[:10]), deduped))
    return out


def simulate(snaps, mode):
    """Replay the history day by day. `mode` is 'aging' or 'cohort'."""
    subs = [(f"s{i}@x.test", ARCHETYPES[i % len(ARCHETYPES)])
            for i in range(len(ARCHETYPES) * PER_ARCHETYPE)]
    sent = {e: set() for e, _ in subs}
    last = {e: None for e, _ in subs}
    eligible_seen, mailed_on = {}, {}

    for day_i, (day, jobs) in enumerate(snaps):
        per_arch = {}
        for idx, arch in enumerate(ARCHETYPES):
            res, _ = match.run(profile_for(arch), jobs)
            per_arch[idx] = [r for r in res if r["score"] >= MIN_SCORE]
        queue = []
        for i, (email, _) in enumerate(subs):
            new = [r for r in per_arch[i % len(ARCHETYPES)]
                   if send_mail.job_key(r) not in sent[email]]
            for r in new:
                eligible_seen.setdefault((email, send_mail.job_key(r)), day)
            if not new:
                continue
            wait = (day - last[email]).days if last[email] else 10 ** 6
            if mode == "aging":
                ages = [r["age_days"] for r in new if r.get("age_days") is not None]
                p = send_mail.priority(max(r["score"] for r in new), wait,
                                       min(ages) if ages else None, len(new))
            else:
                p = 1.0 if (i % 7) == (day_i % 7) else -1.0
            queue.append((p, email, new))
        queue.sort(key=lambda t: (-t[0], t[1]))
        served = 0
        for p, email, new in queue:
            if served >= send_mail.DAILY_MAIL_CAP:
                break
            if mode == "cohort" and p < 0:
                continue
            for r in new:
                k = send_mail.job_key(r)
                sent[email].add(k)
                mailed_on.setdefault((email, k), day)
            last[email] = day
            served += 1

    final_live = {send_mail.job_key(j) for j in snaps[-1][1]}
    last_day = snaps[-1][0]
    missed = sum(1 for pair in eligible_seen
                 if pair not in mailed_on and pair[1] not in final_live)
    # Starvation is how long a listing sat ELIGIBLE and ALIVE without reaching
    # the person it matched. A subscriber with nothing matching is not starving:
    # an empty board is the honest answer for them, and counting that as a wait
    # makes the number meaningless.
    waited = []
    for pair, seen_day in eligible_seen.items():
        got = mailed_on.get(pair)
        if got is not None:
            waited.append((got - seen_day).days)
        elif pair[1] in final_live:
            waited.append((last_day - seen_day).days)
    return {"miss": missed / len(eligible_seen) if eligible_seen else 0.0,
            "max_wait": max(waited) if waited else 0,
            "pairs": len(eligible_seen)}


class PriorityFormula(unittest.TestCase):
    """The card's coefficients, and the one property they exist to guarantee."""

    def test_the_coefficients_are_the_cards(self):
        self.assertEqual(send_mail.PRIORITY_WAIT, 1.2)
        self.assertEqual(send_mail.PRIORITY_FRESH, 0.5)
        self.assertEqual(send_mail.PRIORITY_COUNT, 0.3)
        self.assertEqual(send_mail.PRIORITY_COUNT_CAP, 5)

    def test_waiting_beats_the_best_possible_quality_score(self):
        """Starvation has to be arithmetically impossible, not merely unlikely.

        The matcher's ceiling is the interest cap, 12. Six days of waiting is
        THE CARD'S OWN ARITHMETIC IS WRONG HERE, and it is worth writing down.
        It argues "six days of waiting is +7.2 and catches the highest quality
        score (12)" -- comparing waiting against the interest cap alone and
        forgetting the other two terms the same formula introduced. The best
        possible rival is 12 + 3.5 (posted today) + 1.5 (the count cap) = 17.0,
        so the crossover is 17.0 / 1.2 = about 15 days, not 6.

        The guarantee itself survives: waiting is the only unbounded term and
        every other one is capped, so whoever waits long enough goes first. The
        bound is two weeks rather than one. Measured against the real history
        the worst observed wait is nowhere near either number.
        """
        best_rival = send_mail.priority(12, 0, 0, send_mail.PRIORITY_COUNT_CAP)
        self.assertEqual(best_rival, 17.0)
        crossover = best_rival / send_mail.PRIORITY_WAIT
        self.assertLess(send_mail.priority(0, crossover - 1, None, 0), best_rival)
        self.assertGreater(send_mail.priority(0, crossover + 1, None, 0), best_rival)
        self.assertLessEqual(crossover, 15)

    def test_never_mailed_sorts_first(self):
        self.assertEqual(send_mail.waiting_days("nobody", {}), float("inf"))
        self.assertEqual(send_mail.priority(0, float("inf"), None, 0),
                         float("inf"))

    def test_a_corrupt_last_sent_is_treated_as_never_mailed(self):
        """A bad date must not silently park somebody at the back forever."""
        state = {"abc": {"last_sent": "not-a-date"}}
        self.assertEqual(send_mail.waiting_days("abc", state), float("inf"))

    def test_freshness_only_counts_inside_the_window(self):
        inside = send_mail.priority(0, 0, 0, 0)
        edge = send_mail.priority(0, 0, send_mail.PRIORITY_FRESH_DAYS, 0)
        outside = send_mail.priority(0, 0, 90, 0)
        self.assertGreater(inside, edge)
        self.assertEqual(edge, outside)

    def test_the_count_term_saturates(self):
        five = send_mail.priority(0, 0, None, 5)
        fifty = send_mail.priority(0, 0, None, 50)
        self.assertEqual(five, fifty)


class RankingIsUsed(unittest.TestCase):
    """A formula nothing calls is decoration."""

    def test_rank_targets_puts_the_longest_waiter_first(self):
        jobs = json.loads((ENGINE / "data" / "jobs.json").read_text())
        fed = ("fed@x.test", profile_for(["machine learning"]), None)
        starved = ("starved@x.test", profile_for(["machine learning"]), None)
        import hashlib
        fed_id = hashlib.sha1(b"fed@x.test").hexdigest()[:12]
        state = {fed_id: {"sent_keys": [], "last_sent": date.today().isoformat()}}
        order = send_mail.rank_targets([fed, starved], jobs, state, MIN_SCORE)
        self.assertEqual(order[0][0], "starved@x.test")

    def test_the_send_loop_calls_it(self):
        src = (ENGINE / "send_mail.py").read_text()
        self.assertIn("targets = rank_targets(", src)


class SimulationOnRealHistory(unittest.TestCase):
    """The card: 200 subscribers, nobody waits over 8 days, miss <= 10%, and
    the fixed weekly cohort must come out measurably WORSE."""

    @classmethod
    def setUpClass(cls):
        cls.snaps = load_snapshots()
        cls.aging = simulate(cls.snaps, "aging")
        cls.cohort = simulate(cls.snaps, "cohort")

    def test_the_history_is_real_and_long_enough_to_mean_something(self):
        self.assertGreaterEqual(len(self.snaps), 30)
        span = (self.snaps[-1][0] - self.snaps[0][0]).days
        self.assertGreaterEqual(span, 21)

    def test_nobody_waits_longer_than_the_card_allows(self):
        self.assertLessEqual(self.aging["max_wait"], MAX_WAIT_DAYS,
                             f"measured {self.aging['max_wait']} days")

    def test_the_miss_rate_is_under_the_gate(self):
        self.assertLessEqual(self.aging["miss"], MAX_MISS,
                             f"measured {self.aging['miss']:.1%}")

    def test_the_fixed_cohort_is_measurably_worse(self):
        """If it were not, the queue would be complexity for nothing."""
        self.assertGreater(self.cohort["miss"], self.aging["miss"] * 2)
        self.assertGreater(self.cohort["max_wait"], MAX_WAIT_DAYS)


if __name__ == "__main__":
    unittest.main()
