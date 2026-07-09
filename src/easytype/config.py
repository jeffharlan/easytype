from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import tomlkit

DEFAULT_CONFIG_PATH = Path("~/.config/easytype/config.toml").expanduser()

DEFAULT_CONFIG_TOML = """\
capture_mode = "toggle"            # "toggle" | "hold"
max_recording_duration = 60        # seconds — auto-stop safety backstop

[hotkey]
# Record. Raw evdev keycodes for reliability; comment explains them.
keys = [29, 57]                    # Ctrl+Space  (29=KEY_LEFTCTRL, 57=KEY_SPACE)
description = "Ctrl+Space"

[hotkey.cancel]
keys = [1]                         # Esc — only intercepted while recording/transcribing
description = "Esc"

[hotkey.repaste]
keys = [66]                        # F8 — re-inject last transcript
description = "F8"

[audio]
device = ""                        # "" = default mic

[transcription]
model = "small.en"                 # tiny.en | base.en | small.en | medium.en | large-v3 (bigger = more accurate, slower)
language = "en"
device = "auto"                    # auto | cuda | cpu
# Vocabulary hint: bias Whisper toward these spellings at the source. Add your
# proper nouns and jargon here — names, products, acronyms.
initial_prompt = ""

[injection]
method = "type"                    # "type" | "paste"
type_delay_ms = 40                 # ms between simulated keystrokes in type mode (higher = more reliable, slower)

[formatter]
enabled = false
backend = "ollama"                 # "ollama" | "openai"
ollama_model = "llama3.1"
ollama_url = "http://localhost:11434"

[indicator]
enabled = true
position = "top-right"             # top-left | top-center | top-right | bottom-left | bottom-center | bottom-right
count = "up"                       # "up" | "down"

[keyboard]
device = ""                        # "" = auto-detect keyboard device(s)

[media]
pause_while_recording = true       # pause playing media (via playerctl) during capture
"""


@dataclass(frozen=True)
class HotkeySpec:
    keys: tuple[int, ...]
    description: str


@dataclass(frozen=True)
class DictEntry:
    hears: str
    replace: str
    mode: str  # "smart" | "exact"


@dataclass(frozen=True)
class Config:
    capture_mode: str
    max_recording_duration: int
    record: HotkeySpec
    cancel: HotkeySpec
    repaste: HotkeySpec
    audio_device: str
    model: str
    language: str
    transcribe_device: str
    initial_prompt: str
    injection_method: str
    type_delay_ms: int
    formatter_enabled: bool
    formatter_backend: str
    ollama_model: str
    ollama_url: str
    indicator_enabled: bool
    indicator_position: str
    indicator_count: str
    keyboard_device: str
    pause_media_while_recording: bool
    dictionary: tuple[DictEntry, ...]


def load_doc(path: Path = DEFAULT_CONFIG_PATH) -> tomlkit.TOMLDocument:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(DEFAULT_CONFIG_TOML)
    return tomlkit.parse(path.read_text())


def save_doc(doc: tomlkit.TOMLDocument, path: Path = DEFAULT_CONFIG_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(tomlkit.dumps(doc))


def _hotkey(table, default_keys: list[int], default_desc: str) -> HotkeySpec:
    if table is None:
        return HotkeySpec(tuple(default_keys), default_desc)
    keys = tuple(int(k) for k in table.get("keys", default_keys))
    return HotkeySpec(keys, str(table.get("description", default_desc)))


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> Config:
    doc = load_doc(path)
    hk = doc.get("hotkey", {})
    audio = doc.get("audio", {})
    tr = doc.get("transcription", {})
    inj = doc.get("injection", {})
    fmt = doc.get("formatter", {})
    ind = doc.get("indicator", {})
    kbd = doc.get("keyboard", {})
    media = doc.get("media", {})
    entries = tuple(
        DictEntry(str(e["hears"]), str(e["replace"]), str(e.get("mode", "smart")))
        for e in doc.get("dictionary", [])
    )
    return Config(
        capture_mode=str(doc.get("capture_mode", "toggle")),
        max_recording_duration=int(doc.get("max_recording_duration", 60)),
        record=_hotkey(hk, [29, 57], "Ctrl+Space"),
        cancel=_hotkey(hk.get("cancel"), [1], "Esc"),
        repaste=_hotkey(hk.get("repaste"), [66], "F8"),
        audio_device=str(audio.get("device", "")),
        model=str(tr.get("model", "small.en")),
        language=str(tr.get("language", "en")),
        transcribe_device=str(tr.get("device", "auto")),
        initial_prompt=str(tr.get("initial_prompt", "")),
        injection_method=str(inj.get("method", "type")),
        type_delay_ms=int(inj.get("type_delay_ms", 40)),
        formatter_enabled=bool(fmt.get("enabled", False)),
        formatter_backend=str(fmt.get("backend", "ollama")),
        ollama_model=str(fmt.get("ollama_model", "llama3.1")),
        ollama_url=str(fmt.get("ollama_url", "http://localhost:11434")),
        indicator_enabled=bool(ind.get("enabled", True)),
        indicator_position=str(ind.get("position", "top-right")),
        indicator_count=str(ind.get("count", "up")),
        keyboard_device=str(kbd.get("device", "")),
        pause_media_while_recording=bool(media.get("pause_while_recording", True)),
        dictionary=entries,
    )


def _table(doc: tomlkit.TOMLDocument, name: str):
    if name not in doc:
        doc[name] = tomlkit.table()
    return doc[name]


def apply_settings_to_doc(doc: tomlkit.TOMLDocument, values: dict) -> None:
    """Write a flat settings dict into the TOML document, preserving comments.
    Reuses set_hotkey_in_doc for the three hotkeys."""
    doc["capture_mode"] = values["capture_mode"]
    doc["max_recording_duration"] = int(values["max_recording_duration"])

    set_hotkey_in_doc(doc, "record", list(values["record_keys"]), values["record_description"])
    set_hotkey_in_doc(doc, "cancel", list(values["cancel_keys"]), values["cancel_description"])
    set_hotkey_in_doc(doc, "repaste", list(values["repaste_keys"]), values["repaste_description"])

    _table(doc, "audio")["device"] = values["audio_device"]

    tr = _table(doc, "transcription")
    tr["model"] = values["model"]
    tr["language"] = values["language"]
    tr["device"] = values["transcribe_device"]
    tr["initial_prompt"] = values["initial_prompt"]

    inj = _table(doc, "injection")
    inj["method"] = values["injection_method"]
    inj["type_delay_ms"] = int(values["type_delay_ms"])

    fmt = _table(doc, "formatter")
    fmt["enabled"] = bool(values["formatter_enabled"])
    fmt["backend"] = values["formatter_backend"]
    fmt["ollama_model"] = values["ollama_model"]
    fmt["ollama_url"] = values["ollama_url"]

    ind = _table(doc, "indicator")
    ind["enabled"] = bool(values["indicator_enabled"])
    ind["position"] = values["indicator_position"]
    ind["count"] = values["indicator_count"]

    _table(doc, "keyboard")["device"] = values["keyboard_device"]

    _table(doc, "media")["pause_while_recording"] = bool(values["pause_media_while_recording"])


def set_dictionary_in_doc(doc: tomlkit.TOMLDocument, entries: list[tuple[str, str]]) -> None:
    """Replace the [[dictionary]] array-of-tables with (hears, replace) pairs. All
    GUI-added entries use whole-word, case-insensitive ('smart') matching."""
    if "dictionary" in doc:
        del doc["dictionary"]
    if not entries:
        return
    aot = tomlkit.aot()
    for hears, replace in entries:
        item = tomlkit.table()
        item["hears"] = hears
        item["replace"] = replace
        item["mode"] = "smart"
        aot.append(item)
    doc["dictionary"] = aot


def set_hotkey_in_doc(doc: tomlkit.TOMLDocument, name: str, keys: list[int], description: str) -> None:
    if "hotkey" not in doc:
        doc["hotkey"] = tomlkit.table()
    if name == "record":
        target = doc["hotkey"]
    else:
        if name not in doc["hotkey"]:
            doc["hotkey"][name] = tomlkit.table()
        target = doc["hotkey"][name]
    target["keys"] = keys
    target["description"] = description
