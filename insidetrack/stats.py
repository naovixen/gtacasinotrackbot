"""Reading race_log.csv back: what OUR bets have actually returned.

The table this file exists for is what_won(): every race says which PRICE
won, whether or not we backed it, so it measures each horse the way
validate.py measures the 547-race log -- flat-bet ROI for backing that price
every time it appears -- on boards we read ourselves. That, not the ROI on
our own picks, is what PICK_ORDER should eventually be rebuilt from.
"""

from typing import Dict, List, Sequence

from .parsing import odds_label
from .racelog import DEFAULT_PATH, load

Rows = Sequence[Dict[str, str]]


def _number(row: Dict[str, str], key: str) -> float:
    try:
        return float(row.get(key) or 0)
    except ValueError:
        return 0.0


def summarise(label: str, rows: Rows) -> None:
    staked = sum(_number(r, "stake") for r in rows)
    back = sum(_number(r, "payout") for r in rows)
    won = sum(1 for r in rows if r.get("won") == "1")
    roi = (back - staked) / staked * 100 if staked else 0.0
    print(f"    {label:<10} n={len(rows):<5} won {won:>4} "
          f"({won / len(rows) * 100:5.1f}%)  staked ${staked:>12,.0f}  "
          f"back ${back:>12,.0f}  ROI {roi:+7.1f}%")


def _horse_label(row: Dict[str, str]) -> str:
    return odds_label(int(row["horse"])) if row.get("horse") else "?"


def _by_price(keys) -> List[str]:
    def order(key: str) -> int:
        if key == "EVENS":
            return 1
        return int(key.split("/")[0]) if "/" in key else 99
    return sorted(keys, key=order)


def _breakdowns(graded: Rows) -> None:
    print("\n  by horse backed (break-even win rate is 1/(n+1)):")
    for key in _by_price({_horse_label(r) for r in graded}):
        summarise(key, [r for r in graded if _horse_label(r) == key])

    print("\n  by lane backed:")
    lanes = sorted({r["lane"] for r in graded if r.get("lane")}, key=int)
    for lane in lanes:
        summarise(f"lane {lane}", [r for r in graded if r["lane"] == lane])

    print("\n  by bet size:")
    for flag, label in (("1", "max bet"), ("0", "min skip")):
        group = [r for r in graded if r.get("max_bet") == flag]
        if group:
            summarise(label, group)


def report(path: str = DEFAULT_PATH) -> None:
    rows = load(path)
    if not rows:
        print(f"No log yet at {path} -- it is written as the bot runs.")
        return
    graded = [r for r in rows if r.get("win_lane")]
    runs = {r["run_id"] for r in rows}
    print(path)
    print(f"  {len(rows)} bets over {len(runs)} run(s), "
          f"{len(graded)} with a readable winning lane")
    if not graded:
        print("  Nothing graded yet -- is win_lane_region right? "
              "Check with `result`.")
        return
    print()
    summarise("ALL", graded)
    _breakdowns(graded)
    recent = graded[-50:]
    if len(graded) > len(recent):
        print()
        summarise("last 50", recent)
    what_won(rows)
    ungraded = len(rows) - len(graded)
    if ungraded:
        print(f"\n  {ungraded} bet(s) logged without a result (the winning "
              "lane would not read) -- excluded from every figure above.")


def _tally(board: Rows):
    """(appearances, wins, wins by lane) over every price on every board."""
    appear, won, lanes = {}, {}, {}
    for row in board:
        winner = int(row["win_lane"])
        lanes[winner] = lanes.get(winner, 0) + 1
        for lane in range(1, 7):
            price = int(row[f"odds{lane}"])
            appear[price] = appear.get(price, 0) + 1
        winning_price = int(row[f"odds{winner}"])
        won[winning_price] = won.get(winning_price, 0) + 1
    return appear, won, lanes


def what_won(rows: Rows) -> None:
    board = [r for r in rows if r.get("win_lane")
             and all(r.get(f"odds{i}") for i in range(1, 7))]
    if not board:
        print("\n  No races with a readable winning lane yet. Set "
              "win_lane_region and check it with the `result` command; without "
              "the races we LOSE teach us nothing.")
        return
    appear, won, lanes = _tally(board)
    print(f"\n  what actually wins ({len(board)} races, whatever we bet):")
    print(f"    {'price':<8}{'appeared':>9}{'won':>6}{'win rate':>10}"
          f"{'break-even':>12}{'flat ROI':>10}")
    for price in sorted(appear):
        seen, hits = appear[price], won.get(price, 0)
        print(f"    {odds_label(price):<8}{seen:>9}{hits:>6}"
              f"{hits / seen * 100:>9.1f}%{100.0 / (price + 1):>11.1f}%"
              f"{(hits * (price + 1) - seen) / seen * 100:>9.1f}%")
    print("    flat ROI = backing that price every time it appeared.")
    print("\n  winning lane: "
          + "  ".join(f"{lane}: {lanes.get(lane, 0)}" for lane in range(1, 7))
          + f"   (an even split would be {len(board) / 6:.0f} each)")
