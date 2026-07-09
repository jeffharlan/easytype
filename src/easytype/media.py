from __future__ import annotations

import subprocess

TIMEOUT = 2  # seconds — playerctl is local; never let it stall recording


class MediaController:
    """Pause/resume media players via playerctl (MPRIS) around a recording.

    Best-effort: if playerctl is missing or errors, every call is a logged no-op
    so recording is never blocked or crashed."""

    def __init__(self) -> None:
        self._paused: list[str] = []

    def pause(self) -> None:
        self._paused = []
        for player in self._players():
            if self._status(player) == "Playing" and self._run(["playerctl", "-p", player, "pause"]):
                self._paused.append(player)

    def resume(self) -> None:
        for player in self._paused:
            self._run(["playerctl", "-p", player, "play"])
        self._paused = []

    def _players(self) -> list[str]:
        result = self._run(["playerctl", "--list-all"])
        return result.stdout.split() if result else []

    def _status(self, player: str) -> str:
        result = self._run(["playerctl", "-p", player, "status"])
        return result.stdout.strip() if result else ""

    def _run(self, cmd: list[str]) -> subprocess.CompletedProcess | None:
        try:
            return subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT, check=True)
        except (OSError, subprocess.SubprocessError) as e:
            print(f"[easytype] media: {' '.join(cmd)} skipped ({e})")
            return None
