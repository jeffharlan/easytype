from easytype.injector.x11 import type_command, paste_key_command


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
