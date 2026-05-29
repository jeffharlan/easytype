from __future__ import annotations

from typing import Protocol


class Injector(Protocol):
    def inject(self, text: str, method: str) -> None: ...


def get_injector(session: str, type_delay_ms: int = 40) -> Injector:
    if session == "wayland":
        raise NotImplementedError(
            "Wayland injector is not implemented in Phase 1. Run on X11, "
            "or use --passive and copy text manually."
        )
    from easytype.injector.x11 import X11Injector
    return X11Injector(type_delay_ms)
