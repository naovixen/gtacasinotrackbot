"""The commands that are not `run`: look at the screen, look at the input
path, and model what the timings cost.
"""

import time

from PIL import Image, ImageDraw

from . import console
from .app import App
from .backends import PostMessageBackend, post_key
from .config import (BET_HOLD_SECONDS, BET_INCREASE_MODE, MAX_BET_PRESSES,
                     PROFIT_PER_RACE, TIMING_NAME, Timing)
from .parsing import odds_label
from .strategy import decide

# What each stage of a cycle costs now, measured on this machine rather than
# guessed: a strided frame capture, one recognition pass over the six stacked
# lane boxes (against 1041ms when every lane went through the detector), and
# a confirmed press that stops at its own budget.
FRAME_S = 0.033
BOARD_READ_S = 0.20
MONEY_READ_S = 0.12
DIGIT_READ_S = 0.04         # measured: one read_win_lane that lands first try
BANNER_CHECK_S = 0.008      # measured: one sees_result_screen, grab included
CONFIRM_S = 0.5


def window_shot(app: App) -> Image.Image:
    return Image.fromarray(app.screen.grab_window())


def probe(app: App) -> None:
    """Save calibrate.png (what the window looks like) and probe.png (the
    same with this profile's boxes drawn on). Run it on the betting board to
    check the odds boxes, and again on a result screen for the win lane."""
    app.machine.ensure_window()
    time.sleep(1.0)
    window = app.screen.window()
    image = window_shot(app)
    image.save("calibrate.png")
    _draw_boxes(image, app.settings.board)
    image.save("probe.png")
    print(console.head(f"Profile {app.settings.profile!r}")
          + f": {window.title!r} at {window.width}x{window.height}")
    print("  calibrate.png -- plain capture, measure new boxes off this one")
    print("  probe.png     -- red on the six odds, blue on the bet amount, "
          "yellow on the win\n                   lane, green on the RESULTS "
          "banner")


def _draw_boxes(image: Image.Image, profile) -> None:
    draw = ImageDraw.Draw(image)
    for index, region in enumerate(profile.odds_regions, start=1):
        _box(draw, region, f"lane {index}", (255, 0, 0))
    _box(draw, profile.bet_amount_region, "bet amount", (0, 80, 255))
    _box(draw, profile.win_lane_region, "win lane", (255, 200, 0))
    _box(draw, profile.result_banner_region, "result banner", (0, 220, 80))


def _box(draw: ImageDraw.ImageDraw, region, label: str, colour) -> None:
    if not region:
        return
    left, top, width, height = region
    draw.rectangle([left, top, left + width, top + height],
                   outline=colour, width=3)
    draw.text((left + 4, max(0, top - 16)), label, fill=colour)


def read_board(app: App) -> None:
    """One verified board read, and what the strategy would do with it."""
    app.machine.ensure_window()
    time.sleep(1.0)
    started = time.time()
    odds, trusted = app.board.read_verified(verbose=True)
    print("Result, lanes 1-6:", [odds_label(value) for value in odds],
          " trusted=" + (console.good("True") if trusted
                         else console.bad("False")),
          console.note(f"({time.time() - started:.2f}s)"))
    print(console.head("Decision:"), decide(odds, app.settings.strategy))


def read_result(app: App) -> None:
    """One read of the result screen: who won, and whether the bot would
    have known it was looking at a result screen at all."""
    app.machine.ensure_window()
    time.sleep(1.0)
    _report_banner(app)
    if app.settings.board.win_lane_region is None:
        print(f"Screen {app.settings.profile!r} has no win_lane box. "
              "Measure it with `python -m insidetrack setup --screen "
              f"{app.settings.profile}` on a result screen, or add "
              "win_lane to that screen in insidetrack.toml.")
        return
    started = time.time()
    lane, raw = app.board.read_win_lane()
    if lane is None:
        print(console.bad("win lane: UNREADABLE") + f" (raw {raw!r})")
        print(console.note("  the box should hold just the winning horse's "
                           "number; check probe.png"))
        print(console.note("  against a result screen."))
    else:
        print(f"win lane: {console.key(str(lane))}")
    print(console.note(f"({time.time() - started:.2f}s)"))


def _report_banner(app: App) -> None:
    """What the result-screen matcher makes of what is on screen now.

    Run it on a result screen and it should say MATCHES; run it on the
    betting board and it should not. Both halves matter -- a box that
    matches everything ends the race wait the moment it starts looking.
    """
    if app.settings.board.result_banner_region is None:
        print(f"Screen {app.settings.profile!r} has no result_banner box, so "
              "the race wait falls back\nto watching for the picture to go "
              "still -- which the camera holding on the\nhorses after the "
              "finish makes flaky, and which is why race_wait_min has to\nbe "
              "generous. Measure it with `python -m insidetrack setup "
              f"--screen\n{app.settings.profile}` on a result screen.\n")
        return
    dark, yellow, matched = app.board.result_signature()
    verdict = (console.good("MATCHES") if matched else console.bad("no match"))
    print(f"result banner: {verdict}  "
          + console.note(f"({dark:.0%} near-black, {yellow:.0%} yellow)"))


def keys(app: App) -> None:
    """Send Right/Right/Left/Left to each candidate window in turn, so you
    can see which HWND chiaki-ng actually listens on."""
    backend = app.keys.backend
    if not isinstance(backend, PostMessageBackend):
        print(f"Input mode is {backend.name!r}; this only applies to "
              "postmessage.")
        return
    targets = backend.targets()
    print(f"Found {len(targets)} candidate window(s):\n")
    for index, (hwnd, label) in enumerate(targets, start=1):
        print(f"  [{index}] hwnd={hwnd}  {label}")
    print("\nWatch the chiaki-ng window WITHOUT clicking on it -- click "
          "somewhere else first, so a pass only counts if it works "
          "unfocused.\n")
    for index, (hwnd, label) in enumerate(targets, start=1):
        print(f"  -> testing [{index}] {label}")
        for key in ("right", "right", "left", "left"):
            post_key(hwnd, key, 0.05)
            time.sleep(0.25)
        time.sleep(1.5)
    print("\nWhichever index moved the PS5 cursor: put that number in "
          "insidetrack.toml as\n  post_target_index = <number>   "
          "(0, or leaving it out, means [1] -- the top-level window).\n"
          "If none of them worked, set input_mode = \"gamepad\" there "
          "instead -- see the README.")


def _navigation_cost(timing: Timing) -> float:
    """Eight region crossings, ~5.5 ordinary taps, three confirmed presses."""
    hold = _mid(timing.key_hold)
    jitter = _mid(timing.variance)
    plain = hold + _mid(timing.menu_tap_gap) + jitter
    edge = hold + _mid(timing.transition_gap) + jitter
    place = hold + _mid(timing.place_bet_gap) + jitter
    return 7 * edge + place + 5.5 * plain + 3 * CONFIRM_S


def _spam_cost(timing: Timing) -> float:
    if BET_INCREASE_MODE == "hold":
        return BET_HOLD_SECONDS + 0.3
    per_tap = _mid(timing.spam_hold) + _mid(timing.bet_tap_gap)
    return MAX_BET_PRESSES * per_tap + 0.3


def _ocr_cost(timing: Timing) -> float:
    boards = 2.0 if timing.double_read else 1.3    # weak lanes get a recheck
    return (timing.ocr_settle + boards * BOARD_READ_S
            + MONEY_READ_S + DIGIT_READ_S)


def _race_cost(timing: Timing, banner: bool) -> float:
    """The floor, plus whatever ends the wait.

    The banner path's floor is only a guard against the pre-race screens, so
    what it really costs is the rest of the race -- which this cannot know,
    and which the log has instead. Modelled here as the poll that catches
    the banner and the one that confirms it. Without a banner box the floor
    has to clear the pause after the finish as well, and that part is not
    measurable in advance either.
    """
    if banner:
        return (timing.banner_wait_min
                + (timing.result_poll + BANNER_CHECK_S) * 1.5)
    return timing.race_wait_min + timing.race_still_samples * FRAME_S + 0.2


def _mid(band) -> float:
    return sum(band) / 2


def budget(app: App) -> None:
    """Model the cycle time from the current timings. The strategy is worth
    ~$4,900 a race; whether that lands in the 500-800k/h band is entirely a
    question of how many races an hour this loop manages."""
    timing = app.settings.timing
    banner = app.settings.board.result_banner_region is not None
    parts = {"nav": _navigation_cost(timing), "betspam": _spam_cost(timing),
             "ocr": _ocr_cost(timing), "race": _race_cost(timing, banner)}
    total = sum(parts.values())
    rate = 3600 / total
    print(f"Cycle-time model for the {TIMING_NAME!r} timings\n")
    print("  " + "  ".join(f"{name} {value:5.1f}s"
                           for name, value in parts.items())
          + f"  = {total:5.1f}s/race -> {rate:5.1f} races/h "
            f"-> ${rate * PROFIT_PER_RACE:,.0f}/h")
    print("\n  His claim: 103 races/h ($506k/h). The race itself is the "
          "floor, and it ends\n  when the result is on screen rather than "
          "after a fixed sleep, so the race\n  column is an estimate and the "
          "log has the truth. If the real cycle is much\n  worse than this, "
          "the bet spam or a transition_gap is where the time is going.")
    if not banner:
        print("\n  No result_banner box on this screen, so the race wait is "
              "watching for the\n  picture to go still, and race_wait_min has "
              "to cover the pause after the\n  finish as well. Measuring one "
              "is what lets that number come down.")
