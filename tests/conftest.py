import pytest

from easytype import history


@pytest.fixture(autouse=True)
def history_file(tmp_path, monkeypatch):
    """Redirect transcript history for every test. Without this, any test that
    drives a Controller through a successful transcription writes to the real
    ~/.local/share/easytype/history.txt."""
    path = tmp_path / "history.txt"
    monkeypatch.setattr(history, "HISTORY_PATH", path)
    return path
