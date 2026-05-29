# EasyType — Design Spec

- **Date:** 2026-05-29
- **Status:** Approved for Phase 1 implementation (pending final user review of this doc)
- **Repo:** https://github.com/jeffharlan/easytype
- **License:** MIT

---

## 1. Summary

EasyType is a system-wide voice dictation tool for Linux. Press a hotkey, speak, and the
cleaned-up text is inserted at the current cursor position in whatever app is focused.
Transcription runs **locally** (faster-whisper) — no API bill, nothing leaves the machine.
It supports both **toggle** (tap to start, tap to stop) and **hold** (push-to-talk) capture,
and consumes its hotkey so combos like Ctrl+Space don't leak to the focused app.

This document specifies **Phase 1 — the engine**: a headless background process driven
entirely by a config file. A later **Phase 2** adds a systray icon and settings GUI (its own
spec). Building the engine config-first means the GUI is purely a face on the config and never
blocks dictation from working.

---

## 2. Goals & non-goals

**Goals (Phase 1)**
- Reliable, private, local dictation that inserts text in any focused X11 app.
- User fully in control of the hotkey (any key/combo, no blocked keys).
- Consume the hotkey via grab-and-replay so it never triggers the focused app's behavior.
- Safe by construction: the keyboard grab is always released on every exit path.
- Both toggle and hold capture modes, with clear on-screen feedback in toggle mode.
- Clean, swappable modules — the text injector especially is a backend interface so other
  platforms (Wayland) drop in later without touching the rest.

**Non-goals (Phase 1)**
- No GUI / systray (Phase 2).
- No Wayland injector implementation (interface only; user is on X11).
- No accounts, auto-update, beta channel, usage analytics (these are SaaS-product concerns,
  not applicable to a local open-source tool).

---

## 3. Scope

### Phase 1 — engine (this spec)
Core dictation; grab-and-replay hotkey consume; toggle + hold; floating timer indicator;
record / cancel / repaste-last hotkeys; word-replacement dictionary; optional magic formatter;
X11 injector (Type default, Paste optional); preflight checks; TOML config; pipx packaging;
optional systemd user service.

### Phase 2 — face (separate spec, later)
Systray icon + Control Center GUI: settings screens, searchable transcription history,
dictionary editor, per-app paste-mode overrides, waveform/gradient indicator colors,
mute-other-apps-while-recording, transcription tone (Normal/Casual/Very casual),
AI command modes ("Reply"/"Rewrite").

### Out of scope (commercial-SaaS only — not building)
Accounts / login / PRO tier; automatic updates + beta-release channel; Discord; usage
analytics dashboard. (Updates are `pipx upgrade easytype`. Launch-at-login is the systemd
service.)

---

## 4. Target environment & assumptions

Verified on the developer's machine (2026-05-29):

- **Session:** X11 (Cinnamon / Linux Mint). `XDG_SESSION_TYPE=x11`.
- **Python:** 3.12. `pipx` available.
- **GPU:** NVIDIA RTX 1000 Ada → faster-whisper uses CUDA automatically (CPU fallback).
- **Already installed:** `xdotool`, `xclip`, `notify-send`, PortAudio, Ollama.
- **Permission gaps (needed only for the grab-and-replay consume feature):**
  - User is **not** in the `input` group (needed to read/grab `/dev/input`).
  - `/dev/uinput` is root-only (needed to create the virtual keyboard). Requires a udev rule.
- Passive mode (`--passive`) needs none of these and is the safe first-run path.

---

## 5. Architecture

### 5.1 Module boundaries

Four independent units, each one job, communicating through narrow interfaces:

| Module        | Responsibility                                                        | Depends on            |
|---------------|-----------------------------------------------------------------------|-----------------------|
| `hotkey`      | Read `/dev/input` (evdev), detect chords, grab-and-replay to consume  | python-evdev, uinput  |
| `recorder`    | Capture mic → in-memory buffer; start/stop; enforce duration cap      | sounddevice           |
| `transcriber` | Audio buffer → text, locally                                          | faster-whisper        |
| `injector`    | Put text at the cursor — **swappable backend interface**              | xdotool / xclip (X11) |

Supporting modules: `config`, `preflight`, `dictionary`, `formatter`, `indicator`, `cli`.

`injector` is an abstract interface:

```python
class Injector(Protocol):
    def inject(self, text: str, method: str) -> None: ...
```

`X11Injector` implements it in Phase 1. A `WaylandInjector` (wl-copy + ydotool) can be added
later with zero changes to the other modules — that's the whole point of the boundary.

### 5.2 Concurrency model (safety-relevant)

Because the hotkey module **grabs** the physical keyboard, its event loop must **never block** —
a stall freezes the user's keyboard.

- **Main thread:** evdev read → replay-through-virtual-device loop across all grabbed devices
  (via a selector). Does no heavy work; only forwards events, detects chords, flips state, and
  signals the worker.
- **Audio:** `sounddevice.InputStream` fills the buffer on its own callback thread (non-blocking).
- **Worker thread:** transcription + dictionary + formatter + injection run here, off the event
  loop. Transcribing a clip never freezes the keyboard.
- **Indicator:** owns its own thread with a Tk root + mainloop; the recorder signals it through a
  thread-safe flag polled via `root.after`. All Tk calls happen on that one thread.

X11 injection uses XTEST, which the X server delivers directly to apps — it is **not** seen by
our evdev grab, so there's no feedback loop. (Note for a future Wayland backend: `ydotool` injects
through uinput and *would* be seen by the grab; that backend must exclude its own virtual device.)

### 5.3 Data flow

```
hotkey trigger ─▶ recorder starts ─▶ (indicator shows) ─▶ hotkey trigger / cap ─▶ recorder stops
       └▶ worker: transcribe ─▶ dictionary replace ─▶ [magic formatter if on] ─▶ inject ─▶ store as last-transcript
```

Dictionary replacement runs **before** the formatter (matches the reference behavior:
"dictionary replacements apply before tone styling").

---

## 6. Component design

### 6.1 Hotkey listener + grab-and-replay consume

- Listen via python-evdev on auto-detected keyboard device(s); config override available.
  Reading `/dev/input` works identically on X11 and Wayland.
- **Grab-and-replay:** `EVIOCGRAB` the physical keyboard device(s); create one uinput virtual
  keyboard mirroring their capabilities; forward **every** event verbatim through the virtual
  device **except** the configured chords, which are swallowed and handled internally.
- **Chord match:** a chord is a set of evdev keycodes; it fires when all its keys are held
  simultaneously. The chord's **trigger** = its non-modifier key (or, if all keys are modifiers,
  the last key in the configured list). Modifiers are forwarded normally; only the trigger's
  key-down/up are swallowed when the rest of the chord is held.
  - *Ctrl+Space:* Ctrl forwarded (a lone Ctrl tap does nothing), Space swallowed → no IBus toggle.
  - *Ctrl+\\:* Ctrl forwarded, `\` swallowed → no SIGQUIT in terminals.
  - *F9 / Right_Ctrl / Ctrl+Alt+Space:* same principle.

### 6.2 The three hotkeys

| Hotkey         | Default     | Behavior                                                                 |
|----------------|-------------|--------------------------------------------------------------------------|
| Record         | Ctrl+Space  | Toggle: tap=start, tap=stop. Hold: record while held, transcribe on release. |
| Cancel         | Esc         | Abort an in-progress recording/transcription. **Only swallowed while busy** — Esc passes through normally otherwise. |
| Repaste last   | F8          | Re-inject the last transcript using the current injection method.        |

Ctrl+\\ is the documented alternate record hotkey.

### 6.3 `--set-hotkey` interactive capture

- Prints "press the key or combination you want, then release", reads the **actual evdev
  keycodes**, and saves them (raw codes + a human-readable comment in the config).
- Supports single keys and modifier combos. **No blocked keys** — whatever is pressed is saved.
- After capture, checks the chord against a small **known-conflicts table** (e.g. Ctrl+Space =
  IBus input-method switch; Ctrl+\\ = SIGQUIT in terminals). On a match, prints an **informational
  note only** — what the key normally does, and that the consume feature prevents that side
  effect — then **saves it anyway**. The table never blocks or alters behavior.
- If the chosen chord is a lone common modifier (e.g. bare Ctrl), warns that consuming it would
  swallow all normal use of that key — then still saves it.
- `--set-hotkey` can target record / cancel / repaste (e.g. `--set-hotkey cancel`).

### 6.4 Grab safety (critical)

- Grab released + virtual device destroyed on **every** exit path: normal quit, exceptions, and
  `SIGINT`/`SIGTERM`/`SIGHUP` — via `try/finally` plus signal handlers.
- If the grab can't be cleanly established/held → **fall back to passive (non-grabbing) mode and
  warn loudly** rather than risk a stuck keyboard.
- `--passive` flag forces non-grabbing mode (zero permissions needed) for safe first-run testing.
- Clean Ctrl+C always works.

### 6.5 Recorder + capture modes

- `sounddevice` records to an in-memory buffer at whisper-friendly settings (16 kHz mono).
- `capture_mode = "toggle"` (default) | `"hold"`.
- **`max_recording_duration` (default 60s):** a forgotten toggle recording always auto-stops.
  Pressing the record hotkey again can always stop it too. It is a *safety backstop* — set it
  comfortably above your longest normal dictation so it never cuts you off mid-sentence.
- **Toggle feedback:** `notify-send` desktop notification + terminal log line on start and stop
  (no held key as a reminder), plus the floating indicator below.

### 6.6 Recording indicator (floating timer)

- A small always-on-top **pill** (Tkinter) shown while recording: `● REC  0:07`, **counting up**
  in mm:ss.
- **Focus-safe:** an `overrideredirect`, non-focusable, no-taskbar window. It must **never** take
  keyboard focus, or injected text would land in it instead of the user's app.
- Turns **amber** in the final seconds before the cap.
- Disappears the instant recording stops.
- **Optional + self-healing:** its own module; if Tkinter (`python3-tk`) is missing, EasyType
  falls back to popup + terminal line and keeps working — never crashes over the indicator.
- Config: `enabled`, `position` (default `top-right`), `count` (`up` default | `down`).

### 6.7 Transcriber

- faster-whisper, local. `model` (default `base.en`), `language` (default `en`), both
  configurable. `device = "auto"` → CUDA if available else CPU. Models auto-download on first run.

### 6.8 Word-replacement dictionary

- Applied to the raw transcript before injection (and before the formatter).
- Each entry: `hears`, `replace`, `mode`.
  - **`smart`:** whole-word, case-insensitive match (regex word boundaries + `IGNORECASE`).
  - **`exact`:** literal phrase replacement.
- Stored as a TOML array of tables. The GUI editor for these is Phase 2.

### 6.9 Magic formatter (optional, off by default)

- When on, runs the (post-dictionary) transcript through a cleanup pass that removes filler words
  and resolves self-corrections.
- Pluggable backend: local **Ollama** endpoint *or* **OpenAI** key from env. If neither is
  configured/reachable, cleanup is **skipped gracefully** — the transcript is never lost.
- Transcription tone (Normal/Casual/Very casual) folds in here as a formatter option in Phase 2.

### 6.10 Injector (X11)

- **`type`** (default): `xdotool type` with a tuned inter-keystroke delay and cleared modifiers.
  Works everywhere including terminals; never touches the clipboard. Most dependable.
- **`paste`** (optional): `xclip` sets the clipboard, then `xdotool key ctrl+v`; the user's prior
  clipboard contents are **saved and restored** afterward.
- `method` is a single global config value in Phase 1. (Per-app overrides are Phase 2.)

### 6.11 Preflight + session detection

- On startup: detect session type (`XDG_SESSION_TYPE` / `WAYLAND_DISPLAY`); verify `input` group
  membership, `/dev/uinput` access, and required binaries (`xdotool`, `xclip`, `notify-send`;
  `python3-tk` for the indicator).
- On any gap → **fail with the exact fix commands** (the `usermod -aG input` line, the
  `/dev/uinput` udev rule, install commands) — never a raw traceback.
- `easytype --check` runs preflight and exits.
- On normal startup, log the current **record hotkey, capture mode, and session type** so the
  running state is visible during testing.

---

## 7. Configuration

TOML at `~/.config/easytype/config.toml`, created with defaults on first run.

```toml
capture_mode = "toggle"            # "toggle" | "hold"
max_recording_duration = 60        # seconds — auto-stop safety backstop

[hotkey]
# Record. Raw evdev keycodes for reliability; comment explains them.
keys = [29, 57]                    # Ctrl+Space  (29=KEY_LEFTCTRL, 57=KEY_SPACE)
description = "Ctrl+Space"

[hotkey.cancel]
keys = [1]                         # Esc — only intercepted while recording/transcribing
description = "Esc"

[hotkey.repaste]
keys = [66]                        # F8 — re-inject last transcript
description = "F8"

[audio]
device = ""                        # "" = default mic

[transcription]
model = "base.en"
language = "en"
device = "auto"                    # auto | cuda | cpu

[injection]
method = "type"                    # "type" | "paste"

[formatter]
enabled = false
backend = "ollama"                 # "ollama" | "openai"
ollama_model = "llama3.1"
ollama_url = "http://localhost:11434"

[indicator]
enabled = true
position = "top-right"             # top-right | top-center | bottom-right | ...
count = "up"                       # "up" | "down"

[keyboard]
device = ""                        # "" = auto-detect keyboard device(s)

[[dictionary]]
hears = "ops plus"
replace = "OPS+"
mode = "smart"

[[dictionary]]
hears = "claw dot md"
replace = "claude.md"
mode = "smart"
```

---

## 8. CLI surface

| Command / flag                | Effect                                                            |
|-------------------------------|-------------------------------------------------------------------|
| `easytype`                    | Run the background process (grab mode if permitted).              |
| `easytype --passive`          | Run in non-grabbing passive mode (no special permissions).        |
| `easytype --check`            | Run preflight checks and exit (prints fixes for any gaps).        |
| `easytype --set-hotkey [name]`| Interactively capture a hotkey (`record` default / `cancel` / `repaste`). |

---

## 9. Packaging & repo layout

- `pyproject.toml`, pip/pipx-installable, exposes the `easytype` console command.
- Files: `README.md`, `LICENSE` (MIT), `.gitignore`, `config.sample.toml`, optional
  `systemd/easytype.service` (user service) + instructions.
- README covers: what it is; `apt` system deps (portaudio, plus the missing Wayland deps noted as
  optional/future); the permissions setup walkthrough; config docs; `--set-hotkey` usage; the
  Ctrl+Space / Ctrl+\\ conflict note; X11-vs-Wayland troubleshooting.

```
easytype/
├── pyproject.toml
├── README.md
├── LICENSE
├── .gitignore
├── config.sample.toml
├── systemd/easytype.service
├── docs/superpowers/specs/2026-05-29-easytype-design.md
├── src/easytype/
│   ├── __init__.py
│   ├── __main__.py
│   ├── cli.py
│   ├── config.py
│   ├── preflight.py
│   ├── hotkey.py
│   ├── recorder.py
│   ├── transcriber.py
│   ├── dictionary.py
│   ├── formatter.py
│   ├── indicator.py
│   └── injector/
│       ├── __init__.py        # Injector interface + backend selection
│       └── x11.py
└── tests/
```

---

## 10. systemd user service

Optional `~/.config/systemd/user/easytype.service` so EasyType runs on login. README documents
`systemctl --user enable --now easytype`. (This is the "launch at startup" feature; no separate
auto-update machinery.)

---

## 11. Permissions setup (printed by preflight when missing)

1. Add the user to the `input` group:
   `sudo usermod -aG input $USER`  (then log out / back in)
2. Allow `/dev/uinput` access via udev rule (group `input`, mode `0660`), then reload rules and
   re-trigger — exact commands emitted by `easytype --check`.

Passive mode needs neither.

---

## 12. Testing strategy

- **Unit-testable without hardware (real automated tests, TDD where it fits):**
  config load / defaults / round-trip; chord-matching logic (including the cancel-gating and
  modifier-vs-trigger rules); the known-conflicts table; dictionary smart/exact replacement;
  formatter backend selection + graceful skip; preflight message generation.
- **Hardware / integration (verified by the developer at each checkpoint):**
  audio capture; transcription; evdev listen; grab-and-replay consume; injection.

---

## 13. Build checkpoints (incremental; verify each before moving on)

1. Scaffold + config + preflight → `easytype --check` prints status / exact fixes.
2. Audio capture → record 3s, save WAV, confirm it plays back.
3. Local transcription of that clip → see the text.
4. evdev hotkey listener in `--passive` → chord detected, no grab.
5. Grab-and-replay consume → Ctrl+Space swallowed, normal typing intact, Ctrl+C releases cleanly.
6. Injection → dictate into a text editor (Type mode), then try Paste mode.
7. Wire it together → full toggle + hold flow, with dictionary + cancel + repaste + indicator.

Each checkpoint includes exactly what to run and what "good" looks like.

---

## 14. Risks & mitigations

| Risk                                   | Mitigation                                                            |
|----------------------------------------|-----------------------------------------------------------------------|
| Stuck keyboard if grab not released    | `try/finally` + signal handlers; passive fallback; loud warning.      |
| Keyboard frozen during transcription   | Transcription/injection on a worker thread; event loop never blocks.  |
| Indicator stealing focus → text misroutes | Non-focusable `overrideredirect` window; never given focus.        |
| Esc consumed globally breaking apps    | Cancel hotkey only swallowed while recording/transcribing.            |
| Missing indicator lib crashes startup  | Indicator optional + self-healing; falls back to popup/terminal.      |
| Type mode dropping characters          | Tuned inter-keystroke delay; clear modifiers before typing.           |

---

## 15. Decisions log

- **Wayland:** X11 now, Wayland-ready interface; no Wayland implementation in Phase 1.
- **Injection default:** Type (most dependable; works in terminals; no clipboard touch). Paste
  optional with clipboard save/restore. Per-app overrides deferred to Phase 2.
- **Recording cap:** default 60s, user-configurable.
- **Indicator:** floating count-up timer pill, top-right, focus-safe, optional.
- **Build strategy:** engine first (config-driven), systray + Control Center GUI as Phase 2.
- **Phase 1 extras chosen:** word-replacement dictionary; cancel + repaste-last hotkeys.
- **Deferred to Phase 2:** GUI/systray, per-app paste modes, local history, waveform colors,
  mute-while-recording, transcription tone, AI command modes.
- **Not building:** accounts/PRO, auto-update/beta channel, Discord, usage dashboard.
