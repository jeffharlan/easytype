# Pause media while recording — design

## Problem

When EasyType records, the microphone also picks up any music playing through
the speakers. That background audio bleeds into the recording and degrades
Whisper's transcription. We want EasyType to stop the music for the duration of
a capture and bring it back afterward.

## Behavior

- When recording **starts**, pause any media players that are currently playing.
- When recording **stops** (normal finish, cancel, or the max-duration backstop),
  resume playback — but only for the players we actually paused, so we never
  start something the user had stopped themselves.
- Music resumes the instant the microphone stops, not after transcription
  finishes, so it comes back quickly.
- The whole step is best-effort: if the media tool is missing or errors, EasyType
  logs it and carries on. Recording is never blocked or crashed by this.
- A Settings toggle "Pause media while recording" controls the feature, default
  **on**.

## Mechanism

Use `playerctl` (MPRIS over D-Bus), which pauses and resumes real media players
(Spotify, browsers, VLC, …) at their exact position. Chosen over muting the audio
output because it truly pauses — the song doesn't advance silently and lose a
stretch. `playerctl` is not installed by default; when it is absent the feature
degrades to a logged no-op.

## Components

### `src/easytype/media.py` — `MediaController`

A small collaborator, injected into `Controller` alongside `recorder`/`indicator`.

- `pause()` — enumerate players (`playerctl --list-all`), check each one's status,
  remember the ones currently **Playing**, and pause only those. The remembered
  list is stored on the instance.
- `resume()` — play back only the players recorded by the last `pause()`, then
  clear the list.
- All `playerctl` calls run through `subprocess` with a short timeout. Missing
  binary (`FileNotFoundError`), non-zero exit, timeout, or no players → silent,
  logged no-op; never raises.

### `controller.py`

- `_start()` → `self._media.pause()`, gated on `self._cfg.pause_media_while_recording`.
- Resume at every exit from the recording state, immediately after the recorder
  stops:
  - `_finish_recording()` — after `self._rec.stop()`
  - `on_cancel()` (recording branch) — after `self._rec.stop()`
  - `_cap_reached` needs no change; it routes through `_finish_recording`.
- Resume is likewise gated on the config flag.

### `config.py`

- New `Config` field `pause_media_while_recording: bool`, default `True`.
- New `[media]` table in the default TOML: `pause_while_recording = true`.
- Wired through `load_config` (read with default `True`) and
  `apply_settings_to_doc` (write from the settings dict).

### `gui/settings.py`

- New `QCheckBox` "Pause media while recording", following the existing
  `indicator_enabled` pattern: `setChecked` on load, `isChecked()` into the
  collected values dict.

### `engine.py`

- Construct a `MediaController()` and pass it to `Controller`.

## Testing (TDD — tests written first)

- `test_media.py`
  - `pause()` pauses only players whose status is `Playing`, and records them.
  - `resume()` plays only the players recorded by the prior `pause()`.
  - Missing `playerctl` (subprocess raises `FileNotFoundError`) → no exception.
  - Subprocess errors/timeouts → no exception.
  - (subprocess is mocked; no real player required.)
- `test_controller.py` (fake `media` collaborator)
  - `_start` calls `media.pause()`.
  - Normal finish and cancel each call `media.resume()`.
  - With the config flag off, neither pause nor resume is called.
- `test_config.py`
  - `pause_media_while_recording` defaults to `True`.
  - Round-trips through `apply_settings_to_doc` / `load_config`.

## Out of scope

- Muting-based fallback via `pactl` (rejected: music would advance silently).
- Pausing based on which audio device is capturing (headphones vs speakers) — we
  always pause when the toggle is on.

## Follow-up (not code)

`sudo apt install playerctl` on the dev machine so the feature works live. Without
it the app runs fine; the pause step is just a logged no-op.
