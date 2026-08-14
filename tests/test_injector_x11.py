import subprocess

from easytype.injector.x11 import (
    X11Injector, backspace_command, is_terminal, paste_key_command, type_command,
)


def test_backspace_command_repeats_the_key():
    assert backspace_command(7) == [
        "xdotool", "key", "--clearmodifiers", "--repeat", "7", "BackSpace",
    ]


def test_backspace_of_zero_runs_nothing(monkeypatch):
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: calls.append(a))
    X11Injector().backspace(0)
    assert calls == []


def test_type_text_of_empty_string_runs_nothing(monkeypatch):
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: calls.append(a))
    X11Injector().type_text("")
    assert calls == []


def test_active_window_returns_the_id(monkeypatch):
    class _R:
        returncode = 0
        stdout = "12582918\n"

    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: _R())
    assert X11Injector().active_window() == "12582918"


def test_active_window_is_empty_when_xdotool_fails(monkeypatch):
    def boom(*a, **kw):
        raise FileNotFoundError

    monkeypatch.setattr(subprocess, "run", boom)
    assert X11Injector().active_window() == ""


def test_type_command_uses_clearmodifiers_and_delay():
    cmd = type_command("hello world", delay_ms=12)
    assert cmd[0] == "xdotool"
    assert "type" in cmd
    assert "--clearmodifiers" in cmd
    assert "12" in cmd
    assert cmd[-1] == "hello world"


def test_type_command_stops_option_parsing_before_text():
    cmd = type_command("--weird looking text", delay_ms=12)
    assert "--" in cmd
    assert cmd[cmd.index("--") + 1] == "--weird looking text"


def test_paste_key_command_is_ctrl_v():
    assert paste_key_command() == ["xdotool", "key", "--clearmodifiers", "ctrl+v"]


def test_paste_key_command_shift_is_ctrl_shift_v():
    assert paste_key_command(shift=True) == ["xdotool", "key", "--clearmodifiers", "ctrl+shift+v"]


def test_is_terminal_detects_terminals():
    assert is_terminal("org.wezfurlong.wezterm")
    assert is_terminal("gnome-terminal-server")
    assert is_terminal("konsole")
    assert is_terminal("alacritty")
    assert is_terminal("xterm")


def test_is_terminal_false_for_apps():
    assert not is_terminal("code")
    assert not is_terminal("google-chrome")
    assert not is_terminal("org.gnome.texteditor")


def test_is_terminal_matches_wezterm_process():
    assert is_terminal("wezterm-gui")
    assert is_terminal("gnome-terminal-")
