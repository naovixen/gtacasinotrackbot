"""Ways of getting a keypress to the PS5, behind one interface.

postmessage posts a down/up pair straight to the chiaki-ng window handle, so
the keystroke exists only for that HWND -- nothing else on the system sees
it and you can keep using the PC. gamepad is a virtual DualShock 4, which is
a system-wide HID device: Steam in particular grabs it and retypes it into
whatever window you focused, which is the "it's controlling my program"
effect. keyboard needs chiaki-ng focused and is the last resort.

Each backend does one thing -- hold a key down for a while -- so the timing
layer above never knows which one it is talking to.
"""

import ctypes
import time
from ctypes import wintypes
from typing import Callable, List, Tuple

# chiaki-ng's default keyboard map: Cross = Enter, Circle = Backspace.
KEYS = {"up": "up", "down": "down", "left": "left", "right": "right",
        "cross": "enter", "circle": "backspace"}
VK = {"up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
      "enter": 0x0D, "backspace": 0x08}
# Arrow keys sit on the extended keyboard; Qt reads that bit out of lParam to
# tell them from the numpad, so it has to be set correctly.
EXTENDED_KEYS = {"up", "down", "left", "right"}
WM_KEYDOWN, WM_KEYUP = 0x0100, 0x0101
MAPVK_VK_TO_VSC = 0

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT,
                                 wintypes.WPARAM, wintypes.LPARAM]
_user32.PostMessageW.restype = wintypes.BOOL
_user32.MapVirtualKeyW.argtypes = [wintypes.UINT, wintypes.UINT]
_user32.MapVirtualKeyW.restype = wintypes.UINT


def window_class(hwnd) -> str:
    buffer = ctypes.create_unicode_buffer(256)
    _user32.GetClassNameW(hwnd, buffer, 256)
    return buffer.value


def child_windows(hwnd) -> List[int]:
    found = []
    prototype = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND,
                                   wintypes.LPARAM)

    def collect(handle, _):
        found.append(handle)
        return True

    _user32.EnumChildWindows(hwnd, prototype(collect), 0)
    return found


def post_key(hwnd, key: str, hold: float) -> None:
    """A real down/up pair to one window, and only that window."""
    virtual = VK[KEYS[key]]
    scan = _user32.MapVirtualKeyW(virtual, MAPVK_VK_TO_VSC)
    extended = 1 if KEYS[key] in EXTENDED_KEYS else 0
    down = 1 | (scan << 16) | (extended << 24)
    up = down | (1 << 30) | (1 << 31)          # was-down + transition bits
    _user32.PostMessageW(hwnd, WM_KEYDOWN, virtual, down)
    time.sleep(hold)
    _user32.PostMessageW(hwnd, WM_KEYUP, virtual, up)


class PostMessageBackend:
    """Posts to the chiaki-ng HWND. Scoped to that window; needs no focus."""

    name = "postmessage"

    def __init__(self, window: Callable, target_index=None):
        self._window = window
        self._target_index = target_index
        self._hwnd = None

    def targets(self) -> List[Tuple[int, str]]:
        """[(hwnd, label)] -- top-level chiaki window first, then children."""
        win = self._window()
        top = win._hWnd
        listed = [(top, f"top-level  class={window_class(top)!r}  "
                        f"title={win.title!r}")]
        listed += [(h, f"child      class={window_class(h)!r}")
                   for h in child_windows(top)]
        return listed

    def hwnd(self) -> int:
        if self._hwnd is None:
            index = 0 if self._target_index is None else self._target_index - 1
            self._hwnd = self.targets()[index][0]
        return self._hwnd

    def press(self, key: str, hold: float) -> None:
        post_key(self.hwnd(), key, hold)

    def describe(self) -> str:
        try:
            handle = self.hwnd()
            return (f"posting keys to HWND {handle} "
                    f"({window_class(handle)!r}) -- that window only. If the "
                    "PS5 menu doesn't move, run 'keys' to pick another "
                    "target, or switch input_mode to 'gamepad'.")
        except Exception as error:
            return f"could not resolve a target window: {error}"


class GamepadBackend:
    """Virtual DualShock 4 via ViGEmBus. System-wide: see README-fixes.md."""

    name = "gamepad"

    def __init__(self):
        self._pad = None
        self._vg = None

    def _gamepad(self):
        if self._pad is None:
            import vgamepad
            self._vg, self._pad = vgamepad, vgamepad.VDS4Gamepad()
            print("Virtual DualShock 4 created (ViGEmBus).")
            time.sleep(1.0)
        return self._vg, self._pad

    def press(self, key: str, hold: float) -> None:
        vg, pad = self._gamepad()
        if key in ("up", "down", "left", "right"):
            self._dpad(vg, pad, key, hold)
        else:
            self._button(vg, pad, key, hold)

    @staticmethod
    def _dpad(vg, pad, key: str, hold: float) -> None:
        directions = {"up": vg.DS4_DPAD_DIRECTIONS.DS4_BUTTON_DPAD_NORTH,
                      "down": vg.DS4_DPAD_DIRECTIONS.DS4_BUTTON_DPAD_SOUTH,
                      "left": vg.DS4_DPAD_DIRECTIONS.DS4_BUTTON_DPAD_WEST,
                      "right": vg.DS4_DPAD_DIRECTIONS.DS4_BUTTON_DPAD_EAST}
        pad.directional_pad(direction=directions[key])
        pad.update()
        time.sleep(hold)
        pad.directional_pad(
            direction=vg.DS4_DPAD_DIRECTIONS.DS4_BUTTON_DPAD_NONE)
        pad.update()

    @staticmethod
    def _button(vg, pad, key: str, hold: float) -> None:
        buttons = {"cross": vg.DS4_BUTTONS.DS4_BUTTON_CROSS,
                   "circle": vg.DS4_BUTTONS.DS4_BUTTON_CIRCLE}
        pad.press_button(button=buttons[key])
        pad.update()
        time.sleep(hold)
        pad.release_button(button=buttons[key])
        pad.update()

    def describe(self) -> str:
        if steam_running():
            return ("!! Steam is running. It grabs virtual DualShock pads and "
                    "its desktop layout retypes them into whatever window you "
                    "have focused. Close Steam, turn off Controller > "
                    "PlayStation Controller Support, or hide the pad with "
                    "HidHide.")
        return ("Steam not detected. Any other app that reads gamepads can "
                "still see this virtual pad; HidHide is the only airtight fix.")


class KeyboardBackend:
    """pydirectinput; types into whatever window is FOCUSED."""

    name = "keyboard"

    def press(self, key: str, hold: float) -> None:
        import pydirectinput
        pydirectinput.PAUSE = 0.0
        pydirectinput.keyDown(KEYS[key])
        time.sleep(hold)
        pydirectinput.keyUp(KEYS[key])

    def describe(self) -> str:
        return ("!! keyboard mode types into whatever window is FOCUSED. "
                "You cannot use the PC while this runs.")


def steam_running() -> bool:
    import subprocess
    try:
        listed = subprocess.run(["tasklist", "/FI", "IMAGENAME eq steam.exe"],
                                capture_output=True, text=True, timeout=10)
        return "steam.exe" in listed.stdout.lower()
    except Exception:
        return False


def make_backend(mode: str, window: Callable, target_index=None):
    if mode == "postmessage":
        return PostMessageBackend(window, target_index)
    if mode == "gamepad":
        return GamepadBackend()
    if mode == "keyboard":
        return KeyboardBackend()
    raise ValueError(f"unknown input mode {mode!r}")
