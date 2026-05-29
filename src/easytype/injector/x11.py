from __future__ import annotations

import subprocess
import time

CLIP = ["xclip", "-selection", "clipboard"]


def type_command(text: str, delay_ms: int) -> list[str]:
    return ["xdotool", "type", "--clearmodifiers", "--delay", str(delay_ms), "--", text]


def paste_key_command() -> list[str]:
    return ["xdotool", "key", "--clearmodifiers", "ctrl+v"]


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
        subprocess.run(paste_key_command(), check=True)
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
