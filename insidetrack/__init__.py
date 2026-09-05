"""GTA Online Inside Track auto-bettor (PS5 via chiaki-ng Remote Play).

    python -m insidetrack run --screen 4k

The package is layered so each piece can be tested without the game:
    config      screen profiles, timings, run settings -- data only
    screen      capture and "has the picture stopped moving?"
    vision      numpy preprocessing of a captured box
    ocr         the recogniser, wrapped
    parsing     text -> odds, money, lane numbers
    board       what the bot learns by looking
    backends    ways of getting a keypress to the PS5
    controller  how long to hold, how long to wait, did it land
    machine     the betting machine as a sequence of screens
    strategy    which horse, and what the race was worth
    racelog     our own record; stats reads it back
    loop        the race cycle
    app         composition root; cli, diagnostics, tuning are the commands

NOTE: automation violates Rockstar's ToS; ban/wipe risk is real. Supervise.
"""

from .config import PROFILES, Settings, Timing
from .strategy import decide, grade

__all__ = ["PROFILES", "Settings", "Timing", "decide", "grade"]
