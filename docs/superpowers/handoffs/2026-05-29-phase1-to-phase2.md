# EasyType — Session Handoff

**Date:** 2026-05-29 · **Repo:** https://github.com/jeffharlan/easytype · **Local:** `~/local-git/easytype` · **Branch:** `main`

## TL;DR
Phase 1 (the headless dictation engine) is **built, tested, merged to `main`, pushed, and confirmed working on the user's machine**. The next session's job is **Phase 2: the systray icon + Control Center settings GUI** — brainstorming is already IN PROGRESS. See **⏩ RESUME HERE** immediately below.

## ⏩ RESUME HERE — Phase 2 brainstorming in progress (this supersedes the "Phase 2 — what to build next" section lower down)

We are mid-`superpowers:brainstorming` for Phase 2. **Decisions locked so far:**
- **First deliverable (MVP):** a **systray icon + a settings window** that edits the existing `~/.config/easytype/config.toml`. NOT the full Control Center — searchable history, dictionary editor, and per-app paste overrides are deferred to later cycles.
- **GUI toolkit: Qt / PySide6** (pip-installable into the pipx venv → keeps the clean `pipx install`; native settings window; `QSystemTrayIcon` tray; themeable dark to approximate VibeTyper). PySide6 is a ~100MB bundled dependency — accepted.

**What the MVP should contain (for when you present the design):**
- *Settings window* editing every current config field: capture_mode, max_recording_duration, record/cancel/repaste hotkeys (ideally a "click-to-capture" reusing the evdev logic behind `--set-hotkey`), audio device, transcription model/language/device, injection method + type_delay_ms, formatter enabled/backend/ollama_*, indicator enabled/position/count.
- *Tray menu*: status (idle/recording), start/stop recording, toggle capture mode, open settings, quit.

**OPEN QUESTIONS to resolve next (one at a time, before writing the Phase 2 spec):**
1. **Process architecture — how the tray/GUI relates to the running engine.** The engine currently reads config ONLY at startup and runs its evdev grab loop on the main thread. Options: (a) the tray/GUI becomes the main process and supervises the engine; (b) GUI is a separate companion talking to the engine over an IPC/control socket; (c) GUI just edits config and triggers a restart/reload. This shapes everything — decide first. Note Qt's event loop vs the evdev main-thread loop must coexist (likely run the engine in a thread/subprocess under the Qt app, or keep them as separate processes + IPC).
2. **Config hot-reload vs restart** when settings change.
3. **In-GUI hotkey capture** — reuse the `--set-hotkey` evdev capture inside the settings window (GUI reads evdev, or signals the engine to capture).
4. **Theming fidelity to VibeTyper**, and whether to offer the brainstorming **visual companion** once we reach layout mockups (the 5 VibeTyper screenshots are the visual reference — they're described in the design spec's Phase 2 section).

**Then:** propose 2-3 architecture approaches → present design → write Phase 2 spec to `docs/superpowers/specs/` → `superpowers:writing-plans` → `superpowers:subagent-driven-development` (same loop Phase 1 used).

---

## Reference artifacts (read these — don't re-derive)
- **Design spec:** `docs/superpowers/specs/2026-05-29-easytype-design.md` (full Phase 1 design + a "Phase 2 / Out of scope" section + decisions log)
- **Phase 1 implementation plan:** `docs/superpowers/plans/2026-05-29-easytype-engine.md` (14 tasks, the file structure, all module code)
- **Project memory:** `~/.claude/projects/-home-jefferey-local-git-easytype/memory/easytype-project.md`
- **Source layout:** `src/easytype/{cli,config,preflight,chords,keycodes,dictionary,formatter,recorder,transcriber,indicator,listener,controller}.py` + `injector/{__init__,x11}.py`; tests in `tests/`. README, LICENSE, config.sample.toml, systemd/easytype.service at repo root.

## Current state of `main` (verify, don't rebuild)
- `.venv/bin/pytest -q` → **55 passing**.
- Phase 1 commits + post-merge fixes (all on `main`, pushed):
  - `88f2437` graceful Wayland message + cancel-during-transcribe test
  - `f9dc44d` treat left/right modifier variants as equivalent (either-Ctrl)
  - `7a83986` run indicator in a **subprocess** (fixed `Tcl_AsyncDelete` crash)
  - `12c143b` configurable type-mode keystroke delay (default **40ms**)
  - `04a8957` terminal-aware paste (Ctrl+Shift+V in terminals)
  - `a8ba47f` detect terminals via window **PID → /proc/comm** (older xdotool lacks `getwindowclassname`)
  - `4a63e3d` pre-warm the model at startup so the first dictation is fast

---

## Operational gotchas (NOT discoverable from the repo — important)
- **Editable install:** the user ran `pipx install -e ~/local-git/easytype`, so source edits are live — **but `easytype` is a long-running process; he must Ctrl+C and re-run it to load code changes.** Remind him each time.
- **The repo `.venv` is a TEST venv only:** created with `pip install -e . --no-deps` + `pip install pytest tomlkit numpy`. It deliberately does NOT have the heavy/hardware libs (sounddevice, faster-whisper, evdev). Unit tests pass because those libs are lazy-imported. Do NOT try to run the actual app from `.venv` — use the user's pipx install. Run tests with `.venv/bin/pytest`.
- **Commits:** the user authorized small fix-forward commits straight to `main` + push during this session. He is otherwise strict: "commit/push only when asked." Confirm before larger pushes.
- **His shell is `ble.sh`** — it mangles pasted multi-line and long single-line commands (injects indentation/line-breaks; even base64 got corrupted). **To run scripts on his machine, WRITE them to a file (you share his filesystem — `/home/jefferey/...` and `/tmp` are real) and have him run a short one-liner**, rather than pasting code.
- **Permissions are set:** he's in the `input` group and the `/dev/uinput` udev rule is installed (`/etc/udev/rules.d/99-easytype-uinput.rules`). He used `newgrp input` to avoid logging out; a future fresh login makes it permanent. `easytype --check` returns all green.

## Environment specifics
- X11 / Cinnamon / Linux Mint, ThinkPad, Python 3.12, pipx, **NVIDIA RTX 1000 Ada** (ctranslate2 sees 1 CUDA device → GPU transcription works), Ollama installed.
- **Keyboards:** built-in AT (event3), external **Evision RGB Keyboard** (event19/20) whose Ctrl reports as **RIGHT-Ctrl, code 97** (this drove the either-Ctrl fix), plus a Bluetooth keyboard (event24). `find_keyboards()` grabs all of them.
- **`xdotool` is old: v3.20160805.1** — no `getwindowclassname`. `xprop` IS available; `getwindowpid` works. Terminal detection reads `/proc/<pid>/comm` (e.g. `wezterm-gui` → contains "term").
- He dictates into **WezTerm** and the **Claude Code CLI**; WezTerm pastes on **Ctrl+Shift+V** (confirmed). Default injection is now **paste** mode in his config (`~/.config/easytype/config.toml`).

## Known limitations / optional Phase-1 follow-ups (low priority)
- **Wayland injector not implemented** (interface is ready in `injector/__init__.py`; `cmd_run` exits gracefully on Wayland).
- A CLI fix to make `--passive` report the input-group requirement cleanly was **drafted but the user cancelled it** — not applied. Low priority (he has the group). If revisited: passive mode also needs `input` group to *read* the keyboard, and `cmd_run` currently only gates grab mode on it.
- VS Code's *integrated terminal* won't be detected as a terminal (active window class is `code`) — paste would use Ctrl+V there. Edge case.
- His `config.toml` predates the `type_delay_ms` key, so it isn't in his file — it defaults to 40 via `load_config`. Fine.

---

## Phase 2 — what to build next
**Goal:** a systray icon + "Control Center" settings GUI that is purely a *face on the existing config file* (`~/.config/easytype/config.toml`). The engine already reads everything from that config, so the GUI just edits it; they stay decoupled.

**Source material:** the user shared 5 VibeTyper (the commercial app he's modeling after) screenshots. The decisions already made this session (in the spec's Phase 2 / Out-of-scope sections):
- **In scope for Phase 2:** Control Center GUI (settings screens), searchable transcription **history**, **dictionary editor**, **per-app paste overrides** (Type / Paste / Plain-paste per application — generalizes the terminal-detection we hand-rolled), waveform/gradient indicator colors, mute-other-apps-while-recording.
- **Formatter territory (do with the formatter, later):** transcription **tone** (Normal/Casual/Very casual), **AI command modes** ("Reply"/"Rewrite"), "Your name".
- **Explicitly NOT building (commercial-SaaS only):** accounts/login/PRO tier, auto-update + beta channel, Discord, usage-analytics dashboard.
- **Already decided in Phase 1:** per-app paste overrides and local history were deferred OUT of Phase 1 into Phase 2.

**Open decision for brainstorming:** the **GUI toolkit** is unchosen. Options to weigh: GTK/PyGObject (native on his Cinnamon desktop), Qt/PySide6, or a local web UI (closest to the VibeTyper look, easy to style). Systray likely via AppIndicator (libayatana-appindicator) or `pystray`. Must keep the "separate, swappable concerns" principle — GUI as its own module(s)/package, not entangled with the engine.

**Process to follow (same as Phase 1):**
1. `superpowers:brainstorming` — scope Phase 2, pick the toolkit, decide which screens ship first. The user is decisive but **not a coder** — use plain/business language, ask one question at a time, prefer multiple-choice. He likes `AskUserQuestion` with clear options.
2. `superpowers:writing-plans` — write the plan to `docs/superpowers/plans/`.
3. `superpowers:subagent-driven-development` — execute (this session ran the whole Phase 1 build this way: implementer + spec/quality review per task, fix-forward).

## Working-style reminders (from his global CLAUDE.md)
- He's a CTO at a security-installation company; **vibe-codes, not a hand-coder.** Write the code, run the commands, explain outcomes in business terms, test before declaring done. **Least code that meets the requirement; smallest diff; no speculative abstractions.** Personal git identity `jeffharlan` is auto-selected under `~/local-git`.

## Suggested skills for the next session
- **`superpowers:brainstorming`** (start here)
- **`superpowers:writing-plans`**, then **`superpowers:subagent-driven-development`**
- **`frontend-design`** if a web-based GUI is chosen
- The user has a `graphify` skill and others; not needed for this work.
