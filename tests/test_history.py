from datetime import datetime
from pathlib import Path

from easytype import history


def test_append_then_read_round_trips(tmp_path: Path):
    p = tmp_path / "history.txt"
    history.append("Check the camera counts.", path=p,
                   now=datetime(2026, 8, 14, 9, 12, 33))
    entries = history.read(p)
    assert len(entries) == 1
    assert entries[0].timestamp == "2026-08-14 09:12:33"
    assert entries[0].text == "Check the camera counts."


def test_newest_entry_is_first(tmp_path: Path):
    p = tmp_path / "history.txt"
    history.append("first", path=p, now=datetime(2026, 8, 14, 9, 0, 0))
    history.append("second", path=p, now=datetime(2026, 8, 14, 9, 1, 0))
    assert [e.text for e in history.read(p)] == ["second", "first"]


def test_keeps_only_the_limit_dropping_oldest(tmp_path: Path):
    p = tmp_path / "history.txt"
    for i in range(history.HISTORY_LIMIT + 3):
        history.append(f"entry {i}", path=p, now=datetime(2026, 8, 14, 9, i, 0))
    texts = [e.text for e in history.read(p)]
    assert len(texts) == history.HISTORY_LIMIT
    assert texts[0] == "entry 7"
    assert texts[-1] == "entry 3"


def test_empty_text_is_ignored(tmp_path: Path):
    p = tmp_path / "history.txt"
    history.append("   \n  ", path=p)
    assert history.read(p) == []
    assert not p.exists()


def test_read_missing_file_returns_empty(tmp_path: Path):
    assert history.read(tmp_path / "nope.txt") == []


def test_read_malformed_file_returns_empty(tmp_path: Path):
    p = tmp_path / "history.txt"
    p.write_text("this file has no delimiters at all\n")
    assert history.read(p) == []


def test_multiline_text_round_trips(tmp_path: Path):
    p = tmp_path / "history.txt"
    history.append("line one\nline two", path=p,
                   now=datetime(2026, 8, 14, 9, 0, 0))
    history.append("later", path=p, now=datetime(2026, 8, 14, 9, 5, 0))
    entries = history.read(p)
    assert entries[0].text == "later"
    assert entries[1].text == "line one\nline two"


def test_append_creates_parent_directory(tmp_path: Path):
    p = tmp_path / "nested" / "deeper" / "history.txt"
    history.append("hello", path=p)
    assert p.exists()


def test_append_leaves_no_temp_file_behind(tmp_path: Path):
    p = tmp_path / "history.txt"
    history.append("hello", path=p)
    assert [f.name for f in tmp_path.iterdir()] == ["history.txt"]


def test_menu_label_truncates_long_text():
    label = history.menu_label("x" * 80, limit=50)
    assert label == "x" * 50 + "…"


def test_menu_label_collapses_newlines():
    assert history.menu_label("line one\nline two") == "line one line two"


def test_menu_label_escapes_ampersand_for_qt():
    assert history.menu_label("Smith & Sons") == "Smith && Sons"
