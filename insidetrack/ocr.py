"""The recogniser, wrapped so the rest of the bot never imports easyocr.

The important choice here is recognize() over readtext(). readtext() runs the
CRAFT text *detector* first to find where the words are -- but we already
know: the boxes are calibrated. Measured on six odds boxes, detector-and-
recognise took 1041ms against 138ms for recognition alone, and the detector
was also what lost a lone '1' (see vision.digit_candidates).

Detection is kept as a fallback for a box that will not parse, so the old
path is still there for the reads that need it.
"""

import warnings
from typing import List, Sequence, Tuple

import numpy as np

# EasyOCR pulls in torch, which announces a deprecation in its own internals
# when it loads and a pin_memory notice on every recognition pass. Neither is
# actionable from here and both land in the middle of the race log, so they
# are silenced by message rather than by category -- anything else torch has
# to say still gets through.
warnings.filterwarnings("ignore", message=r".*quantize_per_tensor.*")
warnings.filterwarnings("ignore", message=r".*pin_memory.*")

Read = Tuple[str, float]        # (text, confidence 0..1)

ODDS_CHARS = "EVENS0123456789/"
MONEY_CHARS = "$0123456789,."
DIGIT_CHARS = "123456"


class Ocr:
    """Lazily-loaded EasyOCR. Construct freely; the model loads on first use."""

    def __init__(self, gpu: bool = True):
        self._gpu = gpu
        self._reader = None

    def reader(self):
        if self._reader is None:
            import easyocr
            self._reader = easyocr.Reader(["en"], gpu=self._gpu, verbose=False)
        return self._reader

    @staticmethod
    def _join(results: Sequence) -> Read:
        """Left-to-right into one string, with the weakest confidence."""
        if not results:
            return "", 0.0
        ordered = sorted(results, key=lambda r: r[0][0][0])
        text = "".join(str(r[1]) for r in ordered)
        return text, min(float(r[2]) for r in ordered)

    def read_boxes(self, canvas: np.ndarray,
                   boxes: Sequence[Tuple[int, int, int, int]],
                   allowlist: str) -> List[Read]:
        """One recognition pass over a column of boxes, in the order given.

        Results are matched back by the y they came from, not by the order
        they arrive in, so a lane can never be credited with another lane's
        text.
        """
        raw = self.reader().recognize(
            canvas, horizontal_list=[list(b) for b in boxes], free_list=[],
            allowlist=allowlist, detail=1, paragraph=False,
            batch_size=max(1, len(boxes)))
        by_top = {}
        for box, text, confidence in raw:
            by_top.setdefault(int(box[0][1]), []).append((box, text, confidence))
        return [self._join(by_top.get(top, [])) for _, _, top, _ in boxes]

    def read_image(self, image: np.ndarray, allowlist: str) -> Read:
        height, width = image.shape[:2]
        return self.read_boxes(image, [(0, width, 0, height)], allowlist)[0]

    def detect_and_read(self, image: np.ndarray, allowlist: str) -> Read:
        """The slow path: find the text, then read it. For a box that would
        not parse, where the extra second is worth not guessing."""
        return self._join(self.reader().readtext(
            image, allowlist=allowlist, paragraph=False))

    def read_glyph(self, glyph: np.ndarray) -> Read:
        """A single isolated digit, handed straight to the recogniser."""
        height, width = glyph.shape[:2]
        text, confidence = self.read_boxes(glyph, [(0, width, 0, height)],
                                           DIGIT_CHARS)[0]
        return text.strip(), confidence
