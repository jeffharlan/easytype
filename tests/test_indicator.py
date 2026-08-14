import io

from easytype.indicator import (
    MARGIN, PILL_H, PILL_W, NullIndicator, ProcessIndicator, _position_xy, create_indicator,
    format_elapsed, should_warn, wrap_tail,
)
from easytype.config import load_config


def test_format_elapsed():
    assert format_elapsed(0) == "0:00"
    assert format_elapsed(7) == "0:07"
    assert format_elapsed(75) == "1:15"


def test_should_warn_near_cap():
    assert should_warn(elapsed=56, cap=60) is True
    assert should_warn(elapsed=50, cap=60) is False


def test_bottom_center_is_horizontally_centered_and_low():
    sw, sh = 1920, 1080
    x, y = _position_xy("bottom-center", sw, sh)
    assert x == (sw - PILL_W) // 2
    assert y == sh - PILL_H - MARGIN * 2


def test_unknown_position_falls_back_to_top_right():
    sw, sh = 1920, 1080
    assert _position_xy("nonsense", sw, sh) == (sw - PILL_W - MARGIN, MARGIN)


def test_wrap_tail_wraps_at_width():
    assert wrap_tail("aaa bbb ccc", width=7, max_lines=4) == ["aaa bbb", "ccc"]


def test_wrap_tail_keeps_only_the_last_lines():
    text = " ".join(f"word{i}" for i in range(40))
    lines = wrap_tail(text, width=20, max_lines=3)
    assert len(lines) == 3
    assert "word39" in lines[-1]


def test_wrap_tail_on_empty_text():
    assert wrap_tail("   ", width=20, max_lines=3) == []


class FakeProc:
    def __init__(self, stdin=None):
        self.stdin = io.StringIO() if stdin is None else stdin
        self.terminated = False

    def terminate(self):
        self.terminated = True


def test_caption_writes_one_line_to_the_pill():
    ind = ProcessIndicator("top-right", "up")
    ind._proc = FakeProc()
    ind.caption("hello there")
    assert ind._proc.stdin.getvalue() == "hello there\n"


def test_caption_collapses_whitespace_so_one_caption_is_one_line():
    ind = ProcessIndicator("top-right", "up")
    ind._proc = FakeProc()
    ind.caption("line one\nline two\t\tspaced")
    assert ind._proc.stdin.getvalue() == "line one line two spaced\n"


def test_caption_without_a_running_pill_is_a_noop():
    ind = ProcessIndicator("top-right", "up")
    ind.caption("nobody is listening")      # _proc is None; must not raise


def test_caption_survives_a_broken_pipe():
    class BrokenStdin:
        def write(self, _):
            raise BrokenPipeError

        def flush(self):
            pass

    ind = ProcessIndicator("top-right", "up")
    ind._proc = FakeProc(stdin=BrokenStdin())
    ind.caption("pill already exited")      # must not raise


def test_null_indicator_caption_is_a_noop():
    NullIndicator().caption("anything")


def test_bottom_anchored_window_grows_upward():
    _, y_short = _position_xy("bottom-center", 1920, 1080, PILL_W, PILL_H)
    _, y_tall = _position_xy("bottom-center", 1920, 1080, PILL_W, PILL_H + 100)
    assert y_tall == y_short - 100


def test_right_anchored_window_grows_leftward():
    x_narrow, _ = _position_xy("top-right", 1920, 1080, PILL_W, PILL_H)
    x_wide, _ = _position_xy("top-right", 1920, 1080, PILL_W + 200, PILL_H)
    assert x_wide == x_narrow - 200


def test_create_indicator_returns_null_when_tk_missing(tmp_path, monkeypatch):
    c = load_config(tmp_path / "c.toml")
    monkeypatch.setattr("easytype.indicator._tk_available", lambda: False)
    ind = create_indicator(c)
    # Null indicator: start/stop are safe no-ops
    ind.start(cap=60)
    ind.stop()
    assert ind.is_null is True
