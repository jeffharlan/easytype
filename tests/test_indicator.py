from easytype.indicator import format_elapsed, should_warn, create_indicator
from easytype.config import load_config


def test_format_elapsed():
    assert format_elapsed(0) == "0:00"
    assert format_elapsed(7) == "0:07"
    assert format_elapsed(75) == "1:15"


def test_should_warn_near_cap():
    assert should_warn(elapsed=56, cap=60) is True
    assert should_warn(elapsed=50, cap=60) is False


def test_create_indicator_returns_null_when_tk_missing(tmp_path, monkeypatch):
    c = load_config(tmp_path / "c.toml")
    monkeypatch.setattr("easytype.indicator._tk_available", lambda: False)
    ind = create_indicator(c)
    # Null indicator: start/stop are safe no-ops
    ind.start(cap=60)
    ind.stop()
    assert ind.is_null is True
