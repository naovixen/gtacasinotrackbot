"""Command line.

One command, then options -- no positional profile names, and no flag whose
job was to pick between three timing guesses. Everything the old CLI could
do is still here, with `calibrate` folded into `probe` (which saves both
images).

    python -m insidetrack run --screen 4k
    python -m insidetrack run --dry
    python -m insidetrack read --screen 4k        the betting board
    python -m insidetrack result --screen 4k      the result screen
    python -m insidetrack probe --screen 4k
"""

import argparse
from typing import Callable, Dict, Optional, Sequence

from . import diagnostics, stats
from .app import App, build, preflight
from .config import DEFAULT_PROFILE, PROFILES, Settings
from .screen import WindowMissing
from .tuning import tune

Command = Callable[[App, argparse.Namespace], None]


def _run(app: App, _args) -> None:
    preflight(app)
    app.bot().run()


COMMANDS: Dict[str, Command] = {
    "run": _run,                                    # bet, until stopped
    "read": lambda app, _: diagnostics.read_board(app),    # the betting board
    "result": lambda app, _: diagnostics.read_result(app),  # who won
    "probe": lambda app, _: diagnostics.probe(app),  # calibrate + probe .png
    "keys": lambda app, _: diagnostics.keys(app),   # which window takes input
    "tune": lambda app, _: tune(app),               # do the timings hold up
    "budget": lambda app, _: diagnostics.budget(app),   # cycle time model
    "stats": lambda app, _: stats.report(),         # what our bets returned
}

HELP = {
    "run": "place bets until stopped (ScrollLock pauses)",
    "read": "one board read, and what the strategy would do with it",
    "result": "read the winning lane off a result screen",
    "probe": "save calibrate.png and probe.png to check the boxes",
    "keys": "find which window chiaki-ng takes input on",
    "tune": "check the timings against the real menu (~1 min)",
    "budget": "model cycle time and $/hour from the timings",
    "stats": "what our own logged bets have returned",
}


def parser() -> argparse.ArgumentParser:
    epilog = "\n".join(f"  {name:<7} {HELP[name]}" for name in sorted(COMMANDS))
    parsed = argparse.ArgumentParser(
        prog="insidetrack", formatter_class=argparse.RawDescriptionHelpFormatter,
        description="GTA Online Inside Track auto-bettor (PS5 via chiaki-ng).",
        epilog="commands:\n" + epilog)
    parsed.add_argument("command", choices=sorted(COMMANDS), metavar="command",
                        help="one of: " + ", ".join(sorted(COMMANDS)))
    parsed.add_argument("--screen", choices=sorted(PROFILES),
                        default=DEFAULT_PROFILE,
                        help="which screen profile's boxes to use")
    parsed.add_argument("--dry", action="store_true",
                        help="decide and log, send no input")
    parsed.add_argument("--strategy", choices=("pickorder", "chart"),
                        default="pickorder",
                        help="chart is kept for comparison; it loses "
                             "out-of-sample")
    parsed.add_argument("--debug-images", action="store_true",
                        help="save what the recogniser was given")
    return parsed


def settings_from(args: argparse.Namespace) -> Settings:
    return Settings(profile=args.screen, strategy=args.strategy,
                    dry_run=args.dry, debug_save=args.debug_images)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parser().parse_args(argv)
    try:
        COMMANDS[args.command](build(settings_from(args)), args)
    except WindowMissing as missing:
        print(missing)
        return 2
    except KeyboardInterrupt:
        print("\nstopped")
    return 0
