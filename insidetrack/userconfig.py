"""The user's own config file: where the boxes are, and what to talk to.

The regions are pixel coordinates inside one particular chiaki-ng window at
one particular size, so they cannot ship with the code -- they are the one
thing every new setup has to measure for itself. They live in
`insidetrack.toml`, which is not committed; `insidetrack.example.toml` is
the committed template, and `python -m insidetrack setup` writes a real one
by asking you to point at the boxes on screen.

Reading is tomllib (stdlib). Writing is the little emitter at the bottom --
a config is a handful of scalars and integer boxes, and keeping comments in
the file we generate is worth more than a dependency.
"""

import os
import tomllib
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from .config import DEFAULT_WINDOW_TITLE, Profile, Region, Settings, Timing

CONFIG_NAME = "insidetrack.toml"
EXAMPLE_NAME = "insidetrack.example.toml"
ENV_VAR = "INSIDETRACK_CONFIG"

LANES = 6
INPUT_MODES = ("postmessage", "gamepad", "keyboard")
STRATEGIES = ("pickorder", "chart")

_PACKAGE_ROOT = Path(__file__).resolve().parent.parent


class ConfigError(RuntimeError):
    """Anything that stops us getting a usable config: missing, or wrong."""


@dataclass(frozen=True)
class UserConfig:
    """One config file, parsed and checked."""

    path: Optional[Path] = None
    window_title: str = DEFAULT_WINDOW_TITLE
    input_mode: str = "postmessage"
    post_target_index: Optional[int] = None
    strategy: str = "pickorder"
    default_screen: str = "main"
    screens: Mapping[str, Profile] = field(default_factory=dict)
    timing: Timing = field(default_factory=Timing)

    def screen(self, name: Optional[str]) -> str:
        """Resolve a --screen argument against what the file actually has."""
        wanted = name or self.default_screen
        if wanted in self.screens:
            return wanted
        known = ", ".join(sorted(self.screens)) or "(none)"
        raise ConfigError(
            f"No screen named {wanted!r} in {self.path}. It has: {known}.\n"
            f"Add one with `python -m insidetrack setup --screen {wanted}`.")

    def settings(self, screen: Optional[str] = None, **overrides) -> Settings:
        """A Settings for one run: the file, then anything the CLI overrode."""
        base = Settings(
            profile=self.screen(screen), screens=dict(self.screens),
            window_title=self.window_title, input_mode=self.input_mode,
            post_target_index=self.post_target_index, strategy=self.strategy,
            timing=self.timing)
        return replace(base, **{key: value for key, value in overrides.items()
                                if value is not None})


# --------------------------------------------------------------------------
# Finding and loading


def search_path(explicit: Optional[str] = None) -> List[Path]:
    """Where a config may live, best first.

    The working directory comes before the checkout, so one copy of this
    tool can be driven from two directories with two different windows'
    boxes without either overwriting the other.
    """
    if explicit:
        return [Path(explicit).expanduser()]
    found = []
    if os.environ.get(ENV_VAR):
        found.append(Path(os.environ[ENV_VAR]).expanduser())
    found.append(Path.cwd() / CONFIG_NAME)
    found.append(_PACKAGE_ROOT / CONFIG_NAME)
    found.append(Path.home() / f".{CONFIG_NAME}")
    seen, unique = set(), []
    for path in found:
        if path not in seen:
            seen.add(path)
            unique.append(path)
    return unique


def find(explicit: Optional[str] = None) -> Path:
    for path in search_path(explicit):
        if path.is_file():
            return path
    raise ConfigError(_missing_message(search_path(explicit)))


def example_path() -> Path:
    return _PACKAGE_ROOT / EXAMPLE_NAME


def default_target() -> Path:
    """Where `setup` writes when it is not told otherwise."""
    return Path.cwd() / CONFIG_NAME


def _missing_message(looked: Sequence[Path]) -> str:
    where = "\n".join(f"    {path}" for path in looked)
    return (
        "No config file found.\n\n"
        "The screen regions -- where the odds, the stake and the winning\n"
        "lane sit inside the chiaki-ng window -- depend on your window size,\n"
        "so they are not shipped with the code. Either:\n\n"
        "    python -m insidetrack setup\n"
        "        measures them on screen, ~2 minutes -- start here\n\n"
        "    python -m insidetrack setup --example\n"
        f"        drops {CONFIG_NAME} next to you to fill in by hand\n\n"
        f"Looked in:\n{where}")


def load(explicit: Optional[str] = None) -> UserConfig:
    path = find(explicit)
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as error:
        raise ConfigError(f"{path} is not valid TOML: {error}") from error
    except OSError as error:
        raise ConfigError(f"could not read {path}: {error}") from error
    try:
        return parse(raw, path)
    except ConfigError as error:
        raise ConfigError(f"{path}: {error}") from error


def parse(raw: Mapping[str, Any], path: Optional[Path] = None) -> UserConfig:
    screens = {name: _profile(name, block)
               for name, block in _table(raw, "screens").items()}
    if not screens:
        raise ConfigError(
            "no [screens.<name>] section. Run `python -m insidetrack setup`, "
            f"or copy the boxes out of {EXAMPLE_NAME}.")
    default = raw.get("default_screen") or sorted(screens)[0]
    if default not in screens:
        raise ConfigError(
            f"default_screen = {default!r} is not one of the screens defined "
            f"({', '.join(sorted(screens))}).")
    return UserConfig(
        path=path,
        window_title=str(raw.get("window_title", DEFAULT_WINDOW_TITLE)),
        input_mode=_choice(raw, "input_mode", INPUT_MODES, "postmessage"),
        post_target_index=_target_index(raw.get("post_target_index")),
        strategy=_choice(raw, "strategy", STRATEGIES, "pickorder"),
        default_screen=default,
        screens=screens,
        timing=_timing(_table(raw, "timing")))


def _table(raw: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = raw.get(key, {})
    if not isinstance(value, dict):
        raise ConfigError(f"[{key}] should be a table, not {type(value)}.")
    return value


def _choice(raw: Mapping[str, Any], key: str,
            allowed: Sequence[str], fallback: str) -> str:
    value = str(raw.get(key, fallback))
    if value not in allowed:
        raise ConfigError(
            f"{key} = {value!r} is not one of {', '.join(allowed)}.")
    return value


def _target_index(value) -> Optional[int]:
    """0 and "auto" both mean the top-level window, which is None inside."""
    if value in (None, 0, "", "auto"):
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ConfigError(
            "post_target_index should be a window number from "
            "`python -m insidetrack keys` (1, 2, 3...), or 0 for the "
            "top-level window.")
    return value


def _timing(block: Mapping[str, Any]) -> Timing:
    """Timing defaults, with whatever [timing] overrode.

    The shape of each setting is taken from its own default rather than from
    its annotation: a band is a pair, and everything else is the scalar it
    already is. That way adding a setting to Timing needs nothing here.
    """
    defaults = Timing()
    values = {}
    for key, value in block.items():
        if not hasattr(defaults, key):
            raise ConfigError(
                f"[timing] has no setting called {key!r}. Known: "
                f"{', '.join(sorted(Timing.__dataclass_fields__))}.")
        values[key] = _timing_value(key, getattr(defaults, key), value)
    return Timing(**values)


def _timing_value(key: str, default, value):
    where = f"timing.{key}"
    if isinstance(default, tuple):
        pair = _numbers(where, value)
        if len(pair) != 2:
            raise ConfigError(
                f"[timing] {key} is a pair: [min, max] seconds.")
        return (pair[0], pair[1])
    if isinstance(value, bool) != isinstance(default, bool):
        raise ConfigError(
            f"[timing] {key} should be "
            f"{'true or false' if isinstance(default, bool) else 'a number'}, "
            f"not {value!r}.")
    if isinstance(default, bool):
        return bool(value)
    if not isinstance(value, (int, float)):
        raise ConfigError(f"[timing] {key} should be a number, not {value!r}.")
    return int(value) if isinstance(default, int) else float(value)


# --------------------------------------------------------------------------
# Screens


def _profile(name: str, block: Mapping[str, Any]) -> Profile:
    if not isinstance(block, dict):
        raise ConfigError(f"[screens.{name}] should be a table.")
    where = f"screens.{name}"
    _check_keys(where, block)
    odds = _odds_source(where, block)
    return Profile(
        odds_regions=_odds(where, odds),
        bet_amount_region=_optional_region(f"{where}.bet_amount",
                                           block.get("bet_amount")),
        win_lane_region=_optional_region(f"{where}.win_lane",
                                         block.get("win_lane")))


SCREEN_KEYS = {"odds", "bet_amount", "win_lane"}


def _check_keys(where: str, block: Mapping[str, Any]) -> None:
    unknown = [key for key in block
               if key not in SCREEN_KEYS and not _is_lane_key(key)]
    if unknown:
        raise ConfigError(
            f"[{where}] has {', '.join(sorted(unknown))}; the keys are "
            f"{', '.join(sorted(SCREEN_KEYS))} and odds_lane1..odds_lane"
            f"{LANES}.")


def _is_lane_key(key: str) -> bool:
    return key.startswith("odds_lane") and key[len("odds_lane"):].isdigit()


def _odds_source(where: str, block: Mapping[str, Any]):
    """The odds boxes, however they were written.

    `odds_lane1 = {...}` sits flat in the screen's own table rather than in
    an [screens.x.odds] sub-table, because in TOML every key after a
    sub-table header belongs to it -- so a bet_amount written underneath one
    would silently become part of the odds. Flat keys have no order to get
    wrong.
    """
    flat = {key[len("odds_"):]: value for key, value in block.items()
            if _is_lane_key(key)}
    listed = block.get("odds")
    if listed is not None and flat:
        raise ConfigError(
            f"[{where}] has both odds and odds_lane* -- use one or the "
            "other.")
    if listed is None and not flat:
        raise ConfigError(f"[{where}] has no odds boxes. See {EXAMPLE_NAME}.")
    return _odds(where, listed if listed is not None else flat)


def _odds(where: str, value) -> Sequence[Region]:
    """Six lane boxes, from however few of them were written down.

    A list of six boxes is taken as-is. The table form -- lane1 = {...} --
    only needs the lanes you could be bothered to measure: one full box for
    the size, plus any second lane to fix the spacing, with the rest spaced
    evenly between. The lanes are evenly stacked on this board, so measuring
    lane 1 and lane 6 puts five times less error into the middle four than
    stepping down from lane 1 to lane 2 would.
    """
    if isinstance(value, list):
        boxes = [_region(f"{where}.odds[{index}]", item)
                 for index, item in enumerate(value, start=1)]
        if len(boxes) != LANES:
            raise ConfigError(
                f"[{where}] odds needs {LANES} boxes, got {len(boxes)}.")
        return boxes
    if not isinstance(value, dict):
        raise ConfigError(f"[{where}] odds should be a list of six boxes, or "
                          f"odds_lane1..odds_lane{LANES} keys.")
    return _interpolate_lanes(where, value)


def _interpolate_lanes(where: str, table: Mapping[str, Any]) -> List[Region]:
    known: Dict[int, Tuple[int, int, Optional[int], Optional[int]]] = {}
    for key, item in table.items():
        lane = int(key[len("lane"):])
        if not 1 <= lane <= LANES:
            raise ConfigError(
                f"[{where}] odds_{key} is outside lane 1..{LANES}.")
        known[lane] = _point_or_region(f"{where}.odds_{key}", item)
    if not known:
        raise ConfigError(f"[{where}] has no odds lanes.")
    size = next(((w, h) for _, _, w, h in known.values() if w and h), None)
    if size is None:
        raise ConfigError(
            f"[{where}] needs at least one complete odds box (a width and "
            "height, or a bottom-right corner) to size the others from.")
    if len(known) == 1:
        raise ConfigError(
            f"[{where}] only has odds_lane{next(iter(known))}. Add a second "
            f"lane -- odds_lane{LANES} gives the best spacing -- and the "
            "lanes between the two are filled in evenly.")
    return _straight_line(known, size)


def even_lanes(lane1: Region, last_lane: int,
               last_top_left: Tuple[int, int]) -> List[Region]:
    """The six boxes from lane 1's box and one lower lane's top-left corner.

    What `setup` measures, and what the lane1/lane6 table form expands to.
    """
    left, top, width, height = lane1
    known = {1: (left, top, width, height),
             last_lane: (last_top_left[0], last_top_left[1], None, None)}
    return _straight_line(known, (width, height))


def _straight_line(known, size) -> List[Region]:
    """Fit left/top against lane number through the lanes we were given."""
    width, height = size
    first, last = min(known), max(known)
    span = last - first
    boxes = []
    for lane in range(1, LANES + 1):
        if lane in known:
            left, top = known[lane][0], known[lane][1]
        else:
            fraction = (lane - first) / span
            left = round(known[first][0]
                         + (known[last][0] - known[first][0]) * fraction)
            top = round(known[first][1]
                        + (known[last][1] - known[first][1]) * fraction)
        boxes.append((left, top, width, height))
    return boxes


def _optional_region(where: str, value) -> Optional[Region]:
    return None if value is None else _region(where, value)


def _region(where: str, value) -> Region:
    """A box, either [left, top, width, height] or a corners table."""
    left, top, width, height = _point_or_region(where, value)
    if not width or not height:
        raise ConfigError(
            f"[{where}] needs a full box: either [left, top, width, height], "
            "or { left = .., top = .., right = .., bottom = .. }.")
    return (left, top, width, height)


def _point_or_region(where: str, value):
    """(left, top, width or None, height or None) -- a corner is allowed."""
    if isinstance(value, dict):
        return _corners(where, value)
    numbers = _numbers(where, value)
    if len(numbers) == 2:
        return (int(numbers[0]), int(numbers[1]), None, None)
    if len(numbers) == 4:
        return tuple(int(number) for number in numbers)
    raise ConfigError(f"[{where}] should be [left, top, width, height] "
                      "(or [left, top] for a lane's corner alone).")


def _corners(where: str, table: Mapping[str, Any]):
    allowed = {"left", "top", "right", "bottom", "width", "height"}
    unknown = set(table) - allowed
    if unknown:
        raise ConfigError(f"[{where}] has {', '.join(sorted(unknown))}; the "
                          f"keys are {', '.join(sorted(allowed))}.")
    if "left" not in table or "top" not in table:
        raise ConfigError(f"[{where}] needs at least left and top.")
    left, top = int(table["left"]), int(table["top"])
    width, height = table.get("width"), table.get("height")
    if width is None and "right" in table:
        width = int(table["right"]) - left
    if height is None and "bottom" in table:
        height = int(table["bottom"]) - top
    if (width is not None and int(width) <= 0) or \
            (height is not None and int(height) <= 0):
        raise ConfigError(
            f"[{where}] has a zero or negative size -- is bottom-right "
            "actually below and to the right of top-left?")
    return (left, top,
            None if width is None else int(width),
            None if height is None else int(height))


def _numbers(where: str, value) -> List[float]:
    if not isinstance(value, (list, tuple)):
        raise ConfigError(f"[{where}] should be a list of numbers.")
    out = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise ConfigError(
                f"[{where}] contains {item!r}, which is not a number.")
        out.append(float(item))
    return out


# --------------------------------------------------------------------------
# Writing


HEADER = """\
# insidetrack.toml -- your own copy. Not committed: every box in here is
# pixel coordinates inside YOUR chiaki-ng window at YOUR window size.
#
# Written by `python -m insidetrack setup`. Re-run that whenever the window
# is resized or moved to another monitor, or edit the numbers by hand and
# check them with `python -m insidetrack probe`.
"""

SCREEN_NOTE = """\
# Boxes are [left, top, width, height] in pixels, measured from the top-left
# corner of the chiaki-ng window -- not of the screen. The corner form
# { left = .., top = .., right = .., bottom = .. } works anywhere too.
"""


def dump(config: UserConfig) -> str:
    """The config as TOML, comments and all."""
    index = config.post_target_index
    lines = [HEADER]
    lines.append(_setting(f"window_title = {_string(config.window_title)}",
                          "any window whose title contains this"))
    lines.append(_setting(f"default_screen = {_string(config.default_screen)}",
                          "used when --screen is not given"))
    lines.append(_setting(f"input_mode = {_string(config.input_mode)}",
                          "postmessage | gamepad | keyboard"))
    lines.append(_setting(f"strategy = {_string(config.strategy)}",
                          "pickorder (validated) | chart"))
    lines.append(_setting(f"{'' if index else '# '}post_target_index = "
                          f"{index or 2}",
                          "from `insidetrack keys`; 0 = top-level"))
    lines.append("")
    for name in sorted(config.screens):
        lines.append(_screen_block(name, config.screens[name]))
    return "\n".join(lines).rstrip() + "\n"


def _setting(assignment: str, note: str, column: int = 34) -> str:
    """One line of config, with its comment lined up with the others."""
    return f"{assignment.ljust(max(column, len(assignment) + 1))}# {note}"


def _screen_block(name: str, profile: Profile) -> str:
    rows = [f"    {_array(region)}," for region in profile.odds_regions]
    column = max(len(row) for row in rows) + 3
    lines = [f"[screens.{name}]", SCREEN_NOTE.rstrip(), "odds = ["]
    lines += [_setting(row, f"lane {lane}", column)
              for lane, row in enumerate(rows, start=1)]
    lines.append("]")
    lines.append(_box_line("bet_amount", profile.bet_amount_region,
                           "the stake showing on the bet screen"))
    lines.append(_box_line("win_lane", profile.win_lane_region,
                           "winning horse's number, on the result screen"))
    lines.append("")
    return "\n".join(lines)


def _box_line(key: str, region: Optional[Region], note: str) -> str:
    if region is None:
        return _setting(f"# {key} = [0, 0, 0, 0]", f"{note} -- NOT MEASURED")
    return _setting(f"{key} = {_array(region)}", note)


def _array(region: Region) -> str:
    return "[" + ", ".join(str(int(value)) for value in region) + "]"


def _string(value: str) -> str:
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'


def write(config: UserConfig, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dump(config), encoding="utf-8")
    return path
