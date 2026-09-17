from __future__ import annotations

from typing import Protocol


class Injector(Protocol):
    def inject(self, text: str, method: str) -> None: ...


class NullInjector:
    """Used when the session can't be identified as either X11 or Wayland, so
    there's no injection backend to pick. Injection is a no-op rather than a
    crash — recording and transcription still work, only the final insert doesn't."""

    def inject(self, text: str, method: str) -> None:
        print(f"[easytype] no injector for this session — would have typed: {text!r}")

    def active_window(self) -> str:
        return ""

    def type_text(self, text: str, delay_ms: int | None = None) -> None: ...

    def backspace(self, count: int) -> None: ...


def get_injector(session: str, type_delay_ms: int = 40) -> Injector:
    if session == "wayland":
        from easytype.injector.wayland import WaylandInjector
        return WaylandInjector(type_delay_ms)
    if session == "x11":
        from easytype.injector.x11 import X11Injector
        return X11Injector(type_delay_ms)
    return NullInjector()
