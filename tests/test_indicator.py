from easytype.indicator import (
    MARGIN, PILL_H, PILL_W, _position_xy, create_indicator, format_elapsed, should_warn,
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


def test_create_indicator_returns_null_when_tk_missing(tmp_path, monkeypatch):
    c = load_config(tmp_path / "c.toml")
    monkeypatch.setattr("easytype.indicator._tk_available", lambda: False)
    ind = create_indicator(c)
    # Null indicator: start/stop are safe no-ops
    ind.start(cap=60)
    ind.stop()
    assert ind.is_null is True
