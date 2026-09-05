# The strategy, and the evidence for it

[← back to the README](../README.md)

The strategy is a published rule, replayed here over its author's own 547-race
log (`post-info/`). `python analysis/validate.py` reproduces every number
below (~30s, or `--quick`).

## The rule

1. **Two horses at EVENS** → skip, minimum bet. The pair splits the win
   probability; backing one of them returned −25% over the 16 such races.
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

## Expect variance

Bootstrapping those 547 races 5,000× puts the rule's 95% interval at **+36.5%
to +65.5% ROI**. 547 races is not many, and an hour well below the average is
a normal outcome rather than a broken bot.

## Throughput

Throughput is the other half, and it is the half you control. The median cycle
over the 473 races in this repo's own `data/race_log.csv` is **47s, or ~76
races an hour**, which puts the ROI interval at roughly **$270k–$480k/h**.

`budget` models the same figure from your timings and comes out optimistic
(~85/h), because it estimates the race wait rather than measuring it — the log
is the truth. Published claims of 103 races/h are faster than this gets.

## The other strategy

There is a second strategy, `chart`, kept only for comparison. It looks better
in-sample (+57.4%) and is worse in reality (+38.2% cross-validated). Don't run
it for money.

## Your own numbers

`python -m insidetrack stats` reads `data/race_log.csv` back: what your own
bets returned, broken down by price backed, by lane and by bet size, plus the
table of what actually *wins* over every board you've seen, whatever you bet
on it. A few hundred graded races there are worth more than the numbers above.
