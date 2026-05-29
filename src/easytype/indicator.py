from __future__ import annotations

import threading

from easytype.config import Config

WARN_WINDOW_S = 5


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


class TkIndicator:
    is_null = False

    def __init__(self, position: str, count: str):
        self._position = position
        self._count = count
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._cap = 0

    def start(self, cap: int) -> None:
        self._cap = cap
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1)
            self._thread = None

    def _geometry(self, root, w: int, h: int) -> str:
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        m = 24
        pos = {
            "top-right": (sw - w - m, m), "top-left": (m, m),
            "top-center": ((sw - w) // 2, m),
            "bottom-right": (sw - w - m, sh - h - m * 2),
            "bottom-left": (m, sh - h - m * 2),
        }.get(self._position, (sw - w - m, m))
        return f"{w}x{h}+{pos[0]}+{pos[1]}"

    def _run(self) -> None:
        import tkinter as tk

        root = tk.Tk()
        root.overrideredirect(True)          # borderless, no titlebar
        root.attributes("-topmost", True)
        try:
            root.wm_attributes("-type", "splash")  # never take focus / taskbar (X11)
        except tk.TclError:
            pass
        root.geometry(self._geometry(root, 150, 44))
        label = tk.Label(root, font=("sans", 14, "bold"), fg="white", bg="#111111", padx=12, pady=8)
        label.pack(fill="both", expand=True)

        elapsed = {"s": 0}

        def tick():
            if self._stop.is_set():
                root.destroy()
                return
            s = elapsed["s"]
            shown = s if self._count == "up" else max(0, self._cap - s)
            warn = should_warn(s, self._cap)
            label.config(text=f"● REC  {format_elapsed(shown)}",
                         fg=("#ffb000" if warn else "white"))
            elapsed["s"] += 1
            root.after(1000, tick)

        tick()
        root.mainloop()


def create_indicator(config: Config):
    if not config.indicator_enabled or not _tk_available():
        return NullIndicator()
    return TkIndicator(config.indicator_position, config.indicator_count)
