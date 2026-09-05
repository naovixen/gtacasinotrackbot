"""`tune`: a minute's confidence check on the timings, against the real menu.

Park chiaki-ng on the single-event board with a horse highlighted. Only
Up/Down are sent -- no confirm, so no bet can be placed. It measures the two
things that actually break: that a multi-lane walk lands where it was aimed,
and that a press arriving straight after a region change is not swallowed.

An earlier full sweep found hold length irrelevant (20ms registered as
reliably as 220ms) and a 5-lane walk correct at every cycle down to 120ms,
which is why this no longer sweeps them.
"""

import time
from typing import List, Optional

import numpy as np

from .app import App

PARK, AWAY = "up", "down"


class Tuner:
    """Drives the menu with the live timings and scores what the screen did."""

    def __init__(self, app: App):
        self._app = app
        self._keys = app.keys
        self._screen = app.screen
        self._timing = app.settings.timing
        self._threshold = 0.0
        self._references: List[np.ndarray] = []

    def run(self) -> None:
        self._banner()
        self._threshold = self._noise_floor()
        latency = self._latency()
        if latency is None:
            print("  !! nothing is reaching chiaki-ng. Wrong screen, wrong "
                  "window, or\n     the input mode is not working -- run "
                  "`keys` first.")
            return
        print(f"  input->screen round trip: median {latency * 1000:.0f}ms")
        if not self._learn_lanes():
            return
        walk = self._walk_test()
        self._crossing_test()
        self._park()
        self._verdict(walk)

    def _banner(self) -> None:
        print("TUNE -- put chiaki-ng on the single-event board with a horse")
        print("highlighted. Only Up/Down are sent; no bet can be placed.")
        print("Starting in 5s...\n")
        time.sleep(5)

    def _step(self, key: str, times: int, gap: Optional[float] = None) -> None:
        for _ in range(times):
            self._keys.press(key)
            time.sleep(self._keys.gap(self._timing.menu_tap_gap)
                       if gap is None else gap)

    def _park(self) -> None:
        self._step(PARK, 7, gap=0.32)
        time.sleep(0.45)

    def _noise_floor(self) -> float:
        deltas = []
        previous = self._screen.frame()
        for _ in range(8):
            time.sleep(0.15)
            current = self._screen.frame()
            deltas.append(self._screen.difference(previous, current))
            previous = current
        threshold = max(max(deltas) * 4, sum(deltas) / len(deltas) + 1.5)
        print(f"  stream noise floor {sum(deltas) / len(deltas):.3f}"
              f"  -> change threshold {threshold:.3f}")
        return threshold

    def _latency(self) -> Optional[float]:
        """How long a press takes to show up on screen. This is the number
        the confirm budget has to cover."""
        self._park()
        seen = []
        for _ in range(3):
            base = self._screen.frame()
            started = time.time()
            self._keys.press(AWAY, hold=0.18)
            while time.time() - started < 1.5:
                if self._screen.changed(base, self._screen.frame(),
                                        self._threshold):
                    seen.append(time.time() - started)
                    break
            time.sleep(0.4)
            self._step(PARK, 1, gap=0.35)
        return sorted(seen)[len(seen) // 2] if seen else None

    def _learn_lanes(self) -> bool:
        """A reference frame per lane, so a walk can be scored by where it
        actually landed rather than by whether anything moved."""
        self._references = []
        for lanes_down in range(6):
            self._park()
            self._step(AWAY, lanes_down, gap=0.38)
            time.sleep(0.5)
            self._references.append(self._screen.frame())
        separation = min(
            self._screen.difference(self._references[i], self._references[j])
            for i in range(6) for j in range(i + 1, 6))
        if separation < self._threshold:
            print(f"  !! lanes are not visually distinct (separation "
                  f"{separation:.3f}). Is the window\n     obscured, or is "
                  "this the wrong screen?")
            return False
        return True

    def _landed(self) -> int:
        current = self._screen.frame()
        return min(range(6), key=lambda i: self._screen.difference(
            self._references[i], current))

    def _walk_test(self) -> List[int]:
        band = self._timing.menu_tap_gap
        print(f"\n  5-lane walk at the current pacing (gap "
              f"{band[0] * 1000:.0f}-{band[1] * 1000:.0f}ms):")
        landings = []
        for _ in range(4):
            self._park()
            time.sleep(0.4)
            self._step(AWAY, 5)
            time.sleep(0.5)
            landings.append(self._landed())
        verdict = "ok" if all(x == 5 for x in landings) else "DROPPING PRESSES"
        print(f"    landed {landings}  (want [5, 5, 5, 5])   {verdict}")
        return landings

    def _crossing_test(self) -> None:
        """The press that arrives right after a region change -- the failure
        the transition_gap exists to cover."""
        band = self._timing.transition_gap
        print(f"\n  first press after a region change, at transition_gap "
              f"{band[0] * 1000:.0f}-{band[1] * 1000:.0f}ms:")
        for label, gap in (("menu_tap_gap", sum(self._timing.menu_tap_gap) / 2),
                           ("transition_gap", sum(band) / 2)):
            hits = self._crossing_trials(gap)
            print(f"    {label:<15} waiting {gap * 1000:>4.0f}ms after it: "
                  f"{hits}/4 registered   "
                  f"{'ok' if hits == 4 else 'SWALLOWED'}")

    def _crossing_trials(self, gap: float, trials: int = 4) -> int:
        hits = 0
        for _ in range(trials):
            self._park()
            time.sleep(0.4)
            self._keys.press(AWAY)          # the region-change press stand-in
            time.sleep(gap)
            base = self._screen.frame()
            self._keys.press(AWAY)          # the one that tends to get eaten
            time.sleep(0.55)
            hits += int(self._screen.changed(base, self._screen.frame(),
                                             self._threshold))
        return hits

    @staticmethod
    def _verdict(walk: List[int]) -> None:
        print("\n  " + "-" * 62)
        if all(x == 5 for x in walk):
            print("  These timings walk lanes correctly here.")
        else:
            print("  These timings are dropping presses. Raise "
                  "transition_gap in config.py\n  first -- the press after a "
                  "region change is where the drops happen --\n  then "
                  "menu_tap_gap.")


def tune(app: App) -> None:
    Tuner(app).run()
