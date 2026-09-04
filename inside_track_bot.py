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

TIMING: one set of numbers, in TIMING near the top of this file -- no profile to
choose any more. They are trimmed past what has been measured on this
connection; the comment above TIMING says exactly where each one stands against
the evidence. `tune` checks them against the real lane list in a minute,
`budget` models what they cost in races/hour, and if navigation desyncs the
knob to raise is transition_gap, then menu_tap_gap.

Any command also accepts, in any order:
  main | 4k               which screen profile's coordinates to use
  --dry                   decide and log, send no input
  --chart | --pickorder   override the strategy for this run
e.g.  python inside_track_bot.py run 4k
      python inside_track_bot.py run 4k --dry

COMMANDS
  python inside_track_bot.py calibrate [profile]  capture window -> calibrate.png
  python inside_track_bot.py probe [profile]      probe.png with boxes drawn
  python inside_track_bot.py read [profile]       one verified board read
  python inside_track_bot.py result [profile]     read the result screen
                                                  (checks the result boxes)
  python inside_track_bot.py stats                what OUR bets have
                                                  returned so far
  python inside_track_bot.py keytest [profile]    find the input target
  python inside_track_bot.py tune [profile]       ~1 min check that the
                                                  timings walk lanes
                                                  correctly
  python inside_track_bot.py budget               cycle-time / $-per-hour model
  python inside_track_bot.py [run] [profile]      run the bot

OUR OWN RECORD (race_log.csv)
  The ROI numbers above are fitted to somebody else's 547 races. Every race
  this bot runs is therefore appended to race_log.csv next to this script --
  the whole board, which lane was backed and why, the stake read back off the
  screen, and the one thing worth reading off the result screen before BET
  AGAIN is pressed (it is gone once it is): win_lane_region, the number of
  the horse that won.

  That single number is the whole result. It grades the races we LOSE as
  well, so with the full board in odds1..6 every race becomes a data point
  about which PRICE wins rather than only about us; and the payout follows
  from it by arithmetic -- stake x (odds + 1) when the winning lane is ours,
  0 when it is not -- so there is nothing to gain from OCRing the amount-won
  box as well.

  Rows are only ever appended and each run tags its own with a run_id, so
  nothing from a previous session is overwritten. `stats` reads it back: our
  ROI by horse, lane and bet size, and -- the point of the exercise -- a
  flat-bet ROI table for every price from the races themselves, which is
  what PICK_ORDER should eventually be rebuilt from. Set for the '4k'
  profile; measure the box off probe.png for any other screen.

SETUP
  pip install mss pillow numpy easyocr pydirectinput pygetwindow vgamepad
  The window must stay visible (not minimised or covered) -- capture
  reads pixels. It does NOT need to be focused in postmessage/gamepad mode.
  ScrollLock pauses the bot at any time, from any window.

NOTE: automation violates Rockstar's ToS; ban/wipe risk is real. Supervise.
"""

import csv
import ctypes
import os
import random
import re
import sys
import time
from ctypes import wintypes
from datetime import datetime

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
# calibrate.png. bet_amount_region enables max-bet OCR verification and
# win_lane_region enables result tracking -- the number of the horse that won,
# read off the result screen. Either can be None to disable that feature on a
# profile that has not been measured for it yet.
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
        # Not measured on this screen yet: run `probe main` on a result
        # screen, read the box off probe.png, and put it here to start
        # logging results from this profile too.
        "win_lane_region": None,
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
        # The lane of the horse that actually won: the one thing worth
        # reading off the result screen. It grades every race, including the
        # ~50% we lose -- which, combined with the full board in odds1..6,
        # is what lets us refit the pick order on our own data. The payout
        # box is not read at all: what it would have said is just
        # stake x (odds + 1) when this lane is ours, and 0 when it is not.
        "win_lane_region": (1405, 785, 80, 90),
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

# WHERE PRESSES ACTUALLY GET LOST
# Measured on this setup with `tune`: a repeated press inside one region is
# cheap and robust. A 5-lane walk landed 5/5 lanes on every combination
# tried, down to a 20ms hold and a 120ms press-to-press cycle. Hold length
# is simply not the lever it looks like.
#
# What does drop is the press that CROSSES A BOUNDARY, because the UI is
# animating when the next press arrives:
#   * nothing selected -> Left brings the cursor in at lane 6
#   * Cross selects the horse and the right-hand bet panel redraws
#   * Right moves from the horse column into that bet column
# Those three get `transition_gap`; everything else gets `menu_tap_gap`.
# Slowing every press to cover them is what made the old profile so slow.
#
# `race_wait` is gone: the bot now watches the picture and continues when the
# race animation stops moving, so it neither guesses nor over-waits.
# There is one set of numbers rather than a profile to pick between.
# safe/steady/fast were three guesses, and choosing between them was a coin
# toss made once and never revisited.
#
# These are trimmed deliberately hard: the crossing gap to two thirds, the lane
# walk to half, the bet spam to three quarters. Where each one now sits against
# what has actually been measured on this connection (see README-fixes.md):
#
#   lane walk    within it. A 5-lane walk landed 5/5 at a 120ms press-to-press
#                cycle; key_hold + menu_tap_gap is ~135ms.
#   crossing     thinner. The round trip post -> PS5 -> stream -> screen
#                measured 282ms, and the press now goes in ~355ms after the one
#                that started the animation. Three of the eight crossings are
#                confirmed against the picture and will retry; the other five
#                are not, and a swallowed one there desyncs the rest of the
#                sequence.
#   bet spam     just under it. ~86ms per tap, against the ~0.11s that has
#                been shown to reach $10,000 and the 30-50ms that was found to
#                drop taps -- much nearer the first than the second. It also
#                fails cheaply: verify_max_amount() reads the amount back off
#                the screen and tops it up, so the cost is seconds rather than
#                a wrong stake.
#
# Watch the log for "(cross did not register, retry 2/3)" and "(amount $X: some
# taps eaten)". Those are the early warning that a number went too far, and the
# order to give ground in is transition_gap, then menu_tap_gap.
#
# Ranges are jittered per press, so the input is not perfectly metronomic, and
# `variance` adds a further 0-50ms to every navigation gap on top of that, so
# no two cycles run to the same clock. It only ever adds delay, so it cannot
# push a gap under the band `tune` validated -- it costs about half a second a
# race and buys a rhythm that never repeats.
TIMING_NAME = "trimmed"

TIMING = {
    "menu_tap_gap": (0.05, 0.06),  # between presses inside one region
    "transition_gap": (0.4, 0.5),  # after a press that changes region
    "bet_tap_gap": (0.065, 0.07),   # between bet-increase taps
    "place_bet_gap": (0.2, 0.3),     # the Down that crosses from the bet row
                                     # into Place Bet. Its own knob rather
                                     # than transition_gap, because it is the
                                     # one crossing where the screen is known
                                     # quiet -- verify_max_amount() has just
                                     # read the amount off it -- so it can be
                                     # trimmed without loosening the earlier
                                     # crossings, which happen mid-animation
                                     # and are where presses actually drop.
                                     # Starts equal to transition_gap; take
                                     # it down and watch for "(cross did not
                                     # register" on the Place Bet press.
    "place_bet_settle": 0.0,         # stillness wait before that Place Bet
                                     # Cross. tap_confirm settles for 0 by
                                     # default now -- a still frame costs a
                                     # ~80ms capture and does not fit in its
                                     # 0.5s budget -- so this matches it and
                                     # exists to raise that ONE press if it
                                     # ever needs it. It should not: verify_
                                     # max_amount() has just read this screen,
                                     # so it is known quiet.
    "key_hold": (0.050, 0.075),      # how long each key is held. `tune`
                                     # measured a 20ms hold registering as
                                     # reliably as 220ms, so this is already
                                     # generous -- hold is not the lever it
                                     # looks like.
    "spam_hold": (0.036, 0.050),     # hold during the bet-increase spam. With
                                     # bet_tap_gap that is a ~86ms per-tap
                                     # cycle: a little under the ~0.11s shown
                                     # to reach $10,000 reliably, and well
                                     # clear of the 30-50ms that dropped taps.
    "race_wait_min": 22.0,           # never look for the result before this
    "race_wait_max": 45.0,           # give up waiting for stillness here. A
                                     # cap, not a speed knob: only a long race
                                     # ever reaches it, so trimming it just
                                     # meant walking off the result screen
                                     # mid-animation.
    "ocr_settle": 0.0,
    "variance": (0.0, 0.05),         # extra jitter on EVERY nav gap, on top
                                     # of the band's own spread. Always
                                     # applied, unlike hesitate_chance below,
                                     # so no gap is ever a round number and
                                     # the press-to-press rhythm never
                                     # repeats. Cheap: it only ever slows a
                                     # gap down, and 50ms is well inside the
                                     # bands `tune` validated. Set (0.0, 0.0)
                                     # to switch it off.
    "hesitate_chance": 0.0,          # occasional extra 0-0.5s nav pause
    "double_read": False,            # second read only if the first is weak
}

# If navigation starts desyncing, raise these in this order: transition_gap
# first, because the press after a region change is where drops actually happen
# (see above), then menu_tap_gap. `tune` checks both in about a minute.
#
# An attempt at measuring these automatically -- ramping each part of the cycle
# until it broke -- is not here, and the reason is worth recording: it has to
# score each trial by looking at the screen, and on this stream the frame-to-
# frame noise while nothing is happening came out larger than the difference
# between one highlighted lane and the next. There is nothing to measure
# against, whichever way the comparison is framed. Hence one set of numbers,
# chosen inside the bands `tune` has already validated.

# The bet-increase is 27+ presses of the same button, which is most of the
# non-race time. "hold" tries a single long press and lets the menu's own
# auto-repeat ramp the amount -- far fewer chances to drop an input, and
# verify_max_amount() checks the result either way, so trying it is cheap.
# Switch to "hold", watch the log for the amount it reaches, keep whichever
# reliably hits $10,000.
BET_INCREASE_MODE = "tap"       # "tap" | "hold"
BET_HOLD_SECONDS = 3.0


def T():
    return TIMING


# 100 -> 1000 in 100s (9 presses), 1000 -> 10000 in 500s (18 presses) = 27.
# Spare press in case a tap gets eaten; the increase caps at 10,000.
MAX_BET_PRESSES = 28
MAX_BET = 10_000
MIN_BET = 100

DRY_RUN = False       # True = decide + log only. START WITH TRUE.
DEBUG_SAVE = False    # save debug_lane*.png of each OCR input
CONF_TRUST = 0.55     # min per-lane OCR confidence to bet real money on
RECHECK_CONF = 0.80   # below this, spend a second confirming read

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


def grab_raw(region):
    """The region straight off the screen, unprocessed."""
    win = get_window()
    left, top, w, h = region
    shot = _sct.grab({"left": win.left + left, "top": win.top + top,
                      "width": w, "height": h})
    return Image.frombytes("RGB", shot.size, shot.rgb)


def grab(region, lane_no=None):
    left, top, w, h = region
    img = grab_raw(region)
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


def odds_label(value):
    """1 -> 'EVENS', 4 -> '4/1', None -> '??'."""
    if value is None:
        return "??"
    return "EVENS" if int(value) == 1 else f"{int(value)}/1"


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
    """A trusted board is complete and clears the confidence bar. Setting
    double_read demands a second, agreeing read every time; with it off that
    second read is spent only when the first one is merely adequate (below
    RECHECK_CONF), which is where most of the per-race OCR time used to go.

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


MONEY_RE = re.compile(r"\d+")


def parse_money(text):
    """'$10,000' -> 10000. Separators are stripped only where they really
    are separators (a . or , with exactly three digits behind it), so a
    comma misread as a period does not turn $10,000 into $10."""
    t = re.sub(r"[^\d.,]", "", text)
    t = re.sub(r"[.,](?=\d{3}(?:\D|$))", "", t)
    m = MONEY_RE.search(t)
    return int(m.group()) if m else None


def ocr_money(region):
    """OCR a currency box; int, or None if there is no number in it."""
    if region is None:
        return None
    results = reader().readtext(
        np.array(grab(region)), allowlist="$0123456789,.", paragraph=False
    )
    if not results:
        return None
    results.sort(key=lambda r: r[0][0][0])
    return parse_money("".join(r[1] for r in results))


def read_bet_amount():
    """OCR the current bet amount; int or None."""
    return ocr_money(profile()["bet_amount_region"])


def _isolate_digit(img):
    """Cut the lane number out of its box: (binary glyph, ink aspect w/h),
    or (None, None) if there is no glyph in there.

    Worth the trouble because of the '1'. The number sits in a white disc
    with the dark background showing in the corners, and every digit but the
    1 fills that disc. A 1 is a sliver of ink in a wide white field, which is
    exactly the shape EasyOCR's text *detector* throws away -- so the read
    came back empty and every race won by lane 1 was logged as ungraded.
    (The tell in race_log.csv: lanes 2-6 all showed up, lane 1 never did, and
    the blanks were about as many as lane 1 wins should have been.)

    Isolating the ink and re-padding it to a fixed height frames a 1 exactly
    like a 6, and the recogniser is then handed that box directly, so nothing
    depends on detection at all."""
    import cv2

    g = np.array(img.convert("L"))
    if g.mean() < 128:          # dark disc, light number
        g = 255 - g
    _, bw = cv2.threshold(g, 0, 255,
                          cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    n, _, stats, _ = cv2.connectedComponentsWithStats(bw, 8)
    h_img, w_img = bw.shape

    # The corners outside the disc are ink too. What tells them apart is that
    # each is wedged into a corner -- it runs into two perpendicular edges of
    # the box at once, which the number cannot do even when the region is
    # measured several pixels off. Take the union of everything else that is
    # digit-sized, so a glyph broken in two by antialiasing still comes out
    # whole.
    x0, y0, x1, y1 = w_img, h_img, 0, 0
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        if (x == 0 or x + w == w_img) and (y == 0 or y + h == h_img):
            continue
        if area < 20 or h < h_img * 0.25:
            continue
        x0, y0, x1, y1 = min(x0, x), min(y0, y), max(x1, x + w), max(y1, y + h)
    if x1 <= x0 or y1 <= y0:
        return None, None

    glyph = bw[y0:y1, x0:x1]
    w, h = x1 - x0, y1 - y0
    k = 64.0 / h                # the recogniser's own input height
    glyph = 255 - cv2.resize(glyph, (max(4, int(w * k)), 64),
                             interpolation=cv2.INTER_AREA)
    glyph = cv2.copyMakeBorder(glyph, 24, 24, 24, 24,
                               cv2.BORDER_CONSTANT, value=255)
    return glyph, w / h


def _ocr_lane_digit(region):
    """One read of a single-digit lane box; (lane 1-6 or None, raw text)."""
    glyph, aspect = _isolate_digit(grab_raw(region))
    if glyph is None:
        return None, "(no glyph)"
    if DEBUG_SAVE:
        Image.fromarray(glyph).save("debug_win_lane.png")
    h, w = glyph.shape
    results = reader().recognize(
        glyph, horizontal_list=[[0, w, 0, h]], free_list=[],
        allowlist="123456", detail=1, paragraph=False
    )
    results.sort(key=lambda r: r[0][0][0])
    text = "".join(r[1] for r in results).strip()
    if len(text) == 1:
        return int(text), text
    # Nothing legible, but a glyph this narrow cannot be anything but a 1 --
    # the next thinnest of 1-6 is about half again as wide.
    if aspect is not None and aspect < 0.30:
        return 1, f"{text!r} -> narrow ({aspect:.2f}), read as 1"
    return None, text


def read_win_lane(tries=4, gap=0.3):
    """OCR the lane number of the horse that actually won. Returns
    (lane 1-6 or None, last raw text). This is the whole result: it says who
    won every race rather than only whether OUR horse came in, so the races
    we lose stop being blanks in the record, and the payout follows from the
    board we already read.

    Two consecutive agreeing reads, so it is not read mid-animation.
    Ambiguous text (nothing, or more than one digit) is left as None rather
    than guessed at."""
    region = profile().get("win_lane_region")
    if region is None:
        return None, None
    prev, raw = None, None
    for i in range(tries):
        if i:
            time.sleep(gap)
        lane, raw = _ocr_lane_digit(region)
        if lane is not None and lane == prev:
            return lane, raw
        prev = lane
    return prev, raw


# --------------------------------------------------------------------------
# Race log -- our own record of what we bet and what came back
# --------------------------------------------------------------------------
# One CSV row per placed bet, appended forever. Nothing is ever overwritten:
# every run tags its rows with its own run_id, so the file accumulates across
# sessions and gets more useful as it grows. `python inside_track_bot.py
# stats` reads it back. This is the point of the whole exercise -- the
# strategy in the docstring is fitted to somebody else's 547 races, and this
# is how we replace it with our own numbers.
#
# The result is graded off the win amount on the result screen: > 0 means the
# horse came in and the row records the payout, 0 means it lost, and an
# unreadable box is logged as blank rather than guessed at.

LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "race_log.csv")

LOG_FIELDS = [
    "run_id", "ts", "profile", "strategy", "timing", "dry",
    "odds1", "odds2", "odds3", "odds4", "odds5", "odds6",
    "lane", "horse", "max_bet", "reason",
    "stake", "win_lane", "win_odds", "won", "payout", "profit",
    "trusted", "race_s", "cycle_s", "settled",
]

RUN_ID = time.strftime("%Y%m%d-%H%M%S")


def grade(odds, lane, stake, win_lane):
    """Score a race from the winning lane. Returns (won, payout), both None
    if the lane could not be read.

    The payout is computed, not observed: Inside Track pays (odds + 1) x the
    stake, so the board we already read and the lane that won are between
    them the whole result. Reading the payout box as well was a second OCR
    per race to learn a number we can multiply out."""
    if win_lane is None:
        return None, None
    won = int(win_lane == lane)
    horse = odds[lane - 1] if lane else None
    payout = stake * (horse + 1) if (won and horse and stake) else 0
    return won, payout


def _open_log():
    """Append-mode writer with the header written once. An existing file
    whose columns no longer match is renamed aside rather than appended to
    with a mismatched header, so no data is lost or silently misaligned."""
    exists = os.path.exists(LOG_PATH) and os.path.getsize(LOG_PATH) > 0
    if exists:
        with open(LOG_PATH, newline="", encoding="utf-8") as f:
            header = next(csv.reader(f), [])
        if header != LOG_FIELDS:
            backup = f"{os.path.splitext(LOG_PATH)[0]}.{RUN_ID}.old.csv"
            os.rename(LOG_PATH, backup)
            print(f"  (race log columns changed -- previous log kept as "
                  f"{os.path.basename(backup)})")
            exists = False
    fh = open(LOG_PATH, "a", newline="", encoding="utf-8")
    writer = csv.DictWriter(fh, fieldnames=LOG_FIELDS, extrasaction="ignore")
    if not exists:
        writer.writeheader()
    return fh, writer


def log_race(odds, lane, max_bet, reason, trusted, stake, win_lane,
             race_s, cycle_s, settled):
    """Append one race. Never raises into the run loop: a logging problem
    must not be able to stop the bot mid-cycle."""
    won, payout = grade(odds, lane, stake, win_lane)
    row = {
        "run_id": RUN_ID,
        "ts": datetime.now().isoformat(timespec="seconds"),
        "profile": PROFILE,
        "strategy": STRATEGY,
        "timing": TIMING_NAME,
        "dry": int(bool(DRY_RUN)),
        "lane": lane,
        "horse": odds[lane - 1] if lane else None,
        "max_bet": int(bool(max_bet)),
        "reason": reason,
        "stake": stake,
        "win_lane": win_lane,
        "win_odds": odds[win_lane - 1] if win_lane else None,
        "won": won,
        "payout": payout,
        "profit": None if payout is None else payout - stake,
        "trusted": int(bool(trusted)),
        "race_s": round(race_s, 1),
        "cycle_s": round(cycle_s, 1),
        "settled": int(bool(settled)),
    }
    for i, value in enumerate(odds, start=1):
        row[f"odds{i}"] = value
    try:
        fh, writer = _open_log()
        with fh:
            writer.writerow(row)
    except Exception as e:      # disk full, file open in Excel, ...
        print(f"  (could not write {LOG_PATH}: {e})")


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
    d += random.uniform(*T().get("variance", (0.0, 0.0)))
    if random.random() < T()["hesitate_chance"]:
        d += random.uniform(0.0, 0.5)   # human-like hesitation
    return d


def tap(key):
    if DRY_RUN:
        return
    _press(key)
    time.sleep(_gap(T()["menu_tap_gap"]))


def tap_edge(key, gap_range=None):
    """A press that moves between regions of the menu -- the cursor coming in
    at lane 6, the horse being selected, the jump across to the bet column.
    The UI animates through those, and a press arriving mid-animation is
    swallowed, which desyncs everything after it. Give them room.

    gap_range overrides transition_gap for a crossing that has its own knob."""
    if DRY_RUN:
        return
    _press(key)
    time.sleep(_gap(gap_range or T()["transition_gap"]))


_change_thr = None


def change_threshold():
    """How big a frame-to-frame difference counts as 'the UI reacted'.
    Measured once against the idle stream (the menus animate, so this is not
    zero) and cached."""
    global _change_thr
    if _change_thr is None:
        a = _frame()
        ds = []
        for _ in range(6):
            time.sleep(0.15)
            b = _frame()
            ds.append(float(np.abs(b - a).mean()))
            a = b
        # Capped: if this happens to be measured mid-animation the bar could
        # end up so high that nothing ever counts as a change. A real screen
        # change measures ~40 on this setup, so 12 leaves plenty of headroom.
        _change_thr = min(max(max(ds) * 4, sum(ds) / len(ds) + 1.5, 2.0), 12.0)
        print(f"  (screen-change threshold {_change_thr:.2f})")
    return _change_thr


def wait_still(timeout=3.0, samples=2, gap=0.14):
    """Block until the picture stops changing, or give up after `timeout`.
    Returns whether it actually went still.

    This is the precondition for measuring a press by whether the screen
    changed: while something is animating, *every* frame differs from every
    other one, so a confirm taken mid-animation passes whether or not the
    press landed."""
    thr = change_threshold()
    t0 = time.time()
    prev = _frame()
    still = 0
    while time.time() - t0 < timeout:
        time.sleep(gap)
        cur = _frame()
        if _changed(prev, cur, thr):
            still = 0
        else:
            still += 1
            if still >= samples:
                return True
        prev = cur
    return False


def tap_confirm(key, tries=3, budget=0.5, settle=0.0):
    """A press that must land, for the ones that change the whole screen.
    Presses, watches for the picture to actually change, and presses again if
    it did not. This is what stops the bot sitting on Place Bet forever
    because one Cross was swallowed.

    `budget` is the whole thing: one attempt -- settle, press and verify --
    stops at that deadline instead of each stage carrying its own generous
    timeout. A retry gets a fresh budget, so only a press that genuinely did
    not land pays more than 0.5s.

    Where the old ~1.5s went:
      * the post-change re-check slept a full transition_gap (~0.45s) before
        looking again. It tells a one-frame flicker from a real change, and
        consecutive _frame() captures are already ~80ms apart on this window,
        so that sleep was buying separation the capture cost already gives.
      * `settle` was 3s and wanted two still frames at a 0.14s poll: a ~0.45s
        floor, paid on every press, on screens that were already still.
      * the change hunt had a 2s timeout of its own. It now just runs until
        the deadline.

    Two things worth knowing before trimming `budget` further:

    The deadline governs when the polling STOPS, not the capture in flight,
    and a change seen after it has passed is accepted rather than retried. So
    a confirm can run ~0.1s over. That slack is deliberate: the round trip
    post -> PS5 -> stream -> screen measured 282ms on this connection, which
    already eats most of a 0.5s budget, and the failure mode at the bottom is
    not a slow confirm but a SECOND press -- an extra Cross on Place Bet
    lands on whatever screen comes next. Overshooting by a frame is much
    cheaper than that, and if the log fills with "did not register" the
    connection has outrun the budget: raise it, do not add retries.

    `settle` now defaults to 0. It existed because a press measured against
    an animating screen reads as landed whether or not it did -- how BET
    AGAIN once went unpressed -- but at one still frame per ~80ms capture it
    cannot fit inside this budget alongside the round trip. The guard is now
    the caller's: return_to_start() does its own generous wait_still() before
    pressing, which is the screen that actually animates.

    Returns whether it got through."""
    if DRY_RUN:
        return True
    thr = change_threshold()
    for attempt in range(tries):
        end = time.time() + budget
        if settle:
            wait_still(timeout=min(settle, budget), samples=1, gap=0.03)
        base = _frame()
        _press(key)
        while time.time() < end:
            time.sleep(0.03)
            if _changed(base, _frame(), thr):
                # Re-check, but only if the budget still has room for a
                # frame. Out of time, a single seen change counts: another
                # blind press is more expensive than a rare false positive.
                if time.time() >= end or _changed(base, _frame(), thr):
                    return True
                break        # a blip, not a screen change -- press again
        print(f"  ({key} did not register, retry {attempt + 2}/{tries})")
    return False


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
    return tap_confirm("cross")      # whole screen changes; verified


def spam_increase(n):
    if DRY_RUN:
        return
    if BET_INCREASE_MODE == "hold":
        _press("cross", hold=BET_HOLD_SECONDS)   # one press, menu auto-repeats
    else:
        for _ in range(n):
            tap_fast("cross")
    time.sleep(0.3)   # let the displayed amount settle before any read


def verify_max_amount():
    """Closed-loop check that the bet reached $10,000, correcting the two
    known slip modes. Returns the amount finally showing, or None if it
    could not be read. Needs bet_amount_region; no-op otherwise."""
    if DRY_RUN or profile()["bet_amount_region"] is None:
        return None
    for _ in range(2):
        amt = read_bet_amount()
        if amt is None:
            print("  (bet amount unreadable -- proceeding unverified)")
            return None
        if amt >= MAX_BET:
            return amt
        if amt <= MIN_BET:
            print(f"  (amount ${amt}: Right into increase was eaten -- correcting)")
            tap("right")
        else:
            print(f"  (amount ${amt}: some taps eaten -- topping up)")
        spam_increase(MAX_BET_PRESSES)
    amt = read_bet_amount()
    if amt is not None and amt < MAX_BET:
        print(f"  (WARNING: could not reach max, placing at ${amt})")
    return amt


def place_bet(lane, max_bet):
    """From the single-event screen with nothing selected. Left brings the
    cursor in at lane 6; Up walks 6 -> 1; X selects the horse. Navigate to
    the decrease-bet button (lane-dependent, see UPS_TO_DECREASE). Max bet:
    Right -> increase, X-taps to $10,000 (OCR-verified), Down -> Place Bet.
    Min bet: Down goes straight from decrease to Place Bet.

    The tap_edge() calls are the region crossings that eat presses; the Up
    walk between them is a plain tap and can stay quick. Returns
    (bet went on, stake) -- the stake read back off the screen where that is
    possible, so the log records what was really bet rather than what was
    intended."""
    tap_edge("left")                 # nothing selected -> cursor in at lane 6
    for _ in range(6 - lane):
        tap("up")                    # walking within the lane list
    tap_edge("cross")                # select horse; bet panel redraws
    tap_edge("right")                # horse column -> bet column
    for _ in range(UPS_TO_DECREASE[lane]):
        tap("up")                    # -> decrease-bet button
    stake = MAX_BET if max_bet else MIN_BET
    if max_bet:
        tap("right")                 # -> increase-bet button
        spam_increase(MAX_BET_PRESSES)
        stake = verify_max_amount() or stake
    elif not DRY_RUN:
        stake = read_bet_amount() or stake   # the skip bet, whatever it says
    # bet row -> Place Bet. A region change, so the Cross after it needs room
    # -- but this is the quiet one: the menu has been static since
    # verify_max_amount() read the amount off it, so both halves of the wait
    # get their own knob and can come down without touching the crossings
    # earlier in the walk, which happen mid-animation.
    tap_edge("down", T().get("place_bet_gap"))
    return (tap_confirm("cross", settle=T().get("place_bet_settle", 0.0)),
            stake)                   # place bet; verified, race starts


def return_to_start():
    """After the race result: Down then X selects 'BET AGAIN', returning to
    the machine start screen.

    The result screen is usually still animating when the race wait ends, and
    a press arriving mid-animation is swallowed -- which is how a cycle ends
    with the bot parked on the result screen instead of betting again. So the
    screen is allowed to settle first, generously, and the Cross is confirmed
    against a still picture. No extra Downs on the retries: the highlight is
    already in the button row and walking it again risks moving off BET
    AGAIN. Returns whether it got back."""
    if DRY_RUN:
        return True
    wait_still(timeout=10.0, samples=3)   # result screen finishes animating
    tap_edge("down")                 # highlight moves into the button row
    return tap_confirm("cross", tries=4)


def wait_for_race_end():
    """Replaces the fixed race_wait. Watches the picture and returns once the
    race animation has stopped moving, so a slow race is waited out and a
    quick one is not sat through. Returns (seconds spent, whether it really
    went still rather than hitting the cap)."""
    t = T()
    t0 = time.time()
    if DRY_RUN:
        return 0.0, True
    time.sleep(t["race_wait_min"])
    thr = change_threshold()
    prev = _frame()
    peak = 0.0
    still = 0
    settled = False
    while time.time() - t0 < t["race_wait_max"]:
        time.sleep(0.35)
        cur = _frame()
        d = float(np.abs(cur - prev).mean())
        prev = cur
        peak = max(peak, d)
        # "settled" = well below whatever motion this race actually showed,
        # so it adapts to how busy the result screen is -- but never above a
        # floor tied to the measured idle noise, because a camera cut or a
        # long straight can be quiet in relative terms while the race runs on.
        if d < max(thr * 2.0, peak * 0.12):
            still += 1
            if still >= 5:        # ~1.8s of quiet, not a one-second lull
                settled = True
                break
        else:
            still = 0
    return time.time() - t0, settled


def back_out(steps=1):
    """Circle back one screen, to the machine's start screen.

    This used to fire three unconfirmed Circles, on the theory that spare
    presses were free insurance against a swallowed one. They are not: the
    betting board is a single Circle from the start screen, so the second
    press walked the player out of the machine and the third went into the
    open world. Nothing downstream can recover from that -- the Right and
    Cross of enter_single_event() mean nothing while standing in the casino,
    so every later cycle failed too.

    The two errors are not symmetrical, and that is what sets the design.
    Backing out too far is unrecoverable. Not backing out far enough is
    self-correcting: the board read at the top of the loop fails and brings
    us straight back here. So press once, and press it as a confirmed press
    -- tap_confirm retries only when the screen did not react, which is the
    dropped-press insurance the three blind Circles were reaching for,
    without ever landing a press that was not needed.

    steps is here for a screen that really does sit deeper; raise it only
    with a specific one in mind."""
    for _ in range(steps):
        tap_confirm("circle")
    time.sleep(1.0)


def recover():
    """Back out to a known screen and come in again, rather than pressing on
    blind -- which is how a desync turns into a bet on the wrong horse.

    Only for the retry inside the read loop, which carries on reading where
    it stands. The paths that `continue` must call back_out() alone: the top
    of the loop does its own enter_single_event(), and entering twice puts a
    Right and a Cross into the board instead of the start screen."""
    print("  recovering: backing out to the machine start screen")
    back_out()
    enter_single_event()


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
    print(f"Input mode: {INPUT_MODE}   timings: {TIMING_NAME}   "
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

    races = staked = returned = wins = graded = graded_stake = 0
    t_start = time.time()
    if profile().get("win_lane_region") is None:
        print(f"NOTE: profile {PROFILE!r} has no win_lane_region, so races "
              "will be logged without a result.")
    else:
        print(f"Logging every race to {LOG_PATH} (run {RUN_ID}).")

    while True:
        wait_while_paused()
        t_race = time.time()
        ensure_window()
        enter_single_event()          # no-op in DRY_RUN

        lane = max_bet = None
        for attempt in range(4):
            time.sleep(T()["ocr_settle"])
            odds, trusted = read_board_verified()
            lane, max_bet, reason = decide(odds)
            print(f"[{time.strftime('%H:%M:%S')}] odds={odds} "
                  f"trusted={trusted} -> {reason}")
            if lane is not None and trusted:
                break
            lane = None
            # A trusted read is also the proof we are on the betting board at
            # all. Two failures in a row means we are probably somewhere else.
            if attempt == 1:
                recover()
            else:
                print("  bad/untrusted read; retrying")
        if lane is None:
            print("  board still unreadable -> skipping this cycle, "
                  "no bet placed")
            back_out()          # not recover(): the top of the loop is the
            continue            # thing that comes back in, one line below

        placed, stake = place_bet(lane, max_bet)
        if not placed:
            print("  Place Bet never registered -> recovering, no race counted")
            back_out()          # as above -- recover() here would enter the
            continue            # board twice, and the second Right + Cross
                                # would land on the board itself
        races += 1
        staked += stake
        raced, settled = wait_for_race_end()
        if not settled:
            print(f"  (race screen never went still within {raced:.0f}s -- "
                  "pressing on)")

        # Grade the race off the result screen BEFORE anything is pressed:
        # once BET AGAIN goes in, the winning lane is gone. A lane that
        # cannot be read is left blank in the log rather than guessed at --
        # a missed read and a lost bet are not the same thing once you start
        # fitting numbers to this.
        win_lane = None if DRY_RUN else read_win_lane()[0]
        won, payout = grade(odds, lane, stake, win_lane)
        if won is None:
            print("  result: UNREADABLE -- logged without a result")
        else:
            graded += 1
            graded_stake += stake
            returned += payout
            wins += won
            print(f"  result: lane {win_lane} "
                  f"({odds_label(odds[win_lane - 1])}) won -- "
                  f"{f'${payout:,} back' if won else 'lost'} "
                  f"on ${stake:,}")

        if not return_to_start():
            # The result screen is still up and the next cycle would start
            # from the wrong place. Circle out; the top of the loop comes
            # back in through enter_single_event().
            print("  BET AGAIN never registered -> backing out to the "
                  "machine start screen")
            back_out()

        cycle = time.time() - t_race
        log_race(odds, lane, max_bet, reason, trusted, stake, win_lane,
                 raced, cycle, settled)

        hours = (time.time() - t_start) / 3600
        rate = races / hours
        print(f"  bet {'MAX' if max_bet else f'${MIN_BET}'} on lane {lane} "
              f"(race #{races})  cycle {cycle:.1f}s (race {raced:.1f}s)  "
              f"rate {rate:.0f} races/h")
        if graded:
            net = returned - graded_stake
            # Only the graded races have a return, so measure the ROI over
            # what they staked -- mixing in ungraded stakes would fake a loss.
            print(f"  session: {wins}/{graded} won, ${returned:,} back, "
                  f"net ${net:+,} ({net / graded_stake * 100:+.1f}% ROI) "
                  f"-> ${net / hours:+,.0f}/h"
                  + (f"   [{races - graded} ungraded]"
                     if races > graded else ""))
        else:
            print(f"  projected ${rate * (staked / races) * 0.506:,.0f}/h "
                  "at his +50.6% ROI -- no results of our own yet")


def budget():
    """Model the cycle time from the current timing profile. The strategy is
    worth ~$4,900 a race; whether that lands in his 500-800k/h band is
    entirely a question of how many races per hour this loop manages."""
    profit_per_race = 4917.0     # measured over his 547 races, see validate.py
    print(f"Cycle-time model for the {TIMING_NAME!r} timings\n")
    for name, t in ((TIMING_NAME, TIMING),):
        hold = sum(t["key_hold"]) / 2
        var = sum(t.get("variance", (0.0, 0.0))) / 2   # every gap carries it
        plain = (hold + sum(t["menu_tap_gap"]) / 2 + var
                 + t["hesitate_chance"] * 0.25)
        edge = hold + sum(t["transition_gap"]) / 2 + var
        # 8 region crossings: enter-cross, left, select-cross, right,
        # down-to-place, place-cross, return down, return cross
        # ~5.5 ordinary taps: enter-right, up walk (avg 3), ups (avg .5),
        # right-to-increase
        # +1.5s for the three tap_confirm() round trips: each settles the
        # picture before pressing, then waits for the screen to react and
        # re-checks that the change stuck. One attempt is capped at 0.5s by
        # tap_confirm's budget and the typical one spends most of it, since
        # every stage is a _frame() capture and those measured 79ms on this
        # window. A retry, when one is needed, adds another 0.5s.
        place_edge = (hold + sum(t.get("place_bet_gap",
                                       t["transition_gap"])) / 2 + var)
        nav = 7 * edge + place_edge + 5.5 * plain + 1.5
        if BET_INCREASE_MODE == "hold":
            spam = BET_HOLD_SECONDS + 0.3
        else:
            spam = MAX_BET_PRESSES * (sum(t["spam_hold"]) / 2
                                      + sum(t["bet_tap_gap"]) / 2) + 0.3
        boards = 2.0 if t["double_read"] else 1.25   # weak reads get a recheck
        ocr = t["ocr_settle"] + boards * 0.9 + 0.35   # 6 lanes + bet amount
        race = t["race_wait_min"] + 4.0   # +detection; measured live at runtime
        total = nav + spam + ocr + race
        rate = 3600 / total
        mark = ""
        print(f"  {name:>13}: nav {nav:5.1f}s  betspam {spam:4.1f}s  "
              f"ocr {ocr:4.1f}s  race ~{race:4.1f}s  "
              f"= {total:5.1f}s/race -> {rate:5.1f} races/h "
              f"-> ${rate * profit_per_race:>9,.0f}/h{mark}")
    print("\n  His claim: 103 races/h ($506k/h). The race itself is the floor")
    print("  and is now measured rather than guessed -- the loop watches for")
    print("  the animation to stop instead of sleeping a fixed time, so the")
    print("  'race' column above is an estimate and the log has the truth.")
    print("  If the real cycle is much worse than this, the bet spam or a")
    print("  transition_gap is where the time is going.")


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


def _frame(scale=4):
    """Small greyscale-ish snapshot of the whole window, cheap enough to poll."""
    win = get_window()
    s = _sct.grab({"left": win.left, "top": win.top,
                   "width": win.width, "height": win.height})
    img = Image.frombytes("RGB", s.size, s.rgb)
    img = img.resize((img.width // scale, img.height // scale), Image.BILINEAR)
    return np.asarray(img, dtype=np.int16)


def _changed(a, b, threshold):
    return float(np.abs(a - b).mean()) > threshold


def tune():
    """Quick confidence check on the ACTIVE timing profile (about a minute).

    Park chiaki-ng on the SINGLE EVENT board with a horse highlighted. Only
    Up/Down are sent -- no confirm, so no bet can be placed. It verifies the
    two things that actually break: that a multi-lane walk lands where it was
    aimed, and that a press arriving straight after a region change is not
    swallowed. The window must be visible and unobscured; focus is not needed.

    An earlier full sweep on this setup found hold length irrelevant (20ms
    registered as reliably as 220ms) and a 5-lane walk correct at every cycle
    down to 120ms, which is why this no longer sweeps them."""
    PARK, AWAY = "up", "down"

    print("TUNE -- put chiaki-ng on the SINGLE EVENT board with a horse")
    print("highlighted. Only Up/Down are sent; no bet can be placed.")
    print("Checking the timings in TIMING. Starting in 5s...")
    print()
    time.sleep(5)

    t = T()
    hwnd = target_hwnd()

    def press(key, hold=None):
        hold = random.uniform(*t["key_hold"]) if hold is None else hold
        if INPUT_MODE == "postmessage":
            _post_key(hwnd, key, hold)
        else:
            _press(key, hold=hold)

    def step(key, n, gap=None):
        for _ in range(n):
            press(key)
            time.sleep(random.uniform(*t["menu_tap_gap"]) if gap is None else gap)

    def park():
        step(PARK, 7, gap=0.32)
        time.sleep(0.45)

    # noise floor
    noise = []
    a = _frame()
    for _ in range(8):
        time.sleep(0.15)
        c = _frame()
        noise.append(float(np.abs(c - a).mean()))
        a = c
    thr = max(max(noise) * 4, sum(noise) / len(noise) + 1.5)
    print(f"  stream noise floor {sum(noise)/len(noise):.3f}"
          f"  -> change threshold {thr:.3f}")

    # is anything getting through at all, and how long does it take to show
    park()
    lat = []
    for _ in range(3):
        base = _frame()
        t0 = time.time()
        press(AWAY, 0.18)
        while time.time() - t0 < 1.5:
            if _changed(base, _frame(), thr):
                lat.append(time.time() - t0)
                break
        time.sleep(0.4)
        step(PARK, 1, gap=0.35)
    if not lat:
        print("  !! nothing is reaching chiaki-ng. Wrong screen, wrong window,")
        print("     or the input mode is not working -- run keytest first.")
        return
    lat.sort()
    print(f"  input->screen round trip: median {lat[len(lat)//2]*1000:.0f}ms")

    # lane reference frames, so a walk can be scored against where it landed
    refs = []
    for n in range(6):
        park()
        step(AWAY, n, gap=0.38)
        time.sleep(0.5)
        refs.append(_frame())
    sep = min(float(np.abs(refs[i] - refs[j]).mean())
              for i in range(6) for j in range(i + 1, 6))
    if sep < thr:
        print(f"  !! lanes are not visually distinct (separation {sep:.3f}).")
        print("     Is the window obscured, or is this the wrong screen?")
        return

    def landed():
        cur = _frame()
        return min(range(6), key=lambda i: float(np.abs(refs[i] - cur).mean()))

    # 1. the lane walk at this profile's own pacing
    print()
    print(f"  5-lane walk at the current pacing "
          f"(hold {t['key_hold'][0]*1000:.0f}-{t['key_hold'][1]*1000:.0f}ms, "
          f"gap {t['menu_tap_gap'][0]*1000:.0f}-"
          f"{t['menu_tap_gap'][1]*1000:.0f}ms):")
    walk = []
    for _ in range(4):
        park()
        time.sleep(0.4)
        step(AWAY, 5)
        time.sleep(0.5)
        walk.append(landed())
    print(f"    landed {walk}  (want [5, 5, 5, 5])   "
          f"{'ok' if all(w == 5 for w in walk) else 'DROPPING PRESSES'}")

    # 2. the press that arrives right after a region change -- the one the
    #    lane walk depends on, and the failure this profile is shaped around
    print()
    print(f"  first press after a region change, at transition_gap "
          f"{t['transition_gap'][0]*1000:.0f}-"
          f"{t['transition_gap'][1]*1000:.0f}ms:")
    for label, gap in (("menu_tap_gap  ", sum(t["menu_tap_gap"]) / 2),
                       ("transition_gap", sum(t["transition_gap"]) / 2)):
        hits = 0
        for _ in range(4):
            park()
            time.sleep(0.4)
            press(AWAY)               # the region-change press stand-in
            time.sleep(gap)
            base = _frame()
            press(AWAY)               # the press that tends to get eaten
            time.sleep(0.55)
            hits += _changed(base, _frame(), thr)
        print(f"    waiting {gap*1000:>4.0f}ms after it: {hits}/4 registered"
              f"   {'ok' if hits == 4 else 'SWALLOWED'}")
    park()

    print()
    print("  " + "-" * 62)
    if all(w == 5 for w in walk):
        print("  These timings walk lanes correctly here.")
    else:
        print("  These timings are dropping presses. Raise transition_gap in")
        print("  TIMING first -- the press after a region change is where the")
        print("  drops happen -- then menu_tap_gap.")
    print("  If the two rows above differ, that gap is what the three")
    print("  tap_edge() calls in place_bet() exist to cover.")


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
    for key, label, colour in (
            ("bet_amount_region", "bet amount", (0, 80, 255)),
            ("win_lane_region", "win lane", (255, 200, 0))):
        box = profile().get(key)
        if box:
            l, t, w, h = box
            draw.rectangle([l, t, l + w, t + h], outline=colour, width=3)
            draw.text((l + 4, max(0, t - 16)), label, fill=colour)
    img.save("probe.png")
    print("Saved probe.png -- red boxes should sit exactly on the six odds "
          "values (blue on the bet amount). Run this again on a RESULT "
          "screen to check the yellow 'win lane' box.")


def read_result_once():
    """One read of the result screen, for checking win_lane_region without
    running the bot. Park the game on a result screen and run it."""
    ensure_window()
    time.sleep(1.0)
    if profile().get("win_lane_region") is None:
        print(f"Profile {PROFILE!r} has no win_lane_region set. Capture a "
              "result screen with `calibrate`, measure the winning-horse "
              "number box off it, and put it in PROFILES.")
        return
    t0 = time.time()
    lane, raw = read_win_lane()
    if lane is None:
        print(f"win lane: UNREADABLE (raw {raw!r}) -- the box should contain "
              "just the winning horse's number; check probe.png against a "
              "result screen.")
    else:
        print(f"win lane: {lane}")
    print(f"({time.time() - t0:.2f}s)")


def stats():
    """Read race_log.csv back: what our own bets have actually returned.
    This is the number that eventually replaces the +50.6% in the docstring,
    which was measured on somebody else's races."""
    if not os.path.exists(LOG_PATH):
        print(f"No log yet at {LOG_PATH} -- it is written as the bot runs.")
        return
    with open(LOG_PATH, newline="", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r.get("dry") != "1"]
    runs = {r["run_id"] for r in rows}
    graded = [r for r in rows if r.get("win_lane")]
    print(f"{LOG_PATH}")
    print(f"  {len(rows)} bets over {len(runs)} run(s), "
          f"{len(graded)} with a readable winning lane")
    if not graded:
        print("  Nothing graded yet -- is win_lane_region right? "
              "Check with `python inside_track_bot.py result 4k`.")
        return

    def summarise(label, group):
        stake = sum(float(r["stake"] or 0) for r in group)
        back = sum(float(r["payout"] or 0) for r in group)
        won = sum(1 for r in group if r["won"] == "1")
        roi = (back - stake) / stake * 100 if stake else 0.0
        print(f"    {label:<10} n={len(group):<5} won {won:>4} "
              f"({won / len(group) * 100:5.1f}%)  staked ${stake:>12,.0f}  "
              f"back ${back:>12,.0f}  ROI {roi:+7.1f}%")

    print()
    summarise("ALL", graded)

    def horse_label(r):
        return odds_label(int(r["horse"])) if r["horse"] else "?"

    def by_price(keys):
        return sorted(keys, key=lambda k: 1 if k == "EVENS" else
                      (int(k.split("/")[0]) if "/" in k else 99))

    print("\n  by horse backed (break-even win rate is 1/(n+1)):")
    for key in by_price({horse_label(r) for r in graded}):
        summarise(key, [r for r in graded if horse_label(r) == key])

    print("\n  by lane backed:")
    for lane in sorted({r["lane"] for r in graded if r["lane"]}, key=int):
        summarise(f"lane {lane}", [r for r in graded if r["lane"] == lane])

    print("\n  by bet size:")
    for flag, label in (("1", "max bet"), ("0", "min skip")):
        group = [r for r in graded if r["max_bet"] == flag]
        if group:
            summarise(label, group)

    recent = graded[-50:]
    if len(graded) > len(recent):
        print()
        summarise("last 50", recent)

    what_won(rows)

    ungraded = len(rows) - len(graded)
    if ungraded:
        print(f"\n  {ungraded} bet(s) logged without a result (the winning "
              "lane would not read) -- excluded from every figure above.")


def what_won(rows):
    """The table this log exists for. Every race says which PRICE won,
    whether or not we backed it, so this measures each horse the way
    validate.py measures his 547 races -- flat-bet ROI for backing that price
    every time it appears -- on boards we read ourselves."""
    board = [r for r in rows if r["win_lane"]
             and all(r[f"odds{i}"] for i in range(1, 7))]
    if not board:
        print("\n  No races with a readable winning lane yet. Set "
              "win_lane_region and check it with `result`; without it the "
              "races we LOSE teach us nothing.")
        return
    appear, won, lanes_won = {}, {}, {}
    for r in board:
        wl = int(r["win_lane"])
        lanes_won[wl] = lanes_won.get(wl, 0) + 1
        for i in range(1, 7):
            o = int(r[f"odds{i}"])
            appear[o] = appear.get(o, 0) + 1
        w = int(r[f"odds{wl}"])
        won[w] = won.get(w, 0) + 1

    print(f"\n  what actually wins ({len(board)} races, whatever we bet):")
    print(f"    {'price':<8}{'appeared':>9}{'won':>6}{'win rate':>10}"
          f"{'break-even':>12}{'flat ROI':>10}")
    for o in sorted(appear):
        n, w = appear[o], won.get(o, 0)
        print(f"    {odds_label(o):<8}{n:>9}{w:>6}{w / n * 100:>9.1f}%"
              f"{100.0 / (o + 1):>11.1f}%{(w * (o + 1) - n) / n * 100:>9.1f}%")
    print("    flat ROI = backing that price every time it appeared. This is "
          "what\n    PICK_ORDER should eventually be rebuilt from: the "
          "ordering in this file\n    is his data, not ours.")
    print("\n  winning lane: "
          + "  ".join(f"{l}: {lanes_won.get(l, 0)}" for l in range(1, 7))
          + f"   (an even split would be {len(board) / 6:.0f} each)")


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
                "probe": probe, "keytest": keytest, "budget": budget,
                "tune": tune, "result": read_result_once, "stats": stats}
    # No default mode: a bare `python inside_track_bot.py` used to start
    # betting real money, which is one stray Enter away from an accident.
    if not sys.argv[1:]:
        print(__doc__.split("COMMANDS")[1].split("OUR OWN RECORD")[0].strip())
        print("\nName a command explicitly -- 'run' included.")
        sys.exit(2)
    mode = None
    for a in sys.argv[1:]:
        flag = a.lstrip("-")
        if a in COMMANDS:
            mode = a
        elif a in PROFILES:            # screen profile: main / 4k
            PROFILE = a
        elif flag in ("fast", "steady", "safe"):
            print(f"There are no timing profiles any more: {flag!r} was one of "
                  f"three guesses.")
            print("There is one set of numbers in TIMING, near the top of this "
                  "file; `tune` checks")
            print("them and `budget` models what they cost.")
            sys.exit(1)
        elif flag in ("dry", "dry-run"):
            DRY_RUN = True
        elif flag in ("chart", "pickorder"):
            STRATEGY = flag
        else:
            print(f"Unknown argument {a!r}\n"
                  f"  commands: {'/'.join(COMMANDS)}\n"
                  f"  screens:  {'/'.join(PROFILES)}\n"
                  f"  other:    --dry, --chart, --pickorder")
            sys.exit(1)
    if mode is None:
        print(f"No command given (one of: {'/'.join(COMMANDS)}).")
        sys.exit(2)
    COMMANDS[mode]()
