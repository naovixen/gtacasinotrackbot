"""Where the project keeps things, so no module has to guess.

Three of these matter. `ROOT` is the checkout; `DATA` holds race_log.csv,
the one file we generate and keep; `OUT` holds the ones we generate and
throw away -- the calibration captures, the setup wizard's shots, the debug
crops. OUT is gitignored precisely because everything in it is a
by-product: delete it and the next `probe` or `setup` writes it again.

These are absolute, anchored on this file, so the bot writes to the same
places whichever directory you happen to launch it from. That is the point:
diagnostics used to save calibrate.png into the current working directory,
which meant the file you were told to measure the boxes off could land
anywhere.
"""

import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
OUT = os.path.join(ROOT, "out")


def out_path(name: str) -> str:
    """Absolute path to `name` inside out/, creating out/ if it is missing."""
    os.makedirs(OUT, exist_ok=True)
    return os.path.join(OUT, name)


def data_path(name: str) -> str:
    """Absolute path to `name` in data/, creating data/ if it is missing."""
    os.makedirs(DATA, exist_ok=True)
    return os.path.join(DATA, name)
