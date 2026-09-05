"""Composition root: builds the object graph for one run.

Nothing else in the package constructs its own collaborators, so a test or a
tool can hand any of them a stub -- a fake Screen, a scripted Ocr -- without
the code under test knowing.
"""

from dataclasses import dataclass

from . import console
from .backends import make_backend
from .board import BoardReader
from .config import TIMING_NAME, Settings
from .controller import Controller
from .loop import Bot
from .machine import Machine
from .ocr import Ocr
from .racelog import RaceLog
from .screen import Screen


@dataclass
class App:
    settings: Settings
    screen: Screen
    ocr: Ocr
    board: BoardReader
    keys: Controller
    machine: Machine
    log: RaceLog

    def bot(self) -> Bot:
        return Bot(self.settings, self.screen, self.board, self.machine,
                   self.log)


def build(settings: Settings) -> App:
    screen = Screen(settings.window_title)
    ocr = Ocr()
    board = BoardReader(screen, ocr, settings)
    backend = make_backend(settings.input_mode, screen.window,
                           settings.post_target_index)
    keys = Controller(backend, screen, settings.timing, settings.dry_run)
    machine = Machine(keys, board, screen, settings)
    log = RaceLog(settings, timing_name=TIMING_NAME)
    return App(settings, screen, ocr, board, keys, machine, log)


def preflight(app: App) -> None:
    """The settings this run starts with: one line each, with anything that
    needs explaining as small print under the value.

    Deliberately not on the output grid the race lines use. That grid is
    built to be scanned down a column for hours; this is a handful of facts
    read once before anything starts, and a labelled line each is simply
    easier to read than a table of one row apiece.

    Only the settings themselves. What the backend has to say about itself
    is troubleshooting for a first run -- which HWND, what to do if the menu
    does not move -- and it printed in full before every run thereafter. The
    two backends that carry a real caution rather than a description still
    get one: a virtual pad is system-wide and keyboard mode types into
    whatever is focused, and neither is something to find out by accident.
    """
    settings, profile = app.settings, app.settings.board
    print()
    print(console.setting("profile", settings.profile))
    print(console.setting("strategy", settings.strategy))
    print(console.setting("timings", TIMING_NAME))
    print(console.setting("input", settings.input_mode,
                          "" if settings.input_mode == "postmessage"
                          else app.keys.backend.describe()))
    if profile.win_lane_region is None:
        print(console.setting("log", console.warn("not graded"),
                              "no win_lane box measured, so races are logged "
                              "without a result and `stats` has nothing to "
                              "report"))
    else:
        print(console.setting("log", str(app.log.path)))
    if profile.result_banner_region is not None:
        print(console.setting("race end", "on the RESULTS banner"))
    else:
        print(console.setting("race end", console.warn("on stillness"),
                              "no result_banner box measured, so the end of "
                              "a race is guessed at from the picture going "
                              "still; `insidetrack result` measures one"))
    if settings.dry_run:
        print(console.setting("dry run", console.warn("no input is sent"),
                              "open the SINGLE EVENT screen by hand so the "
                              "reads can see the board"))
    print(console.setting("keys", "ScrollLock pauses, Ctrl-C stops"))
    print()
