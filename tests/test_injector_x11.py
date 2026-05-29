from easytype.injector.x11 import type_command, paste_key_command, is_terminal


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
