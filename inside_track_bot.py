"""GTA Online Inside Track auto-bettor -- entry point.

The bot itself lives in the `insidetrack` package now; this file is the way
in, and the compatibility surface for validate.py, which imports it to score
the shipped strategy against the 547-race log.

    python inside_track_bot.py setup              measure the boxes, first
    python inside_track_bot.py run --screen 4k
    python inside_track_bot.py result --screen 4k
    python inside_track_bot.py probe --screen 4k
    python inside_track_bot.py --help

Start with `setup`: where the odds and the stake sit on screen are pixel
coordinates in your own chiaki-ng window, so they live in insidetrack.toml
rather than in the source, and setup measures them for you.

The old positional forms (`run 4k fast`) are gone: the screen is --screen,
and there are no timing profiles to choose between any more. See
insidetrack/cli.py for the full list of commands.

NOTE: automation violates Rockstar's ToS; ban/wipe risk is real. Supervise.
"""

import sys
from typing import Optional, Sequence

from insidetrack.cli import main
from insidetrack.strategy import (CHART_NO1, CHART_NO12, CHART_NO123,
                                  LANE_TIEBREAK, PICK_ORDER, SKIP_LANE, grade)
from insidetrack.strategy import decide as _decide

__all__ = ["decide", "grade", "STRATEGY", "PICK_ORDER", "LANE_TIEBREAK",
           "SKIP_LANE", "CHART_NO1", "CHART_NO12", "CHART_NO123", "main"]

# validate.py sets this on the module and then calls decide(); the package
# takes the strategy as an argument instead, so this is the bridge.
STRATEGY = "pickorder"


def decide(odds: Sequence[Optional[int]]):
    """(lane, max_bet, reason) under the strategy this module is set to."""
    return _decide(odds, STRATEGY)


if __name__ == "__main__":
    sys.exit(main())
