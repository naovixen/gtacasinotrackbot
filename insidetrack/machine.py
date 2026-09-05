"""The betting machine as a sequence of screens, and how to walk them.

Each method leaves the game on a screen the next one expects, and says
whether it got there. Nothing here reads a strategy or writes a log.
"""

import time
from typing import Optional, Tuple

from . import console
from .config import (BET_HOLD_SECONDS, BET_INCREASE_MODE, MAX_BET,
                     MAX_BET_PRESSES, MIN_BET, Settings)

# From each lane, Right lands on a different button in the right-hand
# column: lanes 1-3 -> decrease (0 ups); lanes 4-5 -> Place Bet (1 up);
# lane 6 -> Cancel (2 ups).
UPS_TO_DECREASE = {1: 0, 2: 0, 3: 0, 4: 1, 5: 1, 6: 2}


class Machine:
    """Navigation. Owns no state beyond what it was constructed with."""

    def __init__(self, controller, board, screen, settings: Settings):
        self._keys = controller
        self._board = board
        self._screen = screen
        self._settings = settings
        self._timing = settings.timing

    @property
    def dry_run(self) -> bool:
        return self._settings.dry_run

    def ensure_window(self) -> bool:
        """The window must exist and not be minimised -- capture needs real
        pixels. Focus is only taken in keyboard mode, which is the whole
        point of the other two."""
        try:
            window = self._screen.window()
            if window.isMinimized:
                window.restore()
                time.sleep(0.5)
            if self._settings.input_mode == "keyboard":
                self._focus(window)
            return True
        except Exception as error:
            print(console.bad_row(f"window check failed: {error}",
                                  "window"))
        return False

    @staticmethod
    def _focus(window) -> None:
        import pydirectinput
        pydirectinput.press("alt")      # allow foreground change on Windows
        window.activate()
        time.sleep(0.7)

    def enter_single_event(self) -> bool:
        """From the machine's start screen: Right hovers the single-event
        button, Cross opens it."""
        self._keys.tap("right")
        return self._keys.confirm("cross")

    def spam_increase(self, presses: int = MAX_BET_PRESSES) -> None:
        if self.dry_run:
            return
        if BET_INCREASE_MODE == "hold":
            self._keys.press("cross", hold=BET_HOLD_SECONDS)
        else:
            for _ in range(presses):
                self._keys.tap_fast("cross")
        time.sleep(0.3)         # let the displayed amount settle before a read

    def verify_max_amount(self) -> Optional[int]:
        """Closed-loop check that the bet reached $10,000, correcting the two
        known slips. Returns the amount finally showing, or None."""
        if self.dry_run or self._settings.board.bet_amount_region is None:
            return None
        for _ in range(2):
            amount = self._board.read_bet_amount()
            if amount is None:
                print(console.warn_row(
                    "bet amount unreadable -- proceeding unverified",
                    "stake"))
                return None
            if amount >= MAX_BET:
                return amount
            self._top_up(amount)
        amount = self._board.read_bet_amount()
        if amount is not None and amount < MAX_BET:
            print(console.bad_row(
                f"could not reach max -- placing at {amount:,}", "stake"))
        return amount

    def _top_up(self, amount: int) -> None:
        if amount <= MIN_BET:
            print(console.warn_row(
                f"at {amount:,}: Right into increase was eaten -- correcting",
                "stake"))
            self._keys.tap("right")
        else:
            print(console.warn_row(
                f"at {amount:,}: some taps eaten -- topping up", "stake"))
        self.spam_increase()

    def place_bet(self, lane: int, max_bet: bool) -> Tuple[bool, int]:
        """From the single-event screen with nothing selected, to a bet on
        the table. Returns (it went on, stake) -- the stake read back off the
        screen where that is possible, so the log records what was really bet
        rather than what was intended."""
        self._select_horse(lane)
        stake = self._set_stake(max_bet)
        # Bet row -> Place Bet: a region change, but the quiet one. The menu
        # has been static since the amount was read off it, so this crossing
        # gets its own gap and can come down without loosening the earlier
        # ones, which happen mid-animation.
        self._keys.tap_edge("down", self._timing.place_bet_gap)
        placed = self._keys.confirm("cross",
                                    settle=self._timing.place_bet_settle)
        return placed, stake

    def _select_horse(self, lane: int) -> None:
        self._keys.tap_edge("left")          # cursor comes in at lane 6
        for _ in range(6 - lane):
            self._keys.tap("up")             # walking within the lane list
        self._keys.tap_edge("cross")         # select; the bet panel redraws
        self._keys.tap_edge("right")         # horse column -> bet column
        for _ in range(UPS_TO_DECREASE[lane]):
            self._keys.tap("up")             # -> decrease-bet button

    def _set_stake(self, max_bet: bool) -> int:
        if max_bet:
            self._keys.tap("right")          # -> increase-bet button
            self.spam_increase()
            return self.verify_max_amount() or MAX_BET
        if self.dry_run:
            return MIN_BET
        return self._board.read_bet_amount() or MIN_BET

    def wait_for_race_end(self) -> Tuple[float, bool]:
        """Wait out the race and return once the result is on screen:
        (seconds spent, whether the result really arrived rather than the
        wait timing out).

        Two ways of deciding, and which one is used depends on whether the
        screen profile has a result_banner box.

        With one the banner itself is the signal, and the floor is
        banner_wait_min -- which is not a guess at when the race ends, only a
        point safely past the screens between placing the bet and the race
        starting. The banner says when.

        Without one it falls back to stillness, which is the flaky thing this
        replaced: the camera holds on the horses for anywhere from half a
        second to three after the finish, so a quiet-frames test either fires
        on that hold or has to have race_wait_min pushed out past the worst
        case. Every race then paid for the worst case, every time.
        """
        if self.dry_run:
            return 0.0, True
        if self._board.can_see_result_screen:
            floor = self._timing.banner_wait_min
            time.sleep(floor)
            return self._wait_for_banner(floor)
        floor = self._timing.race_wait_min
        time.sleep(floor)
        spent, settled = self._screen.wait_settled(
            timeout=self._timing.race_wait_max - floor,
            samples=self._timing.race_still_samples, floor=2.0,
            poll=self._timing.still_poll)
        return floor + spent, settled

    def _wait_for_banner(self, floor: float) -> Tuple[float, bool]:
        """Poll for the result screen's title banner, and return the moment
        it is up.

        Nothing waits for the screen to settle afterwards. The cards, the
        prices and the banner all arrive together, so there is nothing to
        settle for -- and a stillness check here was worse than useless: the
        chip counter ticks up on this screen, so two consecutive quiet frames
        often never came and the wait ran to its whole cap. If a lane number
        ever is caught mid-draw, read_win_lane already asks again.

        Two matching frames rather than one: a check costs about 7ms, so the
        second is cheap insurance against a single odd frame -- a compression
        artefact, or a grab caught mid-fade.
        """
        timing = self._timing
        started = time.time()
        deadline = started + (timing.race_wait_max - floor)
        matched = 0
        while time.time() < deadline:
            matched = matched + 1 if self._board.sees_result_screen() else 0
            if matched >= timing.result_frames:
                return floor + (time.time() - started), True
            time.sleep(timing.result_poll)
        print(console.warn_row("no RESULTS banner in the result box -- "
                               "check it with `insidetrack result`",
                               "banner"))
        return floor + (time.time() - started), False

    def return_to_start(self) -> bool:
        """After the result: Down then Cross selects BET AGAIN, returning to
        the machine start screen.

        The result screen is usually still animating when the race wait ends,
        and a press arriving mid-animation is swallowed -- which is how a
        cycle ends parked on the result screen instead of betting again. So
        it settles first, and this is the settle the confirmed presses lean
        on now that they no longer each carry their own. No extra Downs on
        the retries: the highlight is already in the button row and walking
        it again risks moving off the button.
        """
        if self.dry_run:
            return True
        self._screen.wait_still(timeout=5.0, samples=3,
                                poll=self._timing.still_poll)
        self._keys.tap_edge("down")          # into the button row
        return self._keys.confirm("cross", tries=4)

    def back_out(self, steps: int = 1) -> None:
        """Circle back one screen, to the machine's start screen.

        This used to fire three unconfirmed Circles, on the theory that spare
        presses were free insurance. They are not: the betting board is a
        single Circle from the start screen, so the second press walked the
        player out of the machine and the third into the open world, and
        nothing downstream can recover from that.

        The two errors are not symmetrical. Backing out too far is
        unrecoverable; not far enough is self-correcting, because the board
        read at the top of the loop fails and brings us straight back here.
        So press once, confirmed -- which retries only when the screen did
        not react, the insurance the three blind Circles were reaching for.
        """
        for _ in range(steps):
            self._keys.confirm("circle")
        time.sleep(0.5)

    def recover(self) -> None:
        """Back out to a known screen and come in again, rather than pressing
        on blind -- which is how a desync becomes a bet on the wrong horse.

        Only for the retry inside the read loop. Paths that start the cycle
        over must call back_out() alone: the top of the loop does its own
        enter_single_event(), and entering twice puts a Right and a Cross
        into the board instead of the start screen."""
        print(console.warn_row(
            "backing out to the machine start screen", "recover"))
        self.back_out()
        self.enter_single_event()
