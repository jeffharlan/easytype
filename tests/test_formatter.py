from easytype.config import load_config
from easytype.formatter import format_text


def _cfg(tmp_path, **over):
    path = tmp_path / "c.toml"
    load_config(path)
    from easytype import config as cfg
    doc = cfg.load_doc(path)
    doc["formatter"]["enabled"] = over.get("enabled", False)
    doc["formatter"]["backend"] = over.get("backend", "ollama")
    cfg.save_doc(doc, path)
    return cfg.load_config(path)


def test_disabled_returns_text_unchanged(tmp_path):
    c = _cfg(tmp_path, enabled=False)
    assert format_text("um so like hello", c) == "um so like hello"


def test_unreachable_backend_returns_original(tmp_path, monkeypatch):
    c = _cfg(tmp_path, enabled=True, backend="ollama")

    def boom(*a, **k):
        raise OSError("connection refused")

    monkeypatch.setattr("easytype.formatter._call_ollama", boom)
    assert format_text("raw transcript", c) == "raw transcript"


def test_ollama_result_used(tmp_path, monkeypatch):
    c = _cfg(tmp_path, enabled=True, backend="ollama")
    monkeypatch.setattr("easytype.formatter._call_ollama", lambda text, cfg: "cleaned transcript")
    assert format_text("raw transcript", c) == "cleaned transcript"
