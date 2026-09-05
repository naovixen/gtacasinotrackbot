"""Reading the betting board, the stake and the result.

The costly part of a cycle used to be here: six calls into readtext(), each
running the text detector over a box whose position was already known and
calibrated. This reads all six lanes in one recognition pass over a single
stacked canvas -- about 130ms against 1040ms -- and falls back to detection
only for a lane whose text will not parse.
"""

import time
from typing import Dict, List, Optional, Sequence, Tuple

from . import console, paths
from . import ocr as ocr_module
from . import vision
from .config import CONF_TRUST, RECHECK_CONF, Settings
from .parsing import parse_money, read_odds_text

LaneRead = Tuple[Optional[int], float, str]     # (odds, confidence, raw text)

# How much better the second reading of a badge has to be to win.
POLARITY_MARGIN = 0.05


class BoardReader:
    """Everything the bot learns by looking, for one screen profile."""

    def __init__(self, screen, ocr: ocr_module.Ocr, settings: Settings):
        self._screen = screen
        self._ocr = ocr
        self._settings = settings

    @property
    def _profile(self):
        return self._settings.board

    def _lane_image(self, lane: int):
        region = self._profile.odds_regions[lane - 1]
        image = vision.prepare_text(self._screen.grab(region))
        if self._settings.debug_save:
            _save(image, f"debug_lane{lane}.png")
        return image

    def read_lanes(self, lanes: Sequence[int]) -> Dict[int, LaneRead]:
        """One recognition pass over the given lanes."""
        images = [self._lane_image(lane) for lane in lanes]
        canvas, boxes = vision.stack(images)
        reads = self._ocr.read_boxes(canvas, boxes, ocr_module.ODDS_CHARS)
        return {lane: self._interpret(image, text, confidence)
                for lane, image, (text, confidence)
                in zip(lanes, images, reads)}

    def _interpret(self, image, text: str, confidence: float) -> LaneRead:
        """Parse a lane's text, spending a detector pass only if it fails."""
        value, raw, repaired = read_odds_text(text)
        if value is None:
            text, confidence = self._ocr.detect_and_read(
                image, ocr_module.ODDS_CHARS)
            value, raw, repaired = read_odds_text(text)
            raw = f"{raw} (detector)"
        if value is not None and repaired:
            raw = f"{raw} -> repaired {repaired}"
        return value, confidence, raw or "(nothing)"

    def read_odds(self, verbose: bool = False):
        """(odds for lanes 1-6, per-lane confidence)."""
        lanes = list(range(1, len(self._profile.odds_regions) + 1))
        reads = self.read_lanes(lanes)
        if verbose:
            _report(reads)
        return ([reads[lane][0] for lane in lanes],
                [reads[lane][1] for lane in lanes])

    def read_verified(self, verbose: bool = False):
        """(odds, trusted). A trusted board is complete, clears the
        confidence bar, and -- for any lane that only just cleared it --
        reads the same twice.

        Only the doubtful lanes are read again. Re-reading all six to settle
        one of them was most of the OCR time in a cycle, and a lane that came
        back at 0.95 was never the one in question. A failed first read is
        never rescued: the caller retries the whole cycle, which also gives
        the screen time to settle.
        """
        odds, confidence = self.read_odds(verbose=verbose)
        if not confidence or any(v is None for v in odds):
            return odds, False
        if min(confidence) < CONF_TRUST:
            return odds, False
        doubtful = self._doubtful_lanes(odds, confidence)
        return odds, self._agrees(odds, doubtful)

    def _doubtful_lanes(self, odds, confidence) -> List[int]:
        if self._settings.timing.double_read:
            return list(range(1, len(odds) + 1))
        return [lane for lane, value in enumerate(confidence, start=1)
                if value < RECHECK_CONF]

    def _agrees(self, odds: Sequence[Optional[int]], lanes: List[int]) -> bool:
        if not lanes:
            return True
        second = self.read_lanes(lanes)
        return all(second[lane][0] == odds[lane - 1]
                   and second[lane][1] >= CONF_TRUST for lane in lanes)

    @property
    def can_see_result_screen(self) -> bool:
        """Has this screen profile been measured for the banner at all? If
        not, the race wait has nothing to watch for and falls back."""
        return self._profile.result_banner_region is not None

    def sees_result_screen(self) -> bool:
        """Is the result screen's title banner showing right now?

        This is what ends the race wait. One small grab and two pixel
        counts -- 7ms measured, against 30ms for a single full-window
        stillness frame -- so it can be asked thirty times a second, and
        unlike stillness it answers the question actually being asked. The
        camera holding on the horses for two seconds after the finish is
        quiet and is not the result screen; the result screen fading in is
        busy and is.
        """
        signature = self.result_signature()
        return signature is not None and signature[2]

    def result_signature(self):
        """(dark fraction, yellow fraction, matched) for the banner box, or
        None if this screen has no result_banner box measured. Exposed for
        `insidetrack result`, which is how you check the box is on it."""
        region = self._profile.result_banner_region
        if region is None:
            return None
        dark, yellow = vision.banner_fractions(self._screen.grab(region))
        return dark, yellow, vision.is_banner(dark, yellow)

    def read_bet_amount(self) -> Optional[int]:
        """The stake showing on screen, or None if there is no box for it."""
        region = self._profile.bet_amount_region
        if region is None:
            return None
        image = vision.prepare_text(self._screen.grab(region))
        text, _ = self._ocr.read_image(image, ocr_module.MONEY_CHARS)
        return parse_money(text)

    def read_win_lane(self, tries: int = 3, gap: float = 0.15):
        """The lane of the horse that won: (lane 1-6 or None, raw text).

        This is the whole result -- it grades the races we lose as well, so
        with the board we already read every race becomes a data point about
        which PRICE wins rather than only about us.

        It used to demand two agreeing reads 0.3s apart, to avoid reading
        mid-animation. The caller now proves the screen has stopped moving
        before asking, so a second read of identical pixels only cost time.
        Ambiguous text is left as None rather than guessed at.
        """
        region = self._profile.win_lane_region
        if region is None:
            return None, None
        raw = None
        for attempt in range(tries):
            if attempt:
                time.sleep(gap)
            lane, raw = self._read_digit(region)
            if lane is not None:
                return lane, raw
        return None, raw

    def _read_digit(self, region):
        """One read of the lane-number badge: (lane 1-6 or None, raw text)."""
        candidates = vision.digit_candidates(self._screen.grab(region))
        if not candidates:
            return None, "(no glyph)"
        confidence, digit, text, aspect = self._best_digit(candidates)
        if digit is not None:
            return int(digit), f"{digit} (conf {confidence:.2f})"
        # Nothing legible, but a glyph this narrow cannot be anything but a
        # 1 -- the next thinnest of 1-6 is about half again as wide.
        if aspect < 0.30:
            return 1, f"{text!r} -> narrow ({aspect:.2f}), read as 1"
        return None, text

    def _best_digit(self, candidates):
        """Whichever way round the badge was read, take the one the
        recogniser actually believes.

        The dark-ink reading comes first and keeps its lead unless the other
        beats it clearly: every lane number in the game is dark on a light
        badge, and the light-ink reading is the one that occasionally finds a
        confident digit in a shadow.
        """
        best = (-1.0, None, "", 1.0)
        for index, (glyph, aspect) in enumerate(candidates):
            if self._settings.debug_save:
                _save(glyph, f"debug_win_lane{index}.png")
            text, confidence = self._ocr.read_glyph(glyph)
            digit = text if len(text) == 1 and text.isdigit() else None
            score = confidence if digit else -1.0
            if score > best[0] + POLARITY_MARGIN:
                best = (confidence, digit, text, aspect)
        return best


def _report(reads: Dict[int, LaneRead]) -> None:
    from .parsing import odds_label
    for lane in sorted(reads):
        value, confidence, raw = reads[lane]
        extra = f"  raw={raw!r}" if value is None or "repaired" in raw else ""
        label = odds_label(value)
        label = console.bad(label) if value is None else console.key(label)
        print(f"  lane {lane}: {console.pad(label, 7)}"
              + console.note(f"(conf {confidence:.2f})")
              + console.warn(extra))


def _save(image, name: str) -> None:
    from PIL import Image
    Image.fromarray(image).save(paths.out_path(name))
