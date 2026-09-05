"""`setup`: measure this screen's boxes and write insidetrack.toml.

The boxes are the one part of this bot that cannot be shipped -- they are
pixel coordinates inside your chiaki-ng window at your window size. Editing
them into source by hand was the whole barrier to a first run, so this walks
you through them instead: it tells you which game screen to be on, you click
the corners, and it writes the file.

Clicking happens on a still capture in a `picker` window, not on the live
game. chiaki-ng hides the mouse pointer while it streams, so there is
nothing to aim with over the window itself -- and a still frame is steadier
to work on anyway. Two fallbacks are kept for setups where a GUI window is
not an option: `--point` hovers the live screen and takes a coordinate on
F8, and `--manual` reads them off a saved screenshot you type in. `--example`
skips the walkthrough entirely and drops the template next to you.
"""

import ctypes
import shutil
import time
from ctypes import wintypes
from dataclasses import replace
from pathlib import Path
from typing import Optional, Tuple

from . import userconfig
from .config import Profile, Region
from .screen import Screen, WindowMissing
from .userconfig import ConfigError, UserConfig

Point = Tuple[int, int]

CAPTURE_KEY = 0x77          # F8
CANCEL_KEY = 0x1B           # Escape
SKIP_KEY = 0x53             # S
_HELD = 0x8000

# An odds box narrower than this many times its own height is flagged as
# probably drawn around a short price. Both layouts measured so far came out
# at 1.8 (88x48) and 2.1 (135x65); EVENS is five characters against 2/1's
# three, so a box drawn on the wrong race is not marginally small, it is
# most of a character short.
NARROW_RATIO = 1.7

_user32 = ctypes.WinDLL("user32", use_last_error=True)


class _POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


class Cancelled(RuntimeError):
    """Escape, or Ctrl-C: leave the existing config alone."""


# --------------------------------------------------------------------------
# Three ways of naming a point
#
# Each is a session over one step of the walkthrough: ask for as many points
# as the step needs, then close. `anchor` is the corner already taken, which
# the clicking one draws a live box from and the other two ignore.


class Clicking:
    """Click the corners on a still capture, in a window of our own."""

    def __init__(self, image, title: str):
        from .picker import Picker
        self._picker = Picker(image, title)

    def capture(self, what: str, anchor: Optional[Point] = None,
                allow_skip: bool = False) -> Optional[Point]:
        from .picker import Cancelled as PickerCancelled
        try:
            point = self._picker.point(what, anchor, allow_skip)
        except PickerCancelled as stop:
            raise Cancelled(str(stop)) from None
        print(f"    {_flat(what)}\n      -> "
              + ("skipped" if point is None else str(point)))
        return point

    def confirm(self, question: str, yes: str, no: str, boxes=None,
                note: str = "") -> bool:
        from .picker import Cancelled as PickerCancelled
        try:
            answer = self._picker.confirm(question, yes, no, boxes, note)
        except PickerCancelled as stop:
            raise Cancelled(str(stop)) from None
        print(f"    {_flat(question)}\n      -> {yes if answer else no}")
        return answer

    def show(self, boxes) -> None:
        self._picker.draw(boxes)

    def close(self) -> None:
        self._picker.close()


class Pointing:
    """Hover the live screen and press F8.

    GetAsyncKeyState reads global key state, so F8 lands here whichever
    window has focus -- including the game's, which is where the pointer has
    to be. That is also why this is no longer the default: chiaki-ng hides
    the cursor over its own window, so on the one screen that matters there
    is nothing to aim with.
    """

    def __init__(self, screen: Screen):
        self._screen = screen

    def origin(self) -> Point:
        window = self._screen.window()
        return window.left, window.top

    def capture(self, what: str, anchor: Optional[Point] = None,
                allow_skip: bool = False) -> Optional[Point]:
        keys = [CAPTURE_KEY, CANCEL_KEY] + ([SKIP_KEY] if allow_skip else [])
        _drain(keys)
        left, top = self.origin()
        skip = "   S skip" if allow_skip else ""
        print(f"    {_flat(what)}\n      hover it, then press F8   "
              f"(Esc cancel{skip})")
        while True:
            time.sleep(0.05)
            x, y = cursor()
            inside = (x - left, y - top)
            print(f"      window ({inside[0]:5d}, {inside[1]:5d}) "
                  f" screen ({x:5d}, {y:5d})   ", end="\r", flush=True)
            if _down(CANCEL_KEY):
                print()
                raise Cancelled("cancelled")
            if allow_skip and _down(SKIP_KEY):
                _drain(keys)
                print("\n      skipped")
                return None
            if _down(CAPTURE_KEY):
                _drain(keys)
                print(f"\n      -> ({inside[0]}, {inside[1]})")
                return inside

    def confirm(self, question: str, yes: str, no: str, boxes=None,
                note: str = "") -> bool:
        if note:
            print(f"  {note}")
        return _yes(f"  {_flat(question)}", True)

    def show(self, boxes) -> None:
        pass

    def close(self) -> None:
        pass


class Typing:
    """Coordinates read off the saved screenshot and typed in."""

    def capture(self, what: str, anchor: Optional[Point] = None,
                allow_skip: bool = False) -> Optional[Point]:
        suffix = ", or 's' to skip" if allow_skip else ""
        while True:
            answer = _ask(f"    {_flat(what)}\n"
                          f"      x,y{suffix}: ").replace(" ", "")
            if not answer:
                continue
            if allow_skip and answer.lower() in ("s", "skip"):
                return None
            parts = answer.replace(";", ",").split(",")
            try:
                return int(parts[0]), int(parts[1])
            except (ValueError, IndexError):
                print("      that isn't an x,y pair -- try '246,371'")

    def confirm(self, question: str, yes: str, no: str, boxes=None,
                note: str = "") -> bool:
        if note:
            print(f"  {note}")
        return _yes(f"  {_flat(question)}", True)

    def show(self, boxes) -> None:
        pass

    def close(self) -> None:
        pass


def _flat(what: str) -> str:
    """A prompt written for the picker's two lines, on one terminal line."""
    return " ".join(what.splitlines())


def cursor() -> Point:
    """Where the mouse is, in screen pixels."""
    point = _POINT()
    _user32.GetCursorPos(ctypes.byref(point))
    return int(point.x), int(point.y)


def _down(key: int) -> bool:
    return bool(_user32.GetAsyncKeyState(key) & _HELD)


def _drain(keys) -> None:
    """Wait for every key to come up, so one press is never read twice."""
    while any(_down(key) for key in keys):
        time.sleep(0.02)


def _box(session, what: str, allow_skip: bool = False) -> Optional[Region]:
    """Two corners -> (left, top, width, height).

    Taken either way round: the smaller of the two is the top-left whichever
    order they arrived in.
    """
    while True:
        first = session.capture(f"{what}\nTOP-LEFT corner",
                                allow_skip=allow_skip)
        if first is None:
            return None
        second = session.capture(f"{what}\nBOTTOM-RIGHT corner", anchor=first,
                                 allow_skip=allow_skip)
        if second is None:
            return None
        left, top = min(first[0], second[0]), min(first[1], second[1])
        width = abs(second[0] - first[0])
        height = abs(second[1] - first[1])
        if width >= 4 and height >= 4:
            return left, top, width, height
        print(f"      that box is only {width}x{height}px -- the two corners "
              "were nearly the\n      same point. Try again.")


# --------------------------------------------------------------------------
# The walkthrough


BANNER = """
=========================================================================
  insidetrack setup -- measuring where things are in your chiaki-ng window
=========================================================================

  You will be asked to put the game on a particular screen and press
  Enter. Each time, this grabs the window and opens that still picture in
  a window of its own, where you click the corners of a box or two.

  Clicking happens on the still, not on the live game: chiaki-ng hides the
  mouse pointer over its own window, so there would be nothing to aim
  with. The picker draws a crosshair and magnifies the pixels under it.

  About two minutes, and nothing is written until the end.

  Have chiaki-ng streaming, visible and NOT covered by another window at
  the moment you press Enter -- the grab is of real screen pixels, so
  anything on top of it lands in the picture.
"""

BOARD_STEP = """
-- The betting board ----------------------------------------------------

  In game: walk into the Inside Track machine and open SINGLE EVENT, so
  all six horses are listed with their odds (EVENS, 2/1, 13/1 ...).

  The boxes go around the ODDS TEXT of a lane. Draw them GENEROUSLY WIDE:
  the price sitting there now is whatever this race happens to have, and
  the same box has to hold every other price too -- EVENS is the longest
  and 2/1 the shortest, and EVENS may not even be on the board right now.
  Take the right edge out into the empty space, stopping short of the
  horse's number.

  Slack costs nothing: the reader crops to the text before recognising
  it, so an over-wide box reads exactly the same. A box that clips a
  price does not.
"""

STAKE_STEP = """
-- The stake ------------------------------------------------------------

  Still on SINGLE EVENT: select any horse (Cross) so the betting panel
  opens on the right and a dollar amount is showing.

  Then RUN THE STAKE UP TO ITS MAXIMUM before you measure -- Right onto
  the increase arrow, and hold Cross until it reads $10,000. That is the
  only number this box is ever read for, and it is the widest one: seven
  characters against the four of the $100 it opens on. A box drawn around
  $100 clips $10,000 every single race.

  If you would rather not move the stake, draw the box wide enough for
  three more digits and a comma. Spare space inside it is harmless.
"""

RESULT_STEP = """
-- The result screen ----------------------------------------------------

  Place a bet (or just let a race run) and wait for the finish, so the
  result screen is showing -- the three cards, with RESULTS across the top.

  Two boxes come off this one screen:

    the WINNING HORSE'S NUMBER, which grades every race, including the
    ones the bot loses -- that is what makes the race log worth anything;

    the RESULTS title panel, which is how the bot knows the race is over.
    Without it the wait has to guess from the picture going still, and the
    camera holds on the horses for up to three seconds after the finish,
    so every race pays for that worst case. Skipping it costs seconds a
    race; skipping the lane number means races logged with no result.
"""


def run(args) -> int:
    """The `setup` command. Returns a process exit code."""
    target = Path(args.config).expanduser() if args.config \
        else userconfig.default_target()
    if getattr(args, "example", False):
        return _copy_example(target)
    try:
        return _walk(args, target)
    except Cancelled:
        print("\nCancelled -- nothing was written.")
        return 1
    except KeyboardInterrupt:
        print("\nCancelled -- nothing was written.")
        return 1
    except WindowMissing as missing:
        print(f"\n{missing}")
        return 2


def _copy_example(target: Path) -> int:
    example = userconfig.example_path()
    if not example.is_file():
        print(f"Missing template: {example}")
        return 2
    if target.exists() and not _yes(f"{target} exists. Overwrite?", False):
        print("Left alone.")
        return 1
    shutil.copyfile(example, target)
    print(f"Wrote {target}\n\nOpen it and fill in the boxes for your window. "
          "`python -m insidetrack probe`\nwill draw them on a screenshot so "
          "you can check them.")
    return 0


def _walk(args, target: Path) -> int:
    print(BANNER)
    existing = _existing(target)
    title = _window_title(args, existing)
    screen = Screen(title)
    window = screen.window()
    print(f"  Using window {window.title!r} -- {window.width}x"
          f"{window.height} at ({window.left}, {window.top})\n")

    mode = _capture_mode(args)
    name = _screen_name(args, existing)
    previous = existing.screens.get(name) if existing else None

    odds = _measure_odds(screen, mode, name)
    stake = _measure_stake(screen, mode, name, previous)
    win_lane, banner = _measure_result(screen, mode, name, previous)

    profile = Profile(odds_regions=odds, bet_amount_region=stake,
                      win_lane_region=win_lane,
                      result_banner_region=banner)
    config = _merge(existing, name, profile, title, args)
    return _finish(config, target, name, screen, profile)


def _existing(target: Path) -> Optional[UserConfig]:
    if not target.is_file():
        return None
    try:
        loaded = userconfig.load(str(target))
    except ConfigError as error:
        print(f"  (ignoring the config already at {target}: {error})\n")
        return None
    print(f"  Adding to the config at {target} "
          f"(screens: {', '.join(sorted(loaded.screens))})\n")
    return loaded


def _window_title(args, existing: Optional[UserConfig]) -> str:
    """Find the stream window, and let the user name it if we cannot."""
    default = args.window or (existing.window_title if existing
                              else userconfig.DEFAULT_WINDOW_TITLE)
    title = default
    while True:
        try:
            Screen(title).window()
            return title
        except WindowMissing:
            print(f"  No visible window with {title!r} in its title.")
            _list_windows()
            answer = _ask("  Part of the stream window's title "
                          f"(Enter to retry {title!r}): ")
            title = answer or title


def _list_windows() -> None:
    try:
        import pygetwindow
        titles = sorted({window.title for window in pygetwindow.getAllWindows()
                         if window.title and window.width > 200})
    except Exception as error:
        print(f"  (could not list windows: {error})")
        return
    print("  Open windows:")
    for entry in titles[:25]:
        print(f"    {entry}")


def _capture_mode(args) -> str:
    """How the corners get named. Clicking unless told otherwise."""
    if args.manual:
        return "type"
    if args.point:
        return "point"
    if not _gui_available():
        print("  (no window system available here -- coordinates will be "
              "typed in)\n")
        return "type"
    return "click"


def _gui_available() -> bool:
    try:
        import importlib

        import tkinter
        importlib.import_module("PIL.ImageTk")   # what the picker draws with
        root = tkinter.Tk()
        root.destroy()
        return True
    except Exception as error:
        print(f"  (could not open a window: {error})")
        return False


def _session(mode: str, screen: Screen, image, name: str, tag: str):
    """One capture session for one step of the walkthrough."""
    if mode == "click":
        return Clicking(image, f"insidetrack setup -- {name} / {tag}")
    if mode == "point":
        return Pointing(screen)
    return Typing()


def _screen_name(args, existing: Optional[UserConfig]) -> str:
    if args.screen:
        return args.screen
    default = existing.default_screen if existing else "main"
    answer = _ask("  A name for this screen layout, so you can keep more "
                  f"than one\n  (e.g. 'main', '4k') [{default}]: ").strip()
    return answer or default


def _measure_odds(screen: Screen, mode: str, name: str):
    print(BOARD_STEP)
    image = _wait_for_screen(screen, name, "board", mode)
    session = _session(mode, screen, image, name, "odds")
    try:
        while True:
            boxes = _two_ends(session)
            if session.confirm(
                    "All six lanes, spaced evenly between the two you gave.\n"
                    "Is every price inside its own box?",
                    yes="Yes, use these", no="No, let me place each lane",
                    boxes=boxes):
                return boxes
            boxes = _all_lanes(session, boxes)
            if session.confirm("Is every price inside its own box now?",
                               yes="Yes, use these",
                               no="No, start this screen over", boxes=boxes):
                return boxes
    finally:
        session.close()


def _two_ends(session):
    """Lane 1's box and lane 6's corner, spaced out into six."""
    lane1 = _lane_one(session)
    print("\n    Now one corner of the bottom lane: the lanes are evenly\n"
          "    stacked, so the four between are worked out from these two.\n")
    lane6 = session.capture(
        "LANE 6 odds -- the bottom horse's price\nTOP-LEFT corner")
    boxes = userconfig.even_lanes(lane1, userconfig.LANES, lane6)
    _show_lanes(boxes)
    return boxes


def _lane_one(session):
    """Lane 1's box, checked for width before it sizes the other five.

    This box is the one that matters most: its width is reused for all six
    lanes, and it is measured against whatever price this race happens to
    show. Draw it around a 2/1 and EVENS -- five characters against three --
    is clipped in every lane, in every race, from then on.
    """
    while True:
        region = _box(session, "LANE 1 odds -- the top horse's price")
        session.show([region])
        print(f"      box {list(region)}")
        if session.confirm(
                "Would EVENS fit inside this box?\n"
                "It is the longest price there is, and may not be on the "
                "board right now.",
                yes="Yes, wide enough", no="No, draw it wider",
                boxes=[region], note=_width_note(region)):
            return region


def _width_note(region: Region) -> str:
    """Spare room is free; clipping is not. Say so, and flag a tight box."""
    note = ("Empty space inside the box costs nothing -- the reader crops to "
            "the text before recognising it. Clipping a price costs every "
            "race.")
    width, height = region[2], region[3]
    if width < height * NARROW_RATIO:
        return (f"{note}   This one is {width}x{height}, which is narrow for "
                "its height: on both layouts measured so far a box that fits "
                "EVENS was at least twice as wide as it is tall.")
    return note


def _all_lanes(session, boxes):
    """The escape hatch: take the top-left of each lane separately.

    Real boards are not always perfectly even -- the first row can sit a few
    pixels further from the second than the rest do -- and a box with little
    slack around the text will not forgive it.
    """
    print("\n    Top-left corner of each lane in turn, then. Lane 1's box "
          "size\n    is reused for all of them.\n")
    width, height = boxes[0][2], boxes[0][3]
    measured = [boxes[0]]
    session.show(measured)
    for lane in range(2, userconfig.LANES + 1):
        point = session.capture(
            f"LANE {lane} odds -- the {_ordinal(lane)} price down\n"
            "TOP-LEFT corner")
        measured.append((point[0], point[1], width, height))
        session.show(measured)
    _show_lanes(measured)
    return measured


def _ordinal(number: int) -> str:
    return {2: "second", 3: "third", 4: "fourth",
            5: "fifth", 6: "sixth"}[number]


def _show_lanes(boxes) -> None:
    print("\n    Six odds boxes:")
    for lane, region in enumerate(boxes, start=1):
        print(f"      lane {lane}: {list(region)}")


STAKE_CHECK = ("Would $10,000 fit inside this box?\n"
               "That is the only figure it is ever read for, and the widest "
               "one.")
STAKE_NOTE = (
    "The bot reads this box to confirm the stake reached the maximum before "
    "it commits, so $10,000 is what has to fit -- seven characters against "
    "the four of the $100 the panel opens on. If the stake is not showing "
    "$10,000 right now, leave room for three more digits and a comma; spare "
    "space inside the box is harmless, because the reader crops to the text "
    "before recognising it.")


def _measure_stake(screen: Screen, mode: str, name: str,
                   previous: Optional[Profile]) -> Optional[Region]:
    print(STAKE_STEP)
    if not _step_wanted("Measure the stake box now?", previous
                        and previous.bet_amount_region):
        return previous.bet_amount_region if previous else None
    return _one_box(screen, mode, name, "stake",
                    "the BET AMOUNT -- the $ figure",
                    question=STAKE_CHECK, note=STAKE_NOTE,
                    yes="Yes, wide enough", no="No, draw it wider")


WIN_LANE_CHECK = ("Is the winning horse's number inside this box,\n"
                  "with nothing else's number near it?")
WIN_LANE_NOTE = (
    "One digit, 1 to 6. The badge's border or the card behind it running out "
    "of the box is fine -- ink that touches an edge is treated as background "
    "and dropped, because the number never reaches one. Another lane's digit "
    "creeping in is not.")


BANNER_CHECK = ("Is the RESULTS panel -- black behind, yellow letters --\n"
                "filling this box, with no orange backdrop in it?")
BANNER_NOTE = (
    "This box is never read as text. It is matched on two colours: mostly "
    "near-black, with some yellow in it. So keep it INSIDE the panel -- the "
    "orange backdrop leaking in is the one thing that breaks it -- and keep "
    "the letters in, because a plain black panel is not a match either. "
    "Anywhere across the middle of the title works.")


def _measure_result(screen: Screen, mode: str, name: str,
                    previous: Optional[Profile]):
    """Both result-screen boxes off one capture: (win lane, banner).

    One capture and one picker window for the two of them, because they are
    on the same screen and asking twice would mean sitting through another
    race to get back to it. Skipping either keeps whatever was measured
    before, so an existing config can add the banner without redrawing the
    lane number.
    """
    print(RESULT_STEP)
    win_lane = previous.win_lane_region if previous else None
    banner = previous.result_banner_region if previous else None
    if not _result_wanted(win_lane, banner):
        return win_lane, banner
    image = _wait_for_screen(screen, name, "result", mode)
    session = _session(mode, screen, image, name, "result")
    try:
        win_lane = _pick_box(
            session, "the WINNING HORSE'S NUMBER -- just the digit",
            WIN_LANE_CHECK, WIN_LANE_NOTE) or win_lane
        banner = _pick_box(
            session, "the RESULTS TITLE -- inside the black panel, letters "
            "included", BANNER_CHECK, BANNER_NOTE,
            note_for=lambda region: _banner_note(image, region)) or banner
    finally:
        session.close()
    return win_lane, banner


def _result_wanted(win_lane: Optional[Region],
                   banner: Optional[Region]) -> bool:
    """Both boxes come off one screen, so they are offered together -- but
    named separately, because the usual reason to be here is a config that
    has the lane number from before this and no banner yet."""
    have = [name for name, box in (("the winning lane", win_lane),
                                   ("the RESULTS panel", banner)) if box]
    if have:
        print(f"  Already measured: {' and '.join(have)}.")
    return _yes("  Measure the result-screen boxes now?", len(have) < 2)


def _banner_note(image, region: Region) -> str:
    """What the matcher makes of the box just drawn, on the captured still.

    The box is checked here rather than left to the first race that needs
    it: it is measured on the one screen that proves it, and a box that
    reads 20% black is a five-second fix now against a run that quietly
    waits out race_wait_max every race.
    """
    from . import vision
    left, top, width, height = region
    crop = image[top:top + height, left:left + width]
    if crop.size == 0:
        return "\n\nThat box falls outside the window."
    dark, yellow = vision.banner_fractions(crop)
    verdict = ("MATCHES -- the bot would call this the result screen."
               if vision.is_banner(dark, yellow) else
               "NO MATCH -- the bot would not recognise this as the result "
               "screen. Draw it further inside the panel, or wide enough to "
               "take in the letters.")
    return (f"\n\n{dark:.0%} near-black, {yellow:.0%} yellow: {verdict}")


def _one_box(screen: Screen, mode: str, name: str, tag: str, what: str,
             question: str, note: str = "", yes: str = "Yes, use it",
             no: str = "No, do it again") -> Optional[Region]:
    """One box on a screen of its own: capture, draw, check, keep."""
    image = _wait_for_screen(screen, name, tag, mode)
    session = _session(mode, screen, image, name, tag)
    try:
        return _pick_box(session, what, question, note, yes, no)
    finally:
        session.close()


def _pick_box(session, what: str, question: str, note: str = "",
              yes: str = "Yes, use it", no: str = "No, do it again",
              note_for=None) -> Optional[Region]:
    """One box in an open session, drawn back onto the picture and checked
    before it is kept. `note_for` adds what the box measures to the check."""
    while True:
        region = _box(session, what, allow_skip=True)
        if region is None:
            return None
        print(f"      box {list(region)}")
        session.show([region])
        extra = note_for(region) if note_for else ""
        if session.confirm(question, yes=yes, no=no, boxes=[region],
                           note=note + extra):
            return region


def _step_wanted(question: str, already: Optional[Region]) -> bool:
    if already:
        print(f"  Already measured as {list(already)}.")
        return _yes(f"  {question}", False)
    return _yes(f"  {question}", True)


def _wait_for_screen(screen: Screen, name: str, tag: str, mode: str):
    """Capture the window once that screen is up, and keep the pixels.

    Everything after this works on this one frame rather than on the live
    window, so the game can carry on animating -- or be alt-tabbed away
    from -- while the corners are picked.
    """
    _ask("  Press Enter once that screen is showing... ")
    image = screen.grab_window()
    shot = Path(f"setup-{name}-{tag}.png")
    try:
        from PIL import Image
        Image.fromarray(image).save(shot)
    except Exception as error:
        print(f"  (could not save a screenshot: {error})")
        return image
    if mode == "click":
        print(f"  Captured. A window opens on that picture -- click the "
              f"corners on it.\n  ({shot} is the same frame, if you want it "
              "on disk.)\n")
    else:
        print(f"  Saved {shot}. Read the coordinates off it -- they are\n"
              "  measured from its own top-left corner.\n")
    return image


def _merge(existing: Optional[UserConfig], name: str, profile: Profile,
           title: str, args) -> UserConfig:
    screens = dict(existing.screens) if existing else {}
    screens[name] = profile
    base = existing or UserConfig()
    return replace(base, window_title=title, screens=screens,
                   default_screen=name,
                   input_mode=args.input_mode or base.input_mode)


def _finish(config: UserConfig, target: Path, name: str,
            screen: Screen, profile: Profile) -> int:
    if target.exists():
        print(f"\n  {target} already exists; the {name!r} screen will be "
              "replaced\n  and any others in it kept.")
        if not _yes("  Write it?", True):
            print("\nNot written. The boxes measured were:\n")
            print(userconfig.dump(config))
            return 1
    userconfig.write(config, target)
    print(f"\nWrote {target}\n")
    _draw_check(screen, profile, name)
    steps = [(f"probe --screen {name}", "check the boxes sit on the odds"),
             (f"read  --screen {name}", "one board read, and the decision"),
             ("keys", "confirm input reaches the PS5"),
             (f"run --dry --screen {name}", "a rehearsal, no input sent")]
    print("Next:")
    for command, note in steps:
        print(f"  python -m insidetrack {command:<26}{note}")
    print()
    return 0


def _draw_check(screen: Screen, profile: Profile, name: str) -> None:
    """Same drawing as `probe`, straight away, so a mistake shows now."""
    try:
        from PIL import Image

        from .diagnostics import _draw_boxes
        image = Image.fromarray(screen.grab_window())
        _draw_boxes(image, profile)
        out = Path(f"setup-{name}-check.png")
        image.save(out)
        print(f"Open {out}: red boxes should sit on the six odds, blue on "
              "the stake,\nyellow on the winning lane (whichever of those "
              "the current screen shows).\n")
    except Exception as error:
        print(f"(could not draw the check image: {error})")


# --------------------------------------------------------------------------
# Prompts


def _ask(prompt: str) -> str:
    try:
        return input(prompt)
    except EOFError:
        raise Cancelled("no console to ask on") from None


def _yes(question: str, default: bool) -> bool:
    hint = "[Y/n]" if default else "[y/N]"
    answer = _ask(f"{question} {hint} ").strip().lower()
    if not answer:
        return default
    return answer.startswith("y")
