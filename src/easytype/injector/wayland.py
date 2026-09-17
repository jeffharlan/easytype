from __future__ import annotations

import json
import subprocess
import time

# Linux input-event-codes.h values — stable across kernels, so hardcoded here
# rather than imported from evdev, which the test suite deliberately keeps
# optional (see keycodes.py/listener.py for the same lazy-import convention).
KEY_LEFTCTRL = 29
KEY_LEFTSHIFT = 42
KEY_V = 47
KEY_BACKSPACE = 14

CLIP_COPY = ["wl-copy"]
CLIP_PASTE = ["wl-paste", "--no-newline"]

# App-id / window-class values that paste with Ctrl+Shift+V, not Ctrl+V. Hyprland
# reports whichever the toolkit sets (app_id on native Wayland, WM_CLASS under
# XWayland), so this mixes both conventions rather than picking one.
TERMINAL_CLASSES = frozenset({
    "kitty", "alacritty", "foot", "footclient", "wezterm", "org.wezfurlong.wezterm",
    "com.mitchellh.ghostty", "ghostty", "xterm", "urxvt", "rxvt", "st", "contour",
    "org.gnome.terminal", "gnome-terminal-server", "konsole", "tilix",
    "com.gexperts.tilix", "terminator", "hyper", "wezterm-gui",
})


def type_command(text: str, delay_ms: int) -> list[str]:
    return ["ydotool", "type", "--key-delay", str(delay_ms), "--", text]


def _key_seq(*codes: int) -> list[str]:
    """Press every code in order, then release in reverse — modifiers go down
    first and come up last, same order a real chord would produce."""
    down = [f"{c}:1" for c in codes]
    up = [f"{c}:0" for c in reversed(codes)]
    return down + up


def paste_key_command(shift: bool = False) -> list[str]:
    codes = (
        [KEY_LEFTCTRL, KEY_LEFTSHIFT, KEY_V]
        if shift
        else [KEY_LEFTCTRL, KEY_V]
    )
    return ["ydotool", "key", *_key_seq(*codes)]


def backspace_command(count: int) -> list[str]:
    """ydotool has no --repeat for `key` (only `click`), so N backspaces means
    N explicit down/up pairs."""
    seq: list[str] = []
    for _ in range(count):
        seq += [f"{KEY_BACKSPACE}:1", f"{KEY_BACKSPACE}:0"]
    return ["ydotool", "key", *seq] if seq else []


def is_terminal(name: str) -> bool:
    return "term" in name or name in TERMINAL_CLASSES


def _hyprctl_active_window() -> dict:
    try:
        r = subprocess.run(
            ["hyprctl", "-j", "activewindow"],
            capture_output=True, text=True, timeout=1,
        )
        if r.returncode != 0 or not r.stdout.strip():
            return {}
        return json.loads(r.stdout)
    except Exception:
        return {}


class WaylandInjector:
    def __init__(self, type_delay_ms: int = 40):
        self._delay = type_delay_ms

    def inject(self, text: str, method: str) -> None:
        if not text:
            return
        if method == "paste":
            self._paste(text)
        else:
            subprocess.run(type_command(text, self._delay), check=True)

    def type_text(self, text: str, delay_ms: int | None = None) -> None:
        """Raw incremental typing for live dictation — mirrors X11Injector so
        LiveTypist doesn't need to know which backend it's talking to."""
        if text:
            subprocess.run(
                type_command(text, self._delay if delay_ms is None else delay_ms),
                check=True,
            )

    def backspace(self, count: int) -> None:
        cmd = backspace_command(count)
        if cmd:
            subprocess.run(cmd, check=True)

    def active_window(self) -> str:
        """Focused window address from Hyprland, or "" when it can't be
        determined — callers treat "" as a mismatch, same contract as X11Injector."""
        return _hyprctl_active_window().get("address", "")

    def _paste(self, text: str) -> None:
        saved = self._read_clipboard()
        subprocess.run(CLIP_COPY, input=text.encode(), check=True)
        shift = is_terminal(_hyprctl_active_window().get("class", ""))
        subprocess.run(paste_key_command(shift), check=True)
        time.sleep(0.1)  # let the target app consume the paste before we restore
        if saved is not None:
            subprocess.run(CLIP_COPY, input=saved, check=False)

    @staticmethod
    def _read_clipboard() -> bytes | None:
        try:
            r = subprocess.run(CLIP_PASTE, capture_output=True, timeout=1)
            return r.stdout if r.returncode == 0 else None
        except Exception:
            return None
