from __future__ import annotations

import subprocess
import sys

from easytype.config import Config

WARN_WINDOW_S = 5
PILL_W, PILL_H, MARGIN = 150, 44, 24


def _position_xy(position: str, sw: int, sh: int) -> tuple[int, int]:
    cx = (sw - PILL_W) // 2
    right = sw - PILL_W - MARGIN
    bottom = sh - PILL_H - MARGIN * 2
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
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )

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
    label.pack(fill="both", expand=True)

    state = {"s": 0}

    def tick():
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
    root.mainloop()


if __name__ == "__main__":
    _pos = sys.argv[1] if len(sys.argv) > 1 else "top-right"
    _cnt = sys.argv[2] if len(sys.argv) > 2 else "up"
    _cap = int(sys.argv[3]) if len(sys.argv) > 3 else 0
    _run_pill(_pos, _cnt, _cap)
