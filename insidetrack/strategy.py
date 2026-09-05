"""Which horse to back, and what a finished race was worth.

Validated against the 547-race log in post-info/SecondPost.md; `python
validate.py` reproduces every number.

  1. TWO horses at EVENS -> skip with a minimum bet. Betting one of two
     EVENS returned -25% ROI over the 16 such races: the pair splits the win
     probability and neither is worth 2x.
  2. Otherwise take the first horse present in EVENS > 2/1 > 4/1 > 3/1 > 5/1
     and max-bet it. Head-to-head over races containing both horses confirms
     every link; 4/1 genuinely beats 3/1, because their win rates are close
     (30.3% vs 26.7%) while 4/1 pays 5x against 4x.
  3. Duplicate of the chosen horse -> lane 3,2,1,6,5,4 in that order. Fires
     in 14% of races and is worth ~1 ROI point either way.
  4. Everything 6/1 or longer -> minimum-bet skip.

  Measured: +50.6% ROI, ~$4,900 profit per race.

"chart" restores the per-(track, horse) ROI tables. They look better
in-sample (+57.4%) and are worse in reality: +38.2% under 5-fold cross-
validation, and +53.1% against pickorder's +69.0% on the 132 races recorded
after the first post's charts were published. Each cell rests on 7-40
appearances, so taking the max over six of them mostly selects whichever got
lucky. Kept for comparison; do not run it for money.
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
