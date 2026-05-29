# EasyType

EasyType is a system-wide, local push-to-talk and toggle voice dictation tool for Linux. Press a hotkey, speak, and the transcribed text is inserted at the cursor in whatever app is currently focused — a terminal, a browser text field, a chat window, anything. Transcription runs entirely on your own machine via [faster-whisper](https://github.com/guillaumekl/faster-whisper), so there is no API bill and your audio never leaves the box. Phase 1 targets X11; the architecture is Wayland-ready. Released under the MIT License.

## How it works

EasyType runs a background listener that grabs your keyboard device via evdev. When you press the hotkey, it starts recording from the microphone. In toggle mode, press the hotkey again to stop; in hold mode, release it. The recording is passed to faster-whisper for local transcription. Optional dictionary substitutions are applied (e.g., replace a misheard name), and an optional LLM formatter can clean up punctuation or phrasing. The finished text is injected at the cursor using `xdotool type` or `xdotool key ctrl+v` (paste mode).

Because EasyType uses evdev grab-and-replay — it grabs the keyboard at the device level and synthesises a new virtual device for normal key events — the hotkey chord is fully consumed before the focused application ever sees it. Combos like Ctrl+Space (which normally toggles IBus) and Ctrl+\\ (which sends SIGQUIT in terminals) do not fire their usual side effects.

## Requirements / System dependencies

- Python 3.11+
- System packages:

```bash
sudo apt install xdotool xclip libnotify-bin portaudio19-dev python3-tk
```

`python3-tk` is optional. It powers the small on-screen recording-timer pill. If it is missing, EasyType falls back to desktop notifications.

Wayland support (ydotool, wl-clipboard) is planned but not included in Phase 1. On a Wayland session, use `--passive` mode.

## Install

```bash
pipx install git+https://github.com/jeffharlan/easytype
```

Or clone and install in editable mode:

```bash
git clone https://github.com/jeffharlan/easytype
pipx install -e ./easytype
```

Both methods expose the `easytype` command on your PATH.

## Permissions setup

The grab-and-replay consume feature requires two things:

1. Your user must be in the `input` group.
2. Your user must have write access to `/dev/uinput`.

Run `easytype --check` to see exactly what is missing and the precise commands to fix it.

**Fix 1 — input group:**

```bash
sudo usermod -aG input $USER
```

Log out and back in for the group change to take effect.

**Fix 2 — uinput access (udev rule):**

```bash
echo 'KERNEL=="uinput", GROUP="input", MODE="0660"' | sudo tee /etc/udev/rules.d/99-easytype-uinput.rules
sudo modprobe uinput
sudo udevadm control --reload-rules
sudo udevadm trigger
```

If either prerequisite is not met, EasyType automatically falls back to `--passive` mode and prints a warning rather than crashing. You can also run `--passive` intentionally to skip the grab entirely.

## First run / usage

Start with passive mode to verify transcription works before touching any permissions:

```bash
easytype --passive
```

In passive mode there is no keyboard grab, no `/dev/uinput` access, and no special permissions. The hotkey is detected via a non-grabbing listener, but the chord still reaches the focused application.

Once you are satisfied, run normally:

```bash
easytype
```

**Default hotkeys:**

| Action | Key |
|--------|-----|
| Start / stop recording | Ctrl+Space |
| Cancel in-progress recording | Esc |
| Re-inject last transcript | F8 |

Press Ctrl+Space to begin recording. An on-screen timer pill appears showing elapsed time (counting up by default). Press Ctrl+Space again to stop and transcribe, or press Esc to cancel without inserting anything. When transcription is complete, the text is inserted at your cursor. Press F8 at any time to re-inject the last transcript.

## Configuration

The config file is created automatically at `~/.config/easytype/config.toml` on first run. A fully-commented reference copy is at `config.sample.toml` in this repository.

**Top-level settings:**

| Key | Values | Description |
|-----|--------|-------------|
| `capture_mode` | `toggle` \| `hold` | Toggle: press once to start, press again to stop. Hold: key down to record, key up to stop. |
| `max_recording_duration` | integer (seconds) | Safety auto-stop. Default `60`. |

**`[hotkey]`** — the record hotkey:

| Key | Description |
|-----|-------------|
| `keys` | List of raw evdev keycodes. Default `[29, 57]` (Ctrl+Space). |
| `description` | Human-readable label shown in logs and `--check` output. |

**`[hotkey.cancel]`** — cancels an active recording (default: `keys = [1]`, Esc).

**`[hotkey.repaste]`** — re-injects the last transcript (default: `keys = [66]`, F8).

**`[audio]`:**

| Key | Description |
|-----|-------------|
| `device` | Microphone device name or index. `""` uses the system default. |

**`[transcription]`:**

| Key | Values | Description |
|-----|--------|-------------|
| `model` | `tiny.en`, `base.en`, `small.en`, `medium.en`, … | Whisper model size. Default `base.en`. Larger models are more accurate; your GPU handles them easily. |
| `language` | `en`, `es`, … | Whisper language hint. |
| `device` | `auto` \| `cuda` \| `cpu` | Transcription compute device. `auto` uses CUDA if available. |

**`[injection]`:**

| Key | Values | Description |
|-----|--------|-------------|
| `method` | `type` \| `paste` | `type` uses `xdotool type`; `paste` writes to clipboard and sends Ctrl+V. |

**`[formatter]`** — optional LLM cleanup pass (disabled by default):

| Key | Description |
|-----|-------------|
| `enabled` | `true` \| `false` |
| `backend` | `ollama` \| `openai` |
| `ollama_model` | Model name for Ollama (default `llama3.1`). |
| `ollama_url` | Ollama API URL (default `http://localhost:11434`). |

**`[indicator]`** — on-screen recording timer:

| Key | Values | Description |
|-----|--------|-------------|
| `enabled` | `true` \| `false` | Show the timer pill while recording. |
| `position` | `top-right` \| `top-center` \| `bottom-right` \| `bottom-left` \| `top-left` | Screen corner. |
| `count` | `up` \| `down` | Count up from 0 or count down from `max_recording_duration`. |

**`[keyboard]`:**

| Key | Description |
|-----|-------------|
| `device` | Path to keyboard event device (e.g. `/dev/input/event3`). `""` auto-detects all keyboard devices. |

**`[[dictionary]]`** — repeated table entries for word substitutions:

```toml
[[dictionary]]
hears = "easy type"
replace = "EasyType"
mode = "smart"         # "smart" | "exact"
```

`smart` mode matches the phrase regardless of surrounding punctuation; `exact` requires a verbatim match.

## Changing the hotkey

Capture and save the record hotkey interactively:

```bash
easytype --set-hotkey
```

Capture and save the cancel hotkey:

```bash
easytype --set-hotkey cancel
```

Capture and save the repaste hotkey:

```bash
easytype --set-hotkey repaste
```

Press the key or chord you want to use; EasyType records the actual evdev codes and writes them to your config. Any key or combination is accepted. For known-conflict chords (Ctrl+Space, Ctrl+\\), EasyType prints an informational note explaining the usual side effect and how the consume feature prevents it, then saves your choice.

## Run on login

Copy the included systemd user service and enable it:

```bash
mkdir -p ~/.config/systemd/user
cp systemd/easytype.service ~/.config/systemd/user/
systemctl --user enable --now easytype
```

## Troubleshooting

**Check your session type:**

```bash
echo $XDG_SESSION_TYPE
```

Phase 1 supports X11 only. On a Wayland session, text injection is not implemented yet — use `easytype --passive` to test transcription, and watch for Phase 2.

**Stuck keyboard:** The evdev grab is always released on exit, whether that is a clean shutdown, a crash, or Ctrl+C / SIGTERM. If grab prerequisites are missing at startup, EasyType falls back to passive mode automatically rather than holding the grab in a broken state.

**First run is slow:** The Whisper model is downloaded once on first use (a few hundred MB for `base.en`). Subsequent starts are fast.

**Wrong microphone:** Set `[audio] device` to the device name or index shown by your system's audio settings. Leave it blank for the system default.

**Accuracy:** The default `base.en` model is fast but modest. `small.en` and `medium.en` are meaningfully more accurate. If you have a GPU, `medium.en` with `device = "auto"` transcribes in well under a second.
