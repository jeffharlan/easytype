from pathlib import Path

from easytype import config as cfg


def test_load_creates_default_when_missing(tmp_path: Path):
    path = tmp_path / "config.toml"
    c = cfg.load_config(path)
    assert path.exists()
    assert c.capture_mode == "toggle"
    assert c.max_recording_duration == 60
    assert c.record.keys == (29, 57)
    assert c.record.description == "Ctrl+Space"
    assert c.cancel.keys == (1,)
    assert c.repaste.keys == (66,)
    assert c.injection_method == "type"
    assert c.type_delay_ms == 40
    assert c.formatter_enabled is False
    assert c.indicator_position == "top-right"
    assert c.indicator_count == "up"


def test_defaults_round_trip(tmp_path: Path):
    path = tmp_path / "config.toml"
    cfg.load_config(path)  # writes default
    again = cfg.load_config(path)  # reads it back
    assert again.max_recording_duration == 60
    assert again.dictionary == ()


def test_dictionary_entries_parsed(tmp_path: Path):
    path = tmp_path / "config.toml"
    path.write_text(
        'capture_mode = "toggle"\n'
        "[[dictionary]]\n"
        'hears = "ops plus"\n'
        'replace = "OPS+"\n'
        'mode = "smart"\n'
    )
    c = cfg.load_config(path)
    assert len(c.dictionary) == 1
    assert c.dictionary[0].hears == "ops plus"
    assert c.dictionary[0].replace == "OPS+"
    assert c.dictionary[0].mode == "smart"


def test_set_record_hotkey_preserves_file(tmp_path: Path):
    path = tmp_path / "config.toml"
    cfg.load_config(path)
    doc = cfg.load_doc(path)
    cfg.set_hotkey_in_doc(doc, "record", [29, 43], "Ctrl+\\")
    cfg.save_doc(doc, path)
    c = cfg.load_config(path)
    assert c.record.keys == (29, 43)
    assert c.record.description == "Ctrl+\\"


SAMPLE_SETTINGS = {
    "capture_mode": "hold",
    "max_recording_duration": 30,
    "record_keys": [29, 43], "record_description": "Ctrl+\\",
    "cancel_keys": [1], "cancel_description": "Esc",
    "repaste_keys": [66], "repaste_description": "F8",
    "audio_device": "",
    "model": "small.en", "language": "en", "transcribe_device": "cuda",
    "injection_method": "paste", "type_delay_ms": 25,
    "formatter_enabled": True, "formatter_backend": "ollama",
    "ollama_model": "llama3.1", "ollama_url": "http://localhost:11434",
    "indicator_enabled": False, "indicator_position": "bottom-left", "indicator_count": "down",
    "keyboard_device": "",
}


def test_apply_settings_round_trips(tmp_path: Path):
    path = tmp_path / "config.toml"
    cfg.load_config(path)                       # write defaults
    doc = cfg.load_doc(path)
    cfg.apply_settings_to_doc(doc, SAMPLE_SETTINGS)
    cfg.save_doc(doc, path)
    c = cfg.load_config(path)
    assert c.capture_mode == "hold"
    assert c.max_recording_duration == 30
    assert c.model == "small.en"
    assert c.transcribe_device == "cuda"
    assert c.injection_method == "paste"
    assert c.type_delay_ms == 25
    assert c.formatter_enabled is True
    assert c.indicator_enabled is False
    assert c.indicator_position == "bottom-left"
    assert c.indicator_count == "down"
    assert c.record.keys == (29, 43)
    assert c.record.description == "Ctrl+\\"


def test_apply_settings_preserves_comments(tmp_path: Path):
    path = tmp_path / "config.toml"
    cfg.load_config(path)
    doc = cfg.load_doc(path)
    cfg.apply_settings_to_doc(doc, SAMPLE_SETTINGS)
    cfg.save_doc(doc, path)
    text = path.read_text()
    assert "Raw evdev keycodes" in text          # standalone comment line survives
