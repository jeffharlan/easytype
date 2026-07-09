import subprocess
from unittest.mock import patch

from easytype.media import MediaController


def _cp(stdout=""):
    return subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout, stderr="")


def _player_runner(calls):
    """Simulate two players: spotify Playing, firefox Paused."""
    def run(cmd, **kwargs):
        calls.append(list(cmd))
        if "--list-all" in cmd:
            return _cp("spotify\nfirefox\n")
        if "status" in cmd:
            return _cp("Playing\n" if "spotify" in cmd else "Paused\n")
        return _cp()  # pause / play produce no stdout
    return run


def test_pause_pauses_only_playing_players():
    calls = []
    with patch("easytype.media.subprocess.run", side_effect=_player_runner(calls)):
        MediaController().pause()
    assert ["playerctl", "-p", "spotify", "pause"] in calls
    assert ["playerctl", "-p", "firefox", "pause"] not in calls


def test_resume_plays_only_players_it_paused():
    calls = []
    with patch("easytype.media.subprocess.run", side_effect=_player_runner(calls)):
        m = MediaController()
        m.pause()
        calls.clear()
        m.resume()
    assert ["playerctl", "-p", "spotify", "play"] in calls
    assert ["playerctl", "-p", "firefox", "play"] not in calls


def test_missing_playerctl_is_silent():
    with patch("easytype.media.subprocess.run", side_effect=FileNotFoundError):
        m = MediaController()
        m.pause()   # must not raise
        m.resume()  # must not raise


def test_playerctl_error_is_silent():
    err = subprocess.TimeoutExpired(cmd="playerctl", timeout=2)
    with patch("easytype.media.subprocess.run", side_effect=err):
        m = MediaController()
        m.pause()
        m.resume()
