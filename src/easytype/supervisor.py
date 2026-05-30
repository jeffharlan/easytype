from __future__ import annotations

import threading
from collections.abc import Callable

from easytype.config import load_config


class EngineSupervisor:
    """Owns the dictation engine's lifecycle on a background thread. Qt-free, so it
    is unit-testable and the engine never depends on the GUI."""

    def __init__(self, *, session: str, grab: bool = True,
                 builder: Callable | None = None,
                 config_loader: Callable = load_config):
        self._session = session
        self._grab = grab
        self._builder = builder
        self._load = config_loader
        self._bundle = None
        self._thread: threading.Thread | None = None

    def _build(self, config):
        if self._builder is not None:
            return self._builder(config)
        from easytype.engine import build_engine
        return build_engine(config, self._session)

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        config = self._load()
        self._bundle = self._build(config)
        self._thread = threading.Thread(
            target=self._bundle.listener.run,
            kwargs={"device_override": config.keyboard_device, "grab": self._grab},
            daemon=True,
        )
        self._thread.start()
        threading.Thread(target=self._bundle.warmup, daemon=True).start()

    def stop(self) -> None:
        if self._bundle is not None:
            self._bundle.listener.stop()
        if self._thread is not None:
            self._thread.join(timeout=5)
            # If the listener didn't honor stop() within the timeout the daemon
            # thread may still hold the evdev grab (it dies on process exit). Drop
            # the bundle so a later reload() can't dispatch to a dead engine.
        self._thread = None
        self._bundle = None

    def reload(self) -> None:
        self.stop()
        self.start()

    @property
    def state(self) -> str:
        if self._thread is None or not self._thread.is_alive():
            return "stopped"
        return self._bundle.controller.state if self._bundle else "stopped"

    def toggle_recording(self) -> None:
        if self._bundle is not None:
            self._bundle.controller.toggle_recording()

    def cancel(self) -> None:
        if self._bundle is not None:
            self._bundle.controller.on_cancel()

    def begin_hotkey_capture(self, on_captured: Callable[[list], None]) -> None:
        if self._bundle is not None:
            self._bundle.listener.begin_capture(on_captured)
