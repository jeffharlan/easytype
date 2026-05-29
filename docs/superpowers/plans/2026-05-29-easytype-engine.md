# EasyType Engine (Phase 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a headless, config-driven Linux voice-dictation engine: press a hotkey, speak, and locally-transcribed text is inserted at the cursor — with grab-and-replay hotkey consume, toggle/hold capture, a word-replacement dictionary, and an optional cleanup formatter.

**Architecture:** Four swappable modules (hotkey / recorder / transcriber / injector) plus support modules (config, preflight, dictionary, formatter, indicator). A controller wires them together. The evdev event loop runs on the main thread and never blocks; transcription + injection run on a worker thread; the indicator owns its own Tk thread. Pure logic (config parsing, dictionary, chord matching, command construction, formatter selection) is unit-tested with TDD; hardware-bound pieces (mic, model, evdev, Tk window) are verified at manual checkpoints.

**Tech Stack:** Python 3.11+, sounddevice (PortAudio), faster-whisper, python-evdev (+ uinput), numpy, tomlkit, Tkinter, xdotool/xclip, stdlib urllib for the formatter. Tests: pytest.

**Reference spec:** `docs/superpowers/specs/2026-05-29-easytype-design.md`

---

## File Structure

```
easytype/
├── pyproject.toml                 # packaging + deps + `easytype` console script
├── README.md                      # what it is, deps, permissions, config, troubleshooting
├── LICENSE                        # MIT
├── .gitignore
├── config.sample.toml             # annotated sample config
├── systemd/easytype.service       # optional user service
├── src/easytype/
│   ├── __init__.py                # version
│   ├── __main__.py                # `python -m easytype` → cli.main
│   ├── cli.py                     # arg parsing: --passive, --check, --set-hotkey
│   ├── config.py                  # load/save TOML (tomlkit), Config dataclass
│   ├── preflight.py               # session detect + permission/binary checks + fix text
│   ├── chords.py                  # PURE chord-matching/consume engine (no evdev import)
│   ├── keycodes.py                # evdev keycode name⇄int helpers for --set-hotkey
│   ├── dictionary.py              # smart/exact word replacement
│   ├── formatter.py               # optional Ollama/OpenAI cleanup, graceful skip
│   ├── recorder.py                # sounddevice → in-memory float32 buffer
│   ├── transcriber.py             # faster-whisper wrapper + device resolution
│   ├── indicator.py               # focus-safe Tk timer pill + Null fallback + helpers
│   ├── listener.py                # evdev device discovery + grab-and-replay loop
│   ├── controller.py              # state machine, threads, wires everything
│   └── injector/
│       ├── __init__.py            # Injector protocol + get_injector()
│       └── x11.py                 # X11Injector (type / paste) + command builders
└── tests/
    ├── test_config.py
    ├── test_dictionary.py
    ├── test_preflight.py
    ├── test_chords.py
    ├── test_keycodes.py
    ├── test_injector_x11.py
    ├── test_formatter.py
    ├── test_indicator.py
    └── test_controller.py
```

**Import discipline:** `recorder.py`, `transcriber.py`, `listener.py`, `indicator.py` must import their heavy/hardware libraries (`sounddevice`, `faster_whisper`, `evdev`, `tkinter`) **inside functions/methods**, never at module top — so the pure modules and their tests run without those libraries installed.

---

## Task 1: Project scaffold

**Files:**
- Create: `pyproject.toml`, `src/easytype/__init__.py`, `src/easytype/__main__.py`, `src/easytype/cli.py`, `.gitignore`, `tests/__init__.py`

- [ ] **Step 1: Create `.gitignore`**

```gitignore
__pycache__/
*.pyc
.venv/
venv/
*.egg-info/
.pytest_cache/
dist/
build/
```

- [ ] **Step 2: Create `pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "easytype"
version = "0.1.0"
description = "System-wide local voice dictation for Linux (push-to-talk and toggle)"
readme = "README.md"
license = { text = "MIT" }
requires-python = ">=3.11"
dependencies = [
    "sounddevice>=0.4",
    "faster-whisper>=1.0",
    "evdev>=1.6",
    "numpy>=1.24",
    "tomlkit>=0.12",
]

[project.optional-dependencies]
dev = ["pytest>=8"]

[project.scripts]
easytype = "easytype.cli:main"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
```

- [ ] **Step 3: Create package files**

`src/easytype/__init__.py`:
```python
__version__ = "0.1.0"
```

`src/easytype/__main__.py`:
```python
from easytype.cli import main

if __name__ == "__main__":
    main()
```

`src/easytype/cli.py` (placeholder wiring; fleshed out in Task 13):
```python
import argparse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="easytype", description="Local voice dictation for Linux")
    parser.add_argument("--passive", action="store_true", help="Run without grabbing the keyboard")
    parser.add_argument("--check", action="store_true", help="Run preflight checks and exit")
    parser.add_argument(
        "--set-hotkey", nargs="?", const="record", choices=["record", "cancel", "repaste"],
        help="Interactively capture a hotkey, then save it",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    print(f"easytype: parsed args = {args}")  # replaced in Task 13


if __name__ == "__main__":
    main()
```

`tests/__init__.py`: (empty file)

- [ ] **Step 4: Create venv and install**

Run:
```bash
cd /home/jefferey/local-git/easytype
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```
Expected: install completes (faster-whisper pulls ctranslate2; this may take a minute).

- [ ] **Step 5: Verify the console command and pytest both work**

Run:
```bash
.venv/bin/easytype --help
.venv/bin/pytest -q
```
Expected: `--help` prints usage with `--passive/--check/--set-hotkey`; pytest reports "no tests ran" (exit 0 or 5 — fine, no tests yet).

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "chore: scaffold easytype package, packaging, and CLI skeleton"
```

---

## Task 2: Config module

**Files:**
- Create: `src/easytype/config.py`, `tests/test_config.py`

- [ ] **Step 1: Write failing tests**

`tests/test_config.py`:
```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_config.py -q`
Expected: FAIL (module has no `load_config`).

- [ ] **Step 3: Implement `src/easytype/config.py`**

```python
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
model = "base.en"
language = "en"
device = "auto"                    # auto | cuda | cpu

[injection]
method = "type"                    # "type" | "paste"

[formatter]
enabled = false
backend = "ollama"                 # "ollama" | "openai"
ollama_model = "llama3.1"
ollama_url = "http://localhost:11434"

[indicator]
enabled = true
position = "top-right"             # top-right | top-center | bottom-right | bottom-left | top-left
count = "up"                       # "up" | "down"

[keyboard]
device = ""                        # "" = auto-detect keyboard device(s)
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
    injection_method: str
    formatter_enabled: bool
    formatter_backend: str
    ollama_model: str
    ollama_url: str
    indicator_enabled: bool
    indicator_position: str
    indicator_count: str
    keyboard_device: str
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
        model=str(tr.get("model", "base.en")),
        language=str(tr.get("language", "en")),
        transcribe_device=str(tr.get("device", "auto")),
        injection_method=str(inj.get("method", "type")),
        formatter_enabled=bool(fmt.get("enabled", False)),
        formatter_backend=str(fmt.get("backend", "ollama")),
        ollama_model=str(fmt.get("ollama_model", "llama3.1")),
        ollama_url=str(fmt.get("ollama_url", "http://localhost:11434")),
        indicator_enabled=bool(ind.get("enabled", True)),
        indicator_position=str(ind.get("position", "top-right")),
        indicator_count=str(ind.get("count", "up")),
        keyboard_device=str(kbd.get("device", "")),
        dictionary=entries,
    )


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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_config.py -q`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add src/easytype/config.py tests/test_config.py
git commit -m "feat: config load/save with annotated TOML defaults"
```

---

## Task 3: Dictionary (word replacement)

**Files:**
- Create: `src/easytype/dictionary.py`, `tests/test_dictionary.py`

- [ ] **Step 1: Write failing tests**

`tests/test_dictionary.py`:
```python
from easytype.config import DictEntry
from easytype.dictionary import apply_dictionary


def test_smart_is_case_insensitive_and_whole_word():
    entries = [DictEntry("ops plus", "OPS+", "smart")]
    assert apply_dictionary("Check Ops Plus today", entries) == "Check OPS+ today"


def test_smart_does_not_match_inside_word():
    entries = [DictEntry("main", "MAIN", "smart")]
    assert apply_dictionary("remainder", entries) == "remainder"


def test_exact_is_literal_and_case_sensitive():
    entries = [DictEntry("see see", "Claude Code", "exact")]
    assert apply_dictionary("run see see now", entries) == "run Claude Code now"
    assert apply_dictionary("run SEE SEE now", entries) == "run SEE SEE now"


def test_replacement_with_special_chars_is_literal():
    entries = [DictEntry("slash", "/", "smart")]
    assert apply_dictionary("type slash here", entries) == "type / here"


def test_entries_apply_in_order():
    entries = [DictEntry("claw dot md", "claude.md", "smart"), DictEntry("md", "MD", "exact")]
    # "claw dot md" → "claude.md", then exact "md" → "MD" inside it
    assert apply_dictionary("open claw dot md", entries) == "open claude.MD"


def test_no_entries_returns_input():
    assert apply_dictionary("nothing changes", []) == "nothing changes"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_dictionary.py -q`
Expected: FAIL (no `apply_dictionary`).

- [ ] **Step 3: Implement `src/easytype/dictionary.py`**

```python
from __future__ import annotations

import re
from collections.abc import Sequence

from easytype.config import DictEntry


def apply_dictionary(text: str, entries: Sequence[DictEntry]) -> str:
    for entry in entries:
        if entry.mode == "exact":
            text = text.replace(entry.hears, entry.replace)
        else:  # smart: whole-word, case-insensitive
            pattern = r"\b" + re.escape(entry.hears) + r"\b"
            text = re.sub(pattern, lambda _m, r=entry.replace: r, text, flags=re.IGNORECASE)
    return text
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_dictionary.py -q`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add src/easytype/dictionary.py tests/test_dictionary.py
git commit -m "feat: smart/exact word-replacement dictionary"
```

---

## Task 4: Preflight checks + session detection

**Files:**
- Create: `src/easytype/preflight.py`, `tests/test_preflight.py`

- [ ] **Step 1: Write failing tests**

`tests/test_preflight.py`:
```python
from easytype.preflight import Issue, detect_session, gather_issues, format_report


def test_detect_session_x11(monkeypatch):
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    assert detect_session() == "x11"


def test_detect_session_wayland(monkeypatch):
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    assert detect_session() == "wayland"


def test_all_ok_yields_no_failures():
    issues = gather_issues(
        groups=["input"], uinput_writable=True,
        binaries={"xdotool": True, "xclip": True, "notify-send": True}, tk_ok=True,
    )
    assert all(i.ok for i in issues)


def test_missing_input_group_reports_usermod_fix():
    issues = gather_issues(
        groups=["users"], uinput_writable=True,
        binaries={"xdotool": True, "xclip": True, "notify-send": True}, tk_ok=True,
    )
    group_issue = next(i for i in issues if i.name == "input group")
    assert not group_issue.ok
    assert "usermod -aG input" in group_issue.fix


def test_missing_uinput_reports_udev_rule():
    issues = gather_issues(
        groups=["input"], uinput_writable=False,
        binaries={"xdotool": True, "xclip": True, "notify-send": True}, tk_ok=True,
    )
    u = next(i for i in issues if i.name == "/dev/uinput access")
    assert not u.ok
    assert "uinput" in u.fix


def test_missing_binary_reported():
    issues = gather_issues(
        groups=["input"], uinput_writable=True,
        binaries={"xdotool": False, "xclip": True, "notify-send": True}, tk_ok=True,
    )
    x = next(i for i in issues if i.name == "xdotool")
    assert not x.ok
    assert "apt install" in x.fix


def test_format_report_marks_pass_and_fail():
    issues = [Issue("a", True, ""), Issue("b", False, "do this")]
    report = format_report(issues)
    assert "do this" in report
    assert "b" in report
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_preflight.py -q`
Expected: FAIL (no `preflight` symbols).

- [ ] **Step 3: Implement `src/easytype/preflight.py`**

```python
from __future__ import annotations

import grp
import os
import shutil
from dataclasses import dataclass

REQUIRED_BINARIES = ("xdotool", "xclip", "notify-send")


@dataclass(frozen=True)
class Issue:
    name: str
    ok: bool
    fix: str


def detect_session() -> str:
    if os.environ.get("WAYLAND_DISPLAY") or os.environ.get("XDG_SESSION_TYPE") == "wayland":
        return "wayland"
    if os.environ.get("XDG_SESSION_TYPE") == "x11" or os.environ.get("DISPLAY"):
        return "x11"
    return "unknown"


def gather_issues(*, groups, uinput_writable, binaries, tk_ok) -> list[Issue]:
    issues: list[Issue] = []
    issues.append(Issue(
        "input group", "input" in groups,
        "Add yourself to the 'input' group, then log out and back in:\n"
        "    sudo usermod -aG input $USER",
    ))
    issues.append(Issue(
        "/dev/uinput access", uinput_writable,
        "Allow access to /dev/uinput via a udev rule, then reload:\n"
        "    echo 'KERNEL==\"uinput\", GROUP=\"input\", MODE=\"0660\"' "
        "| sudo tee /etc/udev/rules.d/99-easytype-uinput.rules\n"
        "    sudo modprobe uinput\n"
        "    sudo udevadm control --reload-rules && sudo udevadm trigger",
    ))
    for name in REQUIRED_BINARIES:
        issues.append(Issue(
            name, binaries.get(name, False),
            f"Install {name}:\n    sudo apt install {name}",
        ))
    issues.append(Issue(
        "python3-tk (recording indicator)", tk_ok,
        "Install Tkinter for the on-screen timer (optional — falls back to notifications):\n"
        "    sudo apt install python3-tk",
    ))
    return issues


def _current_groups() -> list[str]:
    names = {g.gr_name for g in grp.getgrall() if os.getgid() in (g.gr_gid,) or os.getuid() in g.gr_mem}
    try:
        names.update(grp.getgrgid(gid).gr_name for gid in os.getgroups())
    except OSError:
        pass
    return list(names)


def _uinput_writable() -> bool:
    return os.access("/dev/uinput", os.W_OK)


def _tk_available() -> bool:
    try:
        import tkinter  # noqa: F401
        return True
    except Exception:
        return False


def check() -> list[Issue]:
    return gather_issues(
        groups=_current_groups(),
        uinput_writable=_uinput_writable(),
        binaries={b: shutil.which(b) is not None for b in REQUIRED_BINARIES},
        tk_ok=_tk_available(),
    )


def format_report(issues: list[Issue]) -> str:
    lines = ["EasyType preflight:\n"]
    for i in issues:
        mark = "OK  " if i.ok else "FAIL"
        lines.append(f"  [{mark}] {i.name}")
        if not i.ok:
            for fixline in i.fix.splitlines():
                lines.append(f"         {fixline}")
    blocking = [i for i in issues if not i.ok and i.name != "python3-tk (recording indicator)"]
    if blocking:
        lines.append("\nGrab mode needs the FAIL items above. Until then, run with --passive.")
    else:
        lines.append("\nAll required checks passed.")
    return "\n".join(lines)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_preflight.py -q`
Expected: PASS (8 tests).

- [ ] **Step 5: Commit**

```bash
git add src/easytype/preflight.py tests/test_preflight.py
git commit -m "feat: preflight checks with exact fix commands and session detection"
```

---

## Task 5: Chord-matching / consume engine (pure)

**Files:**
- Create: `src/easytype/chords.py`, `tests/test_chords.py`

This is the heart of the consume logic, kept free of evdev so it's fully unit-testable. Event `value`: 1=down, 2=repeat, 0=up.

- [ ] **Step 1: Write failing tests**

`tests/test_chords.py`:
```python
from easytype.chords import HotkeyEngine, trigger_key

KEY_LEFTCTRL, KEY_SPACE, KEY_ESC, KEY_F8, KEY_BACKSLASH, KEY_A, KEY_RIGHTCTRL = 29, 57, 1, 66, 43, 30, 97


def test_trigger_is_non_modifier():
    assert trigger_key((KEY_LEFTCTRL, KEY_SPACE)) == KEY_SPACE
    assert trigger_key((KEY_BACKSLASH, KEY_LEFTCTRL)) == KEY_BACKSLASH


def test_trigger_all_modifiers_is_last():
    assert trigger_key((KEY_RIGHTCTRL,)) == KEY_RIGHTCTRL


def make_engine():
    return HotkeyEngine({"record": (KEY_LEFTCTRL, KEY_SPACE), "cancel": (KEY_ESC,), "repaste": (KEY_F8,)})


def test_ctrl_space_fires_and_swallows_only_space():
    eng = make_engine()
    enabled = {"record", "cancel", "repaste"}
    o1 = eng.feed(KEY_LEFTCTRL, 1, enabled)   # ctrl down → forwarded
    assert o1.swallow is False and o1.pressed is None
    o2 = eng.feed(KEY_SPACE, 1, enabled)      # space down while ctrl held → fire+swallow
    assert o2.swallow is True and o2.pressed == "record"
    o3 = eng.feed(KEY_SPACE, 0, enabled)      # space up → swallowed (no leak)
    assert o3.swallow is True
    o4 = eng.feed(KEY_LEFTCTRL, 0, enabled)   # ctrl up → forwarded
    assert o4.swallow is False


def test_lone_keys_pass_through():
    eng = make_engine()
    enabled = {"record", "cancel", "repaste"}
    assert eng.feed(KEY_A, 1, enabled).swallow is False
    assert eng.feed(KEY_A, 0, enabled).swallow is False


def test_space_without_ctrl_does_not_fire():
    eng = make_engine()
    enabled = {"record", "cancel", "repaste"}
    o = eng.feed(KEY_SPACE, 1, enabled)
    assert o.swallow is False and o.pressed is None


def test_cancel_only_active_when_enabled():
    eng = make_engine()
    # cancel NOT enabled → Esc passes through, no fire
    o = eng.feed(KEY_ESC, 1, {"record", "repaste"})
    assert o.swallow is False and o.pressed is None
    eng.feed(KEY_ESC, 0, {"record", "repaste"})
    # cancel enabled → Esc fires and is swallowed
    o2 = eng.feed(KEY_ESC, 1, {"record", "cancel", "repaste"})
    assert o2.swallow is True and o2.pressed == "cancel"


def test_hold_release_reported():
    eng = make_engine()
    enabled = {"record", "cancel", "repaste"}
    eng.feed(KEY_LEFTCTRL, 1, enabled)
    eng.feed(KEY_SPACE, 1, enabled)
    out = eng.feed(KEY_SPACE, 0, enabled)
    assert out.released == "record"


def test_repeat_of_swallowed_trigger_is_swallowed():
    eng = make_engine()
    enabled = {"record", "cancel", "repaste"}
    eng.feed(KEY_LEFTCTRL, 1, enabled)
    eng.feed(KEY_SPACE, 1, enabled)
    out = eng.feed(KEY_SPACE, 2, enabled)  # autorepeat
    assert out.swallow is True and out.pressed is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_chords.py -q`
Expected: FAIL (no `chords` symbols).

- [ ] **Step 3: Implement `src/easytype/chords.py`**

```python
from __future__ import annotations

from dataclasses import dataclass

# evdev modifier keycodes
MODIFIERS = frozenset({29, 97, 56, 100, 42, 54, 125, 126})
# 29=LCTRL 97=RCTRL 56=LALT 100=RALT 42=LSHIFT 54=RSHIFT 125=LMETA 126=RMETA


def trigger_key(chord: tuple[int, ...]) -> int:
    non_mods = [k for k in chord if k not in MODIFIERS]
    return non_mods[-1] if non_mods else chord[-1]


@dataclass(frozen=True)
class KeyOutcome:
    swallow: bool
    pressed: str | None = None   # chord name whose trigger just went down (mods held)
    released: str | None = None  # chord name whose trigger just went up


class HotkeyEngine:
    """Pure consume/match engine. Feed raw key events; get swallow + fire decisions."""

    def __init__(self, chords: dict[str, tuple[int, ...]]):
        self._chords = {name: tuple(keys) for name, keys in chords.items()}
        self._triggers = {name: trigger_key(keys) for name, keys in self._chords.items()}
        self._held: set[int] = set()
        self._swallowed: set[int] = set()      # trigger codes we are actively swallowing
        self._active: dict[int, str] = {}       # trigger code -> chord name currently firing

    def _fire_candidate(self, code: int, enabled: set[str]) -> str | None:
        for name, chord in self._chords.items():
            if name not in enabled:
                continue
            if self._triggers[name] != code:
                continue
            others = set(chord) - {code}
            if others <= self._held:
                return name
        return None

    def feed(self, code: int, value: int, enabled: set[str]) -> KeyOutcome:
        if value == 1:  # key down
            name = self._fire_candidate(code, enabled)
            if name is not None:
                self._swallowed.add(code)
                self._active[code] = name
                self._held.add(code)
                return KeyOutcome(swallow=True, pressed=name)
            self._held.add(code)
            return KeyOutcome(swallow=False)
        if value == 2:  # autorepeat
            return KeyOutcome(swallow=code in self._swallowed)
        # value == 0: key up
        self._held.discard(code)
        if code in self._swallowed:
            self._swallowed.discard(code)
            name = self._active.pop(code, None)
            return KeyOutcome(swallow=True, released=name)
        return KeyOutcome(swallow=False)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_chords.py -q`
Expected: PASS (9 tests).

- [ ] **Step 5: Commit**

```bash
git add src/easytype/chords.py tests/test_chords.py
git commit -m "feat: pure chord-matching and consume engine"
```

---

## Task 6: Keycode helpers (for --set-hotkey + conflicts table)

**Files:**
- Create: `src/easytype/keycodes.py`, `tests/test_keycodes.py`

- [ ] **Step 1: Write failing tests**

`tests/test_keycodes.py`:
```python
from easytype.keycodes import describe_chord, conflict_note


def test_describe_chord_ctrl_space():
    assert describe_chord([29, 57]) == "Ctrl+Space"


def test_describe_chord_ctrl_backslash():
    assert describe_chord([29, 43]) == "Ctrl+\\"


def test_describe_chord_single_key():
    assert describe_chord([66]) == "F8"


def test_conflict_note_ctrl_space_mentions_ibus():
    note = conflict_note([29, 57])
    assert note is not None and "IBus" in note


def test_conflict_note_ctrl_backslash_mentions_sigquit():
    note = conflict_note([29, 43])
    assert note is not None and "SIGQUIT" in note


def test_conflict_note_none_for_unknown():
    assert conflict_note([66]) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_keycodes.py -q`
Expected: FAIL.

- [ ] **Step 3: Implement `src/easytype/keycodes.py`**

```python
from __future__ import annotations

# Friendly names for the keys we expect in hotkeys; falls back to evdev's KEY_ name.
_FRIENDLY = {
    29: "Ctrl", 97: "Ctrl", 56: "Alt", 100: "Alt", 42: "Shift", 54: "Shift",
    125: "Super", 126: "Super", 57: "Space", 1: "Esc", 43: "\\",
    66: "F8", 67: "F9", 100: "AltGr",
}

# Informational only: chord (sorted) -> human note. Never used to block.
_CONFLICTS = {
    (29, 57): "Ctrl+Space normally toggles the IBus input method. EasyType's consume "
              "feature swallows it, so the toggle won't fire while EasyType runs.",
    (29, 43): "Ctrl+\\ normally sends SIGQUIT in a terminal. EasyType's consume feature "
              "swallows it, so no SIGQUIT will fire while EasyType runs.",
}


def _name(code: int) -> str:
    if code in _FRIENDLY:
        return _FRIENDLY[code]
    try:
        from evdev import ecodes
        raw = ecodes.KEY[code]
        label = raw[0] if isinstance(raw, list) else raw
        return label.replace("KEY_", "").title()
    except Exception:
        return f"key{code}"


def describe_chord(keys: list[int]) -> str:
    return "+".join(_name(k) for k in keys)


def conflict_note(keys: list[int]) -> str | None:
    return _CONFLICTS.get(tuple(sorted(keys)))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_keycodes.py -q`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add src/easytype/keycodes.py tests/test_keycodes.py
git commit -m "feat: keycode descriptions and informational conflicts table"
```

---

## Task 7: X11 injector

**Files:**
- Create: `src/easytype/injector/__init__.py`, `src/easytype/injector/x11.py`, `tests/test_injector_x11.py`

- [ ] **Step 1: Write failing tests**

`tests/test_injector_x11.py`:
```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_injector_x11.py -q`
Expected: FAIL.

- [ ] **Step 3: Implement injector**

`src/easytype/injector/__init__.py`:
```python
from __future__ import annotations

from typing import Protocol


class Injector(Protocol):
    def inject(self, text: str, method: str) -> None: ...


def get_injector(session: str) -> Injector:
    if session == "wayland":
        raise NotImplementedError(
            "Wayland injector is not implemented in Phase 1. Run on X11, "
            "or use --passive and copy text manually."
        )
    from easytype.injector.x11 import X11Injector
    return X11Injector()
```

`src/easytype/injector/x11.py`:
```python
from __future__ import annotations

import subprocess
import time

CLIP = ["xclip", "-selection", "clipboard"]


def type_command(text: str, delay_ms: int) -> list[str]:
    return ["xdotool", "type", "--clearmodifiers", "--delay", str(delay_ms), "--", text]


def paste_key_command() -> list[str]:
    return ["xdotool", "key", "--clearmodifiers", "ctrl+v"]


class X11Injector:
    def __init__(self, type_delay_ms: int = 12):
        self._delay = type_delay_ms

    def inject(self, text: str, method: str) -> None:
        if not text:
            return
        if method == "paste":
            self._paste(text)
        else:
            subprocess.run(type_command(text, self._delay), check=True)

    def _paste(self, text: str) -> None:
        saved = self._read_clipboard()
        subprocess.run(CLIP, input=text.encode(), check=True)
        subprocess.run(paste_key_command(), check=True)
        time.sleep(0.1)  # let the target app consume the paste before we restore
        if saved is not None:
            subprocess.run(CLIP, input=saved, check=False)

    @staticmethod
    def _read_clipboard() -> bytes | None:
        try:
            r = subprocess.run([*CLIP, "-o"], capture_output=True, timeout=1)
            return r.stdout if r.returncode == 0 else None
        except Exception:
            return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_injector_x11.py -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Manual checkpoint — inject into a real editor**

Run:
```bash
.venv/bin/python -c "from easytype.injector.x11 import X11Injector; X11Injector().inject('hello from easytype', 'type')"
```
Click into a text editor within the 1–2s and re-run if needed (or wrap in a `sleep`). Expected: "hello from easytype" appears. Repeat with `'paste'` and confirm your clipboard is restored afterward.

- [ ] **Step 6: Commit**

```bash
git add src/easytype/injector tests/test_injector_x11.py
git commit -m "feat: X11 injector with type and clipboard-preserving paste"
```

---

## Task 8: Formatter (optional cleanup)

**Files:**
- Create: `src/easytype/formatter.py`, `tests/test_formatter.py`

- [ ] **Step 1: Write failing tests**

`tests/test_formatter.py`:
```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_formatter.py -q`
Expected: FAIL.

- [ ] **Step 3: Implement `src/easytype/formatter.py`**

```python
from __future__ import annotations

import json
import os
import urllib.request

from easytype.config import Config

PROMPT = (
    "Clean up this dictated text: remove filler words (um, uh, like), resolve spoken "
    "self-corrections, and fix punctuation. Preserve meaning and wording otherwise. "
    "Return ONLY the cleaned text.\n\nText:\n"
)


def format_text(text: str, config: Config) -> str:
    if not config.formatter_enabled or not text.strip():
        return text
    try:
        if config.formatter_backend == "openai":
            return _call_openai(text, config) or text
        return _call_ollama(text, config) or text
    except Exception:
        return text  # never lose the transcript over a cleanup failure


def _call_ollama(text: str, config: Config) -> str:
    payload = json.dumps({
        "model": config.ollama_model,
        "prompt": PROMPT + text,
        "stream": False,
    }).encode()
    req = urllib.request.Request(
        f"{config.ollama_url}/api/generate", data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())["response"].strip()


def _call_openai(text: str, config: Config) -> str:
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        return ""
    payload = json.dumps({
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": PROMPT + text}],
    }).encode()
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions", data=payload,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())["choices"][0]["message"]["content"].strip()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_formatter.py -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add src/easytype/formatter.py tests/test_formatter.py
git commit -m "feat: optional Ollama/OpenAI formatter with graceful skip"
```

---

## Task 9: Recording indicator (timer pill)

**Files:**
- Create: `src/easytype/indicator.py`, `tests/test_indicator.py`

- [ ] **Step 1: Write failing tests**

`tests/test_indicator.py`:
```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_indicator.py -q`
Expected: FAIL.

- [ ] **Step 3: Implement `src/easytype/indicator.py`**

```python
from __future__ import annotations

import threading

from easytype.config import Config

WARN_WINDOW_S = 5


def format_elapsed(seconds: int) -> str:
    return f"{seconds // 60}:{seconds % 60:02d}"


def should_warn(elapsed: int, cap: int) -> bool:
    return cap > 0 and elapsed >= cap - WARN_WINDOW_S


def _tk_available() -> bool:
    try:
        import tkinter  # noqa: F401
        return True
    except Exception:
        return False


class NullIndicator:
    is_null = True

    def start(self, cap: int) -> None: ...
    def stop(self) -> None: ...


class TkIndicator:
    is_null = False

    def __init__(self, position: str, count: str):
        self._position = position
        self._count = count
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._cap = 0

    def start(self, cap: int) -> None:
        self._cap = cap
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1)
            self._thread = None

    def _geometry(self, root, w: int, h: int) -> str:
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        m = 24
        pos = {
            "top-right": (sw - w - m, m), "top-left": (m, m),
            "top-center": ((sw - w) // 2, m),
            "bottom-right": (sw - w - m, sh - h - m * 2),
            "bottom-left": (m, sh - h - m * 2),
        }.get(self._position, (sw - w - m, m))
        return f"{w}x{h}+{pos[0]}+{pos[1]}"

    def _run(self) -> None:
        import tkinter as tk

        root = tk.Tk()
        root.overrideredirect(True)          # borderless, no titlebar
        root.attributes("-topmost", True)
        try:
            root.wm_attributes("-type", "splash")  # never take focus / taskbar (X11)
        except tk.TclError:
            pass
        root.geometry(self._geometry(root, 150, 44))
        label = tk.Label(root, font=("sans", 14, "bold"), fg="white", bg="#111111", padx=12, pady=8)
        label.pack(fill="both", expand=True)

        elapsed = {"s": 0}

        def tick():
            if self._stop.is_set():
                root.destroy()
                return
            s = elapsed["s"]
            shown = s if self._count == "up" else max(0, self._cap - s)
            warn = should_warn(s, self._cap)
            label.config(text=f"● REC  {format_elapsed(shown)}",
                         fg=("#ffb000" if warn else "white"))
            elapsed["s"] += 1
            root.after(1000, tick)

        tick()
        root.mainloop()


def create_indicator(config: Config):
    if not config.indicator_enabled or not _tk_available():
        return NullIndicator()
    return TkIndicator(config.indicator_position, config.indicator_count)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_indicator.py -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Manual checkpoint — see the pill**

Run:
```bash
.venv/bin/python -c "import time; from easytype.config import load_config; from easytype.indicator import create_indicator; \
c=load_config(); i=create_indicator(c); i.start(10); time.sleep(8); i.stop()"
```
Expected: a `● REC 0:00…` pill appears top-right, counts up, turns amber near 0:10, vanishes on stop. Confirm clicking other windows still works while it's shown (it must not steal focus).

- [ ] **Step 6: Commit**

```bash
git add src/easytype/indicator.py tests/test_indicator.py
git commit -m "feat: focus-safe Tk recording indicator with Null fallback"
```

---

## Task 10: Recorder

**Files:**
- Create: `src/easytype/recorder.py`

Hardware-bound (microphone) — implementation + manual checkpoint.

- [ ] **Step 1: Implement `src/easytype/recorder.py`**

```python
from __future__ import annotations

import numpy as np

SAMPLE_RATE = 16000  # whisper-friendly


class Recorder:
    def __init__(self, device: str = "", sample_rate: int = SAMPLE_RATE):
        self._device = device or None
        self._sr = sample_rate
        self._stream = None
        self._frames: list[np.ndarray] = []

    def start(self) -> None:
        import sounddevice as sd

        self._frames = []

        def callback(indata, frames, time_info, status):
            self._frames.append(indata.copy())

        self._stream = sd.InputStream(
            samplerate=self._sr, channels=1, dtype="float32",
            device=self._device, callback=callback,
        )
        self._stream.start()

    def stop(self) -> np.ndarray:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        if not self._frames:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(self._frames, axis=0).flatten()
```

- [ ] **Step 2: Manual checkpoint — record and play back**

Run:
```bash
.venv/bin/python -c "import time, numpy as np, soundfile as sf; \
from easytype.recorder import Recorder, SAMPLE_RATE; \
r=Recorder(); r.start(); print('speak for 3s...'); time.sleep(3); a=r.stop(); \
sf.write('/tmp/easytype_test.wav', a, SAMPLE_RATE); print('samples:', a.shape)" 2>/dev/null \
|| echo "If soundfile missing: .venv/bin/pip install soundfile"
aplay /tmp/easytype_test.wav
```
Expected: prints a non-zero sample count and you hear your 3 seconds played back. (`soundfile` is only for this manual check, not a runtime dep.)

- [ ] **Step 3: Commit**

```bash
git add src/easytype/recorder.py
git commit -m "feat: in-memory microphone recorder (sounddevice)"
```

---

## Task 11: Transcriber

**Files:**
- Create: `src/easytype/transcriber.py`, add a test to `tests/test_transcriber.py`

- [ ] **Step 1: Write failing test (device resolution is pure)**

`tests/test_transcriber.py`:
```python
from easytype.transcriber import resolve_compute_type


def test_compute_type_cpu():
    assert resolve_compute_type("cpu") == "int8"


def test_compute_type_cuda():
    assert resolve_compute_type("cuda") == "float16"


def test_compute_type_auto():
    assert resolve_compute_type("auto") == "default"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_transcriber.py -q`
Expected: FAIL.

- [ ] **Step 3: Implement `src/easytype/transcriber.py`**

```python
from __future__ import annotations

import numpy as np


def resolve_compute_type(device: str) -> str:
    return {"cpu": "int8", "cuda": "float16"}.get(device, "default")


class Transcriber:
    def __init__(self, model: str = "base.en", language: str = "en", device: str = "auto"):
        self._model_name = model
        self._language = language
        self._device = device
        self._model = None

    def _ensure_model(self):
        if self._model is None:
            from faster_whisper import WhisperModel
            self._model = WhisperModel(
                self._model_name, device=self._device,
                compute_type=resolve_compute_type(self._device),
            )
        return self._model

    def transcribe(self, audio: np.ndarray) -> str:
        if audio.size == 0:
            return ""
        model = self._ensure_model()
        segments, _info = model.transcribe(audio, language=self._language, beam_size=5)
        return "".join(seg.text for seg in segments).strip()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_transcriber.py -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Manual checkpoint — transcribe the recorded clip**

Run:
```bash
.venv/bin/python -c "import soundfile as sf; from easytype.transcriber import Transcriber; \
a,_=sf.read('/tmp/easytype_test.wav', dtype='float32'); \
print('TEXT:', Transcriber().transcribe(a))"
```
Expected: first run downloads the `base.en` model, then prints the text of what you said. (Confirms GPU/CPU auto-selection works.)

- [ ] **Step 6: Commit**

```bash
git add src/easytype/transcriber.py tests/test_transcriber.py
git commit -m "feat: faster-whisper transcriber with auto device selection"
```

---

## Task 12: evdev listener (passive + grab-and-replay)

**Files:**
- Create: `src/easytype/listener.py`

Hardware-bound — implementation + manual checkpoints 4 & 5. The pure decision logic lives in `chords.py` (already tested); this module is the evdev plumbing around it.

- [ ] **Step 1: Implement `src/easytype/listener.py`**

```python
from __future__ import annotations

import selectors
from collections.abc import Callable

from easytype.chords import HotkeyEngine


def find_keyboards() -> list:
    """Devices that look like real keyboards (have letter keys)."""
    from evdev import InputDevice, ecodes, list_devices

    keyboards = []
    for path in list_devices():
        try:
            dev = InputDevice(path)
        except Exception:
            continue
        keys = dev.capabilities().get(ecodes.EV_KEY, [])
        if ecodes.KEY_A in keys and ecodes.KEY_Z in keys:
            keyboards.append(dev)
        else:
            dev.close()
    return keyboards


def open_devices(device_override: str) -> list:
    if device_override:
        from evdev import InputDevice
        return [InputDevice(device_override)]
    devices = find_keyboards()
    if not devices:
        raise RuntimeError("No keyboard device found. Set [keyboard] device in config.")
    return devices


class Listener:
    """Reads evdev devices, runs the HotkeyEngine, and (in grab mode) replays
    every non-swallowed event through a uinput virtual keyboard."""

    def __init__(self, engine: HotkeyEngine, enabled_provider: Callable[[], set[str]],
                 on_event: Callable[[object], None]):
        self._engine = engine
        self._enabled = enabled_provider
        self._on_event = on_event
        self._devices: list = []
        self._ui = None
        self._grabbed = False

    def run(self, *, device_override: str = "", grab: bool = True) -> None:
        from evdev import UInput, ecodes

        self._devices = open_devices(device_override)
        try:
            if grab:
                self._ui = UInput.from_device(*self._devices, name="easytype-virtual-kbd")
                for d in self._devices:
                    d.grab()
                self._grabbed = True
            self._loop(ecodes)
        finally:
            self.cleanup()

    def _loop(self, ecodes) -> None:
        sel = selectors.DefaultSelector()
        for d in self._devices:
            sel.register(d, selectors.EVENT_READ)
        while True:
            for key, _mask in sel.select():
                for event in key.fileobj.read():
                    self._handle(event, ecodes)

    def _handle(self, event, ecodes) -> None:
        if event.type != ecodes.EV_KEY:
            if self._ui is not None:
                self._ui.write_event(event)
                self._ui.syn()
            return
        outcome = self._engine.feed(event.code, event.value, self._enabled())
        if outcome.pressed or outcome.released:
            self._on_event(outcome)
        if not outcome.swallow and self._ui is not None:
            self._ui.write_event(event)
            self._ui.syn()

    def cleanup(self) -> None:
        if self._grabbed:
            for d in self._devices:
                try:
                    d.ungrab()
                except Exception:
                    pass
            self._grabbed = False
        if self._ui is not None:
            try:
                self._ui.close()
            except Exception:
                pass
            self._ui = None
        for d in self._devices:
            try:
                d.close()
            except Exception:
                pass
        self._devices = []
```

- [ ] **Step 2: Manual checkpoint 4 — passive listen (no grab)**

Create a throwaway script `/tmp/listen_passive.py`:
```python
from easytype.chords import HotkeyEngine
from easytype.listener import Listener

eng = HotkeyEngine({"record": (29, 57), "cancel": (1,), "repaste": (66,)})
Listener(eng, lambda: {"record", "cancel", "repaste"},
         lambda o: print("EVENT:", o)).run(grab=False)
```
Run: `.venv/bin/python /tmp/listen_passive.py`
Expected: pressing Ctrl+Space prints `EVENT: KeyOutcome(... pressed='record' ...)`. Normal typing in other windows is unaffected (no grab). Ctrl+C exits cleanly.

- [ ] **Step 3: Manual checkpoint 5 — grab-and-replay (needs input group + uinput)**

Ensure preflight passes first (`.venv/bin/easytype --check` once Task 13 lands; for now confirm you're in `input` and `/dev/uinput` is writable). Create `/tmp/listen_grab.py`:
```python
from easytype.chords import HotkeyEngine
from easytype.listener import Listener

eng = HotkeyEngine({"record": (29, 57), "cancel": (1,), "repaste": (66,)})
Listener(eng, lambda: {"record", "cancel", "repaste"},
         lambda o: print("EVENT:", o)).run(grab=True)
```
Run: `.venv/bin/python /tmp/listen_grab.py`
Expected: normal typing still works everywhere (replayed through the virtual keyboard); pressing Ctrl+Space prints the event but does **not** toggle IBus / insert a space in the focused app. Ctrl+C releases the grab cleanly and your keyboard behaves normally afterward. If anything feels stuck, Ctrl+C — the `finally` ungrabs.

- [ ] **Step 4: Commit**

```bash
git add src/easytype/listener.py
git commit -m "feat: evdev listener with passive mode and grab-and-replay consume"
```

---

## Task 13: Controller + CLI wiring

**Files:**
- Create: `src/easytype/controller.py`, `tests/test_controller.py`
- Modify: `src/easytype/cli.py`

- [ ] **Step 1: Write failing tests (pipeline + chord→action, with fakes)**

`tests/test_controller.py`:
```python
import numpy as np

from easytype.config import load_config, DictEntry
from easytype.controller import Controller


class FakeRecorder:
    def __init__(self): self.started = False
    def start(self): self.started = True
    def stop(self): self.started = False; return np.zeros(10, dtype=np.float32)


class FakeTranscriber:
    def transcribe(self, audio): return "ops plus is ready"


class FakeInjector:
    def __init__(self): self.injected = []
    def inject(self, text, method): self.injected.append((text, method))


class FakeIndicator:
    is_null = True
    def start(self, cap): ...
    def stop(self): ...


def build(tmp_path, **over):
    c = load_config(tmp_path / "c.toml")
    inj = FakeInjector()
    ctrl = Controller(
        config=c, recorder=FakeRecorder(), transcriber=FakeTranscriber(),
        injector=inj, indicator=FakeIndicator(), notify=lambda *a: None,
    )
    return ctrl, inj


def test_pipeline_applies_dictionary_before_inject(tmp_path):
    c = load_config(tmp_path / "c.toml")
    inj = FakeInjector()
    ctrl = Controller(
        config=c, recorder=FakeRecorder(), transcriber=FakeTranscriber(),
        injector=inj, indicator=FakeIndicator(), notify=lambda *a: None,
        dictionary=[DictEntry("ops plus", "OPS+", "smart")],
    )
    text = ctrl.process_audio(np.zeros(10, dtype=np.float32))
    assert text == "OPS+ is ready"
    assert inj.injected == [("OPS+ is ready", "type")]


def test_toggle_starts_then_stops(tmp_path):
    ctrl, inj = build(tmp_path)
    assert ctrl.state == "idle"
    ctrl.on_record()       # start
    assert ctrl.state == "recording"
    ctrl.on_record()       # stop → process synchronously in test mode
    assert ctrl.state == "idle"
    assert inj.injected and inj.injected[0][0] == "ops plus is ready"


def test_repaste_reinjects_last(tmp_path):
    ctrl, inj = build(tmp_path)
    ctrl.on_record(); ctrl.on_record()
    inj.injected.clear()
    ctrl.on_repaste()
    assert inj.injected == [("ops plus is ready", "type")]


def test_cancel_during_recording_discards(tmp_path):
    ctrl, inj = build(tmp_path)
    ctrl.on_record()
    ctrl.on_cancel()
    assert ctrl.state == "idle"
    assert inj.injected == []


def test_enabled_names_excludes_cancel_when_idle(tmp_path):
    ctrl, _ = build(tmp_path)
    assert "cancel" not in ctrl.enabled_names()
    ctrl.on_record()
    assert "cancel" in ctrl.enabled_names()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_controller.py -q`
Expected: FAIL.

- [ ] **Step 3: Implement `src/easytype/controller.py`**

```python
from __future__ import annotations

import threading
from collections.abc import Callable, Sequence

import numpy as np

from easytype.config import Config, DictEntry
from easytype.dictionary import apply_dictionary
from easytype.formatter import format_text


class Controller:
    def __init__(self, *, config: Config, recorder, transcriber, injector, indicator,
                 notify: Callable[[str, str], None],
                 dictionary: Sequence[DictEntry] | None = None,
                 synchronous: bool = True):
        self._cfg = config
        self._rec = recorder
        self._tx = transcriber
        self._inj = injector
        self._ind = indicator
        self._notify = notify
        self._dict = list(dictionary if dictionary is not None else config.dictionary)
        self._sync = synchronous  # tests run inline; real runtime sets False
        self.state = "idle"  # idle | recording | transcribing
        self.last_transcript = ""
        self._lock = threading.RLock()
        self._cap_timer: threading.Timer | None = None
        self._cancelled = False

    # --- chord gating -------------------------------------------------------
    def enabled_names(self) -> set[str]:
        names = {"record", "repaste"}
        if self.state in ("recording", "transcribing"):
            names.add("cancel")
        return names

    # --- hotkey handlers ----------------------------------------------------
    def on_record(self) -> None:
        if self._cfg.capture_mode == "hold":
            # in hold mode on_record is the press → start; release handled by on_record_release
            if self.state == "idle":
                self._start()
            return
        with self._lock:
            if self.state == "idle":
                self._start()
            elif self.state == "recording":
                self._stop_and_process()

    def on_record_release(self) -> None:
        if self._cfg.capture_mode == "hold" and self.state == "recording":
            self._stop_and_process()

    def on_cancel(self) -> None:
        with self._lock:
            if self.state == "recording":
                self._cancel_timer()
                self._rec.stop()
                self._ind.stop()
                self.state = "idle"
                self._notify("EasyType", "Recording cancelled")
            elif self.state == "transcribing":
                self._cancelled = True

    def on_repaste(self) -> None:
        if self.last_transcript:
            self._inj.inject(self.last_transcript, self._cfg.injection_method)

    # --- internals ----------------------------------------------------------
    def _start(self) -> None:
        self._cancelled = False
        self.state = "recording"
        self._rec.start()
        self._ind.start(self._cfg.max_recording_duration)
        self._notify("EasyType", "Recording…")
        print("[easytype] recording started")
        self._arm_cap_timer()

    def _arm_cap_timer(self) -> None:
        cap = self._cfg.max_recording_duration
        if cap and cap > 0:
            self._cap_timer = threading.Timer(cap, self._cap_reached)
            self._cap_timer.daemon = True
            self._cap_timer.start()

    def _cancel_timer(self) -> None:
        if self._cap_timer:
            self._cap_timer.cancel()
            self._cap_timer = None

    def _cap_reached(self) -> None:
        with self._lock:
            if self.state == "recording":
                print("[easytype] max duration reached — auto-stopping")
                self._stop_and_process()

    def _stop_and_process(self) -> None:
        self._cancel_timer()
        self.state = "transcribing"
        self._ind.stop()
        audio = self._rec.stop()
        print("[easytype] transcribing…")
        if self._sync:
            self._run_pipeline(audio)
        else:
            threading.Thread(target=self._run_pipeline, args=(audio,), daemon=True).start()

    def _run_pipeline(self, audio: np.ndarray) -> None:
        text = self.process_audio(audio)
        with self._lock:
            self.state = "idle"
        if text:
            print(f"[easytype] inserted: {text!r}")

    def process_audio(self, audio: np.ndarray) -> str:
        text = self._tx.transcribe(audio)
        text = apply_dictionary(text, self._dict)
        text = format_text(text, self._cfg)
        text = text.strip()
        if self._cancelled:
            self._cancelled = False
            return ""
        if text:
            self.last_transcript = text
            self._inj.inject(text, self._cfg.injection_method)
        return text
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_controller.py -q`
Expected: PASS (6 tests).

- [ ] **Step 5: Wire `src/easytype/cli.py` (full implementation)**

```python
from __future__ import annotations

import argparse
import signal
import subprocess
import sys

from easytype import preflight
from easytype.config import DEFAULT_CONFIG_PATH, load_config, load_doc, save_doc, set_hotkey_in_doc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="easytype", description="Local voice dictation for Linux")
    parser.add_argument("--passive", action="store_true", help="Run without grabbing the keyboard")
    parser.add_argument("--check", action="store_true", help="Run preflight checks and exit")
    parser.add_argument(
        "--set-hotkey", nargs="?", const="record", choices=["record", "cancel", "repaste"],
        help="Interactively capture a hotkey, then save it",
    )
    return parser


def _notify(title: str, body: str) -> None:
    subprocess.run(["notify-send", title, body], check=False)


def cmd_check() -> int:
    issues = preflight.check()
    print(preflight.format_report(issues))
    blocking = [i for i in issues if not i.ok and not i.name.startswith("python3-tk")]
    return 1 if blocking else 0


def cmd_set_hotkey(name: str) -> int:
    from easytype.keycodes import conflict_note, describe_chord
    from easytype.listener import open_devices

    print(f"Press the key or combination you want for '{name}', then release.")
    devices = open_devices("")
    pressed: list[int] = []
    seen: set[int] = set()
    try:
        from evdev import ecodes
        import selectors
        sel = selectors.DefaultSelector()
        for d in devices:
            sel.register(d, selectors.EVENT_READ)
        down: set[int] = set()
        while True:
            done = False
            for key, _ in sel.select():
                for ev in key.fileobj.read():
                    if ev.type != ecodes.EV_KEY:
                        continue
                    if ev.value == 1 and ev.code not in seen:
                        seen.add(ev.code); pressed.append(ev.code); down.add(ev.code)
                    elif ev.value == 0:
                        down.discard(ev.code)
                        if pressed and not down:
                            done = True
            if done:
                break
    finally:
        for d in devices:
            d.close()

    desc = describe_chord(pressed)
    note = conflict_note(pressed)
    if note:
        print(f"\nNote: {note}")
    doc = load_doc()
    set_hotkey_in_doc(doc, name, pressed, desc)
    save_doc(doc)
    print(f"Saved {name} hotkey: {desc}  (codes {pressed}) → {DEFAULT_CONFIG_PATH}")
    return 0


def cmd_run(passive: bool) -> int:
    config = load_config()
    session = preflight.detect_session()

    issues = preflight.check()
    blocking = [i for i in issues if not i.ok and not i.name.startswith("python3-tk")]
    grab = not passive
    if blocking and not passive:
        print(preflight.format_report(issues))
        print("\nFalling back to --passive (no consume) because grab prerequisites are missing.")
        grab = False

    from easytype.chords import HotkeyEngine
    from easytype.controller import Controller
    from easytype.indicator import create_indicator
    from easytype.injector import get_injector
    from easytype.listener import Listener
    from easytype.recorder import Recorder
    from easytype.transcriber import Transcriber

    controller = Controller(
        config=config,
        recorder=Recorder(config.audio_device),
        transcriber=Transcriber(config.model, config.language, config.transcribe_device),
        injector=get_injector(session),
        indicator=create_indicator(config),
        notify=_notify,
        synchronous=False,
    )

    engine = HotkeyEngine({
        "record": config.record.keys,
        "cancel": config.cancel.keys,
        "repaste": config.repaste.keys,
    })

    def on_event(outcome):
        if outcome.pressed == "record":
            controller.on_record()
        elif outcome.released == "record":
            controller.on_record_release()
        elif outcome.pressed == "cancel":
            controller.on_cancel()
        elif outcome.pressed == "repaste":
            controller.on_repaste()

    listener = Listener(engine, controller.enabled_names, on_event)

    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))

    print(f"[easytype] session={session}  mode={config.capture_mode}  "
          f"record={config.record.description}  grab={grab}")
    try:
        listener.run(device_override=config.keyboard_device, grab=grab)
    except KeyboardInterrupt:
        print("\n[easytype] shutting down…")
    finally:
        listener.cleanup()
    return 0


def main() -> None:
    args = build_parser().parse_args()
    if args.check:
        sys.exit(cmd_check())
    if args.set_hotkey:
        sys.exit(cmd_set_hotkey(args.set_hotkey))
    sys.exit(cmd_run(args.passive))


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Run the full test suite**

Run: `.venv/bin/pytest -q`
Expected: all tests PASS.

- [ ] **Step 7: Manual checkpoint 7 — full flow**

Run (passive first, safest): `.venv/bin/easytype --passive`
Expected startup line: `[easytype] session=x11 mode=toggle record=Ctrl+Space grab=False`.
Click into a text editor, press Ctrl+Space (pill appears, "Recording…" notification), speak a sentence, press Ctrl+Space again → your transcribed text is typed into the editor. Try F8 (repaste), and Esc while recording (cancel). Then re-run without `--passive` to confirm grab mode also swallows Ctrl+Space. Ctrl+C exits cleanly.

- [ ] **Step 8: Commit**

```bash
git add src/easytype/controller.py src/easytype/cli.py tests/test_controller.py
git commit -m "feat: controller state machine, hotkey wiring, and full CLI"
```

---

## Task 14: Docs, sample config, systemd, license

**Files:**
- Create: `README.md`, `LICENSE`, `config.sample.toml`, `systemd/easytype.service`

- [ ] **Step 1: Create `LICENSE`** — standard MIT text, copyright `2026 Jeff Harlan`.

- [ ] **Step 2: Create `config.sample.toml`** — copy the exact contents of `DEFAULT_CONFIG_TOML` from `config.py`.

- [ ] **Step 3: Create `systemd/easytype.service`**

```ini
[Unit]
Description=EasyType voice dictation
After=graphical-session.target

[Service]
ExecStart=%h/.local/bin/easytype
Restart=on-failure

[Install]
WantedBy=default.target
```

- [ ] **Step 4: Create `README.md`**

Sections (write complete prose for each):
- **What it is** — local push-to-talk + toggle voice dictation; press hotkey, speak, text appears; X11 (Wayland-ready).
- **Install** — `pipx install git+https://github.com/jeffharlan/easytype` (or `pipx install -e .` from a clone).
- **System dependencies** — `sudo apt install xdotool xclip libnotify-bin portaudio19-dev python3-tk`. Note Wayland deps (`ydotool`, `wl-clipboard`) are future.
- **Permissions setup** — run `easytype --check`; it prints the exact `usermod -aG input` line and the `/dev/uinput` udev rule; log out/in after.
- **First run** — start with `easytype --passive` (no permissions needed) to test safely; then `easytype` for full consume.
- **Config** — location `~/.config/easytype/config.toml`; document each key (capture_mode, max_recording_duration, hotkeys, transcription model/language/device, injection method, formatter, indicator, dictionary entries with smart/exact).
- **Changing the hotkey** — `easytype --set-hotkey` (record), `--set-hotkey cancel`, `--set-hotkey repaste`; note the Ctrl+Space (IBus) and Ctrl+\\ (SIGQUIT) conflict explanation and that consume prevents the side effects.
- **Run on login** — `cp systemd/easytype.service ~/.config/systemd/user/ && systemctl --user enable --now easytype`.
- **Troubleshooting** — X11 vs Wayland (`echo $XDG_SESSION_TYPE`); stuck-grab safety (Ctrl+C always releases; `--passive` fallback); model download time on first run; mic selection via `[audio] device`.

- [ ] **Step 5: Verify the package builds and the suite is green**

Run:
```bash
.venv/bin/pytest -q
.venv/bin/python -m build 2>/dev/null || echo "(optional: pip install build to produce a wheel)"
```
Expected: tests PASS.

- [ ] **Step 6: Commit**

```bash
git add README.md LICENSE config.sample.toml systemd/easytype.service
git commit -m "docs: README, MIT license, sample config, systemd service"
```

---

## Self-Review (completed during authoring)

**Spec coverage:** capture modes + cap (Task 13 controller), grab-and-replay consume (Tasks 5/12), safety/cleanup on all exit paths (Task 12 `finally` + Task 13 signal handlers + `--passive` fallback), `--set-hotkey` + conflicts table (Tasks 6/13), session detection + preflight with exact fixes (Task 4), faster-whisper + GPU auto (Task 11), dictionary (Task 3), formatter (Task 8), injector type/paste swappable (Task 7), focus-safe indicator (Task 9), config schema (Task 2), packaging/README/systemd (Tasks 1/14). All spec sections map to a task.

**Placeholders:** none — every code step contains complete code; README step lists exact section content to write.

**Type consistency:** `Config`/`HotkeySpec`/`DictEntry` (Task 2) are reused verbatim in Tasks 3/8/9/13. `KeyOutcome` fields (`swallow/pressed/released`) from Task 5 are consumed unchanged in Tasks 12/13. `Injector.inject(text, method)` (Task 7) matches controller calls (Task 13). `create_indicator`/`start(cap)`/`stop()` (Task 9) match controller usage (Task 13).

**Known manual-only areas (by nature, not gaps):** microphone (Task 10), model inference (Task 11), evdev grab + Tk window (Tasks 9/12) — each has an explicit manual checkpoint with expected output.
```
