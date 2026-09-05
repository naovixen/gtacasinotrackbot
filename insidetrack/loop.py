"""The race cycle: read the board, back a horse, watch the race, log it.

The loop owns the decisions about what happens when something goes wrong.
The rule it is built on: a bet is only ever placed from a screen we have
proved we are on, and anything unproven backs out one screen and starts the
cycle again, because the top of the loop is the thing that comes back in.
"""

import time
from dataclasses import dataclass
from typing import Optional

from .config import Settings
from .controller import wait_while_paused
from .parsing import odds_label
from .racelog import Race
from .strategy import decide, grade

READ_ATTEMPTS = 4


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

    def _announce(self) -> None:
        print(f"Profile {self._settings.profile!r} -- "
              f"dry_run={self._settings.dry_run}")
        if self._settings.dry_run:
            print("DRY RUN: no input will be sent. Open the single-event "
                  "screen by hand so the reads can see the board.")
        if self._settings.board.win_lane_region is None:
            print(f"NOTE: profile {self._settings.profile!r} has no "
                  "win_lane_region, so races are logged without a result.")
        else:
            print(f"Logging every race to {self._log.path} "
                  f"(run {self._log.run_id}).")
        if self._settings.board.result_banner_region is None:
            print(f"NOTE: profile {self._settings.profile!r} has no "
                  "result_banner box, so the end of a race is\n      guessed "
                  "at from the picture going still. Measuring it lets "
                  "race_wait_min\n      come down under the finish -- see "
                  "`python -m insidetrack result`.")
        print("ScrollLock pauses at any time. Starting in 5s...")
        self._machine.ensure_window()
        time.sleep(5)

    def _cycle(self) -> None:
        started = time.time()
        self._machine.ensure_window()
        self._machine.enter_single_event()
        odds, lane, max_bet, reason, trusted = self._read_board()
        if lane is None:
            print("  board still unreadable -> skipping this cycle, "
                  "no bet placed")
            return self._machine.back_out()
        placed, stake = self._machine.place_bet(lane, max_bet)
        if not placed:
            print("  Place Bet never registered -> recovering, "
                  "no race counted")
            return self._machine.back_out()
        race = Race(odds=odds, lane=lane, max_bet=max_bet, reason=reason,
                    trusted=trusted, stake=stake)
        self._run_race(race, started)

    def _read_board(self):
        """Read until a trusted board comes back, recovering once on the way.

        A trusted read is also the proof we are on the betting board at all,
        so two failures in a row mean we are probably somewhere else.
        """
        for attempt in range(READ_ATTEMPTS):
            time.sleep(self._settings.timing.ocr_settle)
            odds, trusted = self._board.read_verified()
            lane, max_bet, reason = decide(odds, self._settings.strategy)
            print(f"[{time.strftime('%H:%M:%S')}] odds={odds} "
                  f"trusted={trusted} -> {reason}")
            if lane is not None and trusted:
                return odds, lane, max_bet, reason, trusted
            if attempt == 1:
                self._machine.recover()
            else:
                print("  bad/untrusted read; retrying")
        return odds, None, False, reason, trusted

    def _run_race(self, race: Race, started: float) -> None:
        self._tally.races += 1
        self._tally.staked += race.stake or 0
        race.race_s, race.settled = self._machine.wait_for_race_end()
        if not race.settled:
            print(f"  (race screen never went still within {race.race_s:.0f}s "
                  "-- pressing on)")
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
            print("  result: UNREADABLE -- logged without a result")
            return
        tally = self._tally
        tally.graded += 1
        tally.graded_stake += race.stake or 0
        tally.returned += payout
        tally.wins += won
        outcome = f"${payout:,} back" if won else "lost"
        print(f"  result: lane {race.win_lane} "
              f"({odds_label(race.odds[race.win_lane - 1])}) won "
              f"-- {outcome} on ${race.stake:,}")

    def _finish(self, race: Race, started: float) -> None:
        if not self._machine.return_to_start():
            # The result screen is still up and the next cycle would start
            # from the wrong place. Circle out; the top of the loop comes
            # back in through enter_single_event().
            print("  BET AGAIN never registered -> backing out to the "
                  "machine start screen")
            self._machine.back_out()
        race.cycle_s = time.time() - started
        self._log.append(race)
        self._report(race)

    def _report(self, race: Race) -> None:
        tally = self._tally
        size = "MAX" if race.max_bet else f"${race.stake:,}"
        print(f"  bet {size} on lane {race.lane} (race #{tally.races})  "
              f"cycle {race.cycle_s:.1f}s (race {race.race_s:.1f}s)  "
              f"rate {tally.rate():.0f} races/h")
        if tally.graded:
            print(f"  session: {tally.wins}/{tally.graded} won, "
                  f"${tally.returned:,} back, net ${tally.net():+,} "
                  f"({tally.net() / tally.graded_stake * 100:+.1f}% ROI) "
                  f"-> ${tally.net() / tally.hours():+,.0f}/h"
                  + (f"   [{tally.races - tally.graded} ungraded]"
                     if tally.races > tally.graded else ""))
