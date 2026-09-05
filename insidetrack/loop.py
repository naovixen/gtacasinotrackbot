"""The race cycle: read the board, back a horse, watch the race, log it.

The loop owns the decisions about what happens when something goes wrong.
The rule it is built on: a bet is only ever placed from a screen we have
proved we are on, and anything unproven backs out one screen and starts the
cycle again, because the top of the loop is the thing that comes back in.

What it prints goes on the grid in `console` -- see the note there. The
layout it produces:

    time      lane     1       2       3       4       5       6
    21:04:12  board    EVENS   5/1     13/1    4/1     26/1    20/1
              bet      lane 1  EVENS   MAX     10,000
              result   lane 1  EVENS   WON     +10,000
              session  1/1 won                 +10,000
              session  37.4s/r    +100.0% ROI  +374,000/h

`bet` and `result` share their cells deliberately: what we backed sits
directly above what won, so whether they match is a matter of the two lines
looking the same rather than of reading either of them.

The settings the run starts with are NOT on this grid -- see `app.preflight`.
They are read once rather than scanned, and a line per setting beats a table
of one row each.
"""

import time
from dataclasses import dataclass
from typing import Optional

from . import console
from .config import PROFIT_PER_RACE, Settings
from .controller import wait_while_paused
from .parsing import odds_label
from .racelog import Race
from .strategy import decide, grade

READ_ATTEMPTS = 4

# The two fields before the money on the session's second line, in the order
# they print: seconds per race, then ROI. They add up to three cells on
# purpose -- the same three that `4/7 won` spans on the line above -- so the
# hourly rate lands in the same column as the running net and the two money
# figures read down as one. 11 + 13 is the split of 24 that leaves ROI its
# two-space gap; `s/r` is short enough to spend the slack on the decimal.
CYCLE_W = 11        # '37.4s/r'
ROI_W = 13          # '+100.0% ROI'


def _board_row(odds, chosen: Optional[int]) -> str:
    """The six prices as prices, in grid cells, the backed one picked out.

    `odds=[1, 4, 7, 3, 12, 2]` was the raw list, which meant reading it as
    numbers and translating -- and the lane that mattered was wherever you
    counted to. Fixed cells put lane 6 in the same place on every line.
    """
    labels = []
    for lane, value in enumerate(odds, start=1):
        label = odds_label(value)
        if value is None:
            label = console.bad(label)
        elif lane == chosen:
            label = console.paint(label, "bold", "cyan")
        labels.append(label)
    return console.cells(*labels)


def _header() -> str:
    """Names the board row's six cells once. The other rows label themselves
    -- `lane 4`, `EVENS`, `WON` -- so only the positional ones need it."""
    return console.row("lane", console.cells(*"123456"), stamp="time")


@dataclass
class Tally:
    """What this run has done so far. Only graded races have a return, so
    ROI is measured over what they staked -- mixing in ungraded stakes would
    fake a loss."""

    races: int = 0
    staked: int = 0
    graded: int = 0
    graded_stake: int = 0
    returned: int = 0
    wins: int = 0
    started: float = 0.0

    def hours(self) -> float:
        return max(1e-9, (time.time() - self.started) / 3600)

    def rate(self) -> float:
        return self.races / self.hours()

    def net(self) -> int:
        return self.returned - self.graded_stake


class Bot:
    """One run of the bot: the composition of everything else."""

    def __init__(self, settings: Settings, screen, board, machine, log):
        self._settings = settings
        self._screen = screen
        self._board = board
        self._machine = machine
        self._log = log
        self._tally = Tally()

    def run(self) -> None:
        self._announce()
        self._tally.started = time.time()
        while True:
            wait_while_paused()
            self._cycle()

    # ----------------------------------------------------------------------
    # Printing. Everything goes through console.row(), so the grid holds.

    def _announce(self) -> None:
        self._machine.ensure_window()
        # Measure the screen-change bar HERE, on a screen that is sitting
        # still, and not inside the first confirmed press. It costs six
        # frames -- a whole confirm budget -- so whichever press triggered
        # it used to run out of time and report a failure, every first
        # cycle; and it was measuring that press's own animation, which is
        # the opposite of the idle stream the bar is supposed to describe.
        if not self._settings.dry_run:
            self._screen.threshold()
        print(_header())
        time.sleep(5)

    # ----------------------------------------------------------------------

    def _cycle(self) -> None:
        started = time.time()
        self._machine.ensure_window()
        self._machine.enter_single_event()
        odds, lane, max_bet, reason, trusted = self._read_board()
        if lane is None:
            print(console.bad_row(
                "board unreadable -- no bet placed this cycle"))
            return self._machine.back_out()
        placed, stake = self._machine.place_bet(lane, max_bet)
        if not placed:
            print(console.bad_row("Place Bet never registered -- recovering, "
                                  "no race counted"))
            return self._machine.back_out()
        self._bet_row(lane, odds[lane - 1], max_bet, stake)
        race = Race(odds=odds, lane=lane, max_bet=max_bet, reason=reason,
                    trusted=trusted, stake=stake)
        self._run_race(race, started)

    def _read_board(self):
        """Read until a trusted board comes back, recovering once on the way.

        A trusted board is also the proof we are on the betting board at all,
        so two failures in a row mean we are probably somewhere else.
        """
        for attempt in range(READ_ATTEMPTS):
            time.sleep(self._settings.timing.ocr_settle)
            odds, trusted = self._board.read_verified()
            lane, max_bet, reason = decide(odds, self._settings.strategy)
            # No reason printed on a good read: it says the same thing every
            # race, and the bet row underneath already names the lane and the
            # price it chose.
            print(console.row("board",
                              _board_row(odds, lane if trusted else None),
                              stamp=time.strftime("%H:%M:%S")))
            if lane is not None and trusted:
                return odds, lane, max_bet, reason, trusted
            print(console.warn_row(
                "untrusted read -- reading the board again"))
            if attempt == 1:
                self._machine.recover()
        return odds, None, False, reason, trusted

    def _bet_row(self, lane: int, price, max_bet: bool, stake: int) -> None:
        size = console.key("MAX") if max_bet else console.warn("MIN")
        print(console.row("bet", console.cells(
            f"lane {lane}", odds_label(price), size)
            + console.money(stake)))

    def _run_race(self, race: Race, started: float) -> None:
        self._tally.races += 1
        self._tally.staked += race.stake or 0
        race.race_s, race.settled = self._machine.wait_for_race_end()
        if not race.settled:
            print(console.warn_row(
                f"no result within {race.race_s:.0f}s -- pressing on"))
        # Grade BEFORE anything is pressed: once BET AGAIN goes in, the
        # winning lane is gone. A lane that cannot be read is left blank in
        # the log rather than guessed at -- a missed read and a lost bet are
        # not the same thing once you start fitting numbers to this.
        race.win_lane = self._read_result()
        self._score(race)
        self._finish(race, started)

    def _read_result(self) -> Optional[int]:
        if self._settings.dry_run:
            return None
        return self._board.read_win_lane()[0]

    def _score(self, race: Race) -> None:
        won, payout = grade(race.odds, race.lane, race.stake, race.win_lane)
        if won is None:
            print(console.row("result",
                              console.cells("--", "--", console.warn("??"))))
            print(console.warn_row(
                "winning lane unreadable -- logged without a result"))
            return
        tally = self._tally
        tally.graded += 1
        tally.graded_stake += race.stake or 0
        tally.returned += payout
        tally.wins += won
        # The verdict and what it made are one fact, so they carry one colour
        # between them rather than two competing for the line.
        tint = console.good if won else console.bad
        profit = payout - (race.stake or 0)
        print(console.row("result", console.cells(
            f"lane {race.win_lane}",
            odds_label(race.odds[race.win_lane - 1]),
            tint("WON" if won else "LOST"))
            + tint(f"{'+' if profit >= 0 else '-'}{abs(profit):,}")))

    def _finish(self, race: Race, started: float) -> None:
        if not self._machine.return_to_start():
            # The result screen is still up and the next cycle would start
            # from the wrong place. Circle out; the top of the loop comes
            # back in through enter_single_event().
            print(console.bad_row(
                "BET AGAIN never registered -- backing out to the machine "
                "start screen"))
            self._machine.back_out()
        race.cycle_s = time.time() - started
        self._log.append(race)
        self._session_rows(race)

    def _session_rows(self, race: Race) -> None:
        """Two lines, because they answer two questions.

        The first ends on the running net, in the cell the race's own profit
        was just printed in, so a screenful of results and the total they add
        up to read down as one column. The second is the rates, which are
        worth a glance a minute rather than a glance a race.
        """
        tally = self._tally
        if not tally.graded:
            return
        won = f"{tally.wins}/{tally.graded} won"
        print(console.row("session", console.cells((won, 3))
                          + console.money(tally.net(), signed=True)))
        roi = tally.net() / tally.graded_stake * 100
        # Throughput in the units it is actually worth. Races an hour is a
        # number you then have to do arithmetic on; this is that arithmetic,
        # at the average a race returns under the validated strategy. It is
        # what the rate IMPLIES rather than what this session has made --
        # the realised figure is the net on the line above, and over a few
        # dozen races that one is mostly variance.
        expected = round(tally.rate() * PROFIT_PER_RACE, -3)
        # End to end, not the race alone. The race is the part nothing can
        # do anything about; the cycle is the number a change to the timings
        # or the waits actually moves, and it is what the rate is made of.
        aside = (console.pad(f"{race.cycle_s:.1f}s/r", CYCLE_W)
                 + console.pad(f"{roi:+.1f}% ROI", ROI_W)
                 + f"{expected:+,.0f}/h")
        print(console.row("session", console.note(aside.rstrip())))
        print()
