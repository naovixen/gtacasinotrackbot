"""Click the corners on a still picture of the window.

chiaki-ng hides the mouse pointer while it is streaming, so "hover the spot
and press a key" is unusable on the one window it matters for -- there is
nothing to aim with. This takes one capture of the window and puts it in a
plain tkinter window instead, where the cursor is a normal, visible
crosshair and nothing is moving.

tkinter is stdlib and PIL is already a dependency, so this costs no install.
The magnifier is the part that makes it accurate: the capture is usually
taller than the monitor showing it, so what you click is a scaled-down
pixel, and the inset shows the real ones around it at 8x.
"""

import tkinter as tk
from typing import Optional, Tuple

from PIL import Image, ImageTk

Point = Tuple[int, int]

MAGNIFIER = 168             # on-screen size of the inset, pixels
MAGNIFIED_PIXELS = 21       # how many source pixels across it shows

CANVAS_PAD = 24             # the padding around the picture itself
TITLE_BAR = 40              # if Windows will not say how tall its own is
SIDE_ROOM = 40              # so the window is not flush with the screen edge

INK = "#e8e8e8"
DIM = "#8a8a8a"
GUIDE = "#ff3b30"           # the crosshair and the box being drawn
SETTLED = "#32d74b"         # boxes already decided
BACKDROP = "#141414"


class Cancelled(RuntimeError):
    """Escape, or the window closed: leave the existing config alone."""


def _work_area(root) -> Tuple[int, int]:
    """The desktop minus the taskbar, which is not the same as the screen.

    Tk only knows the whole screen (and `maxsize()` reports the whole
    multi-monitor desktop), so a window sized from that hides its own bottom
    edge behind the taskbar -- and with it the magnifier and the buttons.
    """
    try:
        import ctypes
        from ctypes import wintypes

        class RECT(ctypes.Structure):
            _fields_ = [("left", wintypes.LONG), ("top", wintypes.LONG),
                        ("right", wintypes.LONG), ("bottom", wintypes.LONG)]

        rect = RECT()
        spi_getworkarea = 0x0030
        if ctypes.WinDLL("user32").SystemParametersInfoW(
                spi_getworkarea, 0, ctypes.byref(rect), 0):
            return rect.right - rect.left, rect.bottom - rect.top
    except Exception:
        pass
    return root.winfo_screenwidth(), root.winfo_screenheight() - 60


class Picker:
    """One window showing one captured frame, asked for a point at a time.

    The window is built once and kept for the whole step: `point()` runs the
    event loop until a click, then returns without tearing anything down, so
    picking four corners does not flash four windows.
    """

    def __init__(self, image, title: str = "insidetrack setup"):
        self._source = Image.fromarray(image)
        self._result: Optional[Point] = None
        self._cancelled = False
        self._skipped = False
        self._answer: Optional[bool] = None
        self._anchor: Optional[Point] = None
        self._allow_skip = False
        self._marks: list = []          # cleared on every mouse move
        self._kept: list = []           # boxes already decided, left drawn
        self._magnified = None          # PhotoImage, kept off the GC
        self._build(title)

    # ----------------------------------------------------------------- ask

    def point(self, prompt: str, anchor: Optional[Point] = None,
              allow_skip: bool = False) -> Optional[Point]:
        """Block until the picture is clicked. None if skipped."""
        self._anchor = anchor
        self._allow_skip = allow_skip
        self._result, self._skipped, self._answer = None, False, None
        keys = "Esc cancels" + ("   S skips this box" if allow_skip else "")
        self._ask(prompt, keys)
        return None if self._skipped else self._result

    def confirm(self, prompt: str, yes: str, no: str,
                boxes=None, note: str = "") -> bool:
        """Ask a yes/no here rather than in the console.

        Anything the walkthrough needs to ask *about the picture* has to be
        asked on the picture: the window is the only thing on screen while
        it is up, and a question printed behind it is a question nobody can
        see, let alone answer.
        """
        if boxes is not None:
            self.draw(boxes)
        self._answer = None
        self._buttons(yes, no)
        try:
            self._ask(prompt, note or "Esc cancels")
        finally:
            self._button_row.pack_forget()
            self._prompt.config(wraplength=self._picture_width())
        return bool(self._answer)

    def draw(self, boxes) -> None:
        """Leave these boxes drawn on the picture from now on."""
        for item in self._kept:
            self._canvas.delete(item)
        self._kept = []
        for index, region in enumerate(boxes, start=1):
            if region:
                self._kept.extend(self._outline(region, str(index)))
        self._canvas.update_idletasks()

    def close(self) -> None:
        try:
            self._root.destroy()
        except tk.TclError:
            pass

    def _ask(self, prompt: str, hint: str):
        self._prompt.config(text=prompt)
        self._hint.config(text=hint)
        self._root.lift()
        self._root.focus_force()
        self._root.mainloop()
        if self._cancelled:
            raise Cancelled("cancelled")

    # --------------------------------------------------------------- build

    def _build(self, title: str) -> None:
        self._root = tk.Tk()
        self._root.title(title)
        self._root.configure(bg=BACKDROP)
        self._root.geometry("+0+0")     # never hanging off the top or left
        self._root.protocol("WM_DELETE_WINDOW", self._on_close)

        # The buttons sit beside the question, not under the picture. A
        # window this tall puts its own bottom edge a thousand pixels below
        # the text you are reading, which is far enough away to be missed
        # entirely -- the answer belongs where the question is.
        header = tk.Frame(self._root, bg=BACKDROP)
        header.pack(fill="x")
        self._button_row = tk.Frame(header, bg=BACKDROP)
        self._yes = tk.Button(self._button_row, text="Yes",
                              font=("Segoe UI", 11, "bold"), padx=18, pady=6,
                              cursor="hand2",
                              command=lambda: self._decide(True))
        self._yes.pack(side="left", padx=(0, 8))
        self._no = tk.Button(self._button_row, text="No",
                             font=("Segoe UI", 11), padx=18, pady=6,
                             cursor="hand2",
                             command=lambda: self._decide(False))
        self._no.pack(side="left")

        self._prompt = tk.Label(header, text="", bg=BACKDROP, fg=INK,
                                font=("Segoe UI", 13, "bold"), anchor="w",
                                justify="left", padx=12, pady=(8))
        self._prompt.pack(side="left")

        self._hint = tk.Label(self._root, text="", bg=BACKDROP, fg=DIM,
                              font=("Segoe UI", 9), anchor="w", padx=12,
                              justify="left")
        self._hint.pack(fill="x")

        self._status = tk.Label(self._root, text="", bg=BACKDROP, fg=DIM,
                                font=("Consolas", 10), anchor="w", padx=12,
                                pady=(6))
        self._status.pack(fill="x")

        # The canvas gets whatever is left once everything else has said how
        # tall it is -- including the buttons, which are only shown for a
        # question but must never be the thing that pushes the window under
        # the taskbar. Guessing that number is how the magnifier ended up
        # off-screen: it parks in a corner of the canvas.
        self._canvas = tk.Canvas(self._root, bg=BACKDROP,
                                 highlightthickness=0, cursor="crosshair")
        self._canvas.pack(before=self._status, padx=12, pady=8)
        self._fill_canvas()
        self._button_row.pack_forget()

        self._canvas.bind("<Motion>", self._on_move)
        self._canvas.bind("<Button-1>", self._on_click)
        self._root.bind("<Return>", self._on_return)
        self._root.bind("<Escape>", lambda _: self._on_close())
        self._root.bind("<KeyPress-s>", self._on_skip)
        self._root.bind("<KeyPress-S>", self._on_skip)

    def _fill_canvas(self) -> None:
        width, height = self._source.size
        self._scale = self._fit(width, height)
        view = self._source.resize(
            (max(1, round(width * self._scale)),
             max(1, round(height * self._scale))), Image.LANCZOS)
        self._photo = ImageTk.PhotoImage(view)
        self._canvas.config(width=view.width, height=view.height)
        self._canvas.create_image(0, 0, anchor="nw", image=self._photo)
        # Wrap the text to the picture rather than letting a long note
        # stretch the window wider than the thing it is about.
        self._prompt.config(wraplength=view.width)
        self._hint.config(wraplength=view.width)

    def _fit(self, width: int, height: int) -> float:
        """Shrink to fit the desktop's usable area, never enlarge."""
        room_x, room_y = self._room()
        return min(1.0, room_x / width, room_y / height)

    def _room(self) -> Point:
        """What is left for the picture after the desktop and the window."""
        self._show_buttons()                # measure the tallest case:
        self._prompt.config(text="X\nX")    # two lines of prompt, two of
        self._hint.config(text="X\nX")      # hint, and the buttons shown
        self._canvas.config(width=1, height=1)   # not its placeholder size
        self._root.update_idletasks()
        chrome = self._root.winfo_reqheight()
        desk_x, desk_y = _work_area(self._root)
        title = max(0, self._root.winfo_rooty() - self._root.winfo_y()) \
            or TITLE_BAR
        return (desk_x - SIDE_ROOM,
                desk_y - chrome - title - CANVAS_PAD)

    # -------------------------------------------------------------- events

    def _buttons(self, yes: str, no: str) -> None:
        """Show the answers, and leave the question the room that is left."""
        self._yes.config(text=yes)
        self._no.config(text=no)
        self._show_buttons()
        self._root.update_idletasks()
        self._prompt.config(
            wraplength=max(200, self._picture_width()
                           - self._button_row.winfo_reqwidth() - 48))

    def _show_buttons(self) -> None:
        """Right of the question, and up against it.

        Not right-aligned in the header: this window is as wide as the game
        capture, so the far edge is over a thousand pixels from the words
        being read, which is its own way of being invisible.
        """
        self._button_row.pack(side="left", padx=(16, 12), pady=8)

    def _picture_width(self) -> int:
        return int(self._canvas["width"] or 0)

    def _decide(self, answer: bool) -> None:
        self._answer = answer
        self._root.quit()

    def _on_return(self, _event) -> None:
        if self._button_row.winfo_ismapped():
            self._decide(True)

    def _on_move(self, event) -> None:
        self._draw(self._to_source(event.x, event.y), event.x, event.y)

    def _on_click(self, event) -> None:
        if self._button_row.winfo_ismapped():
            return                      # a question is up; answer that first
        self._result = self._to_source(event.x, event.y)
        self._root.quit()

    def _on_skip(self, _event) -> None:
        if self._allow_skip:
            self._skipped = True
            self._root.quit()

    def _on_close(self) -> None:
        self._cancelled = True
        self._root.quit()

    def _to_source(self, x: int, y: int) -> Point:
        """Canvas pixel -> pixel in the window that was captured."""
        width, height = self._source.size
        return (max(0, min(width - 1, round(x / self._scale))),
                max(0, min(height - 1, round(y / self._scale))))

    # ------------------------------------------------------------- drawing

    def _draw(self, where: Point, x: int, y: int) -> None:
        self._clear()
        self._crosshair(x, y)
        if self._anchor is not None:
            self._rectangle(self._anchor, where)
        self._magnify(where, x, y)
        self._status.config(text=self._readout(where))

    def _clear(self) -> None:
        for item in self._marks:
            self._canvas.delete(item)
        self._marks = []

    def _keep(self, *items) -> None:
        self._marks.extend(items)

    def _crosshair(self, x: int, y: int) -> None:
        width = int(self._canvas["width"])
        height = int(self._canvas["height"])
        self._keep(
            self._canvas.create_line(0, y, width, y, fill=GUIDE),
            self._canvas.create_line(x, 0, x, height, fill=GUIDE))

    def _rectangle(self, anchor: Point, corner: Point) -> None:
        """The box being drawn, from the corner already clicked."""
        left, top = self._to_canvas(min(anchor[0], corner[0]),
                                    min(anchor[1], corner[1]))
        right, bottom = self._to_canvas(max(anchor[0], corner[0]),
                                        max(anchor[1], corner[1]))
        self._keep(self._canvas.create_rectangle(
            left, top, right, bottom, outline=GUIDE, width=2))

    def _outline(self, region, label: str) -> list:
        """A settled box, drawn to stay: rectangle plus its number."""
        left, top, width, height = region
        x1, y1 = self._to_canvas(left, top)
        x2, y2 = self._to_canvas(left + width, top + height)
        return [
            self._canvas.create_rectangle(x1, y1, x2, y2, outline=SETTLED,
                                          width=2),
            self._canvas.create_text(x1 + 3, y1 - 9, text=label, fill=SETTLED,
                                     anchor="w", font=("Segoe UI", 10,
                                                       "bold"))]

    def _to_canvas(self, x: int, y: int) -> Point:
        return round(x * self._scale), round(y * self._scale)

    def _magnify(self, where: Point, x: int, y: int) -> None:
        """The real pixels around the cursor, at 8x, out of its way."""
        half = MAGNIFIED_PIXELS // 2
        patch = self._source.crop((where[0] - half, where[1] - half,
                                   where[0] + half + 1, where[1] + half + 1))
        self._magnified = ImageTk.PhotoImage(
            patch.resize((MAGNIFIER, MAGNIFIER), Image.NEAREST))
        left = 8 if x > int(self._canvas["width"]) / 2 \
            else int(self._canvas["width"]) - MAGNIFIER - 8
        top = 8 if y > int(self._canvas["height"]) / 2 \
            else int(self._canvas["height"]) - MAGNIFIER - 8
        middle = MAGNIFIER // 2
        self._keep(
            self._canvas.create_image(left, top, anchor="nw",
                                      image=self._magnified),
            self._canvas.create_rectangle(left, top, left + MAGNIFIER,
                                          top + MAGNIFIER, outline=GUIDE),
            self._canvas.create_line(left, top + middle, left + MAGNIFIER,
                                     top + middle, fill=GUIDE),
            self._canvas.create_line(left + middle, top, left + middle,
                                     top + MAGNIFIER, fill=GUIDE))

    def _readout(self, where: Point) -> str:
        text = f"window ({where[0]:5d}, {where[1]:5d})"
        if self._anchor is not None:
            width = abs(where[0] - self._anchor[0])
            height = abs(where[1] - self._anchor[1])
            text += f"     box {width} x {height}"
        return text
