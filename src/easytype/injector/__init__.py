from __future__ import annotations

from typing import Protocol


class Injector(Protocol):
    def inject(self, text: str, method: str) -> None: ...


class NullInjector:
    """Wayland has no working injector in Phase 1. cli.py's --passive is the
    only way to reach this on Wayland (a real run is refused before the engine
    is built), so injection is expected to be a no-op there rather than a crash —
    the point of --passive is to exercise recording and transcription only."""

    def inject(self, text: str, method: str) -> None:
        print(f"[easytype] Wayland injection not implemented yet — would have typed: {text!r}")

    def active_window(self) -> str:
        return ""

    def type_text(self, text: str, delay_ms: int | None = None) -> None: ...

    def backspace(self, count: int) -> None: ...


def get_injector(session: str, type_delay_ms: int = 40) -> Injector:
    if session == "wayland":
        return NullInjector()
    from easytype.injector.x11 import X11Injector
    return X11Injector(type_delay_ms)
