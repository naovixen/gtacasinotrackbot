"""
Validate the Inside Track strategy against the raw race log.
    python validate.py            # full report
    python validate.py --quick    # skip the bootstrap and cross-validation

Everything here is measured on the 547 races the Reddit author transcribed
in post-info/SecondPost.md, using his own accounting: stake 100 per bet, a
win on an n/1 horse returns (n+1)x, only the slot marked 'w' pays.
"""
import itertools
import random
import statistics
import sys

from parse_races import load
import inside_track_bot as bot

MAX_BET, MIN_BET = 10_000, 100
SECONDS_PER_RACE = 35.0          # his pace: 103 races/hour
RACES_PER_HOUR = 3600 / SECONDS_PER_RACE

RACES, PROBLEMS = load("SecondPost.md")
FIRST_POST = 415                 # FirstPostComment.md is the first 415 races
TAIL = RACES[FIRST_POST:]        # recorded after the charts were published
QUICK = "--quick" in sys.argv


def rule(title):
    print(f"\n{'=' * 74}\n{title}\n{'=' * 74}")


# --------------------------------------------------------------------------
# Scoring
# --------------------------------------------------------------------------

def score(races, strategy):
    """Returns (roi_pct, profit_per_race, skips, win_rate_on_real_bets)."""
    staked = returned = skips = wins = 0
    for race in races:
        lane, max_bet = strategy([h["horse"] for h in race])
        stake = MAX_BET if max_bet else MIN_BET
        skips += not max_bet
        staked += stake
        h = race[lane - 1]
        if h["win"]:
            returned += (h["horse"] + 1) * stake
            wins += max_bet
    real = len(races) - skips
    return ((returned - staked) / staked * 100,
            (returned - staked) / len(races),
            skips,
            wins / real * 100 if real else 0.0)


def report(races, strategy, label):
    roi, ppr, skips, wr = score(races, strategy)
    print(f"  {label:<36} ROI {roi:+7.1f}%   ${ppr:>7,.0f}/race   "
          f"${ppr * RACES_PER_HOUR:>9,.0f}/h   skip {skips:>3}   win {wr:4.1f}%")
    return roi


# --------------------------------------------------------------------------
# Strategies
# --------------------------------------------------------------------------

def live(odds):
    """The shipped decide(), so this measures the actual bot."""
    lane, max_bet, _ = bot.decide(list(odds))
    return lane, max_bet


def pickorder(order=(1, 2, 4, 3, 5), skip_two_evens=True,
              tiebreak=(3, 2, 1, 6, 5, 4)):
    def strat(odds):
        evens = [i + 1 for i, o in enumerate(odds) if o == 1]
        if skip_two_evens and len(evens) >= 2:
            return 3, False
        for target in order:
            lanes = [i + 1 for i, o in enumerate(odds) if o == target]
            if lanes:
                return min(lanes, key=tiebreak.index), True
        return 3, False
    return strat


def lowest_odds(odds):
    best = min(odds)
    lanes = [i + 1 for i, o in enumerate(odds) if o == best]
    return min(lanes, key=(3, 2, 1, 6, 5, 4).index), True


def chart_strategy(charts, min_roi=1):
    no1, no12, no123 = charts

    def strat(odds):
        evens = [i + 1 for i, o in enumerate(odds) if o == 1]
        if len(evens) >= 2:
            return 3, False
        if len(evens) == 1:
            return evens[0], True
        present = {o for o in odds if 2 <= o <= 5}
        if not present:
            return 3, False
        chart = no1 if 2 in present else (no12 if 3 in present else no123)
        cands = [(chart[i + 1][o], i + 1) for i, o in enumerate(odds)
                 if 2 <= o <= 5 and o in chart[i + 1]]
        if not cands:
            return 3, False
        roi, lane = max(cands, key=lambda c: (c[0], -(3, 2, 1, 6, 5, 4).index(c[1])))
        return (lane, True) if roi >= min_roi else (3, False)
    return strat


def fit_charts(train):
    """Rebuild the three conditional (track, horse) ROI tables from races."""
    def table(cond, cols):
        counts = {}
        for race in train:
            nums = {h["horse"] for h in race}
            if not cond(nums):
                continue
            for track, h in enumerate(race, start=1):
                if h["horse"] in cols:
                    w, a = counts.get((track, h["horse"]), (0, 0))
                    counts[(track, h["horse"])] = (w + h["win"], a + 1)
        return {track: {n: (((counts.get((track, n), (0, 0))[0] * (n + 1))
                             / counts[(track, n)][1] - 1) * 100
                            if counts.get((track, n), (0, 0))[1] else -999)
                        for n in cols}
                for track in range(1, 7)}
    return (table(lambda s: 1 not in s, {2, 3, 4, 5}),
            table(lambda s: not ({1, 2} & s), {3, 4, 5}),
            table(lambda s: not ({1, 2, 3} & s), {4, 5}))


# --------------------------------------------------------------------------
# 1. The data
# --------------------------------------------------------------------------

rule("1. THE DATA")
print(f"  {len(RACES)} races parsed from post-info/SecondPost.md"
      f"   ({len(PROBLEMS)} rejected: {PROBLEMS[0] if PROBLEMS else '-'})")
print("\n  Per-horse ROI, all races -- compare with his published chart\n"
      "  (his figures, on 512 races: 1=+14% 2=+36% 3=+4% 4=+51% 5=+18%)")
print("\n  horse  appearances  wins   win rate   odds imply   ROI")
for n in range(1, 8):
    apps = sum(1 for r in RACES for h in r if h["horse"] == n)
    wins = sum(1 for r in RACES for h in r if h["horse"] == n and h["win"])
    if apps:
        print(f"   {n:>2}       {apps:>5}     {wins:>4}    {wins/apps*100:>5.1f}%"
              f"       {100/(n+1):>5.1f}%    {wins/apps*(n+1)-1:+.0%}")
print("\n  Every favourite pays more than its odds imply -- that is the whole")
print("  edge. Horses 6/1 and longer are at or below break-even.")

# --------------------------------------------------------------------------
# 2. Does the shipped bot reproduce his numbers?
# --------------------------------------------------------------------------

rule("2. THE SHIPPED BOT vs HIS CLAIM"
     f"   ({MAX_BET:,} max bet, ${MIN_BET} skip, {RACES_PER_HOUR:.0f} races/h)")
bot.STRATEGY = "pickorder"
report(RACES, live, "inside_track_bot (pickorder)")
bot.STRATEGY = "chart"
report(RACES, live, "inside_track_bot (chart)")
bot.STRATEGY = "pickorder"
print()
report(RACES, pickorder(), "his SecondPost rule, reimplemented")
report(RACES, pickorder(skip_two_evens=False), "  without the two-EVENS skip")
report(RACES, lowest_odds, "always the lowest odds (no fitting)")
for t in (3, 4):
    report(RACES, lambda o, t=t: (t, True), f"always track {t}")
random.seed(0)
report(RACES, lambda o: (random.randint(1, 6), True), "random lane")
print("\n  He claims 500-800k/h. The pick-order rule lands at the bottom of")
print("  that band, and only if you actually hit ~103 races/hour.")

# --------------------------------------------------------------------------
# 3. The charts are overfit
# --------------------------------------------------------------------------

rule("3. WHY THE ROI CHARTS LOSE OUT-OF-SAMPLE")
print(f"  Held out: the {len(TAIL)} races recorded AFTER the first post's")
print("  charts were published, so they cannot have shaped those charts.\n")
bot.STRATEGY = "chart"
report(TAIL, live, "chart strategy")
bot.STRATEGY = "pickorder"
report(TAIL, live, "pickorder")
report(TAIL, lowest_odds, "always lowest odds")

if not QUICK:
    print("\n  5-fold cross-validation, charts refitted on each training split,")
    print("  averaged over 20 shuffles:\n")
    agg = {}
    for seed in range(20):
        idx = list(range(len(RACES)))
        random.Random(seed).shuffle(idx)
        folds = [[RACES[i] for i in idx[j::5]] for j in range(5)]
        tot = {}
        for j in range(5):
            test = folds[j]
            train = [r for m, f in enumerate(folds) if m != j for r in f]
            for name, strat in (("chart (refit)", chart_strategy(fit_charts(train))),
                                ("pickorder", pickorder()),
                                ("lowest odds", lowest_odds)):
                staked = returned = 0
                for race in test:
                    lane, mx = strat([h["horse"] for h in race])
                    stake = MAX_BET if mx else MIN_BET
                    staked += stake
                    h = race[lane - 1]
                    if h["win"]:
                        returned += (h["horse"] + 1) * stake
                a, b = tot.get(name, (0, 0))
                tot[name] = (a + staked, b + returned)
        for name, (s, r) in tot.items():
            agg.setdefault(name, []).append((r / s - 1) * 100)
    for name, rois in agg.items():
        m = statistics.mean(rois)
        print(f"    {name:<16} OOS ROI {m:+6.1f}%   ${m/100*MAX_BET*RACES_PER_HOUR:>9,.0f}/h")

print("\n  Each chart cell rests on 7-40 appearances and 1-20 wins. Taking")
print("  max() over six such cells picks whichever one got lucky, so the")
print("  in-sample ROI is an artefact. This is why STRATEGY defaults to")
print("  'pickorder'.")

# --------------------------------------------------------------------------
# 4. Is the pick order right?
# --------------------------------------------------------------------------

rule("4. IS THE PICK ORDER EVENS > 2/1 > 4/1 > 3/1 > 5/1 CORRECT?")
print("  Head-to-head: ROI of each horse restricted to races containing BOTH,")
print("  so the two columns are measured over exactly the same races.\n")
print("   pair      n     A ROI     B ROI    winner")


def roi_of(race, horse):
    for h in race:
        if h["horse"] == horse:
            return (horse + 1) * 100 if h["win"] else 0
    return None


for a in range(1, 6):
    for b in range(a + 1, 6):
        n = ra = rb = 0
        for race in RACES:
            x, y = roi_of(race, a), roi_of(race, b)
            if x is None or y is None:
                continue
            n, ra, rb = n + 1, ra + x, rb + y
        if n < 15:
            continue
        A, B = (ra / (n * 100) - 1) * 100, (rb / (n * 100) - 1) * 100
        print(f"   {a} vs {b}  {n:>4}   {A:+7.1f}%  {B:+7.1f}%    horse "
              f"{a if A > B else b}")
print("\n  1>2, 2>3, 2>4, 2>5, 4>3, 4>5, 3>5  =>  1 > 2 > 4 > 3 > 5. His order")
print("  holds. 4/1 beating 3/1 is real: their win rates are close (30.3% vs")
print("  26.7%) but 4/1 pays 5x against 4x.")

print("\n  Sanity check on the favourite-first rule -- inside the 185 races")
print("  with exactly one EVENS:")
one_ev = [r for r in RACES if sum(h["horse"] == 1 for h in r) == 1]
for pick, label in ((1, "the EVENS horse"), (2, "the 2/1 instead"),
                    (4, "the 4/1 instead")):
    st = re = n = 0
    for race in one_ev:
        v = roi_of(race, pick)
        if v is None:
            continue
        n, st, re = n + 1, st + 100, re + v
    print(f"    bet {label:<20} n={n:>3}   ROI {(re/st-1)*100:+6.1f}%")
print("  Marginal per-horse ROI says 4/1 is the best horse overall; that is a")
print("  selection effect. Once an EVENS is in the race, everything else")
print("  collapses. Always take the shortest price.")

print("\n  The two-EVENS skip:")
two = [r for r in RACES if sum(h["horse"] == 1 for h in r) >= 2]
st = re = 0
for race in two:
    h = [x for x in race if x["horse"] == 1][0]
    st += 100
    re += 200 if h["win"] else 0
print(f"    {len(two)} races; betting one of the two EVENS: "
      f"ROI {(re/st-1)*100:+.1f}%  -> skipping is correct")

if not QUICK:
    print("\n  All 120 orderings of horses 1-5, scored on all 547 races:")
    scored = sorted(((score(RACES, pickorder(order=o))[0], o)
                     for o in itertools.permutations([1, 2, 3, 4, 5])),
                    reverse=True)
    for roi, o in scored[:3]:
        print(f"    {'>'.join(map(str, o))}   ROI {roi:+6.1f}%")
    print(f"    ...")
    for roi, o in scored[-2:]:
        print(f"    {'>'.join(map(str, o))}   ROI {roi:+6.1f}%")
    print("  His order ranks 1st. That it is also the order he tuned ON this")
    print("  data is worth remembering -- but unlike the charts it has 5")
    print("  parameters over 547 races, not 24 cells over 71-346.")

    print("\n  Lane tiebreak (only fires on 14% of races):")
    for tb in ((3, 2, 1, 6, 5, 4), (3, 1, 2, 5, 6, 4), (1, 2, 3, 4, 5, 6)):
        r = score(RACES, pickorder(tiebreak=tb))[0]
        note = "  <- his" if tb == (3, 2, 1, 6, 5, 4) else ""
        print(f"    {tb}  ROI {r:+6.1f}%{note}")
    print("  Worth about one ROI point. Not worth optimising.")

# --------------------------------------------------------------------------
# 5. How certain is any of this?
# --------------------------------------------------------------------------

if not QUICK:
    rule("5. HOW MUCH OF THE EDGE IS REAL?")
    print("  Bootstrap: resample the 547 races with replacement, 5,000 times.\n")
    rng = random.Random(1)
    for name, strat in (("pickorder (default)", pickorder()),
                        ("chart", chart_strategy(
                            (bot.CHART_NO1, bot.CHART_NO12, bot.CHART_NO123))),
                        ("always lowest odds", lowest_odds)):
        out = []
        for _ in range(5000):
            sample = [RACES[rng.randrange(len(RACES))] for _ in range(len(RACES))]
            out.append(score(sample, strat)[0])
        out.sort()
        lo, hi, m = out[125], out[4875], statistics.mean(out)
        print(f"    {name:<22} ROI {m:+6.1f}%  95% CI [{lo:+.1f}%, {hi:+.1f}%]"
              f"  -> ${lo/100*MAX_BET*RACES_PER_HOUR:>7,.0f}"
              f" .. ${hi/100*MAX_BET*RACES_PER_HOUR:,.0f}/h")
    print("\n  547 races is not many. The edge is clearly positive, but the")
    print("  hourly rate is a wide band, and a bad hour inside it is normal.")

# --------------------------------------------------------------------------
# 6. Throughput
# --------------------------------------------------------------------------

rule("6. THROUGHPUT IS THE BINDING CONSTRAINT")
ppr = score(RACES, pickorder())[1]
print(f"  Profit per race at +50.6% ROI: ${ppr:,.0f}\n")
print("   races/h   seconds/race   $/hour")
for rate in (60, 75, 90, 103, 110):
    print(f"    {rate:>4}         {3600/rate:>5.1f}      ${ppr*rate:>10,.0f}"
          + ("   <- his claimed pace" if rate == 103 else ""))
print("\n  Run `python inside_track_bot.py budget` for what the bot's own")
print("  timing profiles actually achieve.")
