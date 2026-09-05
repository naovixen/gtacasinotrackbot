"""Screen profiles, timings and run settings.

Everything here is data: no capture, no input, no OCR. The rest of the
package takes what it needs as constructor arguments, so a profile or a set
of timings can be swapped for a test without touching a global.

The boxes themselves are NOT here any more. They are pixel coordinates in
one particular window at one particular size, so hard-coding them meant
every new setup started by editing source. They come out of the user's own
`insidetrack.toml` instead -- see `userconfig`, and
`python -m insidetrack setup`, which measures them by asking you to point at
them on screen.
"""

from dataclasses import dataclass, field
from typing import Mapping, Optional, Sequence, Tuple

Region = Tuple[int, int, int, int]      # (left, top, width, height) in-window
Band = Tuple[float, float]              # a jittered delay, seconds

DEFAULT_WINDOW_TITLE = "chiaki"


@dataclass(frozen=True)
class Profile:
    """The boxes for one screen layout, measured off its own calibrate.png.

    bet_amount_region enables max-bet verification; win_lane_region enables
    result grading. Either may be None on a screen not measured for it yet.
    """

    odds_regions: Sequence[Region]
    bet_amount_region: Optional[Region] = None
    win_lane_region: Optional[Region] = None


@dataclass(frozen=True)
class Timing:
    """One set of numbers, trimmed against what `tune` measured here.

    Ranges are jittered per press; `variance` adds a further 0-50ms to every
    navigation gap, so no two cycles run to the same clock. It only ever adds
    delay, so it cannot push a gap under the band `tune` validated.

    If navigation starts desyncing, raise transition_gap first -- the press
    after a region change is where drops actually happen -- then menu_tap_gap.
    """

    menu_tap_gap: Band = (0.05, 0.06)     # between presses inside one region
    transition_gap: Band = (0.4, 0.5)     # after a press that changes region
    bet_tap_gap: Band = (0.065, 0.07)     # between bet-increase taps
    place_bet_gap: Band = (0.2, 0.3)      # bet row -> Place Bet: a crossing,
                                          # but a quiet one (the amount has
                                          # just been read off a static menu)
    key_hold: Band = (0.050, 0.075)       # `tune` found 20ms as reliable as
                                          # 220ms: hold is not the lever it
                                          # looks like
    spam_hold: Band = (0.036, 0.050)      # with bet_tap_gap, ~86ms per tap
    variance: Band = (0.0, 0.05)          # extra jitter on EVERY nav gap
    hesitate_chance: float = 0.0          # occasional extra 0-0.5s nav pause

    confirm_budget: float = 0.5           # whole tap_confirm attempt: settle,
                                          # press and verify. A retry gets a
                                          # fresh one. See inputs.Controller.
    confirm_settle: float = 0.0           # stillness wait before a confirmed
                                          # press; 0 leans on the caller's own
    place_bet_settle: float = 0.0         # that one press, if it ever needs it

    still_poll: float = 0.02              # sleep between stillness frames. A
                                          # frame costs ~33ms to capture, so
                                          # this is nearly the whole cadence
    still_samples: int = 2                # quiet frames that mean "stopped"

    race_wait_min: float = 32.0           # never look for the result before
    race_wait_max: float = 45.0           # give up waiting for stillness. A
                                          # cap, not a speed knob
    race_still_samples: int = 3           # the result screen gets one more
                                          # than a menu: a camera cut mid-race
                                          # can be quiet for two frames
    ocr_settle: float = 0.0
    double_read: bool = False             # second board read even when the
                                          # first one is confident


@dataclass(frozen=True)
class Settings:
    """What a single run was asked to do.

    `screens` is whatever the config file defined; `profile` picks one of
    them. Both travel together so nothing downstream has to reach back into
    a module global to find out where the odds are.
    """

    profile: str = "main"
    screens: Mapping[str, Profile] = field(default_factory=dict)
    window_title: str = DEFAULT_WINDOW_TITLE
    strategy: str = "pickorder"           # "pickorder" (validated) | "chart"
    input_mode: str = "postmessage"       # "postmessage" | "gamepad" | "keyboard"
    post_target_index: Optional[int] = None   # None = top-level chiaki window
    dry_run: bool = False
    debug_save: bool = False
    timing: Timing = field(default_factory=Timing)

    @property
    def board(self) -> Profile:
        try:
            return self.screens[self.profile]
        except KeyError:
            known = ", ".join(sorted(self.screens)) or "(none)"
            raise KeyError(
                f"no screen {self.profile!r} in the config; it has {known}. "
                "Run `python -m insidetrack setup`.") from None


# Betting. 100 -> 1000 in 100s (9 presses), 1000 -> 10000 in 500s (18) = 27,
# plus one spare; the increase caps at $10,000 so an extra press is free.
MIN_BET = 100
MAX_BET = 10_000
MAX_BET_PRESSES = 28
BET_INCREASE_MODE = "tap"      # "tap" | "hold" (one long press, menu repeats)
BET_HOLD_SECONDS = 3.0

CONF_TRUST = 0.55              # min per-lane OCR confidence to bet real money
RECHECK_CONF = 0.80            # below this, spend a second confirming read

# Written into the race log's `timing` column, so a change of numbers is
# visible in the record afterwards.
TIMING_NAME = "trimmed"
