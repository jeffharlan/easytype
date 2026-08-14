from __future__ import annotations

import queue
import subprocess
import sys
import textwrap
import threading

from easytype.config import Config

WARN_WINDOW_S = 5
PILL_W, PILL_H, MARGIN = 150, 44, 24
CAPTION_W, CAPTION_LINES, CAPTION_CHARS = 420, 4, 52
CAPTION_LINE_H = 18
# Lines carrying this prefix set the pill's header and freeze its timer. A control
# character keeps it unambiguous: transcripts never contain one.
STATUS_PREFIX = "\x01"


def _position_xy(position: str, sw: int, sh: int,
                 w: int = PILL_W, h: int = PILL_H) -> tuple[int, int]:
    cx = (sw - w) // 2
    right = sw - w - MARGIN
    bottom = sh - h - MARGIN * 2
    return {
        "top-left": (MARGIN, MARGIN),
        "top-center": (cx, MARGIN),
        "top-right": (right, MARGIN),
        "bottom-left": (MARGIN, bottom),
        "bottom-center": (cx, bottom),
        "bottom-right": (right, bottom),
    }.get(position, (right, MARGIN))


def format_elapsed(seconds: int) -> str:
    return f"{seconds // 60}:{seconds % 60:02d}"


def should_warn(elapsed: int, cap: int) -> bool:
    return cap > 0 and elapsed >= cap - WARN_WINDOW_S


def wrap_tail(text: str, width: int, max_lines: int) -> list[str]:
    """Wrapped text, keeping only the last max_lines — the box reads as scrolling
    captions, with the oldest words falling off the top."""
    if not text.strip():
        return []
    return textwrap.wrap(text, width)[-max_lines:]


def _tk_available() -> bool:
    try:
        import tkinter  # noqa: F401
        return True
    except Exception:
        return False


class NullIndicator:
    is_null = True

    def start(self, cap: int) -> None: ...
    def stop(self) -> None: ...
    def caption(self, text: str) -> None: ...
    def status(self, text: str) -> None: ...


class ProcessIndicator:
    """Shows the timer pill in a separate process so Tk always runs on its own
    main thread — avoids Tcl cross-thread teardown crashes."""

    is_null = False

    def __init__(self, position: str, count: str):
        self._position = position
        self._count = count
        self._proc = None

    def start(self, cap: int) -> None:
        self._proc = subprocess.Popen(
            [sys.executable, "-m", "easytype.indicator", self._position, self._count, str(cap)],
            stdin=subprocess.PIPE, text=True,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )

    def caption(self, text: str) -> None:
        """Push preview text to the pill. Whitespace is collapsed so one caption
        is always exactly one line — the pill re-wraps for display anyway, so the
        original breaks carry no information and no escaping scheme is needed.
        Captions are advisory: if the pill has already exited (e.g. the cap timer
        fired), the write is dropped."""
        self._send(" ".join(text.split()))

    def status(self, text: str) -> None:
        """Replace the timer with a fixed label and freeze it — the pill outlives
        the recording now, and a still-counting timer would read as still recording."""
        self._send(STATUS_PREFIX + " ".join(text.split()))

    def _send(self, line: str) -> None:
        if self._proc is None or self._proc.stdin is None:
            return
        try:
            self._proc.stdin.write(line + "\n")
            self._proc.stdin.flush()
        except (BrokenPipeError, ValueError, OSError):
            pass

    def stop(self) -> None:
        if self._proc is not None:
            self._proc.terminate()
            self._proc = None


def create_indicator(config: Config):
    if not config.indicator_enabled or not _tk_available():
        return NullIndicator()
    return ProcessIndicator(config.indicator_position, config.indicator_count)


def _run_pill(position: str, count: str, cap: int) -> None:
    import tkinter as tk

    root = tk.Tk()
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    try:
        root.wm_attributes("-type", "splash")  # no focus / no taskbar (X11)
    except tk.TclError:
        pass

    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    x, y = _position_xy(position, sw, sh)
    root.geometry(f"{PILL_W}x{PILL_H}+{x}+{y}")

    label = tk.Label(root, font=("sans", 14, "bold"), fg="white", bg="#111111", padx=12, pady=8)
    label.pack(side="top", fill="both", expand=True)
    caption = tk.Label(root, font=("sans", 11), fg="#dddddd", bg="#111111",
                       justify="left", anchor="w", padx=12, pady=6,
                       wraplength=CAPTION_W - 24)

    captions: queue.Queue[str] = queue.Queue()
    state = {"s": 0, "shown": False, "counting": True}

    def read_stdin():
        for line in sys.stdin:
            captions.put(line.rstrip("\n"))

    threading.Thread(target=read_stdin, daemon=True).start()

    def drain():
        # Tk widgets may only be touched from the thread running mainloop, so the
        # reader thread only queues text and this poll applies it.
        newest_caption = None
        while not captions.empty():        # only the newest caption matters
            line = captions.get_nowait()
            if line.startswith(STATUS_PREFIX):
                state["counting"] = False  # a status line ends the recording display
                label.config(text=line[len(STATUS_PREFIX):], fg="white")
            else:
                newest_caption = line
        if newest_caption is not None:
            show(newest_caption)
        root.after(100, drain)

    def show(text: str):
        lines = wrap_tail(text, CAPTION_CHARS, CAPTION_LINES)
        if not lines:
            return
        if not state["shown"]:
            caption.pack(side="top", fill="both", expand=True)
            state["shown"] = True
        caption.config(text="\n".join(lines))
        h = PILL_H + CAPTION_LINE_H * len(lines) + 12
        cx, cy = _position_xy(position, sw, sh, CAPTION_W, h)
        root.geometry(f"{CAPTION_W}x{h}+{cx}+{cy}")

    def tick():
        if not state["counting"]:
            root.after(1000, tick)   # frozen: the owner decides when to close us
            return
        s = state["s"]
        if cap and s > cap:
            root.destroy()
            return
        shown = s if count == "up" else max(0, cap - s)
        label.config(text=f"● REC  {format_elapsed(shown)}",
                     fg=("#ffb000" if should_warn(s, cap) else "white"))
        state["s"] += 1
        root.after(1000, tick)

    tick()
    drain()
    root.mainloop()


if __name__ == "__main__":
    _pos = sys.argv[1] if len(sys.argv) > 1 else "top-right"
    _cnt = sys.argv[2] if len(sys.argv) > 2 else "up"
    _cap = int(sys.argv[3]) if len(sys.argv) > 3 else 0
    _run_pill(_pos, _cnt, _cap)
