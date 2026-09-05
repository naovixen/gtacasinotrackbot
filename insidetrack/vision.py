"""Turning a captured box into something the recogniser can read.

Pure numpy/cv2 and pure functions: no capture, no OCR, no state.

The thing that matters most here is framing. The recogniser scales whatever
it is handed to a 64-pixel-tall input, so if the text is a third of the box
the glyphs arrive about 20 pixels tall and thin ones stop being themselves --
13/1 came back as 19/1, 3/1 as 9/1. Handing over a box cropped to the ink
instead makes the glyphs fill the input, and on a live board that is the
difference between four lanes of six and all six, at a tenth of the cost of
letting a text detector find them.
"""

from typing import List, Optional, Sequence, Tuple

import cv2
import numpy as np

Bounds = Tuple[int, int, int, int]      # x0, y0, x1, y1

OCR_HEIGHT = 150        # binarise the odds boxes at this height
GLYPH_HEIGHT = 64       # the recogniser's own input height
PAD = 24                # white border, so nothing sits on an edge
INK_MARGIN = 0.12       # border round cropped ink, as a fraction of its height
MIN_INK_AREA = 20       # smaller than this is a speck, not a stroke
DIGIT_ASPECT_MAX = 0.85  # 1-6 are all taller than they are wide -- the
                         # widest measured 0.47 -- and the diamond they sit
                         # in measures 1.00, which is what this cut is for
_LUMA = np.array([0.299, 0.587, 0.114], dtype=np.float32)   # PIL's weights


def to_grey(rgb: np.ndarray) -> np.ndarray:
    if rgb.ndim == 2:
        return rgb.astype(np.float32)
    return rgb[:, :, :3].astype(np.float32) @ _LUMA


def stretch(grey: np.ndarray) -> np.ndarray:
    """Autocontrast: pull the darkest pixel to 0 and the brightest to 255."""
    low, high = float(grey.min()), float(grey.max())
    if high - low < 1.0:
        return np.zeros_like(grey)
    return (grey - low) * (255.0 / (high - low))


def as_dark_on_white(grey: np.ndarray) -> np.ndarray:
    """The game draws light text on dark and dark text on light depending on
    the panel; the recogniser wants one of them. Count, do not average: a
    thin glyph on a big field moves the mean far less than it moves nothing.
    """
    if int((grey < 128).sum()) > int((grey >= 128).sum()):
        return 255.0 - grey
    return grey


def pad(image: np.ndarray, border: int = PAD) -> np.ndarray:
    return cv2.copyMakeBorder(image, border, border, border, border,
                              cv2.BORDER_CONSTANT, value=255)


def scale_to_height(image: np.ndarray, height: int) -> np.ndarray:
    """Upscale only -- shrinking text to fit a target loses strokes."""
    if image.size == 0:
        raise ValueError("empty capture: the region falls outside the "
                         "window -- wrong --screen profile, or the window "
                         "has been moved or resized since it was calibrated")
    factor = max(1.0, height / float(image.shape[0]))
    if factor == 1.0:
        return image
    size = (max(16, int(image.shape[1] * factor)),
            max(16, int(image.shape[0] * factor)))
    return cv2.resize(image, size, interpolation=cv2.INTER_LANCZOS4)


def binarise(rgb: np.ndarray, height: int = OCR_HEIGHT) -> np.ndarray:
    """A captured box as black ink on white, at a workable size."""
    grey = to_grey(scale_to_height(rgb, height))
    grey = as_dark_on_white(stretch(grey))
    return np.where(grey > 150, 255, 0).astype(np.uint8)


def _ink_boxes(binary: np.ndarray, min_height: float) -> List[Sequence[int]]:
    """Connected strokes worth keeping: big enough, tall enough."""
    mask = (binary < 128).astype(np.uint8)
    count, _, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    tall_enough = min_height * binary.shape[0]
    return [stats[i] for i in range(1, count)
            if stats[i][4] >= MIN_INK_AREA and stats[i][3] >= tall_enough]


def _touches_edge(box: Sequence[int], shape) -> bool:
    x, y, width, height = box[0], box[1], box[2], box[3]
    return (x == 0 or y == 0
            or x + width == shape[1] or y + height == shape[0])


def ink_bounds(binary: np.ndarray, min_height: float = 0.15,
               interior: bool = False,
               aspect_max: Optional[float] = None) -> Optional[Bounds]:
    """Box round the ink, or None if there is nothing usable in there.

    `interior` drops anything touching the edge of the crop. That is what
    separates a lane number from what surrounds it: the digit sits inside its
    badge, while the card behind it and the badge's own border both run off
    the side of the box.
    """
    boxes = _ink_boxes(binary, min_height)
    if interior:
        boxes = [b for b in boxes if not _touches_edge(b, binary.shape)]
    if not boxes:
        return None
    x0 = int(min(b[0] for b in boxes))
    y0 = int(min(b[1] for b in boxes))
    x1 = int(max(b[0] + b[2] for b in boxes))
    y1 = int(max(b[1] + b[3] for b in boxes))
    if aspect_max is not None and (x1 - x0) > (y1 - y0) * aspect_max:
        return None
    return x0, y0, x1, y1


def frame_ink(binary: np.ndarray, bounds: Bounds,
              height: int = GLYPH_HEIGHT,
              margin: Optional[float] = None) -> Tuple[np.ndarray, float]:
    """Crop to the ink and scale it to the recogniser's own height, so the
    glyphs fill the input whatever size the box was. Returns (image, aspect).
    """
    x0, y0, x1, y1 = bounds
    margin = INK_MARGIN if margin is None else margin
    ink = binary[y0:y1, x0:x1]
    factor = height / float(y1 - y0)
    ink = cv2.resize(ink, (max(4, int((x1 - x0) * factor)), height),
                     interpolation=cv2.INTER_AREA)
    return pad(ink, max(2, int(height * margin))), (x1 - x0) / float(y1 - y0)


def prepare_text(rgb: np.ndarray, height: int = OCR_HEIGHT) -> np.ndarray:
    """A captured box -> what the recogniser should see: the text, cropped
    to itself, on a white border."""
    binary = binarise(rgb, height)
    bounds = ink_bounds(binary)
    if bounds is None:            # nothing legible; let the recogniser say so
        return pad(binary)
    return frame_ink(binary, bounds)[0]


def digit_candidates(rgb: np.ndarray) -> List[Tuple[np.ndarray, float]]:
    """The lane number, read both ways round: [(image, aspect)].

    A lane number is a small dark digit on a coloured badge -- red, yellow,
    green, white, gold on the winner's card -- sometimes filling the box and
    sometimes floating in the dark card behind it. Deciding the polarity from
    the average brightness gets that wrong whenever the surround outweighs
    the badge, which is how the reader ended up with no glyph at all on half
    the screens. So both polarities are prepared and the caller picks whichever
    the recogniser is more confident about; it costs one extra ~20ms read.
    """
    grey = stretch(to_grey(rgb)).astype(np.uint8)
    found = []
    for mode in (cv2.THRESH_BINARY_INV, cv2.THRESH_BINARY):
        _, otsu = cv2.threshold(grey, 0, 255, mode | cv2.THRESH_OTSU)
        binary = 255 - otsu                    # ink black, like the text path
        bounds = ink_bounds(binary, interior=True, aspect_max=DIGIT_ASPECT_MAX)
        if bounds is None:
            bounds = ink_bounds(binary, aspect_max=DIGIT_ASPECT_MAX)
        if bounds is not None:
            found.append(frame_ink(binary, bounds))
    return found


def stack(images, gap: int = PAD):
    """Lay images out in one column: (canvas, [(x0, x1, y0, y1), ...]).

    One call into the recogniser instead of six. The boxes come back keyed by
    their y position, so a lane is identified by where it sits rather than by
    trusting the order results arrive in.
    """
    width = max(image.shape[1] for image in images)
    height = sum(image.shape[0] for image in images) + gap * (len(images) - 1)
    canvas = np.full((height, width), 255, np.uint8)
    boxes, top = [], 0
    for image in images:
        rows, cols = image.shape
        canvas[top:top + rows, 0:cols] = image
        boxes.append((0, cols, top, top + rows))
        top += rows + gap
    return canvas, boxes


# --------------------------------------------------------------------------
# The result screen's title banner
#
# Stillness is a bad proxy for "the race is over". The camera holds on the
# horses for somewhere between half a second and three seconds after the
# finish, so a quiet-frames test either fires on that hold or has to be
# pushed out past the worst case -- which is what race_wait_min was really
# paying for.
#
# The banner is the opposite kind of signal: it is only ever on screen when
# the result screen is, it looks the same every race, and the two things
# that DO differ from race to race -- which horse won and what the bet paid
# -- are nowhere near it. So it is matched by colour rather than by OCR:
# "RESULTS" in flat yellow on a near-black panel is two pixel counts, about
# a millisecond, against ~20ms and a confidence to second-guess for a read.

BANNER_DARK_MAX = 70        # every channel below this is panel, not backdrop
BANNER_DARK_MIN = 0.55      # panel, as a fraction of the box
BANNER_YELLOW_MIN = 0.02    # some lettering, or it is a plain black panel
BANNER_YELLOW_MAX = 0.45    # and not so much that the box is mostly ink

# The lettering. The last two terms are what keep the orange backdrop out:
# it is red enough to pass the first, but its green channel is far too low,
# and its lighter bands run orange rather than yellow -- red and green a
# long way apart.
_YELLOW_RED_MIN = 140
_YELLOW_GREEN_MIN = 110
_YELLOW_BLUE_MAX = 100
_YELLOW_SPREAD_MIN = 90     # red over blue
_YELLOW_BALANCE_MAX = 90    # red against green


def banner_fractions(rgb: np.ndarray) -> Tuple[float, float]:
    """(dark fraction, yellow fraction) of a captured box."""
    pixels = rgb[:, :, :3].astype(np.int16)
    red, green, blue = pixels[..., 0], pixels[..., 1], pixels[..., 2]
    dark = pixels.max(axis=2) < BANNER_DARK_MAX
    yellow = ((red > _YELLOW_RED_MIN) & (green > _YELLOW_GREEN_MIN)
              & (blue < _YELLOW_BLUE_MAX)
              & (red - blue > _YELLOW_SPREAD_MIN)
              & (np.abs(red - green) < _YELLOW_BALANCE_MAX))
    return float(dark.mean()), float(yellow.mean())


def is_banner(dark: float, yellow: float) -> bool:
    """Do those fractions say the result screen's title panel is showing?"""
    return (dark >= BANNER_DARK_MIN
            and BANNER_YELLOW_MIN <= yellow <= BANNER_YELLOW_MAX)
