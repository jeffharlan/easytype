from easytype import autostart


def test_disabled_when_no_file(tmp_path):
    assert autostart.is_enabled(tmp_path / "easytype.desktop") is False


def test_enable_writes_desktop_entry(tmp_path):
    p = tmp_path / "easytype.desktop"
    autostart.set_enabled(True, p)
    assert autostart.is_enabled(p) is True
    assert "easytype-gui" in p.read_text()


def test_disable_removes_file(tmp_path):
    p = tmp_path / "easytype.desktop"
    autostart.set_enabled(True, p)
    autostart.set_enabled(False, p)
    assert autostart.is_enabled(p) is False


def test_disable_when_absent_is_noop(tmp_path):
    autostart.set_enabled(False, tmp_path / "nope.desktop")  # must not raise
