"""Our own record: one CSV row per placed bet, appended forever.

The ROI numbers in strategy.py are fitted to somebody else's 547 races. This
is how they get replaced with ours. Nothing is ever overwritten -- each run
tags its rows with a run_id -- and the row carries the whole board, so the
races we LOSE are data too: every race says which PRICE won, not just
whether we were on it.
"""

import csv
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Sequence

from .config import Settings
from .strategy import grade

FIELDS = [
    "run_id", "ts", "profile", "strategy", "timing", "dry",
    "odds1", "odds2", "odds3", "odds4", "odds5", "odds6",
    "lane", "horse", "max_bet", "reason",
    "stake", "win_lane", "win_odds", "won", "payout", "profit",
    "trusted", "race_s", "cycle_s", "settled",
]

DEFAULT_PATH = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "race_log.csv")


@dataclass
class Race:
    """One placed bet and how it turned out."""

    odds: Sequence[Optional[int]] = field(default_factory=list)
    lane: Optional[int] = None
    max_bet: bool = False
    reason: str = ""
    trusted: bool = False
    stake: Optional[int] = None
    win_lane: Optional[int] = None
    race_s: float = 0.0
    cycle_s: float = 0.0
    settled: bool = False


class RaceLog:
    """Append-only writer. Never raises into the run loop: a logging problem
    must not be able to stop the bot mid-cycle."""

    def __init__(self, settings: Settings, path: str = DEFAULT_PATH,
                 timing_name: str = "trimmed"):
        self._settings = settings
        self._path = path
        self._timing_name = timing_name
        self.run_id = time.strftime("%Y%m%d-%H%M%S")

    @property
    def path(self) -> str:
        return self._path

    def append(self, race: Race) -> None:
        try:
            handle, writer = self._open()
            with handle:
                writer.writerow(self._row(race))
        except Exception as error:      # disk full, file open in Excel, ...
            print(f"  (could not write {self._path}: {error})")

    def _row(self, race: Race) -> dict:
        row = dict(self._identity(), **self._bet(race), **self._result(race))
        for index, value in enumerate(race.odds, start=1):
            row[f"odds{index}"] = value
        return row

    def _identity(self) -> dict:
        return {
            "run_id": self.run_id,
            "ts": datetime.now().isoformat(timespec="seconds"),
            "profile": self._settings.profile,
            "strategy": self._settings.strategy,
            "timing": self._timing_name,
            "dry": int(bool(self._settings.dry_run)),
        }

    @staticmethod
    def _bet(race: Race) -> dict:
        return {
            "lane": race.lane,
            "horse": race.odds[race.lane - 1] if race.lane else None,
            "max_bet": int(bool(race.max_bet)),
            "reason": race.reason,
            "stake": race.stake,
            "trusted": int(bool(race.trusted)),
            "race_s": round(race.race_s, 1),
            "cycle_s": round(race.cycle_s, 1),
            "settled": int(bool(race.settled)),
        }

    @staticmethod
    def _result(race: Race) -> dict:
        won, payout = grade(race.odds, race.lane, race.stake, race.win_lane)
        return {
            "win_lane": race.win_lane,
            "win_odds": race.odds[race.win_lane - 1] if race.win_lane else None,
            "won": won,
            "payout": payout,
            "profit": None if payout is None else payout - (race.stake or 0),
        }

    def _open(self):
        """Append mode, header written once. A file whose columns no longer
        match is renamed aside rather than appended to with a mismatched
        header, so no data is lost or silently misaligned."""
        exists = (os.path.exists(self._path)
                  and os.path.getsize(self._path) > 0)
        if exists and self._header() != FIELDS:
            backup = f"{os.path.splitext(self._path)[0]}.{self.run_id}.old.csv"
            os.rename(self._path, backup)
            print(f"  (race log columns changed -- previous log kept as "
                  f"{os.path.basename(backup)})")
            exists = False
        handle = open(self._path, "a", newline="", encoding="utf-8")
        writer = csv.DictWriter(handle, fieldnames=FIELDS,
                                extrasaction="ignore")
        if not exists:
            writer.writeheader()
        return handle, writer

    def _header(self):
        with open(self._path, newline="", encoding="utf-8") as handle:
            return next(csv.reader(handle), [])


def load(path: str = DEFAULT_PATH):
    """Every non-dry row ever logged."""
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as handle:
        return [row for row in csv.DictReader(handle) if row.get("dry") != "1"]
