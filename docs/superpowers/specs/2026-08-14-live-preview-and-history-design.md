# Live preview and recent-transcription history — design

## Problem

Two gaps in the dictation loop, both about visibility.

1. **Nothing is visible while you speak.** Whisper runs once, on the whole clip,
   after recording stops. Until then the only feedback is a timer pill. You have
   to finish and stop before you learn whether the transcription is any good.
2. **Transcripts vanish after injection.** `last_transcript` holds exactly one
   entry, in memory, and F8 re-injects it. Anything before that is gone, and
   nothing survives a restart. There is no way to go back and copy an earlier
   dictation into something else.

## Behavior

### Live preview

- While recording, the on-screen indicator shows a running transcript of what
  has been captured so far, updating every second or so.
- Preview text is **display only**. Nothing is injected until you stop; the
  existing full-clip pass still produces the text that gets typed.
- Preview runs on its own model, configurable, defaulting to `tiny.en` for
  speed. Setting it to the main transcription model makes the preview exact at
  the cost of latency on long clips.
- Controlled by a Settings toggle, default **on**. With the on-screen indicator
  disabled, preview is inert regardless of this toggle — there is nowhere to
  draw it.
- Best-effort throughout: a failed preview pass is logged and skipped. Preview
  never blocks, delays, or degrades recording or the final transcription.

### History

- Every successful dictation is appended to a history file. The five most recent
  are kept, newest first.
- Cancelled recordings and empty transcripts are not recorded.
- The tray menu gains a **Recent** submenu listing the five, each labelled with
  a truncated preview of its text. Activating one copies the full text to the
  clipboard. A **Open history file…** item opens the file in the user's editor.
- Controlled by a Settings toggle, default **on**. This is a privacy switch:
  the feature writes everything the user says to disk, and in a public OSS tool
  that must be declinable.

## Mechanism

### Why re-transcribe rather than stream

faster-whisper has no streaming API; it transcribes a complete array. Live
preview therefore means running it repeatedly over a growing buffer.

Two alternatives were rejected:

- **Chunk-and-append** (transcribe only the newest N seconds, concatenate the
  results). Cheapest — O(n) rather than O(n²) — but Whisper depends on sentence
  context, and arbitrary split points mangle words at every seam. Silence-aligned
  splitting via VAD would fix it and is far more machinery than a 60-second
  capture warrants.
- **Reusing the main model for preview.** No extra VRAM and an exact preview,
  but `small.en` re-reading a growing buffer falls behind audibly on longer
  clips and contends with Ollama for the GPU when AI cleanup is on.

Whole-buffer re-transcription with a small fast model keeps preview latency
roughly flat regardless of clip length. `tiny.en` at float16 is ~75 MB of VRAM,
comfortable alongside `small.en` and Ollama on a 6 GB card. Because the model is
a config value, pointing it at the main model recovers the rejected alternative's
exactness without any extra code.

### Why a pipe to the indicator

The indicator already runs as a **separate process** (`ProcessIndicator`) so Tk
always owns its own main thread — a deliberate fix for Tcl cross-thread teardown
crashes. Preview text must therefore cross a process boundary. The subprocess is
launched with `stdin=PIPE` and captions are written as newline-delimited records;
the pill reads them on a background thread. This keeps the existing process
isolation intact and adds no new dependency.

## Components

### `src/easytype/preview.py` — `PreviewWorker` (new)

A collaborator injected into `Controller` alongside `recorder`/`indicator`,
constructed in `engine.py`.

- `__init__(recorder, transcriber, indicator, interval=PREVIEW_INTERVAL)`, where
  `PREVIEW_INTERVAL = 1.0` seconds — the gap *between* passes, not a deadline.
- `start()` — spins up a daemon thread; no-op if already running.
- `stop()` — clears the running flag and joins with a short timeout. A pass
  already in flight finishes on its own and its result is discarded. `stop()`
  never blocks the final transcription.
- Loop body: snapshot the recorder's audio; skip if shorter than
  `MIN_PREVIEW_SECONDS` (0.5 s) — too little to transcribe usefully; transcribe;
  if still running, `indicator.caption(text)`; sleep `interval`.
- **Self-throttling by construction**: the next pass starts only after the
  previous one returns, so passes never queue up or overlap.
- Exceptions inside a pass are caught, logged, and the loop continues.

### `src/easytype/recorder.py`

- New `snapshot() -> np.ndarray` — concatenates the frames captured so far
  without touching the stream. Returns an empty array when nothing is buffered.
- Reads a shallow copy of `self._frames` so the audio callback thread can keep
  appending during the concatenate. `list.append` and slicing are atomic under
  the GIL; no lock is needed and none is added, since a lock in the audio
  callback risks dropouts.

### `src/easytype/indicator.py`

- `ProcessIndicator.start()` passes `stdin=subprocess.PIPE`.
- New `ProcessIndicator.caption(text)` — collapses all whitespace runs to single
  spaces (so one caption is always exactly one line, with no escaping scheme to
  get wrong on either side), writes it, and flushes. The pill re-wraps the text
  for display anyway, so the original line breaks carry no information.
  A `BrokenPipeError`/`ValueError` (pill already exited, e.g. the cap timer fired)
  is swallowed — captions are advisory.
- `NullIndicator.caption(text)` — no-op, keeping the two interchangeable.
- New pure helper `wrap_tail(text, width, max_lines) -> list[str]` — wraps to
  `width` characters and returns the **last** `max_lines` lines, so the box reads
  as scrolling captions with the oldest text falling off the top. Pure and
  Tk-free, therefore directly unit-testable.
- `_run_pill` gains a caption label under the timer and a stdin reader thread
  that marshals updates onto the Tk thread via `root.after(0, ...)`. Direct Tk
  calls from the reader thread are not safe.
- Geometry: the window keeps its pill size until the first caption arrives, then
  resizes to `CAPTION_W` wide and tall enough for the wrapped lines. `_position_xy`
  is extended to take the current width and height so that bottom-anchored
  positions grow **upward** and right-anchored positions grow **leftward**,
  instead of running off the screen edge.

### `src/easytype/history.py` (new)

- `HISTORY_PATH = ~/.local/share/easytype/history.txt` (XDG data dir — this is
  user data, not configuration).
- `HISTORY_LIMIT = 5`.
- Record format, newest first:

  ```
  --- 2026-08-14 09:12:33 ---
  So what I need you to do is check the camera counts.

  --- 2026-08-14 09:08:01 ---
  Confirming the Milestone server upgrade is Thursday.
  ```

  Plain text so it is readable and pasteable in any editor, with a delimiter
  regular enough to parse reliably.
- `append(text, path=HISTORY_PATH, now=None)` — prepends a new entry, truncates
  to `HISTORY_LIMIT`, writes atomically (temp file in the same directory, then
  `os.replace`) so a concurrent read from the tray can never see a partial file.
  Empty/whitespace text is ignored. `now` is injectable for deterministic tests.
- `read(path=HISTORY_PATH) -> list[HistoryEntry]` — parses the file into
  `HistoryEntry(timestamp: str, text: str)`. A missing or malformed file yields
  an empty list; history is never allowed to break the caller.

### `src/easytype/controller.py`

- Takes a `preview` collaborator, default `None`, exactly as `media` does — every
  call site guards with `if self._preview:` rather than requiring a null object.
- `_start()` → `self._preview.start()` after the recorder starts.
- `_preview.stop()` at every exit from the recording state, before the final
  transcription: in `_finish_recording()` and in the recording branch of
  `on_cancel()`. `_cap_reached` needs no change; it routes through
  `_finish_recording`.
- `process_audio()` → after polish, on non-empty text and when not cancelled, and
  gated on `self._cfg.history_enabled`, call `history.append(text)` before
  injection. Wrapped so a history failure cannot stop the text from being typed.

### `src/easytype/engine.py`

- Build a second `Transcriber` for preview, using `config.preview_model` (falling
  back to `config.model` when blank), and pass a `PreviewWorker` to `Controller`.
  When preview or the indicator is disabled, pass `None`.
- `EngineBundle.warmup` warms **both** models, so the first preview pass does not
  pay a model load.

### `src/easytype/config.py`

- New `Config` fields: `preview_enabled: bool` (default `True`),
  `preview_model: str` (default `"tiny.en"`), `history_enabled: bool`
  (default `True`).
- New default TOML tables:

  ```toml
  [preview]
  enabled = true
  model = "tiny.en"      # "" = reuse the transcription model

  [history]
  enabled = true
  ```

- Wired through `load_config` and `apply_settings_to_doc`, following the
  existing `[media]` pattern.

### `src/easytype/gui/settings.py`

- Indicator tab gains a "Show live preview while recording" checkbox and a
  "Preview model" editable combo (reusing `MODELS`), following the
  `indicator_enabled` pattern: `setCurrentText`/`setChecked` in `_load`,
  read back in `_values`.
- Advanced tab gains a "Keep the last 5 transcriptions" checkbox.

### `src/easytype/gui/app.py`

- Tray menu gains a **Recent** submenu, rebuilt on its `aboutToShow` signal so
  it always reflects the file on disk (the engine writes it from another thread).
- Each entry's label is the first ~50 characters of its text, elided, with
  newlines collapsed. Activating it calls `QApplication.clipboard().setText(full)`.
  This is safe alongside dictation: paste-mode injection already saves and
  restores the clipboard around itself, and the two are user-sequenced anyway.
- An **Open history file…** item uses `QDesktopServices.openUrl`.
- With no history, the submenu holds a single disabled "No recent transcriptions".

## Testing (TDD — tests written first)

- `test_history.py`
  - `append` writes an entry that `read` round-trips.
  - Keeps exactly `HISTORY_LIMIT`, newest first, dropping the oldest.
  - Empty/whitespace text is ignored.
  - `read` on a missing file returns `[]`; on a malformed file returns `[]`.
  - Multi-line text round-trips intact.
  - `menu_label` truncates, collapses newlines, and doubles `&` so Qt does not
    read it as a menu mnemonic.
- `test_preview.py` (fake recorder/transcriber/indicator)
  - A pass transcribes the snapshot and publishes the result as a caption.
  - Audio shorter than `MIN_PREVIEW_SECONDS` is skipped without transcribing.
  - A pass that completes after `stop()` publishes nothing.
  - A transcriber exception is swallowed, so the loop survives it.
  - `start()` then `stop()` leaves no live thread behind.

  Passes cannot overlap by construction — the loop calls them sequentially — so
  there is no test for it; asserting it would only be testing Python.
- `test_recorder.py` (new file — the recorder has no tests today)
  - `snapshot` returns accumulated frames without stopping the stream, and
    `stop` afterwards still returns the full audio.
  - `snapshot` with nothing buffered returns an empty array.
- `test_indicator.py`
  - `wrap_tail` wraps at width, returns at most `max_lines`, keeps the **tail**,
    handles empty text.
  - `ProcessIndicator.caption` writes one flushed line to a fake process stdin,
    escaping embedded newlines.
  - `caption` on a broken pipe does not raise.
  - `NullIndicator.caption` is a no-op.
  - `_position_xy` grows upward from bottom anchors and leftward from right
    anchors as the window height/width increase.
- `test_controller.py` (fake `preview` collaborator, patched history)
  - `_start` calls `preview.start()`.
  - Normal finish and cancel each call `preview.stop()`.
  - History is written on a successful transcript and not on a cancelled one.
  - With `history_enabled` off, nothing is written.
  - A history write failure still injects the text.
- `test_config.py`
  - `preview_enabled`, `preview_model`, `history_enabled` defaults.
  - Round-trip through `apply_settings_to_doc` / `load_config`.

No test loads a real Whisper model, starts a real audio stream, or opens a Tk
window; all three are faked, matching the existing suite.

## Shipping

Two PRs, in order, each green on CI before the next starts:

1. **History + tray menu** — `history.py`, `controller.py`, `config.py`,
   `gui/settings.py`, `gui/app.py`. Self-contained and independently useful.
2. **Live preview** — `preview.py`, `recorder.py`, `indicator.py`,
   `controller.py`, `engine.py`, `config.py`, `gui/settings.py`.

`README.md` and `config.sample.toml` are updated in whichever PR introduces the
setting.

## Out of scope

- **Injecting preview text live into the focused window.** Whisper revises
  earlier words as it hears more, so live injection requires backspacing over
  text in the user's real document. Explicitly deferred; the overlay was chosen
  instead.
- **VAD-aligned incremental transcription.** See "Why re-transcribe" above.
- **A configurable history size.** Five, as asked. A knob can be added if a
  second need for it appears.
- **Searching or editing history from the GUI.** Copy and open-the-file cover
  the stated need.

## Known trade-offs

- **Preview text can differ from the injected text** when the preview model is
  smaller than the transcription model. Inherent to the approach and the reason
  the model is configurable.
- **Short bursts show nothing.** In `hold` mode, a tap under ~2 seconds ends
  before the first preview pass completes. Expected, not a defect.
- **Two models resident in VRAM.** ~75 MB extra at the default. Worth watching
  only if the main model is raised to `medium.en` or larger while Ollama is
  also loaded.
- **A transcript containing a line that looks exactly like a history delimiter**
  (`--- YYYY-MM-DD HH:MM:SS ---`, alone on its line) would be read back as two
  entries. Whisper does not emit that shape, and the file is personal dictation
  history, so the plain-text format is kept for readability rather than hardened
  against it.

## Follow-up (not code)

The tray app is an editable pipx install; it must be restarted after merge before
any of this is visible live.
