"""Command line.

One command, then options -- no positional profile names, and no flag whose
job was to pick between three timing guesses. Everything the old CLI could
do is still here, with `calibrate` folded into `probe` (which saves both
images).

Where the boxes are lives in `insidetrack.toml`, not in the source. `setup`
writes one by asking you to point at them; every other command reads it.

    python -m insidetrack setup                   measure the boxes, once
    python -m insidetrack run --screen 4k
    python -m insidetrack run --dry
    python -m insidetrack read --screen 4k        the betting board
    python -m insidetrack result --screen 4k      the result screen
    python -m insidetrack probe --screen 4k
"""

import argparse
from typing import Callable, Dict, Optional, Sequence

from . import console, diagnostics, stats, userconfig, wizard
from .app import App, build, preflight
from .screen import WindowMissing
from .tuning import tune
from .userconfig import ConfigError

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

# `setup` runs before there is a config to build an App from, so it is not
# in COMMANDS -- main() dispatches it directly.
SETUP = "setup"

HELP = {
    SETUP: "measure this screen's boxes and write insidetrack.toml",
    "run": "place bets until stopped (ScrollLock pauses)",
    "read": "one board read, and what the strategy would do with it",
    "result": "read the winning lane off a result screen",
    "probe": "save calibrate.png and probe.png to check the boxes",
    "keys": "find which window chiaki-ng takes input on",
    "tune": "check the timings against the real menu (~1 min)",
    "budget": "model cycle time and $/hour from the timings",
    "stats": "what our own logged bets have returned",
}

CHOICES = sorted(COMMANDS) + [SETUP]


def parser() -> argparse.ArgumentParser:
    epilog = "\n".join(f"  {name:<7} {HELP[name]}" for name in sorted(CHOICES))
    parsed = argparse.ArgumentParser(
        prog="insidetrack",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="GTA Online Inside Track auto-bettor (PS5 via chiaki-ng). "
                    "Start with `setup`.",
        epilog="commands:\n" + epilog)
    parsed.add_argument("command", choices=sorted(CHOICES), metavar="command",
                        help="one of: " + ", ".join(sorted(CHOICES)))
    # Free-form rather than a choices= list: the names come from the user's
    # own config file, which has not been read at the time the parser is
    # built, and `setup` uses it to name a screen that does not exist yet.
    parsed.add_argument("--screen", metavar="NAME", default=None,
                        help="which screen layout's boxes to use "
                             "(default: the config's default_screen)")
    parsed.add_argument("--config", metavar="PATH", default=None,
                        help=f"path to {userconfig.CONFIG_NAME} "
                             "(default: the first one found next to you)")
    parsed.add_argument("--dry", action="store_true",
                        help="decide and log, send no input")
    parsed.add_argument("--strategy", choices=userconfig.STRATEGIES,
                        default=None,
                        help="chart is kept for comparison; it loses "
                             "out-of-sample")
    parsed.add_argument("--input-mode", choices=userconfig.INPUT_MODES,
                        default=None, dest="input_mode",
                        help="override the config's input mode for this run")
    parsed.add_argument("--debug-images", action="store_true",
                        help="save what the recogniser was given")
    parsed.add_argument("--no-colour", "--no-color", action="store_true",
                        dest="no_colour",
                        help="plain text, no ANSI colour (also honours the "
                             "NO_COLOR environment variable, and turns "
                             "itself off when output is piped to a file)")
    setup = parsed.add_argument_group("setup only")
    setup.add_argument("--point", action="store_true",
                       help="hover the live screen and press F8, instead of "
                            "clicking on a captured still (chiaki-ng hides "
                            "the cursor over its own window, so this is "
                            "usually harder)")
    setup.add_argument("--manual", action="store_true",
                       help="type coordinates read off a saved screenshot")
    setup.add_argument("--example", action="store_true",
                       help=f"just copy {userconfig.EXAMPLE_NAME} and stop, "
                            "to fill in by hand")
    setup.add_argument("--window", metavar="TITLE", default=None,
                       help="part of the stream window's title, if it is not "
                            "'chiaki'")
    return parsed


def settings_from(args: argparse.Namespace, config: userconfig.UserConfig):
    return config.settings(
        args.screen, strategy=args.strategy, input_mode=args.input_mode,
        dry_run=args.dry or None, debug_save=args.debug_images or None)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parser().parse_args(argv)
    if args.no_colour:
        console.disable()
    if args.command == SETUP:
        return wizard.run(args)
    try:
        config = userconfig.load(args.config)
        COMMANDS[args.command](build(settings_from(args, config)), args)
    except ConfigError as bad:
        print(bad)
        return 2
    except WindowMissing as missing:
        print(missing)
        return 2
    except KeyboardInterrupt:
        print("\nstopped")
    return 0
