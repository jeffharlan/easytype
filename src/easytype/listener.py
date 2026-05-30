from __future__ import annotations

import os
import selectors
from collections.abc import Callable

from easytype.chords import HotkeyEngine


def find_keyboards() -> list:
    """Devices that look like real keyboards (have letter keys)."""
    from evdev import InputDevice, ecodes, list_devices

    keyboards = []
    for path in list_devices():
        try:
            dev = InputDevice(path)
        except Exception:
            continue
        keys = dev.capabilities().get(ecodes.EV_KEY, [])
        if ecodes.KEY_A in keys and ecodes.KEY_Z in keys:
            keyboards.append(dev)
        else:
            dev.close()
    return keyboards


def open_devices(device_override: str) -> list:
    if device_override:
        from evdev import InputDevice
        return [InputDevice(device_override)]
    devices = find_keyboards()
    if not devices:
        raise RuntimeError("No keyboard device found. Set [keyboard] device in config.")
    return devices


class Listener:
    """Reads evdev devices, runs the HotkeyEngine, and (in grab mode) replays
    every non-swallowed event through a uinput virtual keyboard."""

    def __init__(self, engine: HotkeyEngine, enabled_provider: Callable[[], set[str]],
                 on_event: Callable[[object], None]):
        self._engine = engine
        self._enabled = enabled_provider
        self._on_event = on_event
        self._devices: list = []
        self._ui = None
        self._grabbed = False
        self._stop_r = -1
        self._stop_w = -1
        self._stopping = False
        self._capture = None        # ChordCollector while capturing a hotkey
        self._capture_cb = None

    def run(self, *, device_override: str = "", grab: bool = True) -> None:
        from evdev import UInput, ecodes

        self._devices = open_devices(device_override)
        self._stop_r, self._stop_w = os.pipe()
        self._stopping = False
        try:
            if grab:
                self._ui = UInput.from_device(*self._devices, name="easytype-virtual-kbd")
                for d in self._devices:
                    d.grab()
                self._grabbed = True
            self._loop(ecodes)
        finally:
            self.cleanup()

    def stop(self) -> None:
        """Ask the run loop to exit promptly. Safe to call from another thread."""
        self._stopping = True
        if self._stop_w != -1:
            try:
                os.write(self._stop_w, b"\x00")
            except OSError:
                pass

    def begin_capture(self, on_captured: Callable[[list], None]) -> None:
        """Capture the next key chord and deliver its keycodes to on_captured.
        Called from the GUI thread; the callback fires on the listener thread."""
        from easytype.chords import ChordCollector
        # Set the callback before arming capture so the listener thread never sees
        # capture active with a None callback.
        self._capture_cb = on_captured
        self._capture = ChordCollector()

    def _loop(self, ecodes) -> None:
        sel = selectors.DefaultSelector()
        for d in self._devices:
            sel.register(d, selectors.EVENT_READ)
        sel.register(self._stop_r, selectors.EVENT_READ)
        while not self._stopping:
            for key, _mask in sel.select():
                if key.fd == self._stop_r:
                    return
                for event in key.fileobj.read():
                    self._handle(event, ecodes)

    def _handle(self, event, ecodes) -> None:
        if self._capture is not None:
            if event.type == ecodes.EV_KEY and self._capture.feed(event.code, event.value):
                keys = self._capture.keys
                cb = self._capture_cb
                self._capture = None
                self._capture_cb = None
                if cb:
                    cb(keys)
            return                          # swallow everything during capture
        if event.type != ecodes.EV_KEY:
            if self._ui is not None:
                self._ui.write_event(event)
                self._ui.syn()
            return
        outcome = self._engine.feed(event.code, event.value, self._enabled())
        if outcome.pressed or outcome.released:
            self._on_event(outcome)
        if not outcome.swallow and self._ui is not None:
            self._ui.write_event(event)
            self._ui.syn()

    def cleanup(self) -> None:
        if self._grabbed:
            for d in self._devices:
                try:
                    d.ungrab()
                except Exception:
                    pass
            self._grabbed = False
        if self._ui is not None:
            try:
                self._ui.close()
            except Exception:
                pass
            self._ui = None
        for d in self._devices:
            try:
                d.close()
            except Exception:
                pass
        self._devices = []
        for fd in (self._stop_r, self._stop_w):
            if fd != -1:
                try:
                    os.close(fd)
                except OSError:
                    pass
        self._stop_r = self._stop_w = -1
        self._stopping = False
