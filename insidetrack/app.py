"""Composition root: builds the object graph for one run.

Nothing else in the package constructs its own collaborators, so a test or a
tool can hand any of them a stub -- a fake Screen, a scripted Ocr -- without
the code under test knowing.
"""

from dataclasses import dataclass

from .backends import make_backend
from .board import BoardReader
from .config import POST_TARGET_INDEX, TIMING_NAME, WINDOW_TITLE, Settings
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
    screen = Screen(WINDOW_TITLE)
    ocr = Ocr()
    board = BoardReader(screen, ocr, settings)
    backend = make_backend(settings.input_mode, screen.window,
                           POST_TARGET_INDEX)
    keys = Controller(backend, screen, settings.timing, settings.dry_run)
    machine = Machine(keys, board, screen, settings)
    log = RaceLog(settings, timing_name=TIMING_NAME)
    return App(settings, screen, ocr, board, keys, machine, log)


def preflight(app: App) -> None:
    """Say which backend is about to be used, and warn about the setups that
    let a virtual pad leak into other windows."""
    print(f"Input mode: {app.settings.input_mode}   timings: {TIMING_NAME}   "
          f"strategy: {app.settings.strategy}")
    print("  " + app.keys.backend.describe())
