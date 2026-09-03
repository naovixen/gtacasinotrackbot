"""
GTA Online Inside Track auto-bettor (PS5 via chiaki-ng Remote Play on PC)
=========================================================================

STRATEGY (validated against the 547-race log in post-info/SecondPost.md --
run `python validate.py` to reproduce every number below)

  1. TWO horses at EVENS -> skip with a minimum ($100) bet.
     Betting one of two EVENS returned -25% ROI over the 16 such races:
     the pair splits the win probability and neither is worth 2x.
  2. Otherwise take the first horse present in the order
     EVENS > 2/1 > 4/1 > 3/1 > 5/1, and max-bet it.
     Head-to-head over races containing both horses confirms every link
     in that chain (1>2, 2>4, 4>3, 3>5); note 4/1 genuinely beats 3/1,
     because their win rates are close (30.3% vs 26.7%) while 4/1 pays
     5x against 4x.
  3. Duplicate of the chosen horse -> pick lane 3,2,1,6,5,4 in that order.
     Only fires in 14% of races and is worth ~1 ROI point either way.
  4. Everything 6/1 or longer -> minimum-bet skip (never occurred in 547
     races, kept as a guard).

  Measured on his data: +50.6% ROI, ~$4,900 profit per race.
  At 103 races/hour that is ~$505k/h, which is his claim. Throughput,
  not the strategy, is what decides whether you land in his 500-800k
  band -- see `python inside_track_bot.py budget`.

  STRATEGY = "chart" restores the per-(track, horse) ROI tables. They
  look better in-sample (+57.4%) and are worse in reality: +38.2% under
  5-fold cross-validation with the cells refitted per split, and +53.1%
  against pickorder's +69.0% on the 132 races recorded after the first
  post's charts were published. Each cell rests on 7-40 appearances and
  1-20 wins, so taking the max over six of them mostly selects whichever
  got lucky. Left in for comparison; do not run it for money.

INPUT MODE -- how to keep this off your other monitor
  "postmessage" (default): posts key messages straight to the chiaki-ng
    window handle. Nothing else on the system can see them, so you can
    click into any other program and keep working. Verify it drives your
    build with `python inside_track_bot.py keytest` before trusting it.
  "gamepad": virtual DualShock 4 via ViGEmBus+vgamepad. A virtual pad is
    a system-wide HID device -- Steam in particular grabs it and its
    desktop layout retypes the input into whatever window you focused,
    which is the "it's controlling my program" effect. To use this mode
    safely see INPUT ISOLATION in README-fixes.md (HidHide + Steam).
  "keyboard": pydirectinput; needs chiaki-ng focused. Last resort.

SCREENS: coordinates live in PROFILES, one entry per monitor/layout,
selected with a CLI arg. Calibrate once per profile and don't move or
resize the window on that screen afterwards.

COMMANDS  (a profile name can be added to any of them, e.g. 'read 4k')
  python inside_track_bot.py calibrate [profile]  capture window -> calibrate.png
  python inside_track_bot.py probe [profile]      probe.png with boxes drawn
  python inside_track_bot.py read [profile]       one verified board read
  python inside_track_bot.py keytest [profile]    find the input target
  python inside_track_bot.py budget               cycle-time / $-per-hour model
  python inside_track_bot.py [run] [profile]      run the bot

SETUP
  pip install mss pillow numpy easyocr pydirectinput pygetwindow vgamepad
  The window must stay visible (not minimised or covered) -- capture
  reads pixels. It does NOT need to be focused in postmessage/gamepad mode.
  ScrollLock pauses the bot at any time, from any window.

NOTE: automation violates Rockstar's ToS; ban/wipe risk is real. Supervise.
"""

import ctypes
import random
import re
import sys
import time
from ctypes import wintypes

import mss
import numpy as np
import pygetwindow as gw
from PIL import Image, ImageDraw, ImageOps

# --------------------------------------------------------------------------
# CONFIG
# --------------------------------------------------------------------------

WINDOW_TITLE = "chiaki"

# One profile per screen/layout. All boxes are (left, top, width, height)
# relative to the WINDOW's top-left, measured on that profile's own
# calibrate.png. bet_amount_region enables max-bet OCR verification
# (None disables it).
PROFILES = {
    "main": {   # ultrawide 1440p
        "odds_regions": [
            (246, 371, 88, 48),  # lane 1
            (246, 496, 88, 48),  # lane 2
            (246, 616, 88, 48),  # lane 3
            (246, 736, 88, 48),  # lane 4
            (246, 856, 88, 48),  # lane 5
            (246, 976, 88, 48),  # lane 6
        ],
        "bet_amount_region": (1315, 480, 140, 75),
    },
    "4k": {     # 4K side monitor
        "odds_regions": [
            (370, 560, 135, 65),   # lane 1
            (370, 743, 135, 65),   # lane 2
            (370, 926, 135, 65),   # lane 3
            (370, 1109, 135, 65),  # lane 4
            (370, 1292, 135, 65),  # lane 5
            (370, 1475, 135, 65),  # lane 6
        ],
        "bet_amount_region": (1985, 765, 220, 130),
    },
}
DEFAULT_PROFILE = "main"
PROFILE = DEFAULT_PROFILE   # set from CLI arg in __main__

# chiaki-ng's default keyboard map: Cross = Enter, Circle = Backspace.
KEYS = {
    "up": "up",
    "down": "down",
    "left": "left",
    "right": "right",
    "cross": "enter",
    "circle": "backspace",
}

INPUT_MODE = "postmessage"   # "postmessage" | "gamepad" | "keyboard"

# Which HWND postmessage mode targets. None = the top-level chiaki window,
# which is right for a Qt app. If `keytest` shows a child window is the one
# that responds, put its 1-based index from keytest's listing here.
POST_TARGET_INDEX = None

# "safe" is the original conservative pacing; it cannot reach his race rate.
# "fast" trims the gaps that are pure overhead. Start on "safe", confirm the
# navigation never desyncs, then move to "fast" and watch the achieved
# races/hour the run loop prints.
TIMING_PROFILE = "fast"

TIMINGS = {
    "safe": {
        "menu_tap_gap": (0.30, 0.45),   # between navigation presses
        "bet_tap_gap": (0.03, 0.07),    # between bet-increase taps
        "key_hold": (0.07, 0.12),       # how long each key is held
        "spam_hold": (0.07, 0.12),      # hold during the bet-increase spam
        "race_wait": 34.0,              # bet placed -> result dismissable
        "ocr_settle": 1.0,
        "hesitate_chance": 0.2,         # occasional extra 0-0.5s nav pause
        "double_read": True,            # always read the board twice
    },
    "fast": {
        "menu_tap_gap": (0.10, 0.15),
        "bet_tap_gap": (0.012, 0.022),
        "key_hold": (0.030, 0.045),
        "spam_hold": (0.018, 0.028),
        "race_wait": 31.5,
        "ocr_settle": 0.35,
        "hesitate_chance": 0.0,
        "double_read": False,           # second read only if the first is weak
    },
}


def T():
    return TIMINGS[TIMING_PROFILE]


# 100 -> 1000 in 100s (9 presses), 1000 -> 10000 in 500s (18 presses) = 27.
# Spare press in case a tap gets eaten; the increase caps at 10,000.
MAX_BET_PRESSES = 28
MAX_BET = 10_000
MIN_BET = 100

DRY_RUN = False       # True = decide + log only. START WITH TRUE.
DEBUG_SAVE = False    # save debug_lane*.png of each OCR input
CONF_TRUST = 0.55     # min per-lane OCR confidence to bet real money on
RECHECK_CONF = 0.80   # "fast" profile: below this, spend a confirming read

# --------------------------------------------------------------------------
# Strategy
# --------------------------------------------------------------------------

STRATEGY = "pickorder"    # "pickorder" (validated) or "chart" (overfit)

PICK_ORDER = [1, 2, 4, 3, 5]        # EVENS > 2/1 > 4/1 > 3/1 > 5/1
LANE_TIEBREAK = [3, 2, 1, 6, 5, 4]  # between duplicates of the chosen horse

MIN_CELL_ROI = 1          # chart mode: min ROI% to max-bet, else min-bet skip

# Chart mode tables, recomputed from the full 547-race log (the values that
# used to be here came from the first post's 283/153/61-race charts, i.e. a
# subset). ROI % per (track, horse); horse n pays (n+1)x.
CHART_NO1 = {             # races with no horse 1 (no EVENS): 346 races
    1: {2: 76,  3: 0,   4: 74,  5: -36},
    2: {2: 58,  3: -11, 4: 54,  5: 41},
    3: {2: 11,  3: 33,  4: 114, 5: 135},
    4: {2: 11,  3: 45,  4: 45,  5: -11},
    5: {2: 59,  3: 86,  4: 92,  5: 24},
    6: {2: 56,  3: 20,  4: 18,  5: 24},
}
CHART_NO12 = {            # races with no horse 1 or 2: 181 races
    1: {3: 14,  4: 133, 5: -71},
    2: {3: 0,   4: 59,  5: 85},
    3: {3: 41,  4: 125, 5: 147},
    4: {3: 60,  4: 59,  5: -25},
    5: {3: 100, 4: 163, 5: 71},
    6: {3: 0,   4: 25,  5: 36},
}
CHART_NO123 = {           # races with no horse 1, 2 or 3: 71 races
    1: {4: 122, 5: -45},
    2: {4: 76,  5: 125},
    3: {4: 106, 5: 329},
    4: {4: -23, 5: -60},
    5: {4: 218, 5: 100},
    6: {4: 11,  5: -8},
}

# From each lane, Right lands on a different button in the right-hand
# column: lanes 1-3 -> decrease (0 ups); lanes 4-5 -> Place Bet (1 up);
# lane 6 -> Cancel (2 ups).
UPS_TO_DECREASE = {1: 0, 2: 0, 3: 0, 4: 1, 5: 1, 6: 2}

SKIP_LANE = 3             # lane to park the $100 skip bet on


def _tiebreak_key(lane):
    return LANE_TIEBREAK.index(lane)


def decide(odds):
    """odds: list of 6 ints/None, index 0 = lane 1.
    Returns (lane_number_1to6, max_bet: bool, reason: str)."""
    if any(o is None for o in odds):
        return None, False, (
            f"OCR failed on lanes {[i+1 for i, o in enumerate(odds) if o is None]}"
        )

    evens_lanes = [i + 1 for i, o in enumerate(odds) if o == 1]
    if len(evens_lanes) >= 2:
        return SKIP_LANE, False, "two EVENS -> min-bet skip"
    if len(evens_lanes) == 1:
        return evens_lanes[0], True, f"EVENS in lane {evens_lanes[0]}"

    present = {o for o in odds if 2 <= o <= 5}
    if not present:
        return SKIP_LANE, False, "all horses 6/1+ -> min-bet skip"

    if STRATEGY == "chart":
        return _decide_chart(odds, present)

    for target in PICK_ORDER[1:]:        # EVENS already handled above
        lanes = [i + 1 for i, o in enumerate(odds) if o == target]
        if lanes:
            lane = min(lanes, key=_tiebreak_key)
            return lane, True, f"best horse {target}/1 in lane {lane}"
    return SKIP_LANE, False, "no ranked horse -> min-bet skip"


def _decide_chart(odds, present):
    """Legacy per-cell ROI lookup. Kept for comparison; loses out-of-sample."""
    if 2 in present:
        chart, name = CHART_NO1, "no-EVENS chart"
    elif 3 in present:
        chart, name = CHART_NO12, "no-1/2 chart"
    else:
        chart, name = CHART_NO123, "no-1/2/3 chart"

    candidates = [(chart[i + 1][o], i + 1, o) for i, o in enumerate(odds)
                  if 2 <= o <= 5 and o in chart[i + 1]]
    if not candidates:
        return SKIP_LANE, False, f"nothing in {name} -> min-bet skip"
    best_roi, lane, horse = max(
        candidates, key=lambda c: (c[0], -_tiebreak_key(c[1])))
    if best_roi < MIN_CELL_ROI:
        return SKIP_LANE, False, (
            f"best cell {horse}/1 lane {lane} ROI {best_roi}% "
            f"< {MIN_CELL_ROI}% ({name}) -> min-bet skip")
    return lane, True, f"{horse}/1 in lane {lane}, ROI {best_roi}% ({name})"


# --------------------------------------------------------------------------
# Window / regions
# --------------------------------------------------------------------------

_sct = getattr(mss, "MSS", mss.mss)()   # mss.mss() is deprecated in new mss


def profile():
    return PROFILES[PROFILE]


def get_window():
    wins = [w for w in gw.getAllWindows()
            if WINDOW_TITLE.lower() in w.title.lower() and w.width > 200]
    if not wins:
        raise RuntimeError(
            f"No window matching '{WINDOW_TITLE}' found. Is chiaki-ng running? "
            "If its title differs, change WINDOW_TITLE."
        )
    return wins[0]


def grab(region, lane_no=None):
    win = get_window()
    left, top, w, h = region
    shot = _sct.grab({"left": win.left + left, "top": win.top + top,
                      "width": w, "height": h})
    img = Image.frombytes("RGB", shot.size, shot.rgb)
    # Normalise to a fixed height so OCR sees a consistent text size.
    k = max(1.0, 150.0 / h)
    img = img.resize((max(16, int(w * k)), max(16, int(h * k))), Image.LANCZOS)
    img = ImageOps.autocontrast(ImageOps.grayscale(img))
    hist = img.histogram()
    if sum(hist[:128]) > sum(hist[128:]):
        img = ImageOps.invert(img)
    img = img.point(lambda p: 255 if p > 150 else 0)
    img = ImageOps.expand(img, border=24, fill=255)
    if DEBUG_SAVE and lane_no:
        img.save(f"debug_lane{lane_no}.png")
    return img


# --------------------------------------------------------------------------
# OCR (EasyOCR + strict validation)
# --------------------------------------------------------------------------

_reader = None


def reader():
    global _reader
    if _reader is None:
        print("Loading EasyOCR (first ever run downloads its model)...")
        import easyocr
        _reader = easyocr.Reader(["en"], gpu=True, verbose=False)
    return _reader


ODDS_RE = re.compile(r"^(EVENS|([2-9]|[12][0-9]|30)/1)$")


def parse_odds(text):
    t = text.strip().upper().replace(" ", "")
    if not ODDS_RE.match(t):
        return None
    return 1 if t == "EVENS" else int(t.split("/")[0])


def repair_text(t):
    """Conservative fixes for characteristic OCR drops, still validated
    against the strict pattern afterwards."""
    if t.startswith("EVEN"):
        return "EVENS"
    m = re.match(r"^(\d{1,2})1$", t)   # slash dropped: '71'->'7/1'
    if m:
        return f"{m.group(1)}/1"
    m = re.match(r"^(\d{1,2})/$", t)   # trailing 1 dropped
    if m:
        return f"{m.group(1)}/1"
    return t


def ocr_lane(img):
    """Return (odds_value or None, confidence 0..1, raw_text)."""
    results = reader().readtext(
        np.array(img), allowlist="EVENS0123456789/", paragraph=False
    )
    if not results:
        return None, 0.0, "(nothing)"
    results.sort(key=lambda r: r[0][0][0])
    text = "".join(r[1] for r in results).strip().upper().replace(" ", "")
    conf = min(float(r[2]) for r in results)
    value = parse_odds(text)
    if value is None:
        repaired = repair_text(text)
        value = parse_odds(repaired)
        if value is not None:
            text = f"{text} -> repaired {repaired}"
    return value, conf, text


def read_board(verbose=False):
    odds, confs = [], []
    for i, region in enumerate(profile()["odds_regions"], start=1):
        img = grab(region, lane_no=i)
        value, conf, raw = ocr_lane(img)
        if verbose:
            label = "EVENS" if value == 1 else (f"{value}/1" if value else "??")
            extra = f"  raw={raw!r}" if (value is None or "repaired" in raw) else ""
            print(f"  lane {i}: {label}  (conf {conf:.2f}){extra}")
        odds.append(value)
        confs.append(conf)
    return odds, confs


def read_board_verified(verbose=False):
    """A trusted board is complete and clears the confidence bar. The "safe"
    profile also demands a second, agreeing read; "fast" spends that second
    read only when the first one is merely adequate (below RECHECK_CONF),
    which is where most of the per-race OCR time used to go.

    A failed first read is never rescued by a second one -- the caller
    retries the whole cycle, which also gives the screen time to settle."""
    o1, c1 = read_board(verbose=verbose)
    if not (c1 and all(v is not None for v in o1) and min(c1) >= CONF_TRUST):
        return o1, False
    if not T()["double_read"] and min(c1) >= RECHECK_CONF:
        return o1, True
    o2, c2 = read_board()
    return o1, (o1 == o2 and all(v is not None for v in o2)
                and min(c2) >= CONF_TRUST)


def read_bet_amount():
    """OCR the current bet amount; int or None."""
    region = profile()["bet_amount_region"]
    if region is None:
        return None
    img = grab(region)
    results = reader().readtext(
        np.array(img), allowlist="$0123456789,.", paragraph=False
    )
    digits = "".join(c for r in results for c in r[1] if c.isdigit())
    return int(digits) if digits else None


# --------------------------------------------------------------------------
# Input backends
# --------------------------------------------------------------------------

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT,
                                 wintypes.WPARAM, wintypes.LPARAM]
_user32.PostMessageW.restype = wintypes.BOOL
_user32.MapVirtualKeyW.argtypes = [wintypes.UINT, wintypes.UINT]
_user32.MapVirtualKeyW.restype = wintypes.UINT

WM_KEYDOWN, WM_KEYUP = 0x0100, 0x0101
MAPVK_VK_TO_VSC = 0

VK = {"up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
      "enter": 0x0D, "backspace": 0x08}
# Arrow keys sit on the extended keyboard; Qt reads that bit out of lParam
# to distinguish them from the numpad, so it has to be set correctly.
EXTENDED_KEYS = {"up", "down", "left", "right"}

_target_hwnd = None


def _enum_children(hwnd):
    out = []
    proto = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def cb(h, _):
        out.append(h)
        return True

    _user32.EnumChildWindows(hwnd, proto(cb), 0)
    return out


def _window_class(hwnd):
    buf = ctypes.create_unicode_buffer(256)
    _user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def input_targets():
    """[(hwnd, label)] -- the top-level chiaki window first, then children.
    keytest walks this list so you can find the one that actually reacts."""
    win = get_window()
    top = win._hWnd
    out = [(top, f"top-level  class={_window_class(top)!r}  title={win.title!r}")]
    for h in _enum_children(top):
        out.append((h, f"child      class={_window_class(h)!r}"))
    return out


def target_hwnd():
    global _target_hwnd
    if _target_hwnd is None:
        targets = input_targets()
        idx = 0 if POST_TARGET_INDEX is None else POST_TARGET_INDEX - 1
        _target_hwnd = targets[idx][0]
    return _target_hwnd


def _post_key(hwnd, key_name, hold):
    """Post a real down/up pair to one window. Because it is PostMessage and
    not SendInput, the keystroke exists only for this HWND -- no other
    application, and no focused window, ever sees it."""
    vk = VK[KEYS[key_name]]
    scan = _user32.MapVirtualKeyW(vk, MAPVK_VK_TO_VSC)
    ext = 1 if KEYS[key_name] in EXTENDED_KEYS else 0
    lp_down = 1 | (scan << 16) | (ext << 24)
    lp_up = lp_down | (1 << 30) | (1 << 31)   # was-down + transition bits
    _user32.PostMessageW(hwnd, WM_KEYDOWN, vk, lp_down)
    time.sleep(hold)
    _user32.PostMessageW(hwnd, WM_KEYUP, vk, lp_up)


_pad = None


def _gamepad():
    global _pad
    if _pad is None:
        import vgamepad as vg
        _pad = (vg, vg.VDS4Gamepad())
        print("Virtual DualShock 4 created (ViGEmBus).")
        time.sleep(1.0)
    return _pad


def _press(key, hold=None):
    """Down-hold-up on the active input backend."""
    if hold is None:
        hold = random.uniform(*T()["key_hold"])
    if INPUT_MODE == "postmessage":
        _post_key(target_hwnd(), key, hold)
    elif INPUT_MODE == "gamepad":
        vg, pad = _gamepad()
        if key in ("up", "down", "left", "right"):
            dirs = {"up": vg.DS4_DPAD_DIRECTIONS.DS4_BUTTON_DPAD_NORTH,
                    "down": vg.DS4_DPAD_DIRECTIONS.DS4_BUTTON_DPAD_SOUTH,
                    "left": vg.DS4_DPAD_DIRECTIONS.DS4_BUTTON_DPAD_WEST,
                    "right": vg.DS4_DPAD_DIRECTIONS.DS4_BUTTON_DPAD_EAST}
            pad.directional_pad(direction=dirs[key])
            pad.update()
            time.sleep(hold)
            pad.directional_pad(
                direction=vg.DS4_DPAD_DIRECTIONS.DS4_BUTTON_DPAD_NONE)
            pad.update()
        else:
            btns = {"cross": vg.DS4_BUTTONS.DS4_BUTTON_CROSS,
                    "circle": vg.DS4_BUTTONS.DS4_BUTTON_CIRCLE}
            pad.press_button(button=btns[key])
            pad.update()
            time.sleep(hold)
            pad.release_button(button=btns[key])
            pad.update()
    else:
        import pydirectinput
        pydirectinput.PAUSE = 0.0
        pydirectinput.keyDown(KEYS[key])
        time.sleep(hold)
        pydirectinput.keyUp(KEYS[key])


def _gap(base_range):
    d = random.uniform(*base_range)
    if random.random() < T()["hesitate_chance"]:
        d += random.uniform(0.0, 0.5)   # human-like hesitation
    return d


def tap(key):
    if DRY_RUN:
        return
    _press(key)
    time.sleep(_gap(T()["menu_tap_gap"]))


def tap_fast(key):
    """Rapid tap for the bet-increase spam: no hesitation, tight jitter."""
    if DRY_RUN:
        return
    _press(key, hold=random.uniform(*T()["spam_hold"]))
    time.sleep(random.uniform(*T()["bet_tap_gap"]))


# --------------------------------------------------------------------------
# Pause switch
# --------------------------------------------------------------------------

VK_SCROLL = 0x91


def paused():
    """ScrollLock's toggle state -- readable without focus, so it works as a
    panic button from whatever window you happen to be using."""
    return bool(_user32.GetKeyState(VK_SCROLL) & 1)


def wait_while_paused():
    if not paused():
        return
    print("  ScrollLock is on -- paused. Turn it off to resume.")
    while paused():
        time.sleep(0.5)
    print("  resumed")


# --------------------------------------------------------------------------
# Sequences
# --------------------------------------------------------------------------

def enter_single_event():
    """From the machine's start screen: Right hovers 'Place Bet on Single
    Event', X opens it."""
    tap("right")
    tap("cross")


def spam_increase(n):
    for _ in range(n):
        tap_fast("cross")
    time.sleep(0.3)   # let the displayed amount settle before any read


def verify_max_amount():
    """Closed-loop check that the bet reached $10,000, correcting the two
    known slip modes. Needs bet_amount_region; no-op otherwise."""
    if DRY_RUN or profile()["bet_amount_region"] is None:
        return
    for _ in range(2):
        amt = read_bet_amount()
        if amt is None:
            print("  (bet amount unreadable -- proceeding unverified)")
            return
        if amt >= MAX_BET:
            return
        if amt <= MIN_BET:
            print(f"  (amount ${amt}: Right into increase was eaten -- correcting)")
            tap("right")
        else:
            print(f"  (amount ${amt}: some taps eaten -- topping up)")
        spam_increase(MAX_BET_PRESSES)
    amt = read_bet_amount()
    if amt is not None and amt < MAX_BET:
        print(f"  (WARNING: could not reach max, placing at ${amt})")


def place_bet(lane, max_bet):
    """From the single-event screen with nothing selected. Left brings the
    cursor in at lane 6; Up walks 6 -> 1; X selects the horse. Navigate to
    the decrease-bet button (lane-dependent, see UPS_TO_DECREASE). Max bet:
    Right -> increase, X-taps to $10,000 (OCR-verified), Down -> Place Bet.
    Min bet: Down goes straight from decrease to Place Bet."""
    tap("left")                      # cursor appears on lane 6
    for _ in range(6 - lane):
        tap("up")
    tap("cross")                     # select horse
    tap("right")
    for _ in range(UPS_TO_DECREASE[lane]):
        tap("up")                    # -> decrease-bet button
    if max_bet:
        tap("right")                 # -> increase-bet button
        spam_increase(MAX_BET_PRESSES)
        verify_max_amount()
    tap("down")                      # -> Place Bet
    tap("cross")                     # place bet; race starts


def return_to_start():
    """After the race result: Down then X selects 'bet again', returning
    to the machine start screen."""
    tap("down")
    tap("cross")


def ensure_window():
    """Make sure the window exists and is not minimised (capture needs real
    pixels). Never takes focus unless we are in keyboard mode, which is the
    whole point of the other two modes."""
    try:
        win = get_window()
        if win.isMinimized:
            win.restore()
            time.sleep(0.5)
        if INPUT_MODE == "keyboard":
            import pydirectinput
            pydirectinput.press("alt")   # allow foreground change on Windows
            win.activate()
            time.sleep(0.7)
        return True
    except Exception as e:
        print(f"(window check failed: {e})")
    return False


def preflight():
    """Warn about the setups that make a virtual pad leak into other windows."""
    print(f"Input mode: {INPUT_MODE}   timing profile: {TIMING_PROFILE}   "
          f"strategy: {STRATEGY}")
    if INPUT_MODE == "postmessage":
        try:
            hwnd = target_hwnd()
            print(f"  posting keys to HWND {hwnd} "
                  f"({_window_class(hwnd)!r}) -- scoped to that window only.")
            print("  If the PS5 menu doesn't move, run 'keytest' to pick "
                  "another target, or switch INPUT_MODE to 'gamepad'.")
        except Exception as e:
            print(f"  could not resolve a target window: {e}")
    elif INPUT_MODE == "gamepad":
        steam = _steam_running()
        if steam:
            print("  !! Steam is running. Steam grabs virtual DualShock pads "
                  "and its desktop layout retypes them into whatever window "
                  "you have focused -- that is the 'it controls my other "
                  "program' bug. Close Steam, or turn off Settings > "
                  "Controller > PlayStation Controller Support, or hide the "
                  "pad from everything but chiaki-ng with HidHide.")
        else:
            print("  Steam not detected. Any other app that reads gamepads "
                  "can still see this virtual pad; HidHide is the only "
                  "airtight fix. See README-fixes.md.")
    elif INPUT_MODE == "keyboard":
        print("  !! keyboard mode types into whatever window is FOCUSED. "
              "You cannot use the PC while this runs.")


def _steam_running():
    try:
        import subprocess
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq steam.exe"],
                             capture_output=True, text=True, timeout=10)
        return "steam.exe" in out.stdout.lower()
    except Exception:
        return False


# --------------------------------------------------------------------------
# Modes
# --------------------------------------------------------------------------

def run():
    print(f"Profile '{PROFILE}' -- DRY_RUN={DRY_RUN}")
    preflight()
    if DRY_RUN:
        print("DRY RUN: no input will be sent. Manually open the "
              "single-event screen so the reads can see the board.")
    print("ScrollLock pauses at any time. Starting in 5s...")
    ensure_window()
    time.sleep(5)

    races = staked = 0
    t_start = time.time()

    while True:
        wait_while_paused()
        t_race = time.time()
        ensure_window()
        enter_single_event()          # no-op in DRY_RUN

        lane = max_bet = None
        for attempt in range(3):
            time.sleep(T()["ocr_settle"])
            odds, trusted = read_board_verified()
            lane, max_bet, reason = decide(odds)
            print(f"[{time.strftime('%H:%M:%S')}] odds={odds} "
                  f"trusted={trusted} -> {reason}")
            if lane is not None and trusted:
                break
            print("  bad/untrusted read; retrying")
            lane = None
        if lane is None:
            lane, max_bet = SKIP_LANE, False
            print("  board unreadable after 3 tries -> min-bet skip to cycle it")

        place_bet(lane, max_bet)
        races += 1
        staked += MAX_BET if max_bet else MIN_BET
        time.sleep(T()["race_wait"])
        return_to_start()

        cycle = time.time() - t_race
        rate = races / ((time.time() - t_start) / 3600)
        print(f"  bet {'MAX' if max_bet else f'${MIN_BET}'} on lane {lane} "
              f"(race #{races})  cycle {cycle:.1f}s  "
              f"rate {rate:.0f} races/h  ->  projected "
              f"${rate * (staked / races) * 0.506:,.0f}/h at +50.6% ROI")


def budget():
    """Model the cycle time from the current timing profile. The strategy is
    worth ~$4,900 a race; whether that lands in his 500-800k/h band is
    entirely a question of how many races per hour this loop manages."""
    profit_per_race = 4917.0     # measured over his 547 races, see validate.py
    print(f"Cycle-time model for TIMING_PROFILE = {TIMING_PROFILE!r}\n")
    for name, t in TIMINGS.items():
        nav_press = sum(t["key_hold"]) / 2
        nav_gap = sum(t["menu_tap_gap"]) / 2 + t["hesitate_chance"] * 0.25
        nav = nav_press + nav_gap
        # enter(2) + left(1) + up(avg 3) + cross(1) + right(1) + ups(avg .5)
        # + right(1) + down(1) + cross(1) + return_to_start(2)
        nav_taps = 13.5
        spam = MAX_BET_PRESSES * (sum(t["spam_hold"]) / 2
                                  + sum(t["bet_tap_gap"]) / 2) + 0.3
        boards = 2.0 if t["double_read"] else 1.25   # fast rechecks weak reads
        ocr = t["ocr_settle"] + boards * 0.9 + 0.35   # 6 lanes + bet amount
        total = nav_taps * nav + spam + ocr + t["race_wait"]
        rate = 3600 / total
        mark = " <- active" if name == TIMING_PROFILE else ""
        print(f"  {name:>5}: nav {nav_taps * nav:5.1f}s  betspam {spam:4.1f}s  "
              f"ocr {ocr:4.1f}s  race {t['race_wait']:4.1f}s  "
              f"= {total:5.1f}s/race -> {rate:5.1f} races/h "
              f"-> ${rate * profit_per_race:>9,.0f}/h{mark}")
    print("\n  His claim: 103 races/h ($506k/h). race_wait is the floor -- "
          "everything else is overhead worth trimming.")
    print("  The run loop prints the achieved rate each race; if it is far "
          "below this model, lower race_wait until 'bad/untrusted read' "
          "starts appearing, then add a second back.")


def keytest():
    """Send Right/Left to each candidate window in turn so you can see which
    HWND chiaki-ng actually listens on. Watch the PS5 screen while it runs."""
    targets = input_targets()
    print(f"Found {len(targets)} candidate window(s):\n")
    for i, (hwnd, label) in enumerate(targets, start=1):
        print(f"  [{i}] hwnd={hwnd}  {label}")
    print("\nSending Right, Right, Left, Left to each in turn. Watch the "
          "chiaki-ng window WITHOUT clicking on it -- click somewhere else "
          "first, so a pass only counts if it works unfocused.\n")
    for i, (hwnd, label) in enumerate(targets, start=1):
        print(f"  -> testing [{i}] {label}")
        for key in ("right", "right", "left", "left"):
            _post_key(hwnd, key, 0.05)
            time.sleep(0.25)
        time.sleep(1.5)
    print("\nWhichever index moved the PS5 cursor: set POST_TARGET_INDEX to "
          "that number (or leave it None if it was [1]).")
    print("If none of them worked, chiaki-ng is not taking posted key "
          "messages on this build -- use INPUT_MODE = 'gamepad' and follow "
          "the isolation steps in README-fixes.md.")


def calibrate():
    ensure_window()
    time.sleep(1.0)
    win = get_window()
    shot = _sct.grab({"left": win.left, "top": win.top,
                      "width": win.width, "height": win.height})
    Image.frombytes("RGB", shot.size, shot.rgb).save("calibrate.png")
    print(f"Profile '{PROFILE}': captured '{win.title}' at "
          f"{win.width}x{win.height} -> calibrate.png")
    print("Measure the lane odds boxes (and bet amount box) off this image "
          f"into PROFILES[{PROFILE!r}], then keep the window where it is.")


def probe():
    """Save probe.png: live window capture with the profile's lane boxes
    (red) and bet-amount box (blue) drawn on."""
    win = get_window()
    print(f"Profile '{PROFILE}'; window: left={win.left} top={win.top} "
          f"{win.width}x{win.height}")
    shot = _sct.grab({"left": win.left, "top": win.top,
                      "width": win.width, "height": win.height})
    img = Image.frombytes("RGB", shot.size, shot.rgb)
    draw = ImageDraw.Draw(img)
    for i, (l, t, w, h) in enumerate(profile()["odds_regions"], start=1):
        draw.rectangle([l, t, l + w, t + h], outline=(255, 0, 0), width=3)
        draw.text((l + 4, max(0, t - 16)), f"lane {i}", fill=(255, 0, 0))
    bet = profile()["bet_amount_region"]
    if bet:
        l, t, w, h = bet
        draw.rectangle([l, t, l + w, t + h], outline=(0, 80, 255), width=3)
        draw.text((l + 4, max(0, t - 16)), "bet amount", fill=(0, 80, 255))
    img.save("probe.png")
    print("Saved probe.png -- red boxes should sit exactly on the six odds "
          "values (blue on the bet amount).")


def read_once():
    ensure_window()
    time.sleep(1.0)
    t0 = time.time()
    odds, trusted = read_board_verified(verbose=True)
    print("Result, lanes 1-6:",
          ["EVENS" if o == 1 else (f"{o}/1" if o else "??") for o in odds],
          f" trusted={trusted}  ({time.time() - t0:.2f}s)")
    print("Decision:", decide(odds))


if __name__ == "__main__":
    COMMANDS = {"run": run, "read": read_once, "calibrate": calibrate,
                "probe": probe, "keytest": keytest, "budget": budget}
    mode = "run"
    for a in sys.argv[1:]:
        if a in COMMANDS:
            mode = a
        elif a in PROFILES:
            PROFILE = a
        else:
            print(f"Unknown argument {a!r} "
                  f"(commands: {'/'.join(COMMANDS)}; profiles: "
                  f"{', '.join(PROFILES)})")
            sys.exit(1)
    COMMANDS[mode]()
