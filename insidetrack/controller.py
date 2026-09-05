"""Press semantics: how long to hold, how long to wait, and how to know a
press actually landed.

Three kinds of press, because they fail differently:
  tap        inside one region of the menu -- cheap and reliable. A 5-lane
             walk landed 5/5 at a 120ms press-to-press cycle.
  tap_edge   across a region boundary, where the UI is animating and the
             next press gets swallowed. This is where drops happen.
  confirm    the ones that change the whole screen. Measured against the
             picture and pressed again if nothing moved.
"""

import ctypes
import random
import time
from typing import Optional

from .config import Band, Timing

VK_SCROLL = 0x91
_user32 = ctypes.WinDLL("user32", use_last_error=True)


def paused() -> bool:
    """ScrollLock's toggle state -- readable without focus, so it works as a
    panic button from whatever window you happen to be using."""
    return bool(_user32.GetKeyState(VK_SCROLL) & 1)


def wait_while_paused() -> None:
    if not paused():
        return
    print("  ScrollLock is on -- paused. Turn it off to resume.")
    while paused():
        time.sleep(0.5)
    print("  resumed")


class Controller:
    """A backend plus the timings that make its presses land."""

    def __init__(self, backend, screen, timing: Timing, dry_run: bool = False):
        self._backend = backend
        self._screen = screen
        self._timing = timing
        self._dry_run = dry_run

    @property
    def backend(self):
        return self._backend

    def gap(self, band: Band) -> float:
        """A jittered delay: the band, plus variance on every gap, plus the
        occasional hesitation. Only ever adds, so no gap can fall under what
        `tune` validated."""
        delay = random.uniform(*band) + random.uniform(*self._timing.variance)
        if random.random() < self._timing.hesitate_chance:
            delay += random.uniform(0.0, 0.5)
        return delay

    def press(self, key: str, hold: Optional[float] = None) -> None:
        if self._dry_run:
            return
        self._backend.press(key, self.gap(self._timing.key_hold)
                            if hold is None else hold)

    def tap(self, key: str) -> None:
        if self._dry_run:
            return
        self.press(key)
        time.sleep(self.gap(self._timing.menu_tap_gap))

    def tap_edge(self, key: str, band: Optional[Band] = None) -> None:
        """A press that moves between regions. The UI animates through those
        and a press arriving mid-animation is swallowed, which desyncs
        everything after it -- so give them room."""
        if self._dry_run:
            return
        self.press(key)
        time.sleep(self.gap(band or self._timing.transition_gap))

    def tap_fast(self, key: str) -> None:
        """Rapid tap for the bet-increase spam: tight jitter, no hesitation."""
        if self._dry_run:
            return
        self.press(key, hold=random.uniform(*self._timing.spam_hold))
        time.sleep(random.uniform(*self._timing.bet_tap_gap))

    def confirm(self, key: str, tries: int = 3,
                budget: Optional[float] = None,
                settle: Optional[float] = None) -> bool:
        """A press that must land. Presses, watches for the picture to
        change, presses again if it did not. This is what stops the bot
        sitting on Place Bet forever because one Cross was swallowed.

        `budget` is the whole attempt -- settle, press and verify -- against
        one deadline instead of three stacked timeouts. A retry gets a fresh
        one, so only a press that genuinely did not land costs more.
        """
        if self._dry_run:
            return True
        budget = self._timing.confirm_budget if budget is None else budget
        settle = self._timing.confirm_settle if settle is None else settle
        for attempt in range(tries):
            if self._attempt(key, budget, settle):
                return True
            print(f"  ({key} did not register, retry {attempt + 2}/{tries})")
        return False

    def _attempt(self, key: str, budget: float, settle: float) -> bool:
        deadline = time.time() + budget
        if settle:
            self._screen.wait_still(min(settle, budget), samples=1)
        base = self._screen.frame()
        self.press(key)
        while time.time() < deadline:
            time.sleep(self._timing.still_poll)
            if self._screen.changed(base, self._screen.frame()):
                return self._stuck(base, deadline)
        return False

    def _stuck(self, base, deadline: float) -> bool:
        """Tell a one-frame flicker from a real screen change -- but only if
        there is budget left for another frame. Out of time, a single seen
        change counts: a second blind press is more expensive than a rare
        false positive, because it lands on whatever screen comes next.

        The deadline governs when polling stops, not the capture in flight,
        so a confirm can run a frame over. That slack is deliberate: the
        round trip to the PS5 and back measured 282ms here, which is most of
        a 0.5s budget already.
        """
        if time.time() >= deadline:
            return True
        return self._screen.changed(base, self._screen.frame())
