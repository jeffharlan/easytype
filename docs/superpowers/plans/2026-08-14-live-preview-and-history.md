# Live Preview and Transcript History Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show a running transcript in the on-screen indicator while the user
speaks, and keep the last five completed transcripts in a file reachable from the
tray menu.

**Architecture:** Preview is whole-buffer re-transcription — a background worker
snapshots the growing audio buffer roughly once a second, runs it through a
second, faster Whisper model, and pushes the text over a pipe to the existing
indicator subprocess, which draws it as a wrapped caption under the timer. The
final full-clip pass and injection are untouched. History is a plain-text file in
the XDG data directory, written atomically by the controller and read by the tray.

**Tech Stack:** Python 3.11+, faster-whisper, numpy, PySide6 (tray/settings),
tkinter (indicator subprocess), tomlkit (config), pytest.

**Spec:** `docs/superpowers/specs/2026-08-14-live-preview-and-history-design.md`

## Global Constraints

- **Branch is already created:** `live-preview-and-history`, off `main`, and it
  already carries the design-doc commit. Do not create another branch for PR 1.
- **Never commit to `main`.** Every change lands through a PR with green CI, per
  `CLAUDE.md`.
- **TDD is mandatory.** Write the failing test, run it, watch it fail, then
  implement. New behavior always gets a test.
- **Full suite must be green before every commit:** `.venv/bin/python -m pytest -q`
- **Test output must be pristine** — no warnings, no stray prints from tests.
- **No test may load a real Whisper model, open a real audio stream, or open a
  real Tk window.** All three are faked.
- **Preview is display-only.** Nothing a preview pass produces may ever reach the
  injector.
- **Preview and history must both be failure-transparent.** An exception in
  either is caught and logged; it must never block recording, transcription, or
  injection.
- Log lines use the existing `print(f"[easytype] …")` convention.
- Python version floor is whatever `pyproject.toml` already declares — do not
  raise it, and do not add a new runtime dependency. Everything here uses the
  standard library plus what is already installed.

---

# PR 1 — History and the tray Recent menu

Tasks 1–5. Self-contained: after this PR merges, the user has a working history
file and can copy past transcripts from the tray.

---

### Task 1: The history module

**Files:**
- Create: `src/easytype/history.py`
- Test: `tests/test_history.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `HISTORY_PATH: Path` — `~/.local/share/easytype/history.txt`
  - `HISTORY_LIMIT: int` = `5`
  - `HistoryEntry` — frozen dataclass with `timestamp: str`, `text: str`
  - `read(path: Path | None = None) -> list[HistoryEntry]`
  - `append(text: str, path: Path | None = None, now: datetime | None = None) -> None`
  - `menu_label(text: str, limit: int = 50) -> str`

**Why `path` defaults to `None` rather than `HISTORY_PATH`:** Python binds
default arguments once, at function-definition time. If the default were
`HISTORY_PATH` directly, a test that monkeypatches `history.HISTORY_PATH` would
have no effect and would write to the developer's real history file. Resolving
inside the body (`path = path or HISTORY_PATH`) keeps it patchable.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_history.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_history.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'easytype.history'`

- [ ] **Step 3: Write the implementation**

Create `src/easytype/history.py`:

```python
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

HISTORY_PATH = Path("~/.local/share/easytype/history.txt").expanduser()
HISTORY_LIMIT = 5

_STAMP_FORMAT = "%Y-%m-%d %H:%M:%S"
_HEADER = re.compile(r"^--- (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) ---$", re.MULTILINE)


@dataclass(frozen=True)
class HistoryEntry:
    timestamp: str
    text: str


def read(path: Path | None = None) -> list[HistoryEntry]:
    """Newest first. A missing or unparseable file yields no entries rather than
    raising — history must never break the caller."""
    try:
        raw = (path or HISTORY_PATH).read_text()
    except OSError:
        return []
    # re.split with one capture group yields [preamble, stamp, body, stamp, body, …]
    parts = _HEADER.split(raw)
    entries = []
    for i in range(1, len(parts) - 1, 2):
        text = parts[i + 1].strip()
        if text:
            entries.append(HistoryEntry(parts[i], text))
    return entries


def append(text: str, path: Path | None = None, now: datetime | None = None) -> None:
    text = text.strip()
    if not text:
        return
    path = path or HISTORY_PATH
    stamp = (now or datetime.now()).strftime(_STAMP_FORMAT)
    kept = read(path)[: HISTORY_LIMIT - 1]
    blocks = [_block(stamp, text)] + [_block(e.timestamp, e.text) for e in kept]
    _write_atomic(path, "\n\n".join(blocks) + "\n")


def menu_label(text: str, limit: int = 50) -> str:
    """One-line, truncated label for a menu entry. Qt reads a lone '&' as a
    mnemonic marker and swallows it, so it is doubled."""
    flat = " ".join(text.split())
    if len(flat) > limit:
        flat = flat[:limit] + "…"
    return flat.replace("&", "&&")


def _block(timestamp: str, text: str) -> str:
    return f"--- {timestamp} ---\n{text}"


def _write_atomic(path: Path, content: str) -> None:
    """Write via a temp file in the same directory, then rename. The tray reads
    this file while the engine writes it; os.replace is atomic, so a reader sees
    either the old file or the new one, never a half-written one."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(content)
    os.replace(tmp, path)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_history.py -q`
Expected: PASS, 12 tests.

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/python -m pytest -q`
Expected: all green, no warnings.

- [ ] **Step 6: Commit**

```bash
git add src/easytype/history.py tests/test_history.py
git commit -m "feat: add transcript history store keeping the last five entries"
```

---

### Task 2: The `history_enabled` config flag

**Files:**
- Modify: `src/easytype/config.py` (`DEFAULT_CONFIG_TOML`, `Config`, `load_config`, `apply_settings_to_doc`)
- Modify: `config.sample.toml`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces: `Config.history_enabled: bool` (default `True`), and the
  `"history_enabled"` key in the flat settings dict that
  `apply_settings_to_doc` consumes and `gui/settings.py` produces.

**Note:** `SAMPLE_SETTINGS` in `tests/test_config.py` must gain the new key.
`apply_settings_to_doc` indexes the dict directly, so a missing key is a
`KeyError`, not a silent default.

- [ ] **Step 1: Write the failing tests**

In `tests/test_config.py`, add the new key to `SAMPLE_SETTINGS`:

```python
    "pause_media_while_recording": False,
    "history_enabled": False,
}
```

Add to the existing `test_load_creates_default_when_missing`, after the
`pause_media_while_recording` assertion:

```python
    assert c.history_enabled is True
```

Add to the existing `test_apply_settings_round_trips`, after the
`pause_media_while_recording` assertion:

```python
    assert c.history_enabled is False
```

And add a new test:

```python
def test_history_enabled_parsed(tmp_path: Path):
    path = tmp_path / "config.toml"
    path.write_text("[history]\nenabled = false\n")
    assert cfg.load_config(path).history_enabled is False
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_config.py -q`
Expected: FAIL — `AttributeError: 'Config' object has no attribute 'history_enabled'`
and a `KeyError: 'history_enabled'` from `apply_settings_to_doc`.

- [ ] **Step 3: Write the implementation**

In `src/easytype/config.py`, append to `DEFAULT_CONFIG_TOML` (just before the
closing `"""`):

```toml

[history]
enabled = true                     # keep the last 5 transcripts in ~/.local/share/easytype/history.txt
```

Add the field to the `Config` dataclass, immediately after
`pause_media_while_recording: bool`:

```python
    history_enabled: bool
```

In `load_config`, add alongside the other table lookups:

```python
    hist = doc.get("history", {})
```

and add to the `Config(...)` construction, after `pause_media_while_recording=...`:

```python
        history_enabled=bool(hist.get("enabled", True)),
```

In `apply_settings_to_doc`, after the `[media]` line:

```python
    _table(doc, "history")["enabled"] = bool(values["history_enabled"])
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_config.py -q`
Expected: PASS.

- [ ] **Step 5: Mirror the change in the sample config**

Append the same block to `config.sample.toml`:

```toml

[history]
enabled = true                     # keep the last 5 transcripts in ~/.local/share/easytype/history.txt
```

- [ ] **Step 6: Run the full suite**

Run: `.venv/bin/python -m pytest -q`
Expected: all green.

- [ ] **Step 7: Commit**

```bash
git add src/easytype/config.py config.sample.toml tests/test_config.py
git commit -m "feat: add history_enabled config flag"
```

---

### Task 3: The controller writes history

**Files:**
- Modify: `src/easytype/controller.py` (imports, `process_audio`)
- Test: `tests/test_controller.py`

**Interfaces:**
- Consumes: `history.append(text)` from Task 1, `Config.history_enabled` from Task 2.
- Produces: no new public surface — behavior only.

**Where in the pipeline:** after `polish_text`, after the cancellation check, on
non-empty text, immediately before injection. Injection must still happen even if
the history write blows up.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_controller.py`:

```python
from easytype import history


def _build_with_history(tmp_path, monkeypatch, config=None):
    """Point the history module at a temp file so tests never touch the real one."""
    hist_path = tmp_path / "history.txt"
    monkeypatch.setattr(history, "HISTORY_PATH", hist_path)
    c = config or load_config(tmp_path / "c.toml")
    inj = FakeInjector()
    ctrl = Controller(
        config=c, recorder=FakeRecorder(), transcriber=FakeTranscriber(),
        injector=inj, indicator=FakeIndicator(), notify=lambda *a: None,
    )
    return ctrl, inj, hist_path


def test_successful_transcript_is_written_to_history(tmp_path, monkeypatch):
    ctrl, _, hist_path = _build_with_history(tmp_path, monkeypatch)
    ctrl.on_record()
    ctrl.on_record()
    assert [e.text for e in history.read(hist_path)] == ["Ops plus is ready."]


def test_cancelled_transcript_is_not_written_to_history(tmp_path, monkeypatch):
    ctrl, _, hist_path = _build_with_history(tmp_path, monkeypatch)
    ctrl.on_record()
    ctrl.state = "transcribing"
    ctrl.on_cancel()
    ctrl.process_audio(np.zeros(10, dtype=np.float32))
    assert history.read(hist_path) == []


def test_history_not_written_when_flag_off(tmp_path, monkeypatch):
    c = replace(load_config(tmp_path / "c.toml"), history_enabled=False)
    ctrl, _, hist_path = _build_with_history(tmp_path, monkeypatch, config=c)
    ctrl.on_record()
    ctrl.on_record()
    assert history.read(hist_path) == []


def test_history_failure_still_injects(tmp_path, monkeypatch):
    ctrl, inj, _ = _build_with_history(tmp_path, monkeypatch)

    def boom(*a, **kw):
        raise OSError("disk full")

    monkeypatch.setattr(history, "append", boom)
    ctrl.on_record()
    ctrl.on_record()
    assert inj.injected == [("Ops plus is ready.", "type")]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_controller.py -q`
Expected: FAIL — the first test asserts `["Ops plus is ready."]` but gets `[]`;
nothing writes history yet.

- [ ] **Step 3: Write the implementation**

In `src/easytype/controller.py`, add to the imports:

```python
from easytype import history
```

In `process_audio`, change the tail from:

```python
        if text:
            self.last_transcript = text
            self._inj.inject(text, self._cfg.injection_method)
        return text
```

to:

```python
        if text:
            self.last_transcript = text
            self._record_history(text)
            self._inj.inject(text, self._cfg.injection_method)
        return text

    def _record_history(self, text: str) -> None:
        if not self._cfg.history_enabled:
            return
        try:
            history.append(text)
        except Exception as exc:
            print(f"[easytype] history write failed: {exc}")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_controller.py -q`
Expected: PASS.

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/python -m pytest -q`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add src/easytype/controller.py tests/test_controller.py
git commit -m "feat: record successful transcripts to history"
```

---

### Task 4: Settings toggle and tray Recent menu

**Files:**
- Modify: `src/easytype/gui/settings.py` (`_advanced_tab`, `_load`, `_values`)
- Modify: `src/easytype/gui/app.py` (imports, `_build_menu`, new `_fill_recent`, `_copy_to_clipboard`)

**Interfaces:**
- Consumes: `history.read()`, `history.menu_label()`, `history.HISTORY_PATH` from
  Task 1; `Config.history_enabled` and the `"history_enabled"` settings key from
  Task 2.
- Produces: no new public surface.

**No automated tests here.** The suite has no Qt harness and adding one for two
widgets is not worth it; the logic worth testing (`menu_label`) was already
covered in Task 1. This task is verified by hand in Step 4.

- [ ] **Step 1: Add the Settings checkbox**

In `src/easytype/gui/settings.py`, in `_advanced_tab`, add the widget and row:

```python
        self.history_enabled = QCheckBox("Keep the last 5 transcriptions")
```

right after the `self.start_on_login` line, and:

```python
        form.addRow(self.history_enabled)
```

right after the `form.addRow(self.start_on_login)` line.

In `_load`, after the `self.keyboard_device.setText(c.keyboard_device)` line:

```python
        self.history_enabled.setChecked(c.history_enabled)
```

In `_values`, after the `"pause_media_while_recording"` entry:

```python
            "history_enabled": self.history_enabled.isChecked(),
```

- [ ] **Step 2: Add the tray Recent menu**

In `src/easytype/gui/app.py`, extend the imports:

```python
from PySide6.QtCore import Qt, QTimer, QRectF, QUrl
from PySide6.QtGui import (
    QAction, QBrush, QColor, QCursor, QDesktopServices, QFont, QIcon, QPainter, QPen, QPixmap,
)

from easytype import history, preflight
```

(The existing `from easytype import preflight` line is replaced by the last line
above.)

In `_build_menu`, insert after the `self._mode_action` block and its
`menu.addSeparator()`, before the Settings action:

```python
        self._recent_menu = QMenu("Recent", menu)
        self._recent_menu.aboutToShow.connect(self._fill_recent)
        menu.addMenu(self._recent_menu)
```

Add the two new methods to `TrayApp`, after `_open_settings`:

```python
    def _fill_recent(self):
        # Rebuilt on every open: the engine writes history from another thread,
        # so a menu built once at startup would go stale immediately.
        self._recent_menu.clear()
        entries = history.read()
        if not entries:
            empty = QAction("No recent transcriptions", self._recent_menu)
            empty.setEnabled(False)
            self._recent_menu.addAction(empty)
        for entry in entries:
            action = QAction(history.menu_label(entry.text), self._recent_menu)
            action.triggered.connect(
                lambda _checked=False, text=entry.text: self._copy_to_clipboard(text)
            )
            self._recent_menu.addAction(action)
        self._recent_menu.addSeparator()
        open_file = QAction("Open history file…", self._recent_menu)
        open_file.triggered.connect(
            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(history.HISTORY_PATH)))
        )
        self._recent_menu.addAction(open_file)

    def _copy_to_clipboard(self, text: str):
        self._app.clipboard().setText(text)
```

Note the `text=entry.text` default-argument binding in the lambda: without it,
every action would close over the same loop variable and all five would copy the
last entry.

- [ ] **Step 3: Run the full suite**

Run: `.venv/bin/python -m pytest -q`
Expected: all green — nothing here is covered by tests, but the import changes
must not break collection.

- [ ] **Step 4: Verify by hand**

```bash
pkill -f easytype-gui
DISPLAY=:0 XDG_RUNTIME_DIR=/run/user/$(id -u) nohup easytype-gui >/tmp/easytype-gui.log 2>&1 &
```

Then check:
- Tray menu → **Recent** shows "No recent transcriptions" on a fresh history file.
- Dictate something. Reopen the menu — the transcript appears, truncated.
- Click it, paste elsewhere — the full text arrives.
- **Open history file…** opens the file in a text editor.
- Settings → Advanced shows "Keep the last 5 transcriptions", checked. Untick it,
  Save, dictate again — no new entry is written.

- [ ] **Step 5: Commit**

```bash
git add src/easytype/gui/settings.py src/easytype/gui/app.py
git commit -m "feat: add Recent transcripts tray menu and history settings toggle"
```

---

### Task 5: Document and ship PR 1

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Document the feature**

In `README.md`, add this section immediately after the `## Tray & Settings GUI`
section (before `## Configuration`):

```markdown
## Recent transcripts

The last five completed transcripts are kept in
`~/.local/share/easytype/history.txt`, newest first, as plain text you can open
in any editor:

```
--- 2026-08-14 09:12:33 ---
So what I need you to do is check the camera counts at the Louisville site.
```

The tray menu's **Recent** submenu lists them. Click one to copy the full text to
the clipboard; **Open history file…** opens the raw file.

Cancelled recordings are not saved. To turn the whole thing off — it does write
everything you dictate to disk — untick **Keep the last 5 transcriptions** in
Settings → Advanced.
```

Note the nested fenced block: in the real README, the inner example uses a plain
triple-backtick fence, and the outer fence shown here is only this plan quoting it.

- [ ] **Step 2: Run the full suite one final time**

Run: `.venv/bin/python -m pytest -q`
Expected: all green, pristine output.

- [ ] **Step 3: Commit and push**

```bash
git add README.md
git commit -m "docs: document transcript history and the Recent menu"
git push -u origin live-preview-and-history
```

- [ ] **Step 4: Open the PR**

```bash
gh pr create --title "feat: keep the last five transcripts and expose them in the tray" \
  --body "$(cat <<'EOF'
Adds a transcript history file and a tray menu to reach it.

- `history.py` — last 5 transcripts, newest first, plain text at
  `~/.local/share/easytype/history.txt`, written atomically so the tray can never
  read a half-written file.
- Controller records every successful transcript; cancelled ones are skipped, and
  a failed write can't stop the text from being typed.
- Tray gains a **Recent** submenu — click an entry to copy it, or open the raw file.
- Settings → Advanced gains a privacy toggle, default on.

Also includes the design doc for this work and the live-preview feature that
follows in the next PR.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 5: Wait for CI, then merge**

```bash
gh pr checks --watch
gh pr merge --squash --delete-branch
```

Expected: CI green before merging. The merge returns the local checkout to `main`.

- [ ] **Step 6: Confirm main is clean**

Run: `git status --short && git log --oneline -1`
Expected: no changes, and the squashed commit at the tip.

---

# PR 2 — Live preview

Tasks 6–12, on a new branch off the updated `main`.

---

### Task 6: Recorder snapshot

**Files:**
- Modify: `src/easytype/recorder.py`
- Test: `tests/test_recorder.py` (new file)

**Interfaces:**
- Consumes: nothing.
- Produces: `Recorder.snapshot() -> np.ndarray` — the audio captured so far,
  flattened float32, without stopping or clearing the stream. Empty array when
  nothing is buffered.

**Threading note:** `self._frames` is appended to from the sounddevice callback
thread. `snapshot` takes a shallow copy of the list first, so the callback can
keep appending during the concatenate. `list.append` and slicing are atomic under
the GIL, so no lock is needed — and no lock is *wanted*, because blocking inside
an audio callback risks dropouts.

- [ ] **Step 1: Start the branch**

```bash
git checkout main
git pull
git checkout -b live-preview
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_recorder.py`:

```python
import numpy as np

from easytype.recorder import Recorder


def _frames(*values):
    return [np.full((1, 1), v, dtype=np.float32) for v in values]


# These tests set _frames directly rather than driving a real InputStream:
# sounddevice needs a real audio device, which CI does not have.


def test_snapshot_returns_buffered_audio():
    rec = Recorder()
    rec._frames = _frames(1.0, 2.0)
    assert rec.snapshot().tolist() == [1.0, 2.0]


def test_snapshot_does_not_consume_the_buffer():
    rec = Recorder()
    rec._frames = _frames(1.0, 2.0)
    rec.snapshot()
    rec._frames.extend(_frames(3.0))
    assert rec.snapshot().tolist() == [1.0, 2.0, 3.0]


def test_snapshot_with_nothing_buffered_is_empty():
    rec = Recorder()
    assert rec.snapshot().size == 0


def test_stop_still_returns_the_full_buffer():
    rec = Recorder()
    rec._frames = _frames(1.0, 2.0, 3.0)
    assert rec.stop().tolist() == [1.0, 2.0, 3.0]
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_recorder.py -q`
Expected: FAIL — `AttributeError: 'Recorder' object has no attribute 'snapshot'`

- [ ] **Step 4: Write the implementation**

In `src/easytype/recorder.py`, replace the `stop` method with:

```python
    def snapshot(self) -> np.ndarray:
        """Audio captured so far, without touching the stream. The audio callback
        keeps appending to _frames while this runs, so copy the list first."""
        frames = self._frames[:]
        if not frames:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(frames, axis=0).flatten()

    def stop(self) -> np.ndarray:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        return self.snapshot()
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_recorder.py -q`
Expected: PASS, 4 tests.

- [ ] **Step 6: Run the full suite and commit**

```bash
.venv/bin/python -m pytest -q
git add src/easytype/recorder.py tests/test_recorder.py
git commit -m "feat: let the recorder snapshot audio mid-capture"
```

---

### Task 7: Indicator caption plumbing

**Files:**
- Modify: `src/easytype/indicator.py` (`_position_xy`, `NullIndicator`, `ProcessIndicator`, new `wrap_tail`, new constants)
- Test: `tests/test_indicator.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `wrap_tail(text: str, width: int, max_lines: int) -> list[str]`
  - `NullIndicator.caption(text: str) -> None` (no-op)
  - `ProcessIndicator.caption(text: str) -> None`
  - `_position_xy(position: str, sw: int, sh: int, w: int = PILL_W, h: int = PILL_H) -> tuple[int, int]`
  - `CAPTION_W = 420`, `CAPTION_LINES = 4`, `CAPTION_CHARS = 52`, `CAPTION_LINE_H = 18`

**Geometry:** growth falls out of the existing formula. `bottom` is
`sh - h - MARGIN * 2`, so a taller window starts higher — it grows upward.
`right` is `sw - w - MARGIN`, so a wider window starts further left — it grows
leftward. Nothing new is needed beyond threading `w`/`h` through.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_indicator.py`, extending the existing import from
`easytype.indicator` to also include `NullIndicator`, `ProcessIndicator`, and
`wrap_tail`. Do **not** import the `CAPTION_*` constants — these tests pass
explicit widths so they test the wrapping rule rather than restating the
constants, and an unused import would fail lint.

```python
import io


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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_indicator.py -q`
Expected: FAIL — `ImportError: cannot import name 'wrap_tail'`

- [ ] **Step 3: Write the implementation**

In `src/easytype/indicator.py`, add `textwrap` to the imports and the new
constants next to the existing ones:

```python
import textwrap
```

```python
CAPTION_W, CAPTION_LINES, CAPTION_CHARS = 420, 4, 52
CAPTION_LINE_H = 18
```

Replace `_position_xy` with:

```python
def _position_xy(position: str, sw: int, sh: int,
                 w: int = PILL_W, h: int = PILL_H) -> tuple[int, int]:
    cx = (sw - w) // 2
    right = sw - w - MARGIN
    bottom = sh - h - MARGIN * 2
    return {
        "top-left": (MARGIN, MARGIN),
        "top-center": (cx, MARGIN),
        "top-right": (right, MARGIN),
        "bottom-left": (MARGIN, bottom),
        "bottom-center": (cx, bottom),
        "bottom-right": (right, bottom),
    }.get(position, (right, MARGIN))


def wrap_tail(text: str, width: int, max_lines: int) -> list[str]:
    """Wrapped text, keeping only the last max_lines — the box reads as scrolling
    captions, with the oldest words falling off the top."""
    if not text.strip():
        return []
    return textwrap.wrap(text, width)[-max_lines:]
```

Add to `NullIndicator`:

```python
    def caption(self, text: str) -> None: ...
```

Add to `ProcessIndicator`, after `start`:

```python
    def caption(self, text: str) -> None:
        """Push preview text to the pill. Whitespace is collapsed so one caption
        is always exactly one line — the pill re-wraps for display anyway, so the
        original breaks carry no information and no escaping scheme is needed.
        Captions are advisory: if the pill has already exited (e.g. the cap timer
        fired), the write is dropped."""
        if self._proc is None or self._proc.stdin is None:
            return
        try:
            self._proc.stdin.write(" ".join(text.split()) + "\n")
            self._proc.stdin.flush()
        except (BrokenPipeError, ValueError, OSError):
            pass
```

And in `start`, add the pipe:

```python
    def start(self, cap: int) -> None:
        self._proc = subprocess.Popen(
            [sys.executable, "-m", "easytype.indicator", self._position, self._count, str(cap)],
            stdin=subprocess.PIPE, text=True,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_indicator.py -q`
Expected: PASS.

- [ ] **Step 5: Run the full suite and commit**

```bash
.venv/bin/python -m pytest -q
git add src/easytype/indicator.py tests/test_indicator.py
git commit -m "feat: add a caption channel to the on-screen indicator"
```

---

### Task 8: The pill draws captions

**Files:**
- Modify: `src/easytype/indicator.py` (`_run_pill` only)

**Interfaces:**
- Consumes: `wrap_tail`, `_position_xy`, `CAPTION_*` from Task 7.
- Produces: no new public surface.

**No automated test.** `_run_pill` opens a real Tk window and blocks in
`mainloop`; the suite deliberately never does that, and the logic worth testing
(`wrap_tail`, geometry) is already covered in Task 7. Verified by hand in Step 3.

**Threading:** the stdin reader runs on a background thread, but Tk widgets must
only be touched from the thread running `mainloop`. The reader therefore only
puts strings on a `queue.Queue`, and a `root.after` poll drains it on the Tk
thread. Calling `root.after` itself from the reader thread would appear to work
and is not guaranteed to.

- [ ] **Step 1: Rewrite `_run_pill`**

In `src/easytype/indicator.py`, add to the imports:

```python
import queue
import threading
```

Replace `_run_pill` with:

```python
def _run_pill(position: str, count: str, cap: int) -> None:
    import tkinter as tk

    root = tk.Tk()
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    try:
        root.wm_attributes("-type", "splash")  # no focus / no taskbar (X11)
    except tk.TclError:
        pass

    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    x, y = _position_xy(position, sw, sh)
    root.geometry(f"{PILL_W}x{PILL_H}+{x}+{y}")

    label = tk.Label(root, font=("sans", 14, "bold"), fg="white", bg="#111111", padx=12, pady=8)
    label.pack(side="top", fill="both", expand=True)
    caption = tk.Label(root, font=("sans", 11), fg="#dddddd", bg="#111111",
                       justify="left", anchor="w", padx=12, pady=6, wraplength=CAPTION_W - 24)

    captions: queue.Queue[str] = queue.Queue()
    state = {"s": 0, "shown": False}

    def read_stdin():
        for line in sys.stdin:
            captions.put(line.rstrip("\n"))

    threading.Thread(target=read_stdin, daemon=True).start()

    def drain():
        text = None
        while not captions.empty():        # only the newest caption matters
            text = captions.get_nowait()
        if text is not None:
            show(text)
        root.after(100, drain)

    def show(text: str):
        lines = wrap_tail(text, CAPTION_CHARS, CAPTION_LINES)
        if not lines:
            return
        if not state["shown"]:
            caption.pack(side="top", fill="both", expand=True)
            state["shown"] = True
        caption.config(text="\n".join(lines))
        h = PILL_H + CAPTION_LINE_H * len(lines) + 12
        cx, cy = _position_xy(position, sw, sh, CAPTION_W, h)
        root.geometry(f"{CAPTION_W}x{h}+{cx}+{cy}")

    def tick():
        s = state["s"]
        if cap and s > cap:
            root.destroy()
            return
        shown = s if count == "up" else max(0, cap - s)
        label.config(text=f"● REC  {format_elapsed(shown)}",
                     fg=("#ffb000" if should_warn(s, cap) else "white"))
        state["s"] += 1
        root.after(1000, tick)

    tick()
    drain()
    root.mainloop()
```

- [ ] **Step 2: Run the full suite**

Run: `.venv/bin/python -m pytest -q`
Expected: all green.

- [ ] **Step 3: Verify the pill by hand**

Drive it directly, without the rest of the app:

```bash
printf 'hello world\nthis is a much longer caption that should wrap across several lines and keep only the tail visible in the box\n' \
  | .venv/bin/python -m easytype.indicator top-right up 60
```

Expected: the pill appears top-right, shows the timer, then grows a caption area.
Feed it a long line and confirm it wraps to at most 4 lines and keeps the tail.
Re-run with `bottom-right` and confirm the box grows **upward and leftward**
rather than off the screen. Ctrl+C to quit.

- [ ] **Step 4: Commit**

```bash
git add src/easytype/indicator.py
git commit -m "feat: draw preview captions in the indicator pill"
```

---

### Task 9: The preview worker

**Files:**
- Create: `src/easytype/preview.py`
- Test: `tests/test_preview.py`

**Interfaces:**
- Consumes: `Recorder.snapshot()` from Task 6, `indicator.caption()` from Task 7,
  and any object with `transcribe(audio) -> str` (the existing `Transcriber`).
- Produces:
  - `PREVIEW_INTERVAL = 1.0`, `MIN_PREVIEW_SECONDS = 0.5`
  - `PreviewWorker(recorder, transcriber, indicator, interval=PREVIEW_INTERVAL)`
    with `start() -> None` and `stop() -> None`

**Why a stop `Event` and not a flag:** `Event.wait(timeout)` gives an
interruptible sleep, so `stop()` takes effect immediately instead of waiting out
the remaining interval. Note the polarity — the event means *stop requested*; an
event meaning *running* would make `wait()` return instantly and spin the loop.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_preview.py`:

```python
import numpy as np

from easytype.preview import MIN_PREVIEW_SECONDS, PreviewWorker
from easytype.recorder import SAMPLE_RATE


class FakeRecorder:
    def __init__(self, seconds=2.0):
        self.audio = np.zeros(int(SAMPLE_RATE * seconds), dtype=np.float32)

    def snapshot(self):
        return self.audio


class FakeTranscriber:
    def __init__(self, text="preview text"):
        self.text = text
        self.calls = 0

    def transcribe(self, audio):
        self.calls += 1
        return self.text


class FakeIndicator:
    def __init__(self):
        self.captions = []

    def caption(self, text):
        self.captions.append(text)


def _worker(recorder=None, transcriber=None, indicator=None):
    return PreviewWorker(
        recorder or FakeRecorder(),
        transcriber or FakeTranscriber(),
        indicator or FakeIndicator(),
        interval=0.01,
    )


def test_a_pass_captions_the_transcribed_snapshot():
    ind = FakeIndicator()
    worker = _worker(indicator=ind)
    worker._pass()
    assert ind.captions == ["preview text"]


def test_audio_below_the_minimum_is_not_transcribed():
    tx = FakeTranscriber()
    ind = FakeIndicator()
    worker = _worker(recorder=FakeRecorder(seconds=MIN_PREVIEW_SECONDS / 2),
                     transcriber=tx, indicator=ind)
    worker._pass()
    assert tx.calls == 0
    assert ind.captions == []


def test_empty_transcript_is_not_captioned():
    ind = FakeIndicator()
    worker = _worker(transcriber=FakeTranscriber(text="   "), indicator=ind)
    worker._pass()
    assert ind.captions == []


def test_a_pass_finishing_after_stop_publishes_nothing():
    ind = FakeIndicator()
    worker = _worker(indicator=ind)
    worker.stop()          # a pass already in flight must not publish its result
    worker._pass()
    assert ind.captions == []


def test_a_transcriber_failure_does_not_propagate():
    class Boom:
        def transcribe(self, audio):
            raise RuntimeError("cuda out of memory")

    worker = _worker(transcriber=Boom())
    worker._pass()          # must not raise


def test_start_then_stop_leaves_no_live_thread():
    worker = _worker()
    worker.start()
    worker.stop()
    assert worker._thread is None


def test_start_is_idempotent():
    worker = _worker()
    worker.start()
    first = worker._thread
    worker.start()
    assert worker._thread is first
    worker.stop()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_preview.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'easytype.preview'`

- [ ] **Step 3: Write the implementation**

Create `src/easytype/preview.py`:

```python
from __future__ import annotations

import threading

from easytype.recorder import SAMPLE_RATE

PREVIEW_INTERVAL = 1.0      # seconds between passes, not a deadline for one
MIN_PREVIEW_SECONDS = 0.5   # below this there is nothing worth transcribing


class PreviewWorker:
    """Re-transcribes the growing audio buffer while recording and pushes the
    result to the indicator. Display only — nothing here reaches the injector."""

    def __init__(self, recorder, transcriber, indicator, interval: float = PREVIEW_INTERVAL):
        self._rec = recorder
        self._tx = transcriber
        self._ind = indicator
        self._interval = interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Returns promptly. A pass still in flight finishes on its own and
        discards its result, so the final transcription is never held up."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=0.2)
        self._thread = None

    def _loop(self) -> None:
        while not self._stop.is_set():
            self._pass()
            self._stop.wait(self._interval)

    def _pass(self) -> None:
        try:
            audio = self._rec.snapshot()
            if audio.size < MIN_PREVIEW_SECONDS * SAMPLE_RATE:
                return
            text = self._tx.transcribe(audio)
        except Exception as exc:
            print(f"[easytype] preview pass failed: {exc}")
            return
        if text.strip() and not self._stop.is_set():
            self._ind.caption(text)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_preview.py -q`
Expected: PASS, 7 tests.

- [ ] **Step 5: Run the full suite and commit**

```bash
.venv/bin/python -m pytest -q
git add src/easytype/preview.py tests/test_preview.py
git commit -m "feat: add the live preview worker"
```

---

### Task 10: Preview config and Settings controls

**Files:**
- Modify: `src/easytype/config.py`
- Modify: `config.sample.toml`
- Modify: `src/easytype/gui/settings.py` (`_indicator_tab`, `_load`, `_values`)
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `Config.preview_enabled: bool` (default `True`),
  `Config.preview_model: str` (default `"tiny.en"`), and the
  `"preview_enabled"` / `"preview_model"` keys in the settings dict.

- [ ] **Step 1: Write the failing tests**

In `tests/test_config.py`, add both keys to `SAMPLE_SETTINGS`:

```python
    "history_enabled": False,
    "preview_enabled": False,
    "preview_model": "base.en",
}
```

Add to `test_load_creates_default_when_missing`:

```python
    assert c.preview_enabled is True
    assert c.preview_model == "tiny.en"
```

Add to `test_apply_settings_round_trips`:

```python
    assert c.preview_enabled is False
    assert c.preview_model == "base.en"
```

And a new test for the blank-means-reuse convention:

```python
def test_blank_preview_model_is_preserved(tmp_path: Path):
    path = tmp_path / "config.toml"
    path.write_text('[preview]\nenabled = true\nmodel = ""\n')
    c = cfg.load_config(path)
    assert c.preview_model == ""
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_config.py -q`
Expected: FAIL — no `preview_enabled` attribute, and `KeyError: 'preview_enabled'`.

- [ ] **Step 3: Write the config implementation**

In `src/easytype/config.py`, append to `DEFAULT_CONFIG_TOML`:

```toml

[preview]
enabled = true                     # show a running transcript while you speak
model = "tiny.en"                  # "" = reuse the transcription model (exact, but slower)
```

Add to the `Config` dataclass, after `history_enabled: bool`:

```python
    preview_enabled: bool
    preview_model: str
```

In `load_config`, add the table lookup:

```python
    prev = doc.get("preview", {})
```

and to the `Config(...)` construction:

```python
        preview_enabled=bool(prev.get("enabled", True)),
        preview_model=str(prev.get("model", "tiny.en")),
```

In `apply_settings_to_doc`, after the `[history]` line:

```python
    prev = _table(doc, "preview")
    prev["enabled"] = bool(values["preview_enabled"])
    prev["model"] = values["preview_model"]
```

Mirror the same TOML block into `config.sample.toml`.

- [ ] **Step 4: Run the config tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_config.py -q`
Expected: PASS.

- [ ] **Step 5: Add the Settings controls**

In `src/easytype/gui/settings.py`, in `_indicator_tab`, add after the
`self.indicator_count` line:

```python
        self.preview_enabled = QCheckBox("Show live preview text while recording")
        self.preview_model = QComboBox()
        self.preview_model.setEditable(True)
        self.preview_model.addItems(MODELS)
        self.preview_model.setToolTip(
            "Smaller is faster and keeps up with your voice. "
            "Set it to your main model for an exact preview at the cost of lag."
        )
```

and the rows after `form.addRow("Count", self.indicator_count)`:

```python
        form.addRow(self.preview_enabled)
        form.addRow("Preview model", self.preview_model)
```

In `_load`, after `self.indicator_count.setCurrentText(c.indicator_count)`:

```python
        self.preview_enabled.setChecked(c.preview_enabled)
        self.preview_model.setCurrentText(c.preview_model)
```

In `_values`, after the `"indicator_count"` entry:

```python
            "preview_enabled": self.preview_enabled.isChecked(),
            "preview_model": self.preview_model.currentText(),
```

- [ ] **Step 6: Run the full suite and commit**

```bash
.venv/bin/python -m pytest -q
git add src/easytype/config.py config.sample.toml src/easytype/gui/settings.py tests/test_config.py
git commit -m "feat: add preview config and settings controls"
```

---

### Task 11: Wire preview into the controller and engine

**Files:**
- Modify: `src/easytype/controller.py` (`__init__`, `_start`, `on_cancel`, `_finish_recording`)
- Modify: `src/easytype/engine.py` (`build_engine`)
- Test: `tests/test_controller.py`

**Interfaces:**
- Consumes: `PreviewWorker` from Task 9, `Config.preview_enabled` /
  `Config.preview_model` from Task 10, `Recorder.snapshot` from Task 6,
  `indicator.caption` / `is_null` from Task 7.
- Produces: `Controller(..., preview=None)` keyword argument.

**Guarding:** `preview` defaults to `None` and every call site guards with
`if self._preview:`, exactly as `media` does. No null-object class is added.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_controller.py`:

```python
class FakePreview:
    def __init__(self): self.events = []
    def start(self): self.events.append("start")
    def stop(self): self.events.append("stop")


def _build_with_preview(tmp_path, preview):
    return Controller(
        config=load_config(tmp_path / "c.toml"), recorder=FakeRecorder(),
        transcriber=FakeTranscriber(), injector=FakeInjector(),
        indicator=FakeIndicator(), notify=lambda *a: None, preview=preview,
    )


def test_recording_starts_then_stops_preview(tmp_path):
    preview = FakePreview()
    ctrl = _build_with_preview(tmp_path, preview)
    ctrl.on_record()
    assert preview.events == ["start"]
    ctrl.on_record()
    assert preview.events == ["start", "stop"]


def test_cancel_stops_preview(tmp_path):
    preview = FakePreview()
    ctrl = _build_with_preview(tmp_path, preview)
    ctrl.on_record()
    ctrl.on_cancel()
    assert preview.events == ["start", "stop"]


def test_controller_works_without_a_preview(tmp_path):
    ctrl = _build_with_preview(tmp_path, None)
    ctrl.on_record()
    ctrl.on_record()
    assert ctrl.state == "idle"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_controller.py -q`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'preview'`

- [ ] **Step 3: Write the controller implementation**

In `src/easytype/controller.py`, add the parameter to `__init__` after `media=None`:

```python
                 preview=None,
```

and the assignment after `self._media = media`:

```python
        self._preview = preview
```

In `_start`, after `self._rec.start()`:

```python
        if self._preview:
            self._preview.start()
```

In `on_cancel`, in the `recording` branch, after `self._rec.stop()`:

```python
                self._stop_preview()
```

In `_finish_recording`, as the first line of the method body (before
`self._ind.stop()`) — the preview must stop before the pill is torn down and
before the final pass starts:

```python
        self._stop_preview()
```

And the helper, next to `_pause_media` / `_resume_media`:

```python
    def _stop_preview(self) -> None:
        if self._preview:
            self._preview.stop()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_controller.py -q`
Expected: PASS.

- [ ] **Step 5: Wire it up in the engine**

In `src/easytype/engine.py`, replace the body of `build_engine` from the imports
through the `Controller(...)` construction with:

```python
    from easytype.indicator import create_indicator
    from easytype.injector import get_injector
    from easytype.listener import Listener
    from easytype.media import MediaController
    from easytype.preview import PreviewWorker
    from easytype.recorder import Recorder
    from easytype.transcriber import Transcriber

    transcriber = Transcriber(config.model, config.language, config.transcribe_device,
                              initial_prompt=config.initial_prompt)
    recorder = Recorder(config.audio_device)
    indicator = create_indicator(config)

    preview = None
    preview_transcriber = None
    # No indicator means nowhere to draw, so preview is skipped regardless of the flag.
    if config.preview_enabled and not indicator.is_null:
        preview_transcriber = Transcriber(
            config.preview_model or config.model, config.language,
            config.transcribe_device, initial_prompt=config.initial_prompt,
        )
        preview = PreviewWorker(recorder, preview_transcriber, indicator)

    controller = Controller(
        config=config,
        recorder=recorder,
        transcriber=transcriber,
        injector=get_injector(session, config.type_delay_ms),
        indicator=indicator,
        notify=notify,
        media=MediaController(),
        preview=preview,
        synchronous=False,
    )
```

Then replace the **last two lines** of the function — the existing
`listener = Listener(...)` and `return EngineBundle(...)` — with this, so both
models are warmed at startup and the first preview pass doesn't pay a model load:

```python
    def warmup():
        transcriber.warmup()
        if preview_transcriber is not None:
            preview_transcriber.warmup()

    listener = Listener(engine, controller.enabled_names, on_event)
    return EngineBundle(listener=listener, controller=controller, warmup=warmup)
```

Leave the `engine = HotkeyEngine({...})` block and `def on_event(...)` between
the controller and this exactly as they are.

- [ ] **Step 6: Run the full suite and commit**

```bash
.venv/bin/python -m pytest -q
git add src/easytype/controller.py src/easytype/engine.py tests/test_controller.py
git commit -m "feat: run live preview during recording"
```

---

### Task 12: Verify live, document, and ship PR 2

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Restart the app and verify end to end**

The app is an editable pipx install; code changes need a restart.

```bash
pkill -f easytype-gui
DISPLAY=:0 XDG_RUNTIME_DIR=/run/user/$(id -u) nohup easytype-gui >/tmp/easytype-gui.log 2>&1 &
```

Check each of these:
- Press the record hotkey and speak for ~10 seconds. Text appears in the pill
  within a second or two and keeps updating as you talk.
- Stop. The final text is typed as before, and matches roughly (not necessarily
  exactly) what the preview showed.
- Cancel mid-recording with Esc. The pill disappears, nothing is typed, and no
  further captions appear.
- Let a recording run to the max-duration cap. The pill closes itself and the
  final pass still runs — no traceback in `/tmp/easytype-gui.log`.
- Settings → Indicator → untick "Show live preview text while recording", Save,
  record again. Timer pill only, no caption.
- Settings → Indicator → set Preview model to `small.en`, Save, record again.
  Preview still works, visibly slower to update on a long clip.
- Settings → Indicator → untick the indicator entirely, Save, record. No pill, no
  crash, transcription still works.
- `nvidia-smi` during a recording shows both models resident without exhausting
  VRAM.

Check the log for anything unexpected:

```bash
grep -i -E 'preview|traceback|error' /tmp/easytype-gui.log
```

- [ ] **Step 2: Document the feature**

In `README.md`, add this section immediately before `## Recent transcripts`:

```markdown
## Live preview

While you speak, the on-screen indicator shows a running transcript of what has
been captured so far, so you can see how the dictation is going without stopping.

The preview is **display only** — nothing is typed until you stop, and the text
that finally lands comes from the normal full-quality pass over the whole clip,
not from the preview. Because the preview runs on a smaller, faster model, it can
occasionally show a word that comes out differently when typed.

Settings → Indicator has the controls, or in `config.toml`:

    [preview]
    enabled = true
    model = "tiny.en"    # "" = reuse the transcription model

Setting `model = ""` makes the preview exact, at the cost of it falling behind
your voice on longer dictations. Preview draws inside the on-screen indicator, so
it does nothing when the indicator is disabled.
```

The config example is indented four spaces rather than fenced, so it nests
cleanly inside the section without a second fence.

- [ ] **Step 3: Run the full suite one final time**

Run: `.venv/bin/python -m pytest -q`
Expected: all green, pristine output.

- [ ] **Step 4: Commit and push**

```bash
git add README.md
git commit -m "docs: document live transcription preview"
git push -u origin live-preview
```

- [ ] **Step 5: Open the PR**

```bash
gh pr create --title "feat: show a live transcript in the indicator while recording" \
  --body "$(cat <<'EOF'
Shows what Whisper is hearing while you speak, in the on-screen indicator.

- `preview.py` — a worker that re-transcribes the growing audio buffer roughly
  once a second through a second, faster model (`tiny.en` by default) and pushes
  the text to the indicator. Self-throttling: the next pass starts only after the
  previous one returns.
- `Recorder.snapshot()` — reads the buffer mid-capture without stopping the stream.
- The indicator pill grows a wrapped caption area, fed over stdin, and grows
  upward/leftward so it never runs off the screen edge.
- Display only: the text that gets typed still comes from the existing
  full-quality pass on the complete clip.
- Settings → Indicator gains a toggle and a preview-model picker; setting the
  model to your main model gives an exact preview at the cost of lag.

Design: `docs/superpowers/specs/2026-08-14-live-preview-and-history-design.md`

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 6: Wait for CI, then merge**

```bash
gh pr checks --watch
gh pr merge --squash --delete-branch
```

- [ ] **Step 7: Confirm main is clean and restart the app**

```bash
git status --short && git log --oneline -1
pkill -f easytype-gui
DISPLAY=:0 XDG_RUNTIME_DIR=/run/user/$(id -u) nohup easytype-gui >/tmp/easytype-gui.log 2>&1 &
```
