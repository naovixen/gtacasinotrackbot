"""Colour and alignment for everything the bot prints.

The run loop is the thing you actually watch: several lines a race, for
hours, and the useful signal in them is small and repetitive -- did the
board read, did the bet go on, did it win, is the session up. Plain text
makes you read all of it to find any of it. A grid and a little colour make
the answer a glance. Both live here, so every module prints the same way.

Windows needs asking. Its console understands ANSI escapes but starts with
them switched off, so a raw escape prints as literal `[32m` garbage; one
SetConsoleMode call turns them on, and it is done once, lazily, the first
time anything wants a colour. That covers PowerShell in both hosts --
Windows Terminal and the older conhost -- and costs nothing on anything
else.

Colour is dropped whenever it would be noise rather than signal: piped or
redirected output, NO_COLOR set (no-color.org), or --no-colour. Only the
eight basic colours are used, never 256-colour or RGB, so the output sits
inside whatever theme the terminal already has instead of fighting it.
"""

import ctypes
import os
import sys
import textwrap
from ctypes import wintypes
from typing import Optional

# -11 as a DWORD. It is passed to an API that takes an unsigned value, and
# ctypes will not narrow a negative int into one for us.
_STD_OUTPUT_HANDLE = 0xFFFFFFF5
_ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004

RESET = "\033[0m"
STYLES = {
    "bold": "\033[1m",
    "dim": "\033[2m",
    "red": "\033[31m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "blue": "\033[34m",
    "magenta": "\033[35m",
    "cyan": "\033[36m",
    "grey": "\033[90m",
}

_enabled: Optional[bool] = None


def _enable_windows_vt() -> bool:
    """Ask the Windows console to interpret escapes rather than print them.

    The argtypes matter here. A HANDLE is pointer-sized, and ctypes defaults
    an unannotated return to a 32-bit int, which on 64-bit Python truncates
    it -- so the handle would be passed on to GetConsoleMode as a different
    number than the one that came back.
    """
    if os.name != "nt":
        return True
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetStdHandle.argtypes = [wintypes.DWORD]
        kernel32.GetStdHandle.restype = wintypes.HANDLE
        kernel32.GetConsoleMode.argtypes = [wintypes.HANDLE,
                                            ctypes.POINTER(wintypes.DWORD)]
        kernel32.GetConsoleMode.restype = wintypes.BOOL
        kernel32.SetConsoleMode.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel32.SetConsoleMode.restype = wintypes.BOOL

        handle = kernel32.GetStdHandle(_STD_OUTPUT_HANDLE)
        mode = wintypes.DWORD()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False                       # redirected: not a console
        if mode.value & _ENABLE_VIRTUAL_TERMINAL_PROCESSING:
            return True                        # Windows Terminal, usually
        return bool(kernel32.SetConsoleMode(
            handle, mode.value | _ENABLE_VIRTUAL_TERMINAL_PROCESSING))
    except Exception:
        return False


def enabled() -> bool:
    """Whether to colour at all. Decided once, then cached."""
    global _enabled
    if _enabled is None:
        _enabled = _decide()
    return _enabled


def _decide() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        _enable_windows_vt()        # best effort; emit either way
        return True
    try:
        if not sys.stdout.isatty():            # piped, redirected, captured
            return False
    except Exception:
        return False
    return _enable_windows_vt()


def disable() -> None:
    """--no-colour, and anything else that wants plain text."""
    global _enabled
    _enabled = False


def paint(text: str, *styles: str) -> str:
    """`text` wrapped in the named styles, or unchanged if colour is off.

    Unknown names are ignored rather than raised on, so a caller can pass a
    style through as data -- which is how the grid tints a tag.
    """
    if not styles or not enabled():
        return text
    codes = "".join(STYLES[style] for style in styles if style in STYLES)
    return f"{codes}{text}{RESET}" if codes else text


# --------------------------------------------------------------------------
# The vocabulary the rest of the package prints in. Named for what a line
# MEANS rather than for a colour, so the palette is decided in one place and
# a caller never has to remember whether a warning is yellow.

def head(text: str) -> str:
    """A heading, or the first line of a command's output."""
    return paint(text, "bold")


def good(text: str) -> str:
    """It worked, or we are up."""
    return paint(text, "green")


def bad(text: str) -> str:
    """It failed, or we are down."""
    return paint(text, "red")


def warn(text: str) -> str:
    """Recoverable, and worth noticing: a retry, an unread, a fallback."""
    return paint(text, "yellow")


def note(text: str) -> str:
    """Present but not the point -- timestamps, units, asides."""
    return paint(text, "grey")


def key(text: str) -> str:
    """The number the eye is looking for on that line."""
    return paint(text, "cyan")


def money(amount: int, signed: bool = False) -> str:
    """An amount, coloured by which way it went. Signed for a net or a
    profit, plain for a stake -- a stake is not a loss.

    No currency symbol. Every figure the bot prints is in the same chips,
    so a $ on each of them is a column of noise that says nothing, and it
    pushes the digits out of line the moment a sign appears next to it.
    """
    body = f"{abs(amount):,}"
    if not signed:
        return body if amount >= 0 else f"-{body}"
    if amount > 0:
        return good(f"+{body}")
    if amount < 0:
        return bad(f"-{body}")
    return body


# --------------------------------------------------------------------------
# The output grid
#
# Every line the bot prints sits on it: a timestamp, a tag naming the kind of
# line, then values in cells of one uniform width. Uniform matters -- with
# per-column widths the price on a `bet` row landed a character left of the
# prices on the `board` row above it, and the block read as ragged even
# though each row was internally correct.
#
# It lives here rather than in the loop because the loop is not the only
# thing that prints. A retry from the controller or a recovery from the
# machine is part of the same stream, and a line that ignores the grid is
# exactly the line that draws the eye for the wrong reason.

TIME_W = 10         # '21:04:12' and its gap
TAG_W = 9           # 'session', 'warning' and 'recover' tie at 7, plus a gap
CELL = 8            # 'lane 1' is the widest cell value, plus a two-space gap
LANES = 6
PRICE_W = 5         # 'EVENS' is the longest price there is

# A full board row is the widest line the grid can produce, so it is what
# everything else is allowed to reach: five padded cells and a sixth that is
# only as long as the price in it, since nothing pads the last one. A message
# longer than that wraps rather than running off past the block and dragging
# the eye out with it.
LINE_W = TIME_W + TAG_W + (LANES - 1) * CELL + PRICE_W
BODY_W = LINE_W - TIME_W - TAG_W


def row(tag: str, body: str = "", stamp: str = "",
        tag_style: str = "grey") -> str:
    """One line on the grid.

    Right-trimmed: the last cell on a line is padded like every other one,
    and that padding only exists to hold up a column that is not coming.
    """
    stamp = paint(stamp, "grey") if stamp else ""
    return (pad(stamp, TIME_W) + paint(pad(tag, TAG_W), tag_style)
            + body).rstrip()


def message(tag: str, text: str, tint=None, tag_style: str = "grey") -> str:
    """A sentence on the grid, wrapped to the grid's width and carrying its
    tag on the first line only.

    Wrapped before it is coloured, never after: a line broken in the middle
    of an escape sequence prints the escape.
    """
    tint = tint or (lambda value: value)
    lines = textwrap.wrap(text, BODY_W) or [""]
    return "\n".join(
        [row(tag, tint(lines[0]), tag_style=tag_style)]
        + [row("", tint(rest), tag_style=tag_style) for rest in lines[1:]])


def cells(*pairs) -> str:
    """Values laid into grid cells: either a string, or (string, cells) to
    span more than one. Colour is not counted towards the width."""
    out = []
    for pair in pairs:
        text, span = pair if isinstance(pair, tuple) else (pair, 1)
        out.append(pad(text, CELL * span))
    return "".join(out)


def warn_row(text: str, tag: str = "warning") -> str:
    """A warning, on the grid, with the tag in the same colour as the
    message -- so it reads as one thing that is not the normal flow."""
    return message(tag, text, warn, "yellow")


def bad_row(text: str, tag: str = "error") -> str:
    return message(tag, text, bad, "red")


# --------------------------------------------------------------------------
# The startup block
#
# Not on the grid, and deliberately so. The grid exists to be scanned down a
# column; this is a handful of settings read once, where a line per setting
# with its own label is simply easier to read than a table of one row each.

# Tied to the timestamp column rather than measured off the labels, so the
# settings values start exactly where a race line's tag does and the two
# blocks share their spacing as well as their left edge. The longest labels,
# 'race end' and 'strategy', are 8 -- which is the timestamp's own width, so
# they keep a two-space gap without being cramped.
LABEL_W = TIME_W


def setting(label: str, value: str = "", note: str = "") -> str:
    """One setting: `label   value`, with any explanation as small print
    under the value rather than trailing off the end of the line.

    Flush left, where a race line's timestamp starts, so the block hangs off
    the same edge as everything printed after it.
    """
    lines = [pad(paint(label, "grey"), LABEL_W) + value]
    indent = " " * LABEL_W
    for line in textwrap.wrap(note, LINE_W - LABEL_W) if note else []:
        lines.append(indent + paint(line, "grey"))
    return "\n".join(line.rstrip() for line in lines)


def width(text: str) -> int:
    """Printable width, ignoring any escapes -- for lining columns up."""
    if "\033" not in text:
        return len(text)
    out, index = 0, 0
    while index < len(text):
        if text[index] == "\033":
            index = text.find("m", index) + 1 or len(text)
            continue
        out += 1
        index += 1
    return out


def pad(text: str, columns: int, right: bool = False) -> str:
    """Pad to a column count that the escapes do not count towards."""
    spaces = " " * max(0, columns - width(text))
    return spaces + text if right else text + spaces
