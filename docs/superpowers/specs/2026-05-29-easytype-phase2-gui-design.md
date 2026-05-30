# EasyType — Phase 2 Design: System-Tray Icon + Settings GUI

**Date:** 2026-05-29 · **Repo:** `~/local-git/easytype` · **Branch:** `phase2-gui` (off `main`) · **Builds on:** `docs/superpowers/specs/2026-05-29-easytype-design.md` (Phase 1)

## 1. Goal

Give EasyType a face: a **system-tray icon** and a **Settings window** that are a friendly front-end onto the existing `~/.config/easytype/config.toml`. The Phase 1 dictation engine already reads everything from that file; Phase 2 lets the user see status, start/stop dictation, and change every setting without editing TOML by hand or restarting from a terminal.

This is the **MVP** of the larger "Control Center" idea. Searchable history, a dictionary editor, and per-app paste overrides are explicitly **deferred** to later cycles.

## 2. Scope

**In scope (MVP):**
- A tray icon (custom amber "E" mark — **not** a microphone) with a right-click menu: status line, Start/Stop dictation, Toggle⇄Hold switch, Settings…, Quit.
- A tabbed, dark-themed Settings window that reads and writes **every field currently in `config.toml`**.
- In-window **live hotkey capture** (click "Set", press the combo).
- **Apply-on-save:** changing settings reloads the running engine in the background; no manual restart.
- A new `easytype-gui` launcher (plus a sample `autostart/easytype.desktop` for launch-at-login). The existing headless `easytype` command is unchanged.

**Out of scope (deferred to later Phase 2+ cycles):**
- Searchable transcription history, dictionary editor GUI, per-app paste-mode overrides, waveform/gradient indicator colors, mute-other-apps-while-recording, transcription tone, AI command modes.

**Not building (commercial-SaaS only):** accounts/login/PRO tier, auto-update/beta channel, Discord, usage-analytics dashboard.

## 3. Decisions (locked during brainstorming)

| Decision | Choice |
|---|---|
| GUI toolkit | **PySide6 (Qt)** — pip-installable into the pipx venv; native tray + window; themeable. ~100 MB bundled dependency, accepted. |
| Run model | **One process.** The tray app owns the Qt main thread/event loop and runs the dictation engine on a background thread inside the same process. |
| Apply behavior | **Apply right away.** On Save, the engine reloads itself in the background (sub-second for most settings; a transcription-model change re-warms quietly). |
| Hotkey capture | **Live click-and-press,** performed by the engine (it already holds the keyboard grab), so it captures exactly what the keyboard reports — including the external RGB keyboard's right-Ctrl (code 97). |
| Window layout | **Top tabs.** |
| Accent color | **Amber `#f59e0b`** on a dark theme. |
| Logo / tray icon | **Monogram "E"** in a rounded amber tile (idle + recording variants). |

## 4. Architecture

```
                 ┌──────────────────────────────────────────────┐
                 │  easytype-gui  (single process)              │
                 │                                              │
  Qt main thread │  QApplication ─ QSystemTrayIcon ─ Settings    │
  (event loop)   │       │              window (QTabWidget)      │
                 │       │ commands / reload / begin-capture     │
                 │       ▼                                        │
                 │  EngineSupervisor  (Qt-free, plain threading) │
                 │       │ build_engine(config, session)         │
                 │       ▼                                        │
  worker thread  │  Listener ⇄ Controller ⇄ Recorder/Transcriber │
                 │  (evdev grab loop)         /Injector/Indicator│
                 └──────────────────────────────────────────────┘
                                   reads/writes
                                        ▼
                          ~/.config/easytype/config.toml
```

**Separation of concerns** (same principle as Phase 1):
- The **engine** (Phase 1 modules) is untouched in spirit; it gains only two small, generally-useful capabilities (a clean stop, and a hotkey-capture mode).
- The **`EngineSupervisor`** owns the engine's lifecycle on a worker thread and is **deliberately Qt-free**, so its start/stop/reload logic is unit-testable without a display and the engine never depends on the GUI.
- The **`gui/` package** is the only Qt-aware code. It talks to the engine *only* through the supervisor's small interface.

### 4.1 Threading model

- Qt event loop, tray, and window live on the **main thread** (Qt requires UI work there).
- The engine's evdev grab/replay loop runs on a **worker thread** owned by the supervisor. evdev/uinput/`selectors` need no main thread; Python signal handlers (used by the headless CLI) are simply not installed on this thread — the supervisor stops the engine programmatically instead.
- **Engine → GUI** communication:
  - *State* (idle/recording/transcribing) is read by a **QTimer poll** (~150 ms) of `supervisor.state`. No callback wiring into the Controller is needed.
  - *Hotkey-captured* result is delivered via a **Qt signal** emitted from the worker thread (Qt cross-thread signal emit is thread-safe; the slot runs on the main thread).
- **GUI → engine** commands call thread-safe supervisor methods, which call Controller methods (the Controller already guards state with an `RLock`).

## 5. Components & file plan

**New files:**
- `src/easytype/engine.py` — `build_engine(config, session, *, grab) -> EngineBundle`. The engine wiring currently inlined in `cli.cmd_run` (Transcriber + Recorder + Controller + Injector + Indicator + HotkeyEngine + Listener), extracted so both the CLI and the supervisor build the engine the same way. Returns a small bundle exposing the `listener`, `controller`, and a `warmup()` callable.
- `src/easytype/supervisor.py` — `EngineSupervisor` (Qt-free):
  - `start()` — build the engine bundle, start the listener on a worker thread, kick off model warmup in the background.
  - `stop()` — ask the listener to stop, join the thread, clean up.
  - `reload()` — `stop()` → `load_config()` → `start()`.
  - `toggle_recording()` / `cancel()` — passthrough to the Controller for tray-driven control.
  - `begin_hotkey_capture(on_captured)` — put the listener into capture mode; relay the captured chord to the GUI callback.
  - `state` property — `"stopped" | "disabled" | "idle" | "recording" | "transcribing"` plus a `grab`/`passive` flag for the tooltip.
  - Accepts an injectable `builder=build_engine` so tests can pass fakes.
- `src/easytype/gui/__init__.py`
- `src/easytype/gui/app.py` — `main()`: create `QApplication`; enforce single instance; detect Wayland and warn; construct the supervisor and `start()`; build the tray icon (rendered amber-"E" `QIcon`, idle + recording variants) and menu; start the state-poll `QTimer`; open/raise the Settings window; load the stylesheet. Tray icon rendering (small SVG → `QIcon`) lives here.
- `src/easytype/gui/settings.py` — the tabbed Settings window (`QDialog` with a `QTabWidget`):
  - Builds the six tabs (§6) from widgets.
  - Loads current values via `config.load_doc()` (tomlkit) so comments/formatting survive.
  - On **Save**: gather widget values → `config.apply_settings_to_doc(doc, values)` → `config.save_doc(doc)` → `supervisor.reload()`.
  - Hotkey "Set" rows call `supervisor.begin_hotkey_capture(...)`; a `captured = Signal(object)` marshals the result back to the main thread to update the field and show any conflict note.
  - Enumerates input devices (via `sounddevice`) for the mic picker and offers a fixed list of common Whisper models.
- `src/easytype/gui/style.qss` — the dark + amber Qt stylesheet (packaged as data).

**Changed files:**
- `src/easytype/chords.py` — add `ChordCollector`: a tiny state machine (`feed(code, value) -> done: bool`, `.keys`) that records the first-press order of a chord and reports completion on full release. Refactor `cli.cmd_set_hotkey`'s inline loop and the listener's new capture mode to both use it (two real call sites — not premature).
- `src/easytype/listener.py` — two additions:
  1. **Clean stop:** an `os.pipe()` registered in the selector; `stop()` sets a flag and writes a byte so `select()` wakes and the loop returns; `cleanup()` runs as today (ungrab/close).
  2. **Capture mode:** `begin_capture(on_captured)` routes raw key events into a `ChordCollector` instead of the `HotkeyEngine`, **swallows** them (no uinput replay, so the combo doesn't leak to the focused app — best-effort only in passive/no-grab mode), and on completion fires `on_captured(keys)` and resumes normal handling.
- `src/easytype/controller.py` — add `toggle_recording()` (idle→start, recording→stop-and-process, transcribing→ignore) so the tray can start/stop manually regardless of capture mode. Existing hotkey handlers unchanged.
- `src/easytype/config.py` — add `apply_settings_to_doc(doc, values)`: a pure function mapping a flat dict of settings to the tomlkit document (reusing `set_hotkey_in_doc` for hotkeys), preserving comments. Unit-testable, Qt-free.
- `src/easytype/cli.py` — `cmd_run` refactored to use `engine.build_engine(...)`; behavior unchanged (still signal-driven stop for the headless path). `cmd_set_hotkey` uses `ChordCollector`.
- `pyproject.toml` — add `PySide6>=6.6` to `dependencies`; add `easytype-gui = "easytype.gui.app:main"` to `[project.scripts]`; include `gui/style.qss` as package data.

## 6. Settings window — tabs and fields

Every field maps to an existing `config.toml` key. Widgets constrain input so most invalid states are unreachable.

1. **Recording** — capture mode (Toggle/Hold segmented), max length seconds (spinbox), and Record / Cancel / Repaste hotkeys (each row: current description + **Set** button → live capture + conflict warning).
2. **Audio & Transcription** — microphone (dropdown: Default + enumerated input devices), Whisper model (dropdown seeded with `tiny.en`, `base.en`, `small.en`, `medium.en`, `large-v3`), language (editable combo seeded with common codes, e.g. `en`), compute device (Auto/CUDA/CPU).
3. **Typing** — injection method (Type/Paste segmented), keystroke delay ms (spinbox; default 40).
4. **AI cleanup** — formatter enabled (switch); backend (Ollama/OpenAI); Ollama model; Ollama URL. Sub-fields disable when the formatter is off.
5. **Indicator** — enabled (switch); position (dropdown); count up/down.
6. **Advanced** — keyboard device override (text; blank = auto-detect).

Window footer: **Save** (amber, primary) and **Cancel**. Save applies immediately via the supervisor reload; Cancel discards unsaved widget changes.

## 7. Theme & icon

- **Stylesheet** (`style.qss`): dark surfaces (~`#16161a`/`#212128`), light text, amber `#f59e0b` for the active tab, primary button, focus rings, and switches. Loaded once at app start.
- **Icon** (rendered at runtime to a `QIcon`): a bold "E" in a rounded amber tile. Two variants — **idle** (amber tile) and **active** (a clear cue, e.g. an accented/filled ring). The QTimer maps `supervisor.state` to a variant: `recording`/`transcribing` → active; `idle` → idle; `stopped`/`disabled` → idle, dimmed. The same icon is the window icon.

## 8. Data flow

- **Startup:** `app.main()` → load config → `supervisor.start()` builds + runs the engine on a worker thread, warmup runs in background → tray shows idle.
- **Dictation:** unchanged from Phase 1 (hotkeys → Controller → record → transcribe → inject). The tray reflects state via the poll timer.
- **Settings change:** window edits a tomlkit doc → Save writes the file → `supervisor.reload()` rebuilds the engine from the new `Config`. The config file remains the single source of truth.
- **Tray commands:** Start/Stop → `supervisor.toggle_recording()`; Toggle⇄Hold → write `capture_mode` to config + reload; Settings… → raise the window; Quit → `supervisor.stop()` then quit Qt.

## 9. Error handling

- **Wayland:** at startup, if the session is Wayland, show a clear dialog (dictation needs X11 — mirrors the engine's existing refusal). The tray still runs so Settings remain editable to prepare config; engine state shows `disabled`.
- **Missing grab prerequisites:** the engine already falls back to passive mode. The supervisor records grab vs. passive; the tray **tooltip** shows the active mode. (Hotkey capture in passive mode can read but cannot reliably swallow keys — acceptable, noted to the user.)
- **Save failure (disk/permissions):** show a `QMessageBox` with the cause; the engine keeps running on the old config.
- **Hotkey conflict:** show the existing `conflict_note` as a non-blocking warning beside the field.
- **Single instance:** a `QLocalServer` named lock; a second `easytype-gui` launch raises the existing window (or exits) instead of starting a duplicate engine that would fight for the keyboard grab.

## 10. Testing

Matches the Phase 1 pattern: **pure, hardware-free logic is unit-tested in the repo `.venv`; hardware/GUI paths are verified manually** on the user's pipx install.

**Automated (no PySide6, no hardware — run with `.venv/bin/pytest`):**
- `tests/test_chords.py` — `ChordCollector`: press/release sequences → correct key order and completion (single key, modifier+key, multi-key, interleaved release).
- `tests/test_config.py` — `apply_settings_to_doc`: round-trips a full settings dict, preserves comments, writes correct types, and reuses `set_hotkey_in_doc`.
- `tests/test_controller.py` — `toggle_recording()` state transitions (idle→recording→transcribing→idle; no-op while transcribing), using the existing fakes.
- `tests/test_supervisor.py` (new) — `EngineSupervisor` start/stop/reload using an **injected fake engine builder** (fake listener/controller): verifies the thread starts, `stop()` joins, `reload()` rebuilds from fresh config, and `begin_hotkey_capture` relays the chord.

**Manual (on the user's machine, with PySide6 installed via pipx):**
- Launch `easytype-gui`; confirm tray icon + menu, status updates while dictating, Start/Stop, Toggle⇄Hold.
- Open Settings; change a field (e.g., type_delay, indicator position) → Save → confirm it takes effect without a manual restart.
- Switch the transcription model → Save → confirm background re-warm and that the next dictation works.
- Capture each hotkey live, including on the external RGB keyboard (right-Ctrl), and confirm the chord is recorded correctly.
- Single-instance guard: launch twice → second raises the window.

**Keep the heavy/GUI code out of the test import path** (PySide6 imported only inside `gui/`, `sounddevice` lazy where possible) so the existing 55-test suite still runs in the lean `.venv`.

## 11. Packaging & launch

- `pipx install -e ~/local-git/easytype` (editable) pulls **PySide6** automatically. **Reminder:** the running app must be restarted to pick up source edits.
- New entry point: `easytype-gui`. Headless `easytype` is unchanged for server/no-GUI/systemd use.
- **Autostart at login:** documented as a manual step for the MVP — drop a `~/.config/autostart/easytype.desktop` launching `easytype-gui` (sample provided in the repo, mirroring the existing `systemd/easytype.service` for the headless path). A GUI "Start at login" toggle is a deferred follow-up, not part of this build.

## 12. Risks & mitigations

- **Qt event loop vs. evdev loop:** resolved by running the engine on a worker thread; only the GUI touches Qt. The clean-stop pipe makes thread shutdown deterministic.
- **PySide6 size (~100 MB):** accepted; isolated in the pipx venv.
- **Listener changes touch the most hardware-coupled module:** kept minimal (a stop pipe + a capture branch), both behind small interfaces; the chord state machine is unit-tested in isolation.
- **Capturing a hotkey while the engine holds the grab:** solved by capturing *through* the running listener rather than opening a second evdev reader.

## 13. Out of scope / future cycles

History view, dictionary editor, per-app paste overrides, indicator color/waveform options, mute-other-apps, transcription tone, AI command modes. Each will get its own spec → plan → build cycle, reusing this tray + Settings shell.
