"""Which horse to back, and what a finished race was worth.

Validated against the 547-race log in post-info/SecondPost.md; `python
analysis/validate.py` reproduces every number.

  1. TWO horses at EVENS -> skip with a minimum bet. Betting one of two
     EVENS returned -25% ROI over the 16 such races, -15% over the 40 in
     both logs: the pair splits the win probability and neither is worth 2x.
  2. Otherwise take the first horse present in EVENS > 2/1 > 4/1 > 3/1 > 5/1
     and max-bet it. Head-to-head over races containing both horses confirms
     every link; 4/1 genuinely beats 3/1, because their win rates are close
     (30.3% vs 26.7%, and 30.6% vs 30.3% over both logs) while 4/1 pays 5x
     against 4x.
  3. Duplicate of the chosen horse -> lane 3,2,1,6,5,4 in that order. Fires
     in 14% of races and is worth ~1 ROI point either way.
  4. Everything 6/1 or longer -> minimum-bet skip.

  Measured: +50.6% ROI, ~$4,900 profit per race.

Replayed against our own data/race_log.csv -- 656 races over 28 runs on
2026-09-05 -- the same rules return +39.0% ROI and +$3,762 a race. That is
behind the 547-race figure now rather than ahead of it, but the gap
(-$1,155 a race, 95% CI -3,037..+715) still sits inside the noise: an
earlier 185-race cut of this same log read +56.7% and +$5,512, which is how
wide a few hundred races can swing.

  DO NOT RE-FIT PICK_ORDER ON OUR OWN LOG. Enumerated over all 1,956
  orderings of the six prices, the order above comes 3rd on the 1,203
  combined races, at +$4,287 a race against the winner's +$4,296 -- the
  winner being this order with 6/1 spliced in ahead of 4/1, which is a $9
  difference and not a finding. Fit on our 656 races alone the search picks
  4/1 > 6/1 > EVENS > 5/1 > 2/1 > 3/1 instead: +$4,159 a race in-sample,
  and +$3,034 on the 547 against this order's +$4,917. That is chart mode's
  mistake wearing a different hat, and every log invites it.

  EVENS was the specific trap, and it is now the worked example of why the
  short log lies. It read soft at 49.3% of the 67 times it had appeared,
  against a 50% break-even, and 45.2% in an earlier log since deleted for
  OCR errors. Over 264 appearances it reads 54.5%, and 55.3% over the 481
  combined -- back where the 547 had it. On the 401 combined boards with
  exactly one EVENS, backing it is worth +$1,421 a race and the best
  alternative on those same boards -$1,421.

  Rule 3's tiebreak has the same shape. Plain 1,2,3,4,5,6 beat 3,2,1,6,5,4
  by +$1,183 a race over the first 185; over 656 that is +$107, CI
  -534..+762, on the 29 races where it changed the pick, and exactly $0
  over the combined set. Two orderings of a coin flip.

  Per-race SD is $16,622 against a $4,287 mean, so telling apart two
  orderings that differ by $500 a race needs ~4,250 races -- about 48 hours
  at 40.3s a race. Until then the 547 is still the better evidence, and the
  combined set better than either half.

  Rule 4 has never fired: no board in the 1,203 has had all six horses at
  6/1 or longer, because none has lacked a horse at 5/1 or shorter. Kept
  for the board that eventually does.

"chart" restores the per-(track, horse) ROI tables. They look better
in-sample (+57.4%) and are worse in reality: +38.2% under 5-fold cross-
validation, and +53.1% against pickorder's +69.0% on the 132 races recorded
after the first post's charts were published. Our own log is the cleanest
out-of-sample test they will ever get, because the cells were fitted before
a race of it existed, and they lose there too: +36.5% against pickorder's
+39.0% over the 656. Each cell rests on 7-40 appearances, so taking the max
over six of them mostly selects whichever got lucky. Kept for comparison;
do not run it for money.
"""

from typing import Optional, Sequence, Tuple

PICK_ORDER = [1, 2, 4, 3, 5]         # EVENS > 2/1 > 4/1 > 3/1 > 5/1
LANE_TIEBREAK = [3, 2, 1, 6, 5, 4]   # between duplicates of the chosen horse
SKIP_LANE = 3                        # where the $100 skip bet is parked
MIN_CELL_ROI = 1                     # chart mode: min ROI% to max-bet

# ROI % per (lane, horse); horse n pays (n+1)x. Recomputed from the full
# 547-race log, not the first post's subset.
CHART_NO1 = {                        # races with no EVENS: 346 races
    1: {2: 76, 3: 0, 4: 74, 5: -36},
    2: {2: 58, 3: -11, 4: 54, 5: 41},
    3: {2: 11, 3: 33, 4: 114, 5: 135},
    4: {2: 11, 3: 45, 4: 45, 5: -11},
    5: {2: 59, 3: 86, 4: 92, 5: 24},
    6: {2: 56, 3: 20, 4: 18, 5: 24},
}
CHART_NO12 = {                       # no horse 1 or 2: 181 races
    1: {3: 14, 4: 133, 5: -71},
    2: {3: 0, 4: 59, 5: 85},
    3: {3: 41, 4: 125, 5: 147},
    4: {3: 60, 4: 59, 5: -25},
    5: {3: 100, 4: 163, 5: 71},
    6: {3: 0, 4: 25, 5: 36},
}
CHART_NO123 = {                      # no horse 1, 2 or 3: 71 races
    1: {4: 122, 5: -45},
    2: {4: 76, 5: 125},
    3: {4: 106, 5: 329},
    4: {4: -23, 5: -60},
    5: {4: 218, 5: 100},
    6: {4: 11, 5: -8},
}

Decision = Tuple[Optional[int], bool, str]      # (lane, max bet, why)


def _tiebreak_key(lane: int) -> int:
    return LANE_TIEBREAK.index(lane)


def decide(odds: Sequence[Optional[int]],
           strategy: str = "pickorder") -> Decision:
    """odds: six values, index 0 = lane 1. Returns (lane, max_bet, reason)."""
    missing = [i + 1 for i, value in enumerate(odds) if value is None]
    if missing:
        return None, False, f"OCR failed on lanes {missing}"

    evens = [i + 1 for i, value in enumerate(odds) if value == 1]
    if len(evens) >= 2:
        return SKIP_LANE, False, "two EVENS -> min-bet skip"
    if len(evens) == 1:
        return evens[0], True, f"EVENS in lane {evens[0]}"

    present = {value for value in odds if 2 <= value <= 5}
    if not present:
        return SKIP_LANE, False, "all horses 6/1+ -> min-bet skip"
    if strategy == "chart":
        return _decide_chart(odds, present)
    return _decide_pick_order(odds)


def _decide_pick_order(odds: Sequence[int]) -> Decision:
    for target in PICK_ORDER[1:]:        # EVENS is handled by decide()
        lanes = [i + 1 for i, value in enumerate(odds) if value == target]
        if lanes:
            lane = min(lanes, key=_tiebreak_key)
            return lane, True, f"best horse {target}/1 in lane {lane}"
    return SKIP_LANE, False, "no ranked horse -> min-bet skip"


def _chart_for(present) -> Tuple[dict, str]:
    if 2 in present:
        return CHART_NO1, "no-EVENS chart"
    if 3 in present:
        return CHART_NO12, "no-1/2 chart"
    return CHART_NO123, "no-1/2/3 chart"


def _decide_chart(odds: Sequence[int], present) -> Decision:
    """Legacy per-cell ROI lookup. Kept for comparison; loses out-of-sample."""
    chart, name = _chart_for(present)
    cells = [(chart[i + 1][value], i + 1, value)
             for i, value in enumerate(odds)
             if 2 <= value <= 5 and value in chart[i + 1]]
    if not cells:
        return SKIP_LANE, False, f"nothing in {name} -> min-bet skip"
    roi, lane, horse = max(cells, key=lambda c: (c[0], -_tiebreak_key(c[1])))
    if roi < MIN_CELL_ROI:
        return SKIP_LANE, False, (f"best cell {horse}/1 lane {lane} ROI "
                                  f"{roi}% < {MIN_CELL_ROI}% ({name}) "
                                  "-> min-bet skip")
    return lane, True, f"{horse}/1 in lane {lane}, ROI {roi}% ({name})"


def grade(odds: Sequence[Optional[int]], lane: Optional[int],
          stake: Optional[int], win_lane: Optional[int]):
    """Score a race from the winning lane: (won, payout), both None if the
    lane could not be read.

    The payout is computed, not observed: Inside Track pays (odds + 1) x the
    stake, so the board we already read and the lane that won are between
    them the whole result. Reading the payout box too was a second OCR per
    race to learn a number we can multiply out.
    """
    if win_lane is None:
        return None, None
    won = int(win_lane == lane)
    horse = odds[lane - 1] if lane else None
    payout = stake * (horse + 1) if (won and horse and stake) else 0
    return won, payout
