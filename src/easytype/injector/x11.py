from __future__ import annotations

import subprocess
import time
from pathlib import Path

CLIP = ["xclip", "-selection", "clipboard"]

# Terminals paste with Ctrl+Shift+V, not Ctrl+V. Detected by the focused app's
# process name (matched on the "term" substring, plus a few that lack it).
TERMINAL_CLASSES = frozenset({
    "konsole", "alacritty", "kitty", "st", "foot", "urxvt", "rxvt",
    "tilix", "wezterm", "contour", "ghostty", "hyper", "yakuake",
    "guake", "sakura", "terminator", "xterm", "deepin-terminal",
})


def type_command(text: str, delay_ms: int) -> list[str]:
    return ["xdotool", "type", "--clearmodifiers", "--delay", str(delay_ms), "--", text]


def paste_key_command(shift: bool = False) -> list[str]:
    combo = "ctrl+shift+v" if shift else "ctrl+v"
    return ["xdotool", "key", "--clearmodifiers", combo]


def _active_app_name() -> str:
    """Focused app's process name. xdotool's getwindowclassname doesn't exist on
    older xdotool, but getwindowpid does, and /proc/<pid>/comm is enough to spot a
    terminal (e.g. 'wezterm-gui', 'gnome-terminal-')."""
    try:
        r = subprocess.run(
            ["xdotool", "getactivewindow", "getwindowpid"],
            capture_output=True, text=True, timeout=1,
        )
        pid = r.stdout.strip()
        if r.returncode != 0 or not pid:
            return ""
        return Path(f"/proc/{pid}/comm").read_text().strip().lower()
    except Exception:
        return ""


def is_terminal(name: str) -> bool:
    return "term" in name or name in TERMINAL_CLASSES


class X11Injector:
    def __init__(self, type_delay_ms: int = 40):
        self._delay = type_delay_ms

    def inject(self, text: str, method: str) -> None:
        if not text:
            return
        if method == "paste":
            self._paste(text)
        else:
            subprocess.run(type_command(text, self._delay), check=True)

    def _paste(self, text: str) -> None:
        saved = self._read_clipboard()
        subprocess.run(CLIP, input=text.encode(), check=True)
        shift = is_terminal(_active_app_name())
        subprocess.run(paste_key_command(shift), check=True)
        time.sleep(0.1)  # let the target app consume the paste before we restore
        if saved is not None:
            subprocess.run(CLIP, input=saved, check=False)

    @staticmethod
    def _read_clipboard() -> bytes | None:
        try:
            r = subprocess.run([*CLIP, "-o"], capture_output=True, timeout=1)
            return r.stdout if r.returncode == 0 else None
        except Exception:
            return None
