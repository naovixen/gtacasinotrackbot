"""Screen capture and the one question the bot keeps asking the picture:
has it stopped moving?

Everything here works in numpy. The old capture path went through PIL --
Image.frombytes() then a BILINEAR resize -- which measured 84ms per frame on
this window against 33ms for the same grab strided down with numpy. That
frame is the unit of every stillness wait and every confirmed press, so it
set the floor on all of them; a confirm that needs four frames got 200ms
back for free.
"""

import time
from typing import Optional, Tuple

import mss
import numpy as np
import pygetwindow as gw

from .config import Region

# Frame-to-frame difference that counts as "the UI reacted". Measured once
# against the idle stream (the menus animate, so it is not zero) and capped:
# measured mid-animation the bar could otherwise end up so high that nothing
# ever counts as a change. A real screen change measures ~40 here.
_THRESHOLD_CAP = 12.0


class WindowMissing(RuntimeError):
    pass


class Screen:
    """Pixels from one window, by title. Never takes focus."""

    def __init__(self, title: str, downscale: int = 8):
        self._title = title
        self._downscale = downscale
        self._sct = getattr(mss, "MSS", mss.mss)()
        self._threshold: Optional[float] = None

    def window(self):
        wins = [w for w in gw.getAllWindows()
                if self._title.lower() in w.title.lower() and w.width > 200]
        if not wins:
            raise WindowMissing(
                f"No window matching {self._title!r}. Is chiaki-ng "
                "running, visible and not minimised? If its title differs, "
                "set window_title in insidetrack.toml.")
        return wins[0]

    def _shot(self, left: int, top: int, width: int, height: int) -> np.ndarray:
        """BGRA pixels as (h, w, 4) uint8, straight off the screen."""
        shot = self._sct.grab({"left": left, "top": top,
                               "width": width, "height": height})
        buf = np.frombuffer(shot.raw, dtype=np.uint8)
        return buf.reshape(shot.height, shot.width, 4)

    def grab(self, region: Region) -> np.ndarray:
        """One in-window box as RGB (h, w, 3) uint8."""
        win = self.window()
        left, top, width, height = region
        bgra = self._shot(win.left + left, win.top + top, width, height)
        return bgra[:, :, 2::-1]           # BGRA -> RGB

    def grab_window(self) -> np.ndarray:
        win = self.window()
        bgra = self._shot(win.left, win.top, win.width, win.height)
        return bgra[:, :, 2::-1]

    def frame(self) -> np.ndarray:
        """A cheap snapshot of the whole window for motion comparison.

        Strided, not resampled: every 8th pixel is plenty to see a menu
        redraw and costs nothing over the grab itself.
        """
        win = self.window()
        bgra = self._shot(win.left, win.top, win.width, win.height)
        step = self._downscale
        return bgra[::step, ::step, :3].astype(np.int16)

    def difference(self, a: np.ndarray, b: np.ndarray) -> float:
        return float(np.abs(a - b).mean())

    def changed(self, a: np.ndarray, b: np.ndarray,
                threshold: Optional[float] = None) -> bool:
        bar = self.threshold() if threshold is None else threshold
        return self.difference(a, b) > bar

    def threshold(self) -> float:
        """Measured once against the idle stream, then cached."""
        if self._threshold is None:
            self._threshold = self._measure_threshold()
            print(f"  (screen-change threshold {self._threshold:.2f})")
        return self._threshold

    def _measure_threshold(self, samples: int = 6) -> float:
        deltas = []
        prev = self.frame()
        for _ in range(samples):
            time.sleep(0.05)
            cur = self.frame()
            deltas.append(self.difference(prev, cur))
            prev = cur
        floor = max(max(deltas) * 4, sum(deltas) / len(deltas) + 1.5, 2.0)
        return min(floor, _THRESHOLD_CAP)

    def wait_still(self, timeout: float, samples: int = 2,
                   poll: float = 0.02) -> bool:
        """Block until `samples` consecutive frames match, or give up.

        This is the precondition for measuring a press by whether the screen
        changed: while something is animating every frame differs from every
        other one, so a confirm taken mid-animation passes whether or not the
        press landed.
        """
        bar = self.threshold()
        deadline = time.time() + timeout
        prev, still = self.frame(), 0
        while time.time() < deadline:
            time.sleep(poll)
            cur = self.frame()
            still = 0 if self.changed(prev, cur, bar) else still + 1
            prev = cur
            if still >= samples:
                return True
        return False

    def wait_settled(self, timeout: float, samples: int,
                     floor: float, poll: float = 0.02) -> Tuple[float, bool]:
        """Stillness for a screen that was busy: the bar adapts to how much
        motion this particular animation actually showed, but never drops
        below `floor` x the idle noise. Returns (seconds spent, went still).

        Relative alone is not enough -- a camera cut or a long straight is
        quiet in relative terms while the race is still running -- and
        absolute alone is not either, because a busy result screen never gets
        as quiet as an idle menu.
        """
        bar = self.threshold()
        started = time.time()
        prev, peak, still = self.frame(), 0.0, 0
        while time.time() - started < timeout:
            time.sleep(poll)
            cur = self.frame()
            delta = self.difference(prev, cur)
            prev, peak = cur, max(peak, delta)
            still = still + 1 if delta < max(bar * floor, peak * 0.12) else 0
            if still >= samples:
                return time.time() - started, True
        return time.time() - started, False
