import json
import subprocess

from easytype.injector.wayland import (
    WaylandInjector, backspace_command, is_terminal, paste_key_command, type_command,
)


def test_backspace_command_repeats_the_key():
    assert backspace_command(2) == ["ydotool", "key", "14:1", "14:0", "14:1", "14:0"]


def test_backspace_command_of_zero_is_empty():
    assert backspace_command(0) == []


def test_backspace_of_zero_runs_nothing(monkeypatch):
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: calls.append(a))
    WaylandInjector().backspace(0)
    assert calls == []


def test_type_text_of_empty_string_runs_nothing(monkeypatch):
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: calls.append(a))
    WaylandInjector().type_text("")
    assert calls == []


def test_type_text_uses_the_configured_delay_by_default(monkeypatch):
    seen = []
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: seen.append(cmd))
    WaylandInjector(type_delay_ms=40).type_text("hi")
    assert "40" in seen[0]


def test_type_text_delay_can_be_overridden(monkeypatch):
    seen = []
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: seen.append(cmd))
    WaylandInjector(type_delay_ms=40).type_text("hi", delay_ms=10)
    assert "10" in seen[0]
    assert "40" not in seen[0]


def test_active_window_returns_the_address(monkeypatch):
    class _R:
        returncode = 0
        stdout = json.dumps({"address": "0x55f", "class": "kitty"})

    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: _R())
    assert WaylandInjector().active_window() == "0x55f"


def test_active_window_is_empty_when_hyprctl_fails(monkeypatch):
    def boom(*a, **kw):
        raise FileNotFoundError

    monkeypatch.setattr(subprocess, "run", boom)
    assert WaylandInjector().active_window() == ""


def test_active_window_is_empty_on_bad_json(monkeypatch):
    class _R:
        returncode = 0
        stdout = "not json"

    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: _R())
    assert WaylandInjector().active_window() == ""


def test_type_command_uses_key_delay():
    cmd = type_command("hello world", delay_ms=12)
    assert cmd[0] == "ydotool"
    assert "type" in cmd
    assert "12" in cmd
    assert cmd[-1] == "hello world"


def test_type_command_stops_option_parsing_before_text():
    cmd = type_command("--weird looking text", delay_ms=12)
    assert "--" in cmd
    assert cmd[cmd.index("--") + 1] == "--weird looking text"


def test_paste_key_command_is_ctrl_v():
    assert paste_key_command() == ["ydotool", "key", "29:1", "47:1", "47:0", "29:0"]


def test_paste_key_command_shift_is_ctrl_shift_v():
    assert paste_key_command(shift=True) == [
        "ydotool", "key", "29:1", "42:1", "47:1", "47:0", "42:0", "29:0",
    ]


def test_is_terminal_detects_terminals():
    assert is_terminal("kitty")
    assert is_terminal("org.wezfurlong.wezterm")
    assert is_terminal("footclient")
    assert is_terminal("alacritty")


def test_is_terminal_false_for_apps():
    assert not is_terminal("code")
    assert not is_terminal("google-chrome")
    assert not is_terminal("firefox")
