# The strategy, and the evidence for it

[← back to the README](../README.md)

The strategy is a published rule, replayed here over its author's own 547-race
log. Those posts are the author's, so they are not committed: save the
second post as `post-info/SecondPost.md` and `python analysis/validate.py` reproduces every number
below that comes from those 547 races (~30s, or `--quick`); the figures drawn
from our own `data/race_log.csv` are called out where they appear, and
`python -m insidetrack stats` is the reader for that half.

## The rule

1. **Two horses at EVENS** → skip, minimum bet. The pair splits the win
   probability; backing one of them returned −25% over the 16 such races,
   and −15% over the 40 in the two logs together.
2. Otherwise back the first price present in **EVENS > 2/1 > 4/1 > 3/1 > 5/1**
   and max-bet it. (4/1 really does beat 3/1: close win rates, 5× vs 4× payout.)
3. Duplicates of the chosen price → lane 3, 2, 1, 6, 5, 4 in that order.
4. **Nothing better than 6/1** → skip, minimum bet.

## How it compares

| strategy | ROI | $/race |
| --- | --- | --- |
| **pickorder** (the default) | **+50.6%** | **$4,917** |
| always the lowest odds | +42.2% | $4,223 |
| always track 3 | +29.6% | $2,962 |
| random lane | +12.6% | $1,261 |

The edge is real: every favourite wins more often than its price implies.
EVENS wins 56.2% of the time against a 50% break-even, 2/1 wins 45.0% against
33.3%, 4/1 wins 30.3% against 20.0%. Anything at 6/1 or longer is at or below
break-even and gets skipped.

Pooling the 547 with the 656 races we have logged ourselves — 1,203 boards,
`python -m insidetrack stats` for our half — every one of those readings
holds: EVENS 55.3%, 2/1 43.1%, 3/1 30.3%, 4/1 30.6%, 5/1 22.4%, each above
its break-even. Backing everything at 6/1 or longer flat, over 4,812
appearances, returns **−2.5%**. That is the line the rule is drawn on, and
it is drawn in the right place.

## Expect variance

Bootstrapping those 547 races 5,000× puts the rule's 95% interval at **+36.5%
to +65.5% ROI**. 547 races is not many, and an hour well below the average is
a normal outcome rather than a broken bot.

The 656 graded races in this repo's own `data/race_log.csv` are the second
sample, and they land lower in that interval than the middle: **+39.0% ROI,
$3,762 a race**. Pooling both — 1,203 races — gives **+44.3%, with a 95%
interval of +34.8% to +54.2%**. The rule survives the replication; the
headline number was near the top of its range.

## Throughput

Throughput is the other half, and it is the half you control. The median cycle
over the 663 races in `data/race_log.csv` is **40.3s, or ~89 races an hour**,
which puts the pooled ROI interval at roughly **$310k–$484k/h**.

`budget` models the same figure from your timings and comes out optimistic
(~109/h), because it estimates the race wait rather than measuring it — the
log is the truth. Published claims of 103 races/h are still faster than this
gets, but not by as much as they were.

## The other strategy

There is a second strategy, `chart`, kept only for comparison. It looks better
in-sample (+57.4%) and is worse in reality (+38.2% cross-validated, and +36.5%
against pickorder's +39.0% over our own 656 races — boards its tables were
fitted long before). Don't run it for money.

## Your own numbers

`python -m insidetrack stats` reads `data/race_log.csv` back: what your own
bets returned, broken down by price backed, by lane and by bet size, plus the
table of what actually *wins* over every board you've seen, whatever you bet
on it. A few hundred graded races there are worth more than the numbers above.
