# EasyType Phase 2 — Tray + Settings GUI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a PySide6 system-tray app and tabbed Settings window that drive the existing dictation engine and edit `~/.config/easytype/config.toml`, with apply-on-save and live in-window hotkey capture.

**Architecture:** One process. Qt (tray + window) runs on the main thread; the Phase 1 engine runs on a background thread behind a deliberately Qt-free `EngineSupervisor`. The tray reads engine state via a lightweight poll; hotkey-capture results return via a thread-safe Qt signal. The config file stays the single source of truth.

**Tech Stack:** Python 3.12, PySide6 (Qt6), evdev, tomlkit, pytest. Spec: `docs/superpowers/specs/2026-05-29-easytype-phase2-gui-design.md`.

**Setup before Task 1:** create a feature branch off `main` (`phase2-gui`) — the executing skill handles this via superpowers:using-git-worktrees. Run automated tests with `.venv/bin/pytest`. The repo `.venv` deliberately lacks PySide6/evdev/sounddevice/faster-whisper; **GUI and engine-runtime tasks are verified by `python -m py_compile` plus a manual checklist on the user's pipx install**, matching the Phase 1 pattern (pure logic is unit-tested; hardware/GUI paths are verified by hand).

---

## File structure

**New files:**
- `src/easytype/engine.py` — `build_engine(config, session)` + `EngineBundle`; the engine wiring extracted from `cli.cmd_run` so CLI and GUI build it identically.
- `src/easytype/supervisor.py` — `EngineSupervisor`: engine lifecycle on a worker thread (Qt-free, unit-tested).
- `src/easytype/gui/__init__.py` — empty package marker.
- `src/easytype/gui/app.py` — `main()`: QApplication, single-instance, tray icon + menu, state poll, icon rendering.
- `src/easytype/gui/settings.py` — tabbed `SettingsWindow` + `HotkeyRow`.
- `src/easytype/gui/style.qss` — dark + amber stylesheet (package data).
- `autostart/easytype.desktop` — sample launch-at-login entry.
- `tests/test_supervisor.py` — supervisor lifecycle tests with injected fakes.

**Modified files:**
- `src/easytype/chords.py` — add `ChordCollector`.
- `src/easytype/controller.py` — add `toggle_recording()`.
- `src/easytype/config.py` — add `apply_settings_to_doc()` (+ `_table` helper).
- `src/easytype/listener.py` — clean stop (self-pipe) + hotkey capture mode.
- `src/easytype/cli.py` — `cmd_set_hotkey` and `cmd_run` use the shared helpers.
- `pyproject.toml` — PySide6 dependency, `easytype-gui` entry point, package data.
- `README.md` — Phase 2 GUI section.
- `tests/test_chords.py`, `tests/test_config.py`, `tests/test_controller.py` — new tests.

---

## Task 1: `ChordCollector` (shared hotkey-chord state machine)

**Files:**
- Modify: `src/easytype/chords.py`
- Modify: `src/easytype/cli.py` (refactor `cmd_set_hotkey` to use it — its first consumer)
- Test: `tests/test_chords.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_chords.py` (and update the import line at the top to add `ChordCollector`):

```python
from easytype.chords import HotkeyEngine, trigger_key, ChordCollector
```

```python
def test_chord_collector_single_key():
    c = ChordCollector()
    assert c.feed(KEY_SPACE, 1) is False
    assert c.feed(KEY_SPACE, 0) is True
    assert c.keys == [KEY_SPACE]


def test_chord_collector_modifier_combo_completes_on_full_release():
    c = ChordCollector()
    c.feed(KEY_LEFTCTRL, 1)
    c.feed(KEY_SPACE, 1)
    assert c.feed(KEY_SPACE, 0) is False     # ctrl still held
    assert c.feed(KEY_LEFTCTRL, 0) is True
    assert c.keys == [KEY_LEFTCTRL, KEY_SPACE]


def test_chord_collector_preserves_press_order_regardless_of_release_order():
    c = ChordCollector()
    c.feed(KEY_LEFTCTRL, 1)
    c.feed(KEY_SPACE, 1)
    c.feed(KEY_LEFTCTRL, 0)                   # release ctrl first
    assert c.feed(KEY_SPACE, 0) is True
    assert c.keys == [KEY_LEFTCTRL, KEY_SPACE]


def test_chord_collector_ignores_autorepeat_and_duplicate_press():
    c = ChordCollector()
    c.feed(KEY_SPACE, 1)
    c.feed(KEY_SPACE, 2)                      # autorepeat
    c.feed(KEY_SPACE, 1)                      # duplicate down
    assert c.feed(KEY_SPACE, 0) is True
    assert c.keys == [KEY_SPACE]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_chords.py -k chord_collector -v`
Expected: FAIL with `ImportError: cannot import name 'ChordCollector'`.

- [ ] **Step 3: Implement `ChordCollector`**

Append to `src/easytype/chords.py`:

```python
class ChordCollector:
    """Records the first-press order of a key chord and reports completion once
    every pressed key is released. Shared by the CLI `--set-hotkey` capture and
    the GUI's in-window 'Set' capture."""

    def __init__(self) -> None:
        self._pressed: list[int] = []   # first-press order
        self._seen: set[int] = set()
        self._down: set[int] = set()
        self.done = False

    def feed(self, code: int, value: int) -> bool:
        if value == 1:                  # key down
            if code not in self._seen:
                self._seen.add(code)
                self._pressed.append(code)
            self._down.add(code)
        elif value == 0:                # key up
            self._down.discard(code)
            if self._pressed and not self._down:
                self.done = True
        return self.done

    @property
    def keys(self) -> list[int]:
        return list(self._pressed)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_chords.py -k chord_collector -v`
Expected: 4 passed.

- [ ] **Step 5: Refactor `cmd_set_hotkey` to use the collector (DRY its first consumer)**

In `src/easytype/cli.py`, inside `cmd_set_hotkey`, replace the manual capture block. Replace this:

```python
    print(f"Press the key or combination you want for '{name}', then release.")
    devices = open_devices("")
    pressed: list[int] = []
    seen: set[int] = set()
    try:
        sel = selectors.DefaultSelector()
        for d in devices:
            sel.register(d, selectors.EVENT_READ)
        down: set[int] = set()
        while True:
            done = False
            for key, _ in sel.select():
                for ev in key.fileobj.read():
                    if ev.type != ecodes.EV_KEY:
                        continue
                    if ev.value == 1 and ev.code not in seen:
                        seen.add(ev.code); pressed.append(ev.code); down.add(ev.code)
                    elif ev.value == 0:
                        down.discard(ev.code)
                        if pressed and not down:
                            done = True
            if done:
                break
    finally:
        for d in devices:
            d.close()
```

with:

```python
    from easytype.chords import ChordCollector

    print(f"Press the key or combination you want for '{name}', then release.")
    devices = open_devices("")
    collector = ChordCollector()
    try:
        sel = selectors.DefaultSelector()
        for d in devices:
            sel.register(d, selectors.EVENT_READ)
        done = False
        while not done:
            for key, _ in sel.select():
                for ev in key.fileobj.read():
                    if ev.type == ecodes.EV_KEY and collector.feed(ev.code, ev.value):
                        done = True
    finally:
        for d in devices:
            d.close()
    pressed = collector.keys
```

(The following lines — `desc = describe_chord(pressed)` etc. — are unchanged and now consume `pressed` from the collector.)

- [ ] **Step 6: Verify the whole suite still passes and the CLI module compiles**

Run: `.venv/bin/pytest -q && python -m py_compile src/easytype/cli.py src/easytype/chords.py`
Expected: all tests pass (59), no compile output.

- [ ] **Step 7: Commit**

```bash
git add src/easytype/chords.py src/easytype/cli.py tests/test_chords.py
git commit -m "feat: add ChordCollector and reuse it in --set-hotkey capture"
```

---

## Task 2: `Controller.toggle_recording()` (manual start/stop for the tray)

**Files:**
- Modify: `src/easytype/controller.py`
- Test: `tests/test_controller.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_controller.py`:

```python
def test_toggle_recording_starts_then_stops(tmp_path):
    ctrl, inj = build(tmp_path)
    assert ctrl.state == "idle"
    ctrl.toggle_recording()
    assert ctrl.state == "recording"
    ctrl.toggle_recording()                       # synchronous in test mode
    assert ctrl.state == "idle"
    assert inj.injected and inj.injected[0][0] == "ops plus is ready"


def test_toggle_recording_noop_while_transcribing(tmp_path):
    ctrl, inj = build(tmp_path)
    ctrl.toggle_recording()                       # recording
    ctrl.state = "transcribing"
    ctrl.toggle_recording()                       # must do nothing
    assert ctrl.state == "transcribing"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_controller.py -k toggle_recording -v`
Expected: FAIL with `AttributeError: 'Controller' object has no attribute 'toggle_recording'`.

- [ ] **Step 3: Implement the method**

In `src/easytype/controller.py`, add after `on_repaste` (before the `# --- internals` section):

```python
    def toggle_recording(self) -> None:
        """Manual start/stop for the tray, independent of capture_mode."""
        with self._lock:
            if self.state == "idle":
                self._start()
            elif self.state == "recording":
                self._stop_and_process()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_controller.py -k toggle_recording -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add src/easytype/controller.py tests/test_controller.py
git commit -m "feat: Controller.toggle_recording for tray-driven start/stop"
```

---

## Task 3: `apply_settings_to_doc()` (write the Settings form back to TOML)

**Files:**
- Modify: `src/easytype/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_config.py`:

```python
SAMPLE_SETTINGS = {
    "capture_mode": "hold",
    "max_recording_duration": 30,
    "record_keys": [29, 57], "record_description": "Ctrl+Space",
    "cancel_keys": [1], "cancel_description": "Esc",
    "repaste_keys": [66], "repaste_description": "F8",
    "audio_device": "",
    "model": "small.en", "language": "en", "transcribe_device": "cuda",
    "injection_method": "paste", "type_delay_ms": 25,
    "formatter_enabled": True, "formatter_backend": "ollama",
    "ollama_model": "llama3.1", "ollama_url": "http://localhost:11434",
    "indicator_enabled": False, "indicator_position": "bottom-left", "indicator_count": "down",
    "keyboard_device": "",
}


def test_apply_settings_round_trips(tmp_path: Path):
    path = tmp_path / "config.toml"
    cfg.load_config(path)                       # write defaults
    doc = cfg.load_doc(path)
    cfg.apply_settings_to_doc(doc, SAMPLE_SETTINGS)
    cfg.save_doc(doc, path)
    c = cfg.load_config(path)
    assert c.capture_mode == "hold"
    assert c.max_recording_duration == 30
    assert c.model == "small.en"
    assert c.transcribe_device == "cuda"
    assert c.injection_method == "paste"
    assert c.type_delay_ms == 25
    assert c.formatter_enabled is True
    assert c.indicator_enabled is False
    assert c.indicator_position == "bottom-left"
    assert c.indicator_count == "down"


def test_apply_settings_preserves_comments(tmp_path: Path):
    path = tmp_path / "config.toml"
    cfg.load_config(path)
    doc = cfg.load_doc(path)
    cfg.apply_settings_to_doc(doc, SAMPLE_SETTINGS)
    cfg.save_doc(doc, path)
    text = path.read_text()
    assert "Raw evdev keycodes" in text          # standalone comment line survives
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_config.py -k apply_settings -v`
Expected: FAIL with `AttributeError: module 'easytype.config' has no attribute 'apply_settings_to_doc'`.

- [ ] **Step 3: Implement the function**

Append to `src/easytype/config.py`:

```python
def _table(doc: tomlkit.TOMLDocument, name: str):
    if name not in doc:
        doc[name] = tomlkit.table()
    return doc[name]


def apply_settings_to_doc(doc: tomlkit.TOMLDocument, values: dict) -> None:
    """Write a flat settings dict into the TOML document, preserving comments.
    Reuses set_hotkey_in_doc for the three hotkeys."""
    doc["capture_mode"] = values["capture_mode"]
    doc["max_recording_duration"] = int(values["max_recording_duration"])

    set_hotkey_in_doc(doc, "record", list(values["record_keys"]), values["record_description"])
    set_hotkey_in_doc(doc, "cancel", list(values["cancel_keys"]), values["cancel_description"])
    set_hotkey_in_doc(doc, "repaste", list(values["repaste_keys"]), values["repaste_description"])

    _table(doc, "audio")["device"] = values["audio_device"]

    tr = _table(doc, "transcription")
    tr["model"] = values["model"]
    tr["language"] = values["language"]
    tr["device"] = values["transcribe_device"]

    inj = _table(doc, "injection")
    inj["method"] = values["injection_method"]
    inj["type_delay_ms"] = int(values["type_delay_ms"])

    fmt = _table(doc, "formatter")
    fmt["enabled"] = bool(values["formatter_enabled"])
    fmt["backend"] = values["formatter_backend"]
    fmt["ollama_model"] = values["ollama_model"]
    fmt["ollama_url"] = values["ollama_url"]

    ind = _table(doc, "indicator")
    ind["enabled"] = bool(values["indicator_enabled"])
    ind["position"] = values["indicator_position"]
    ind["count"] = values["indicator_count"]

    _table(doc, "keyboard")["device"] = values["keyboard_device"]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_config.py -k apply_settings -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add src/easytype/config.py tests/test_config.py
git commit -m "feat: apply_settings_to_doc to persist the Settings form to TOML"
```

---

## Task 4: Listener — clean stop + hotkey capture mode

**Files:**
- Modify: `src/easytype/listener.py`

No unit test (the listener loop needs real evdev — untested in Phase 1 too). Verified by `py_compile`, the full suite (imports stay valid), and the manual checklist in Task 10.

- [ ] **Step 1: Add the `os` import**

In `src/easytype/listener.py`, change the import block at the top to add `import os`:

```python
from __future__ import annotations

import os
import selectors
from collections.abc import Callable

from easytype.chords import HotkeyEngine
```

- [ ] **Step 2: Extend `__init__` with stop-pipe and capture fields**

Replace the body of `Listener.__init__` with:

```python
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
```

- [ ] **Step 3: Create the stop pipe in `run`**

Replace `Listener.run` with:

```python
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
```

- [ ] **Step 4: Add `stop` and `begin_capture`**

Insert these methods after `run`:

```python
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
        Invoked and fired on the listener thread."""
        from easytype.chords import ChordCollector
        self._capture = ChordCollector()
        self._capture_cb = on_captured
```

- [ ] **Step 5: Make the loop watch the stop pipe**

Replace `Listener._loop` with:

```python
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
```

- [ ] **Step 6: Route events through capture mode in `_handle`**

Replace `Listener._handle` with:

```python
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
```

- [ ] **Step 7: Close the pipe in `cleanup`**

Replace `Listener.cleanup` with:

```python
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
```

- [ ] **Step 8: Verify compile + suite**

Run: `python -m py_compile src/easytype/listener.py && .venv/bin/pytest -q`
Expected: no compile output; all tests pass (61).

- [ ] **Step 9: Commit**

```bash
git add src/easytype/listener.py
git commit -m "feat: listener clean-stop pipe and in-loop hotkey capture mode"
```

---

## Task 5: Extract `build_engine` and refactor `cmd_run`

**Files:**
- Create: `src/easytype/engine.py`
- Modify: `src/easytype/cli.py`

No new unit test (construction needs hardware libs; covered indirectly by Task 6 via an injected fake builder). Verified by `py_compile` and the full suite. Behavior of `easytype` is unchanged.

- [ ] **Step 1: Create `src/easytype/engine.py`**

```python
from __future__ import annotations

import subprocess
from collections.abc import Callable
from dataclasses import dataclass

from easytype.chords import HotkeyEngine
from easytype.config import Config
from easytype.controller import Controller


def notify_send(title: str, body: str) -> None:
    subprocess.run(["notify-send", title, body], check=False)


@dataclass
class EngineBundle:
    listener: object
    controller: Controller
    warmup: Callable[[], None]


def build_engine(config: Config, session: str,
                 notify: Callable[[str, str], None] = notify_send) -> EngineBundle:
    """Wire up the dictation engine from a Config. Shared by the headless CLI and
    the GUI supervisor so both build the engine identically."""
    from easytype.indicator import create_indicator
    from easytype.injector import get_injector
    from easytype.listener import Listener
    from easytype.recorder import Recorder
    from easytype.transcriber import Transcriber

    transcriber = Transcriber(config.model, config.language, config.transcribe_device)
    controller = Controller(
        config=config,
        recorder=Recorder(config.audio_device),
        transcriber=transcriber,
        injector=get_injector(session, config.type_delay_ms),
        indicator=create_indicator(config),
        notify=notify,
        synchronous=False,
    )
    engine = HotkeyEngine({
        "record": config.record.keys,
        "cancel": config.cancel.keys,
        "repaste": config.repaste.keys,
    })

    def on_event(outcome):
        if outcome.pressed == "record":
            controller.on_record()
        elif outcome.released == "record":
            controller.on_record_release()
        elif outcome.pressed == "cancel":
            controller.on_cancel()
        elif outcome.pressed == "repaste":
            controller.on_repaste()

    listener = Listener(engine, controller.enabled_names, on_event)
    return EngineBundle(listener=listener, controller=controller, warmup=transcriber.warmup)
```

- [ ] **Step 2: Refactor `cmd_run` in `src/easytype/cli.py`**

Replace the whole body of `cmd_run` (from `config = load_config()` to `return 0`) with:

```python
    config = load_config()
    session = preflight.detect_session()

    if session == "wayland":
        print(
            "EasyType Phase 1 supports X11 only — Wayland text injection isn't "
            "implemented yet.\nSee the README (Troubleshooting) for status."
        )
        return 1

    issues = preflight.check()
    blocking = [i for i in issues if not i.ok and not i.name.startswith("python3-tk")]
    grab = not passive
    if blocking and not passive:
        print(preflight.format_report(issues))
        print("\nFalling back to --passive (no consume) because grab prerequisites are missing.")
        grab = False

    from easytype.engine import build_engine

    bundle = build_engine(config, session)
    threading.Thread(target=bundle.warmup, daemon=True).start()
    print("[easytype] warming up the transcription model in the background…")

    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, _raise_keyboard_interrupt)

    print(f"[easytype] session={session}  mode={config.capture_mode}  "
          f"record={config.record.description}  grab={grab}")
    try:
        bundle.listener.run(device_override=config.keyboard_device, grab=grab)
    except KeyboardInterrupt:
        print("\n[easytype] shutting down…")
    finally:
        bundle.listener.cleanup()
    return 0
```

- [ ] **Step 3: Remove the now-dead `_notify` helper and `subprocess` import from `cli.py`**

Delete the `import subprocess` line and the `_notify` function:

```python
def _notify(title: str, body: str) -> None:
    subprocess.run(["notify-send", title, body], check=False)
```

(`cmd_run` no longer references `_notify`; `notify_send` now lives in `engine.py`.)

- [ ] **Step 4: Verify compile + full suite + CLI help still works**

Run: `python -m py_compile src/easytype/engine.py src/easytype/cli.py && .venv/bin/pytest -q && .venv/bin/easytype --help`
Expected: no compile output; all tests pass (61); the argparse help prints with `--passive`, `--check`, `--set-hotkey`.

- [ ] **Step 5: Commit**

```bash
git add src/easytype/engine.py src/easytype/cli.py
git commit -m "refactor: extract build_engine; cmd_run builds via shared wiring"
```

---

## Task 6: `EngineSupervisor` (engine lifecycle on a worker thread)

**Files:**
- Create: `src/easytype/supervisor.py`
- Test: `tests/test_supervisor.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_supervisor.py`:

```python
import threading
import time
import types

from easytype.supervisor import EngineSupervisor


class FakeListener:
    def __init__(self):
        self._go = threading.Event()
        self.stopped = False
        self.capture_cb = None
        self.ran = False

    def run(self, *, device_override="", grab=True):
        self.ran = True
        self._go.wait(timeout=5)             # block like the real evdev loop

    def stop(self):
        self.stopped = True
        self._go.set()

    def begin_capture(self, on_captured):
        self.capture_cb = on_captured


class FakeController:
    def __init__(self):
        self.state = "idle"
        self.toggled = 0

    def toggle_recording(self):
        self.toggled += 1

    def on_cancel(self):
        ...


class FakeBundle:
    def __init__(self):
        self.listener = FakeListener()
        self.controller = FakeController()
        self.warmed = False

    def warmup(self):
        self.warmed = True


def _fake_config():
    return types.SimpleNamespace(keyboard_device="")


def _wait(predicate, timeout=2.0):
    deadline = time.time() + timeout
    while not predicate() and time.time() < deadline:
        time.sleep(0.005)


def test_start_runs_engine_then_stop_joins():
    made = []
    sup = EngineSupervisor(session="x11",
                           builder=lambda cfg: made.append(FakeBundle()) or made[-1],
                           config_loader=_fake_config)
    sup.start()
    _wait(lambda: made and made[0].listener.ran)
    assert made[0].listener.ran is True
    assert sup.state == "idle"
    sup.stop()
    assert made[0].listener.stopped is True
    assert sup.state == "stopped"


def test_reload_rebuilds_engine_from_fresh_config():
    builds = []
    sup = EngineSupervisor(session="x11",
                           builder=lambda cfg: builds.append(FakeBundle()) or builds[-1],
                           config_loader=_fake_config)
    sup.start()
    _wait(lambda: builds and builds[0].listener.ran)
    sup.reload()
    assert len(builds) == 2
    assert builds[0].listener.stopped is True
    sup.stop()


def test_toggle_and_capture_delegate_to_engine():
    b = FakeBundle()
    sup = EngineSupervisor(session="x11", builder=lambda cfg: b, config_loader=_fake_config)
    sup.start()
    _wait(lambda: b.listener.ran)
    sup.toggle_recording()
    assert b.controller.toggled == 1
    cb = lambda keys: None
    sup.begin_hotkey_capture(cb)
    assert b.listener.capture_cb is cb
    sup.stop()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_supervisor.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'easytype.supervisor'`.

- [ ] **Step 3: Implement the supervisor**

Create `src/easytype/supervisor.py`:

```python
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
        self._thread = None

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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_supervisor.py -v`
Expected: 3 passed.

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/pytest -q`
Expected: all tests pass (64).

- [ ] **Step 6: Commit**

```bash
git add src/easytype/supervisor.py tests/test_supervisor.py
git commit -m "feat: EngineSupervisor manages engine lifecycle on a worker thread"
```

---

## Task 7: Packaging — PySide6 dependency, `easytype-gui` entry point, package data

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add the dependency**

In `pyproject.toml`, change the `dependencies` list to add PySide6:

```toml
dependencies = [
    "sounddevice>=0.4",
    "faster-whisper>=1.0",
    "evdev>=1.6",
    "numpy>=1.24",
    "tomlkit>=0.12",
    "PySide6>=6.6",
]
```

- [ ] **Step 2: Add the GUI entry point**

Change `[project.scripts]` to:

```toml
[project.scripts]
easytype = "easytype.cli:main"
easytype-gui = "easytype.gui.app:main"
```

- [ ] **Step 3: Ship the stylesheet as package data**

After the `[tool.setuptools.packages.find]` block, add:

```toml
[tool.setuptools.package-data]
easytype = ["gui/style.qss"]
```

- [ ] **Step 4: Verify the project still installs into the test venv (without heavy deps)**

Run: `.venv/bin/pip install -e . --no-deps && .venv/bin/pytest -q`
Expected: install succeeds; all tests pass (64). (PySide6 is NOT installed here — that's intentional; GUI tasks are verified on the pipx install.)

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml
git commit -m "build: add PySide6 dep, easytype-gui entry point, qss package data"
```

---

## Task 8: GUI — tray app + icon (`gui/app.py`)

**Files:**
- Create: `src/easytype/gui/__init__.py`
- Create: `src/easytype/gui/app.py`

Verified by `py_compile` + the Task 10 manual checklist (PySide6 isn't in the test venv).

- [ ] **Step 1: Create the package marker**

Create `src/easytype/gui/__init__.py` (empty file).

- [ ] **Step 2: Create `src/easytype/gui/app.py`**

```python
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QRectF
from PySide6.QtGui import QAction, QBrush, QColor, QFont, QIcon, QPainter, QPen, QPixmap
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from easytype import preflight
from easytype.config import load_config, load_doc, save_doc
from easytype.supervisor import EngineSupervisor

_LOCK_NAME = "easytype-gui-singleton"
_STYLE = Path(__file__).with_name("style.qss")

_STATUS_LABELS = {
    "recording": "Recording…", "transcribing": "Transcribing…",
    "idle": "Idle", "stopped": "Stopped", "disabled": "Disabled (Wayland)",
}


def make_icon(active: bool) -> QIcon:
    pm = QPixmap(64, 64)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(QColor("#f59e0b")))
    p.drawRoundedRect(QRectF(4, 4, 56, 56), 14, 14)
    p.setPen(QColor("#241a06"))
    font = QFont("Sans", 34)
    font.setBold(True)
    p.setFont(font)
    p.drawText(pm.rect(), Qt.AlignCenter, "E")
    if active:
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor("#ffffff"), 4))
        p.drawRoundedRect(QRectF(3, 3, 58, 58), 15, 15)
    p.end()
    return QIcon(pm)


def _already_running() -> bool:
    sock = QLocalSocket()
    sock.connectToServer(_LOCK_NAME)
    running = sock.waitForConnected(150)
    sock.close()
    return running


class TrayApp:
    def __init__(self, app: QApplication):
        self._app = app
        self._idle_icon = make_icon(False)
        self._active_icon = make_icon(True)
        self._settings_window = None

        session = preflight.detect_session()
        self._wayland = session == "wayland"
        self._sup = EngineSupervisor(session=session, grab=self._decide_grab())

        if self._wayland:
            QMessageBox.warning(
                None, "EasyType",
                "EasyType dictation needs an X11 session; Wayland isn't supported yet.\n"
                "You can still edit Settings, but dictation won't run.",
            )
        else:
            self._sup.start()

        self._mode = str(load_config().capture_mode)

        self._tray = QSystemTrayIcon(self._idle_icon)
        self._build_menu()
        self._tray.show()

        self._timer = QTimer()
        self._timer.timeout.connect(self._refresh)
        self._timer.start(200)
        self._refresh()

    def _decide_grab(self) -> bool:
        issues = preflight.check()
        blocking = [i for i in issues if not i.ok and not i.name.startswith("python3-tk")]
        return not blocking

    def _build_menu(self):
        menu = QMenu()
        self._status_action = QAction("Idle")
        self._status_action.setEnabled(False)
        menu.addAction(self._status_action)
        menu.addSeparator()

        self._toggle_rec = QAction("Start dictation")
        self._toggle_rec.triggered.connect(self._sup.toggle_recording)
        menu.addAction(self._toggle_rec)

        self._mode_action = QAction("Switch to Hold mode")
        self._mode_action.triggered.connect(self._switch_mode)
        menu.addAction(self._mode_action)
        menu.addSeparator()

        settings = QAction("Settings…")
        settings.triggered.connect(self._open_settings)
        menu.addAction(settings)

        quit_action = QAction("Quit")
        quit_action.triggered.connect(self._quit)
        menu.addAction(quit_action)

        self._tray.setContextMenu(menu)
        self._update_mode_label()

    def _update_mode_label(self):
        self._mode_action.setText(
            "Switch to Hold mode" if self._mode == "toggle" else "Switch to Toggle mode"
        )

    def _switch_mode(self):
        doc = load_doc()
        self._mode = "hold" if str(doc.get("capture_mode", "toggle")) == "toggle" else "toggle"
        doc["capture_mode"] = self._mode
        save_doc(doc)
        self._update_mode_label()
        if not self._wayland:
            self._sup.reload()

    def _open_settings(self):
        from easytype.gui.settings import SettingsWindow
        if self._settings_window is None:
            self._settings_window = SettingsWindow(self._sup, on_saved=self._after_save)
        self._settings_window.show()
        self._settings_window.raise_()
        self._settings_window.activateWindow()

    def _after_save(self):
        self._mode = str(load_config().capture_mode)
        self._update_mode_label()

    def _refresh(self):
        state = "disabled" if self._wayland else self._sup.state
        label = _STATUS_LABELS.get(state, state)
        self._status_action.setText(label)
        active = state in ("recording", "transcribing")
        self._tray.setIcon(self._active_icon if active else self._idle_icon)
        self._toggle_rec.setText("Stop dictation" if active else "Start dictation")
        self._tray.setToolTip(f"EasyType — {label}")

    def _quit(self):
        self._timer.stop()
        self._sup.stop()
        self._app.quit()


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("EasyType")
    if _already_running():
        print("EasyType is already running.")
        return
    server = QLocalServer()
    QLocalServer.removeServer(_LOCK_NAME)
    server.listen(_LOCK_NAME)

    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.critical(None, "EasyType", "No system tray is available on this desktop.")
        return

    app.setWindowIcon(make_icon(False))
    if _STYLE.exists():
        app.setStyleSheet(_STYLE.read_text())
    app.setQuitOnLastWindowClosed(False)        # closing Settings must not kill the tray

    tray = TrayApp(app)
    app._easytype_tray = tray                     # keep a strong reference
    sys.exit(app.exec())
```

- [ ] **Step 3: Verify it compiles**

Run: `python -m py_compile src/easytype/gui/app.py`
Expected: no output. (Importing it requires PySide6, which the pipx install has — covered by the Task 10 manual run.)

- [ ] **Step 4: Commit**

```bash
git add src/easytype/gui/__init__.py src/easytype/gui/app.py
git commit -m "feat: system-tray app with amber E icon, status poll, and menu"
```

---

## Task 9: GUI — tabbed Settings window (`gui/settings.py`)

**Files:**
- Create: `src/easytype/gui/settings.py`

Verified by `py_compile` + the Task 10 manual checklist. The save path reuses `apply_settings_to_doc` (unit-tested in Task 3).

- [ ] **Step 1: Create `src/easytype/gui/settings.py`**

```python
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPushButton, QSpinBox, QTabWidget, QVBoxLayout, QWidget,
)

from easytype.config import apply_settings_to_doc, load_config, load_doc, save_doc
from easytype.keycodes import conflict_note, describe_chord

MODELS = ["tiny.en", "base.en", "small.en", "medium.en", "large-v3"]
LANGS = ["en", "es", "fr", "de", "it", "pt", "nl"]
COMPUTE = ["auto", "cuda", "cpu"]
POSITIONS = ["top-right", "top-center", "bottom-right", "bottom-left", "top-left"]


def _input_device_names() -> list[str]:
    try:
        import sounddevice as sd
        return [d["name"] for d in sd.query_devices() if d.get("max_input_channels", 0) > 0]
    except Exception:
        return []


class HotkeyRow(QWidget):
    """Current-description + clash note + Set button that captures a chord live."""
    captured = Signal(object)            # emitted (list[int]) from the engine thread

    def __init__(self, supervisor):
        super().__init__()
        self._sup = supervisor
        self.keys: list[int] = []
        self.description = ""
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        self._desc = QLabel("—")
        self._note = QLabel("")
        self._note.setObjectName("conflict")
        self._set = QPushButton("Set")
        self._set.clicked.connect(self._begin)
        row.addWidget(self._desc, 1)
        row.addWidget(self._note, 1)
        row.addWidget(self._set)
        self.captured.connect(self._on_captured)    # delivered on the GUI thread

    def set_value(self, keys, description):
        self.keys = list(keys)
        self.description = description
        self._desc.setText(description or "—")
        self._note.setText("")

    def _begin(self):
        self._set.setText("Press keys…")
        self._set.setEnabled(False)
        self._sup.begin_hotkey_capture(lambda keys: self.captured.emit(keys))

    def _on_captured(self, keys):
        self.keys = list(keys)
        self.description = describe_chord(keys)
        self._desc.setText(self.description or "—")
        self._note.setText(conflict_note(keys) or "")
        self._set.setText("Set")
        self._set.setEnabled(True)


class SettingsWindow(QDialog):
    def __init__(self, supervisor, on_saved=None):
        super().__init__()
        self._sup = supervisor
        self._on_saved = on_saved
        self.setWindowTitle("EasyType — Settings")
        self.resize(480, 440)

        tabs = QTabWidget()
        tabs.addTab(self._recording_tab(), "Recording")
        tabs.addTab(self._audio_tab(), "Audio & Transcription")
        tabs.addTab(self._typing_tab(), "Typing")
        tabs.addTab(self._ai_tab(), "AI cleanup")
        tabs.addTab(self._indicator_tab(), "Indicator")
        tabs.addTab(self._advanced_tab(), "Advanced")

        save = QPushButton("Save")
        save.setObjectName("primary")
        save.clicked.connect(self._save)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.close)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(cancel)
        buttons.addWidget(save)

        root = QVBoxLayout(self)
        root.addWidget(tabs)
        root.addLayout(buttons)
        self._load()

    def _recording_tab(self):
        w = QWidget(); form = QFormLayout(w)
        self.capture_mode = QComboBox(); self.capture_mode.addItems(["toggle", "hold"])
        self.max_duration = QSpinBox(); self.max_duration.setRange(0, 3600); self.max_duration.setSuffix(" s")
        self.record_row = HotkeyRow(self._sup)
        self.cancel_row = HotkeyRow(self._sup)
        self.repaste_row = HotkeyRow(self._sup)
        form.addRow("Mode", self.capture_mode)
        form.addRow("Max length", self.max_duration)
        form.addRow("Record", self.record_row)
        form.addRow("Cancel", self.cancel_row)
        form.addRow("Repaste", self.repaste_row)
        return w

    def _audio_tab(self):
        w = QWidget(); form = QFormLayout(w)
        self.audio_device = QComboBox()
        self.audio_device.addItem("Default", "")
        for name in _input_device_names():
            self.audio_device.addItem(name, name)
        self.model = QComboBox(); self.model.setEditable(True); self.model.addItems(MODELS)
        self.language = QComboBox(); self.language.setEditable(True); self.language.addItems(LANGS)
        self.transcribe_device = QComboBox(); self.transcribe_device.addItems(COMPUTE)
        form.addRow("Microphone", self.audio_device)
        form.addRow("Model", self.model)
        form.addRow("Language", self.language)
        form.addRow("Compute", self.transcribe_device)
        return w

    def _typing_tab(self):
        w = QWidget(); form = QFormLayout(w)
        self.injection_method = QComboBox(); self.injection_method.addItems(["type", "paste"])
        self.type_delay = QSpinBox(); self.type_delay.setRange(0, 500); self.type_delay.setSuffix(" ms")
        form.addRow("Insert via", self.injection_method)
        form.addRow("Keystroke delay", self.type_delay)
        return w

    def _ai_tab(self):
        w = QWidget(); form = QFormLayout(w)
        self.formatter_enabled = QCheckBox("Clean up transcripts with a model")
        self.formatter_backend = QComboBox(); self.formatter_backend.addItems(["ollama", "openai"])
        self.ollama_model = QLineEdit()
        self.ollama_url = QLineEdit()
        self.formatter_enabled.toggled.connect(self._sync_ai_enabled)
        form.addRow(self.formatter_enabled)
        form.addRow("Backend", self.formatter_backend)
        form.addRow("Ollama model", self.ollama_model)
        form.addRow("Ollama URL", self.ollama_url)
        return w

    def _indicator_tab(self):
        w = QWidget(); form = QFormLayout(w)
        self.indicator_enabled = QCheckBox("Show the on-screen recording indicator")
        self.indicator_position = QComboBox(); self.indicator_position.addItems(POSITIONS)
        self.indicator_count = QComboBox(); self.indicator_count.addItems(["up", "down"])
        form.addRow(self.indicator_enabled)
        form.addRow("Position", self.indicator_position)
        form.addRow("Count", self.indicator_count)
        return w

    def _advanced_tab(self):
        w = QWidget(); form = QFormLayout(w)
        self.keyboard_device = QLineEdit()
        self.keyboard_device.setPlaceholderText("blank = auto-detect")
        form.addRow("Keyboard device", self.keyboard_device)
        return w

    def _sync_ai_enabled(self, on):
        for wdg in (self.formatter_backend, self.ollama_model, self.ollama_url):
            wdg.setEnabled(on)

    def _load(self):
        c = load_config()
        self.capture_mode.setCurrentText(c.capture_mode)
        self.max_duration.setValue(c.max_recording_duration)
        self.record_row.set_value(c.record.keys, c.record.description)
        self.cancel_row.set_value(c.cancel.keys, c.cancel.description)
        self.repaste_row.set_value(c.repaste.keys, c.repaste.description)
        idx = self.audio_device.findData(c.audio_device)
        self.audio_device.setCurrentIndex(idx if idx >= 0 else 0)
        self.model.setCurrentText(c.model)
        self.language.setCurrentText(c.language)
        self.transcribe_device.setCurrentText(c.transcribe_device)
        self.injection_method.setCurrentText(c.injection_method)
        self.type_delay.setValue(c.type_delay_ms)
        self.formatter_enabled.setChecked(c.formatter_enabled)
        self.formatter_backend.setCurrentText(c.formatter_backend)
        self.ollama_model.setText(c.ollama_model)
        self.ollama_url.setText(c.ollama_url)
        self.indicator_enabled.setChecked(c.indicator_enabled)
        self.indicator_position.setCurrentText(c.indicator_position)
        self.indicator_count.setCurrentText(c.indicator_count)
        self.keyboard_device.setText(c.keyboard_device)
        self._sync_ai_enabled(c.formatter_enabled)

    def _values(self):
        return {
            "capture_mode": self.capture_mode.currentText(),
            "max_recording_duration": self.max_duration.value(),
            "record_keys": self.record_row.keys, "record_description": self.record_row.description,
            "cancel_keys": self.cancel_row.keys, "cancel_description": self.cancel_row.description,
            "repaste_keys": self.repaste_row.keys, "repaste_description": self.repaste_row.description,
            "audio_device": self.audio_device.currentData() or "",
            "model": self.model.currentText(),
            "language": self.language.currentText(),
            "transcribe_device": self.transcribe_device.currentText(),
            "injection_method": self.injection_method.currentText(),
            "type_delay_ms": self.type_delay.value(),
            "formatter_enabled": self.formatter_enabled.isChecked(),
            "formatter_backend": self.formatter_backend.currentText(),
            "ollama_model": self.ollama_model.text(),
            "ollama_url": self.ollama_url.text(),
            "indicator_enabled": self.indicator_enabled.isChecked(),
            "indicator_position": self.indicator_position.currentText(),
            "indicator_count": self.indicator_count.currentText(),
            "keyboard_device": self.keyboard_device.text(),
        }

    def _save(self):
        try:
            doc = load_doc()
            apply_settings_to_doc(doc, self._values())
            save_doc(doc)
        except Exception as exc:
            QMessageBox.critical(self, "EasyType", f"Could not save settings:\n{exc}")
            return
        self._sup.reload()
        if self._on_saved:
            self._on_saved()
        self.close()
```

- [ ] **Step 2: Verify it compiles**

Run: `python -m py_compile src/easytype/gui/settings.py`
Expected: no output.

- [ ] **Step 3: Commit**

```bash
git add src/easytype/gui/settings.py
git commit -m "feat: tabbed Settings window with live hotkey capture and apply-on-save"
```

---

## Task 10: Theme, autostart sample, docs, and full manual verification

**Files:**
- Create: `src/easytype/gui/style.qss`
- Create: `autostart/easytype.desktop`
- Modify: `README.md`

- [ ] **Step 1: Create `src/easytype/gui/style.qss`**

```css
* { color: #e6e6ea; font-size: 13px; }
QDialog, QWidget { background: #16161a; }
QTabWidget::pane { border: 1px solid #2a2a30; border-radius: 8px; }
QTabBar::tab {
    background: #1b1b21; color: #9a9aa5;
    padding: 7px 14px; margin-right: 2px;
    border-top-left-radius: 6px; border-top-right-radius: 6px;
}
QTabBar::tab:selected { background: #26262e; color: #f5b342; }
QComboBox, QLineEdit, QSpinBox {
    background: #26262e; border: 1px solid #34343d;
    border-radius: 6px; padding: 5px 8px; color: #e6e6ea;
}
QComboBox:focus, QLineEdit:focus, QSpinBox:focus { border: 1px solid #f59e0b; }
QPushButton {
    background: #2d2d35; border: 1px solid #3a3a42;
    border-radius: 7px; padding: 6px 14px; color: #e6e6ea;
}
QPushButton:hover { background: #34343d; }
QPushButton#primary { background: #f59e0b; color: #241a06; font-weight: 600; border: none; }
QPushButton#primary:hover { background: #ffb22e; }
QCheckBox { spacing: 8px; }
QLabel#conflict { color: #ffb22e; font-size: 11px; }
QMenu { background: #1b1b21; border: 1px solid #2a2a30; padding: 4px; }
QMenu::item { padding: 5px 16px; }
QMenu::item:selected { background: #2d2640; color: #f5b342; }
QMenu::item:disabled { color: #7a7a85; }
```

- [ ] **Step 2: Create `autostart/easytype.desktop`**

```ini
[Desktop Entry]
Type=Application
Name=EasyType
Comment=Local voice dictation (system tray)
Exec=easytype-gui
Icon=easytype
Terminal=false
Categories=Utility;Accessibility;
X-GNOME-Autostart-enabled=true
```

- [ ] **Step 3: Add a Phase 2 section to `README.md`**

Add this section (place it after the existing usage/run section):

```markdown
## Tray & Settings GUI (Phase 2)

EasyType ships a system-tray app in addition to the headless `easytype` command.

```bash
easytype-gui
```

This puts an amber **E** icon in your system tray. The right-click menu shows status
(Idle / Recording…), starts/stops dictation, switches Toggle⇄Hold, opens **Settings…**,
and quits. The Settings window edits the same `~/.config/easytype/config.toml`; saving
applies changes immediately (a transcription-model change re-warms in the background).
Set hotkeys live: click **Set**, press your combo, release.

The headless `easytype` command is unchanged and remains the right choice for servers or
a systemd unit.

### Start at login

```bash
mkdir -p ~/.config/autostart
cp autostart/easytype.desktop ~/.config/autostart/
```
```

- [ ] **Step 4: Run the full automated suite + compile every new/changed module**

Run:
```bash
.venv/bin/pytest -q && python -m py_compile \
  src/easytype/chords.py src/easytype/config.py src/easytype/controller.py \
  src/easytype/listener.py src/easytype/cli.py src/easytype/engine.py \
  src/easytype/supervisor.py src/easytype/gui/app.py src/easytype/gui/settings.py
```
Expected: all tests pass (64); no compile output.

- [ ] **Step 5: Commit**

```bash
git add src/easytype/gui/style.qss autostart/easytype.desktop README.md
git commit -m "feat: dark/amber theme, autostart sample, and Phase 2 README"
```

- [ ] **Step 6: Manual verification on the user's machine (hand to the user)**

The repo `.venv` has no PySide6, so the engine/GUI runtime is verified on the pipx install. Because the user's shell (`ble.sh`) mangles pasted multi-line commands, give him short one-liners to run (`!`-prefixed in the session), and remind him the tray app must be restarted to pick up code changes.

Reinstall (pulls PySide6) and launch:
```bash
pipx install -e ~/local-git/easytype --force && easytype-gui
```

Checklist:
- [ ] Amber **E** tray icon appears; tooltip shows "EasyType — Idle".
- [ ] Dictate with the normal hotkey → tray status flips to "Recording…"/"Transcribing…" and the icon shows the active ring; text is inserted as before.
- [ ] Tray **Start dictation** / **Stop dictation** begins and ends a recording.
- [ ] Tray **Switch to Hold/Toggle mode** flips the mode (verify the next dictation behaves accordingly).
- [ ] **Settings…** opens the dark, amber, tabbed window; all six tabs show current values.
- [ ] Change **Keystroke delay** (or indicator position) → **Save** → confirm it takes effect with no manual restart.
- [ ] Switch the **Model** → Save → first dictation re-warms then works.
- [ ] **Set** a hotkey: click, press a combo on the external RGB keyboard (right-Ctrl), release → the description updates correctly; a clash shows the amber note.
- [ ] Launch `easytype-gui` a second time → it reports "already running" and does not start a duplicate.
- [ ] **Quit** from the tray stops dictation cleanly (no lingering process holding the keyboard grab).

---

## Self-review (completed during planning)

**Spec coverage:** tray + menu (T8), tabbed Settings over config.toml (T9), every config field (T9 `_values`/`_load`), apply-on-save reload (T6 `reload` + T9 `_save`), live hotkey capture via the engine (T1 collector, T4 listener capture, T9 `HotkeyRow`), one-process worker-thread architecture (T6 supervisor, T5 build_engine), clean stop (T4), amber monogram icon + dark theme (T8 `make_icon`, T10 qss), Wayland/passive/single-instance/save-error handling (T8 + T9 `_save`), PySide6 packaging + `easytype-gui` (T7), autostart sample + README (T10), testing strategy (TDD on T1/T2/T3/T6; py_compile + manual on T4/T5/T8/T9/T10). No spec requirement is left without a task.

**Placeholder scan:** no TBD/TODO; every code step contains complete code; every command lists expected output.

**Type/name consistency:** `EngineBundle` exposes `.listener`/`.controller`/`.warmup` and is consumed identically in `cmd_run` (T5) and `EngineSupervisor` (T6); fakes in `tests/test_supervisor.py` mirror that shape. `build_engine(config, session)` signature matches both call sites. `apply_settings_to_doc(doc, values)` keys exactly match `SettingsWindow._values()` (T9) and the test dict (T3). `begin_capture(on_captured)` / `begin_hotkey_capture(on_captured)` / `HotkeyRow.captured` are consistent across listener, supervisor, and window. `make_icon(active)` is the single icon builder used for idle/active/window icons.
