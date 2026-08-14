# Live Typing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Type dictation into the window the user is actually working in, as they
speak, without ever corrupting text already in that document.

**Architecture:** The existing preview worker keeps re-transcribing the growing
audio buffer, but its transcripts now feed a `LiveTypist` instead of the on-screen
caption. The typist commits only the leading run that two consecutive passes
agree on, trimmed to whole words, and types it into the window that was focused
when recording began. Cleanup rules that used to run on the finished transcript
move to commit time so they stay append-only. One bounded, focus-guarded
reconciliation runs at the end against the authoritative final transcript.

**Tech Stack:** Python 3.11+, faster-whisper, xdotool (X11), numpy, PySide6
(settings), tomlkit (config), pytest.

**Spec:** `docs/superpowers/specs/2026-08-14-live-typing-design.md`

## Global Constraints

- **Branch is already created:** `live-typing`, off `main`, carrying the design
  commit. Do not create another branch.
- **Never commit to `main`.** Changes land through a PR with green CI.
- **TDD is mandatory.** Failing test first, watch it fail, then implement.
- **Full suite green before every commit:** `.venv/bin/python -m pytest -q`
- **Test output must be pristine** — no warnings, no stray prints.
- **No test may run `xdotool`, load a Whisper model, or open a window.**
- **Append-only while recording.** `LiveTypist.feed` must never call
  `injector.backspace`. Backspace appears in exactly two methods: `undo` and
  `finish`.
- **Every write is focus-guarded.** `type_text` and `backspace` are only ever
  reached after a successful `_focused()` check. `active_window()` returning `""`
  counts as a mismatch — it fails closed.
- **Live typing is off by default** (`inject_live = false`).
- Log lines use the existing `print(f"[easytype] …")` convention.
- No new runtime dependency; standard library only.

---

### Task 1: Serialize transcription

**Files:**
- Modify: `src/easytype/transcriber.py`
- Test: `tests/test_transcriber.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `Transcriber.transcribe` is safe to call from two threads at once.

**Why:** live typing shares one `Transcriber` between the preview thread and the
final pass. `PreviewWorker.stop()` joins with a 0.2s timeout by design, so a pass
can still be running when the final transcription starts. `WhisperModel` makes no
thread-safety guarantee. The lock also covers `_ensure_model`, or two threads
could each construct a model.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_transcriber.py`:

```python
import threading
import time


def test_concurrent_transcribes_never_overlap():
    class _ReentrancyDetector:
        def __init__(self):
            self.inside = 0
            self.overlapped = False

        def transcribe(self, audio, **kwargs):
            self.inside += 1
            if self.inside > 1:
                self.overlapped = True
            time.sleep(0.02)
            self.inside -= 1
            return ([_FakeSegment("hello")], object())

    detector = _ReentrancyDetector()
    tx = Transcriber()
    tx._model = detector
    threads = [
        threading.Thread(target=tx.transcribe, args=(np.ones(16000, dtype=np.float32),))
        for _ in range(4)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert detector.overlapped is False
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_transcriber.py::test_concurrent_transcribes_never_overlap -v`
Expected: FAIL — `assert True is False`, because unsynchronized threads overlap.

- [ ] **Step 3: Write the implementation**

In `src/easytype/transcriber.py`, add `import threading` at the top, then in
`__init__` after `self._model = None`:

```python
        # Preview and the final pass share one Transcriber across threads.
        self._lock = threading.Lock()
```

and wrap `transcribe`:

```python
    def transcribe(self, audio: np.ndarray) -> str:
        if audio.size == 0:
            return ""
        with self._lock:
            model = self._ensure_model()
            segments, _info = model.transcribe(
                audio, language=self._language, beam_size=5,
                initial_prompt=self._initial_prompt or None,
            )
            return "".join(seg.text for seg in segments).strip()
```

- [ ] **Step 4: Run it to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_transcriber.py -q`
Expected: PASS, 6 tests.

- [ ] **Step 5: Full suite and commit**

```bash
.venv/bin/python -m pytest -q
git add src/easytype/transcriber.py tests/test_transcriber.py
git commit -m "fix: serialize transcription so preview and final passes can share a model"
```

---

### Task 2: Split the polish rules

**Files:**
- Modify: `src/easytype/polish.py`
- Test: `tests/test_polish.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `polish_stream(text: str) -> str` — every rule in `polish_text`
  except the closing period, and without the trailing `rstrip`.
  `polish_text` keeps its exact current behavior.

**Why no rstrip:** mid-dictation a trailing space separates the chunk just typed
from the next one. Stripping it would run words together.

**Prefix stability** is the property the whole design leans on: for any
whole-word prefix `p` of `t`, `polish_stream(t)` starts with `polish_stream(p)`.
It holds because every rule is local, and the standalone-"i" rule only breaks on
a *partial* trailing word ("i" → "I" would be wrong if "ice" follows) — which is
why `settled_prefix` trims to whole words.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_polish.py`:

```python
from easytype.polish import polish_stream


def test_polish_stream_adds_no_closing_period():
    assert polish_stream("check the camera counts") == "Check the camera counts"


def test_polish_stream_preserves_a_trailing_space():
    assert polish_stream("check the camera ") == "Check the camera "


def test_polish_stream_capitalizes_sentence_starts_and_standalone_i():
    assert polish_stream("i said hello. then i left") == "I said hello. Then I left"


def test_polish_stream_is_prefix_stable_over_whole_words():
    full = "i said hello. then i left the site"
    whole = polish_stream(full)
    words = full.split(" ")
    for i in range(1, len(words)):
        prefix = " ".join(words[:i]) + " "
        assert whole.startswith(polish_stream(prefix)), f"broke at {prefix!r}"


def test_polish_stream_on_empty_text():
    assert polish_stream("   ") == "   "
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_polish.py -q`
Expected: FAIL — `ImportError: cannot import name 'polish_stream'`

- [ ] **Step 3: Write the implementation**

Replace `polish_text` in `src/easytype/polish.py` with:

```python
def polish_stream(text: str) -> str:
    """Every polish rule except the closing period, and without the trailing
    rstrip. Safe to apply to a growing transcript: for any whole-word prefix p of
    t, polish_stream(t) starts with polish_stream(p)."""
    if not text.strip():
        return text
    text = _SPACE_BEFORE_PUNCT.sub(r"\1", text)
    text = _REPEATED_SPACE.sub(" ", text)
    text = _STANDALONE_I.sub("I", text)
    text = _FIRST_LETTER.sub(lambda m: m.group(1) + m.group(2).upper(), text)
    return _AFTER_SENTENCE.sub(lambda m: m.group(1) + m.group(2).upper(), text)


def polish_text(text: str) -> str:
    """Deterministic sentence polish applied to every transcript: capitalize
    sentence starts and standalone "I", and tidy spacing. Rules, not a model, so
    the mechanical fixes are always correct even when AI cleanup is off."""
    if not text.strip():
        return text
    text = polish_stream(text).rstrip()
    if text and text[-1] not in ".!?":
        text = text.rstrip(",;:") + "."
    return text
```

- [ ] **Step 4: Run them to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_polish.py -q`
Expected: PASS — the new tests plus every pre-existing `polish_text` test
unchanged.

- [ ] **Step 5: Full suite and commit**

```bash
.venv/bin/python -m pytest -q
git add src/easytype/polish.py tests/test_polish.py
git commit -m "refactor: split polish into a prefix-stable streaming pass"
```

---

### Task 3: Injector primitives for live typing

**Files:**
- Modify: `src/easytype/injector/x11.py`
- Test: `tests/test_injector_x11.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `backspace_command(count: int) -> list[str]`
  - `X11Injector.type_text(text: str) -> None`
  - `X11Injector.backspace(count: int) -> None`
  - `X11Injector.active_window() -> str`

**Fails closed:** `active_window` returns `""` when `xdotool` errors or is
missing. `LiveTypist` treats `""` as "not the original window", so a broken
`xdotool` disables typing rather than typing blindly.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_injector_x11.py`:

```python
import subprocess

from easytype.injector.x11 import X11Injector, backspace_command


def test_backspace_command_repeats_the_key():
    assert backspace_command(7) == [
        "xdotool", "key", "--clearmodifiers", "--repeat", "7", "BackSpace",
    ]


def test_backspace_of_zero_runs_nothing(monkeypatch):
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: calls.append(a))
    X11Injector().backspace(0)
    assert calls == []


def test_type_text_of_empty_string_runs_nothing(monkeypatch):
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: calls.append(a))
    X11Injector().type_text("")
    assert calls == []


def test_active_window_returns_the_id(monkeypatch):
    class _R:
        returncode = 0
        stdout = "12582918\n"

    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: _R())
    assert X11Injector().active_window() == "12582918"


def test_active_window_is_empty_when_xdotool_fails(monkeypatch):
    def boom(*a, **kw):
        raise FileNotFoundError

    monkeypatch.setattr(subprocess, "run", boom)
    assert X11Injector().active_window() == ""
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_injector_x11.py -q`
Expected: FAIL — `ImportError: cannot import name 'backspace_command'`

- [ ] **Step 3: Write the implementation**

In `src/easytype/injector/x11.py`, add after `paste_key_command`:

```python
def backspace_command(count: int) -> list[str]:
    return ["xdotool", "key", "--clearmodifiers", "--repeat", str(count), "BackSpace"]
```

and add these methods to `X11Injector`, after `inject`:

```python
    def type_text(self, text: str) -> None:
        """Raw incremental typing for live dictation — no paste path, since
        clipboard round-trips several times a second would trample the clipboard."""
        if text:
            subprocess.run(type_command(text, self._delay), check=True)

    def backspace(self, count: int) -> None:
        if count > 0:
            subprocess.run(backspace_command(count), check=True)

    def active_window(self) -> str:
        """Focused window id, or "" when it cannot be determined. Callers treat ""
        as a mismatch, so a missing or broken xdotool disables typing rather than
        letting it write blind."""
        try:
            r = subprocess.run(["xdotool", "getactivewindow"],
                               capture_output=True, text=True, timeout=1)
            return r.stdout.strip() if r.returncode == 0 else ""
        except Exception:
            return ""
```

- [ ] **Step 4: Run them to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_injector_x11.py -q`
Expected: PASS.

- [ ] **Step 5: Full suite and commit**

```bash
.venv/bin/python -m pytest -q
git add src/easytype/injector/x11.py tests/test_injector_x11.py
git commit -m "feat: add incremental typing, backspace, and focus lookup to the X11 injector"
```

---

### Task 4: The settling rules

**Files:**
- Create: `src/easytype/live.py`
- Test: `tests/test_live.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `settled_prefix(previous: str, current: str) -> str`
  - `pending_chunk(processed: str, already_typed: str) -> str`

**The rule:** compare the two passes case-insensitively (Whisper flips the case
of the opening word as context arrives, and that must not block everything behind
it from settling), take the agreed leading run, then cut back to the last space
inside it. Characters are emitted from `current`, not `previous`, so the newer
spelling wins.

Cutting at the last space deliberately withholds the final agreed word: it sits
at the boundary of the agreed region and could still grow ("camera" → "cameras").

- [ ] **Step 1: Write the failing tests**

Create `tests/test_live.py`:

```python
from easytype.live import pending_chunk, settled_prefix


def test_settled_prefix_holds_back_the_last_agreed_word():
    # "camera" is agreed but sits at the boundary — it could still become "cameras".
    assert settled_prefix("check the camera", "check the camera counts") == "check the "


def test_settled_prefix_grows_as_passes_agree_on_more():
    # Always one word behind the agreed region: "counts" is agreed but withheld.
    assert settled_prefix(
        "check the camera counts", "check the camera counts at the site"
    ) == "check the camera "


def test_settled_prefix_is_empty_when_the_transcript_was_rewritten():
    assert settled_prefix("recognize speech", "wreck a nice beach") == ""


def test_settled_prefix_ignores_a_case_flip_on_the_opening_word():
    assert settled_prefix("Check the camera", "check the camera counts") == "check the "


def test_settled_prefix_emits_the_newer_spelling():
    settled = settled_prefix("Check the camera", "check the camera counts")
    assert settled.startswith("c")


def test_settled_prefix_with_no_complete_shared_word():
    assert settled_prefix("checking", "checkers") == ""


def test_settled_prefix_on_first_pass_has_nothing_to_agree_with():
    assert settled_prefix("", "check the camera") == ""


def test_pending_chunk_returns_what_is_not_yet_typed():
    assert pending_chunk("check the camera counts ", "check the ") == "camera counts "


def test_pending_chunk_is_empty_when_nothing_is_new():
    assert pending_chunk("check the ", "check the ") == ""


def test_pending_chunk_refuses_to_patch_a_changed_earlier_word():
    assert pending_chunk("wreck a nice beach ", "recognize ") == ""
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_live.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'easytype.live'`

- [ ] **Step 3: Write the implementation**

Create `src/easytype/live.py`:

```python
from __future__ import annotations


def settled_prefix(previous: str, current: str) -> str:
    """The leading run two consecutive passes agree on, cut back to whole words.

    Compared case-insensitively because Whisper flips the case of the opening word
    as context arrives; characters come from `current`, so the newer spelling wins.
    The final agreed word is withheld — it sits at the boundary and could still
    grow — which is also what keeps the downstream cleanup rules prefix-stable.
    """
    agreed = 0
    for a, b in zip(previous.lower(), current.lower()):
        if a != b:
            break
        agreed += 1
    cut = current.rfind(" ", 0, agreed)
    return current[: cut + 1] if cut >= 0 else ""


def pending_chunk(processed: str, already_typed: str) -> str:
    """The not-yet-typed remainder. Empty when `processed` is not an extension of
    what was typed: an earlier word changed, and append-only typing cannot fix
    that — finish() reconciles it once, at the end."""
    if not processed.startswith(already_typed):
        return ""
    return processed[len(already_typed):]
```

- [ ] **Step 4: Run them to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_live.py -q`
Expected: PASS, 10 tests.

- [ ] **Step 5: Full suite and commit**

```bash
.venv/bin/python -m pytest -q
git add src/easytype/live.py tests/test_live.py
git commit -m "feat: add the settling rules for live dictation"
```

---

### Task 5: The live typist

**Files:**
- Modify: `src/easytype/live.py`
- Test: `tests/test_live.py`

**Interfaces:**
- Consumes: `settled_prefix` / `pending_chunk` (Task 4); `type_text`,
  `backspace`, `active_window` (Task 3); `polish_stream` (Task 2);
  `apply_dictionary` from `easytype.dictionary`.
- Produces: `LiveTypist(injector, dictionary=())` with `start()`, `feed(raw)`,
  `finish(final) -> str`, `undo() -> bool`, and the `active` property.

**Ordering inside `feed` matters:** dictionary replacements are applied to the
*whole* settled text before the chunk is sliced off, so a multi-word rule
("ops plus" → "OPS+") still matches across what would otherwise be a chunk
boundary. `polish_stream` then runs on the result, and only then is the
already-typed part sliced away.

**What `finish` normally does:** `_typed` always trails the transcript by a word
or so, and the settled text is a clean prefix of the final one, so the usual case
is `extra == 0` — no backspace at all, just the tail appended. A backspace appears
only where the two genuinely disagree, and then only for as many characters as
they disagree on. Both the backspace and the type are guarded against zero-length
calls so the injector is never invoked for nothing.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_live.py`:

```python
from easytype.config import DictEntry
from easytype.live import LiveTypist


class FakeInjector:
    def __init__(self, window="win-1"):
        self.window = window
        self.typed = []
        self.backspaces = []

    def active_window(self):
        return self.window

    def type_text(self, text):
        self.typed.append(text)

    def backspace(self, count):
        self.backspaces.append(count)


def test_feed_types_each_settled_chunk_exactly_once():
    inj = FakeInjector()
    typist = LiveTypist(inj)
    typist.start()
    typist.feed("check the camera")
    typist.feed("check the camera counts")
    typist.feed("check the camera counts at the site")
    assert "".join(inj.typed) == "Check the camera "
    assert inj.backspaces == []


def test_feed_types_nothing_on_the_first_pass():
    inj = FakeInjector()
    typist = LiveTypist(inj)
    typist.start()
    typist.feed("check the camera")
    assert inj.typed == []


def test_multi_word_dictionary_rule_spanning_a_chunk_boundary():
    inj = FakeInjector()
    typist = LiveTypist(inj, dictionary=[DictEntry("ops plus", "OPS+", "smart")])
    typist.start()
    typist.feed("ops plus is")
    typist.feed("ops plus is ready")
    typist.feed("ops plus is ready now")
    assert "".join(inj.typed) == "OPS+ is "


def test_feed_does_not_type_when_focus_moved():
    inj = FakeInjector()
    typist = LiveTypist(inj)
    typist.start()
    inj.window = "win-2"
    typist.feed("check the camera")
    typist.feed("check the camera counts")
    assert inj.typed == []


def test_feed_resumes_when_focus_returns():
    inj = FakeInjector()
    typist = LiveTypist(inj)
    typist.start()
    inj.window = "win-2"
    typist.feed("check the camera")
    typist.feed("check the camera counts")
    inj.window = "win-1"
    typist.feed("check the camera counts at the site")
    assert "".join(inj.typed) == "Check the camera "


def test_feed_never_types_when_the_window_id_is_unknown():
    inj = FakeInjector(window="")
    typist = LiveTypist(inj)
    typist.start()
    typist.feed("check the camera")
    typist.feed("check the camera counts")
    assert inj.typed == []


def test_active_is_false_until_something_is_typed():
    inj = FakeInjector()
    typist = LiveTypist(inj)
    typist.start()
    assert typist.active is False
    typist.feed("check the camera")
    typist.feed("check the camera counts")
    assert typist.active is True


def test_finish_appends_the_remainder_and_the_closing_period():
    inj = FakeInjector()
    typist = LiveTypist(inj)
    typist.start()
    typist.feed("check the camera")
    typist.feed("check the camera counts")          # typed "Check the "
    inj.typed.clear()
    typist.finish("Check the camera counts.")
    assert inj.backspaces == []
    assert "".join(inj.typed) == "camera counts."


def test_finish_backspaces_only_back_to_the_divergence():
    inj = FakeInjector()
    typist = LiveTypist(inj)
    typist.start()
    typist.feed("check the camera counts")
    typist.feed("check the camera counts at")       # typed "Check the camera "
    inj.typed.clear()
    # The final pass settled on "cameras": the two agree through "Check the camera"
    # and diverge one character later, so exactly one character is taken back.
    typist.finish("Check the cameras on site.")
    assert inj.backspaces == [1]
    assert "".join(inj.typed) == "s on site."


def test_finish_types_nothing_when_focus_moved():
    inj = FakeInjector()
    typist = LiveTypist(inj)
    typist.start()
    typist.feed("check the camera")
    typist.feed("check the camera counts")
    inj.typed.clear()
    inj.window = "win-2"
    typist.finish("Check the camera counts.")
    assert inj.typed == []
    assert inj.backspaces == []


def test_undo_backspaces_exactly_what_was_typed():
    inj = FakeInjector()
    typist = LiveTypist(inj)
    typist.start()
    typist.feed("check the camera")
    typist.feed("check the camera counts")
    assert typist.undo() is True
    assert inj.backspaces == [len("Check the ")]
    assert typist.active is False


def test_undo_does_nothing_when_focus_moved():
    inj = FakeInjector()
    typist = LiveTypist(inj)
    typist.start()
    typist.feed("check the camera")
    typist.feed("check the camera counts")
    inj.window = "win-2"
    assert typist.undo() is False
    assert inj.backspaces == []


def test_undo_with_nothing_typed_is_a_noop():
    inj = FakeInjector()
    typist = LiveTypist(inj)
    typist.start()
    assert typist.undo() is True
    assert inj.backspaces == []


def test_start_clears_state_from_the_previous_recording():
    inj = FakeInjector()
    typist = LiveTypist(inj)
    typist.start()
    typist.feed("check the camera")
    typist.feed("check the camera counts")
    typist.start()
    assert typist.active is False
    inj.typed.clear()
    typist.feed("different words entirely")
    typist.feed("different words entirely now")
    assert "".join(inj.typed) == "Different words "
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_live.py -q`
Expected: FAIL — `ImportError: cannot import name 'LiveTypist'`

- [ ] **Step 3: Write the implementation**

Add to `src/easytype/live.py` (keeping the two functions above):

```python
from collections.abc import Sequence

from easytype.config import DictEntry
from easytype.dictionary import apply_dictionary
from easytype.polish import polish_stream


class LiveTypist:
    """Types settled dictation into the window that was focused when recording
    began. Append-only while recording — the only backspaces are undo() and the
    single reconciliation in finish(), both focus-guarded."""

    def __init__(self, injector, dictionary: Sequence[DictEntry] = ()):
        self._inj = injector
        self._dict = list(dictionary)
        self._window = ""
        self._previous = ""
        self._typed = ""
        self._warned = False

    @property
    def active(self) -> bool:
        return bool(self._typed)

    def start(self) -> None:
        self._window = self._inj.active_window()
        self._previous = ""
        self._typed = ""
        self._warned = False

    def feed(self, raw: str) -> None:
        settled = settled_prefix(self._previous, raw)
        self._previous = raw
        if not settled or not self._focused():
            return
        processed = polish_stream(apply_dictionary(settled, self._dict))
        chunk = pending_chunk(processed, self._typed)
        if chunk:
            self._inj.type_text(chunk)
            self._typed = processed

    def finish(self, final: str) -> str:
        """Reconcile the document with the authoritative final transcript. Usually
        an append; when the two diverge, backspace only as far back as they
        disagree."""
        if not self._focused():
            return ""
        keep = _common_prefix_len(self._typed, final)
        extra = len(self._typed) - keep
        if extra:
            self._inj.backspace(extra)
        tail = final[keep:]
        if tail:
            self._inj.type_text(tail)
        self._typed = final
        return tail

    def undo(self) -> bool:
        if not self._typed:
            return True
        if not self._focused():
            print(f"[easytype] left {len(self._typed)} characters in another window")
            return False
        self._inj.backspace(len(self._typed))
        self._typed = ""
        return True

    def _focused(self) -> bool:
        ok = bool(self._window) and self._inj.active_window() == self._window
        if ok:
            self._warned = False
        elif not self._warned:
            print("[easytype] live typing paused — focus is not on the original window")
            self._warned = True
        return ok


def _common_prefix_len(a: str, b: str) -> int:
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    return n
```

- [ ] **Step 4: Run them to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_live.py -q`
Expected: PASS, 24 tests.

- [ ] **Step 5: Full suite and commit**

```bash
.venv/bin/python -m pytest -q
git add src/easytype/live.py tests/test_live.py
git commit -m "feat: add the live typist"
```

---

### Task 6: Give the preview worker a generic sink

**Files:**
- Modify: `src/easytype/preview.py`
- Test: `tests/test_preview.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `PreviewWorker(recorder, transcriber, on_text, interval=PREVIEW_INTERVAL)`
  where `on_text: Callable[[str], None]`. The `indicator` parameter is gone.

**Why:** the worker should not know whether its transcript becomes a caption or
keystrokes. With a callback, "caption or type, never both" is decided once by the
engine and needs no flag inside the worker.

- [ ] **Step 1: Update the tests**

In `tests/test_preview.py`, replace the `FakeIndicator` class with a collector:

```python
class Collector:
    def __init__(self):
        self.texts = []

    def __call__(self, text):
        self.texts.append(text)
```

Replace the `_worker` helper:

```python
def _worker(recorder=None, transcriber=None, on_text=None):
    return PreviewWorker(
        recorder or FakeRecorder(),
        transcriber or FakeTranscriber(),
        on_text or Collector(),
        interval=0.01,
    )
```

Then update the four tests that assert on captions to use the collector — for
example:

```python
def test_a_pass_publishes_the_transcribed_snapshot():
    sink = Collector()
    worker = _worker(on_text=sink)
    worker._pass()
    assert sink.texts == ["preview text"]


def test_audio_below_the_minimum_is_not_transcribed():
    tx = FakeTranscriber()
    sink = Collector()
    worker = _worker(recorder=FakeRecorder(seconds=MIN_PREVIEW_SECONDS / 2),
                     transcriber=tx, on_text=sink)
    worker._pass()
    assert tx.calls == 0
    assert sink.texts == []


def test_empty_transcript_is_not_published():
    sink = Collector()
    worker = _worker(transcriber=FakeTranscriber(text="   "), on_text=sink)
    worker._pass()
    assert sink.texts == []


def test_a_pass_finishing_after_stop_publishes_nothing():
    sink = Collector()
    worker = _worker(on_text=sink)
    worker.stop()
    worker._pass()
    assert sink.texts == []
```

The remaining three tests (transcriber failure, thread cleanup, idempotent start)
need no change.

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_preview.py -q`
Expected: FAIL — the worker still calls `self._ind.caption`, so `Collector` never
receives anything and `AttributeError: 'Collector' object has no attribute 'caption'`.

- [ ] **Step 3: Write the implementation**

In `src/easytype/preview.py`, change the constructor:

```python
    def __init__(self, recorder, transcriber, on_text, interval: float = PREVIEW_INTERVAL):
        self._rec = recorder
        self._tx = transcriber
        self._on_text = on_text
        self._interval = interval
```

and the last line of `_pass`:

```python
        if text.strip() and not self._stop.is_set():
            self._on_text(text)
```

- [ ] **Step 4: Run them to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_preview.py -q`
Expected: PASS, 7 tests.

- [ ] **Step 5: Full suite, and confirm the one stale call site**

```bash
.venv/bin/python -m pytest -q
grep -n "PreviewWorker(" src/easytype/engine.py
```

Expected: the suite is green — no test builds the real engine, so nothing
exercises `build_engine`. The grep shows the single remaining call site, which
still passes an indicator where `on_text` now goes; Task 8 fixes it. Do not fix
it here.

- [ ] **Step 6: Commit**

```bash
git add src/easytype/preview.py tests/test_preview.py
git commit -m "refactor: give the preview worker a text sink instead of an indicator"
```

---

### Task 7: The `inject_live` setting

**Files:**
- Modify: `src/easytype/config.py`, `config.sample.toml`, `src/easytype/gui/settings.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `Config.inject_live: bool` (default `False`) and the
  `"inject_live"` settings-dict key.

- [ ] **Step 1: Write the failing tests**

In `tests/test_config.py`, add to `SAMPLE_SETTINGS`:

```python
    "preview_model": "base.en",
    "inject_live": True,
}
```

Add to `test_load_creates_default_when_missing`:

```python
    assert c.inject_live is False
```

Add to `test_apply_settings_round_trips`:

```python
    assert c.inject_live is True
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_config.py -q`
Expected: FAIL — no `inject_live` attribute, plus `KeyError: 'inject_live'`.

- [ ] **Step 3: Write the implementation**

In `src/easytype/config.py`, extend the `[preview]` block in
`DEFAULT_CONFIG_TOML`:

```toml
[preview]
enabled = true                     # show a running transcript while you speak
model = "tiny.en"                  # "" = reuse the transcription model (exact, but slower)
inject_live = false                # type settled words into the focused app as you speak
```

Add to the `Config` dataclass after `preview_model: str`:

```python
    inject_live: bool
```

In `load_config`, add to the `Config(...)` construction after `preview_model=...`:

```python
        inject_live=bool(prev.get("inject_live", False)),
```

In `apply_settings_to_doc`, in the preview block:

```python
    prev["inject_live"] = bool(values["inject_live"])
```

Mirror the same TOML line into `config.sample.toml`.

- [ ] **Step 4: Run them to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_config.py -q`
Expected: PASS.

- [ ] **Step 5: Add the Settings checkbox**

In `src/easytype/gui/settings.py`, in `_indicator_tab`, after the
`self.preview_model` block:

```python
        self.inject_live = QCheckBox("Type text into the app as I speak (experimental)")
        self.inject_live.setToolTip(
            "Words are typed into whatever window you started dictating in, about "
            "two seconds behind your voice. Uses your main transcription model, "
            "ignoring the preview model above. Not available while AI cleanup is on."
        )
```

and the row after `form.addRow("Preview model", self.preview_model)`:

```python
        form.addRow(self.inject_live)
```

In `_load`, after `self.preview_model.setCurrentText(c.preview_model)`:

```python
        self.inject_live.setChecked(c.inject_live)
```

In `_values`, after `"preview_model"`:

```python
            "inject_live": self.inject_live.isChecked(),
```

- [ ] **Step 6: Full suite and commit**

```bash
.venv/bin/python -m pytest -q
git add src/easytype/config.py config.sample.toml src/easytype/gui/settings.py tests/test_config.py
git commit -m "feat: add the inject_live setting"
```

---

### Task 8: Wire live typing through the controller and engine

**Files:**
- Modify: `src/easytype/controller.py`, `src/easytype/engine.py`
- Test: `tests/test_controller.py`

**Interfaces:**
- Consumes: `LiveTypist` (Task 5), `PreviewWorker(…, on_text)` (Task 6),
  `Config.inject_live` (Task 7).
- Produces: `Controller(..., live=None)`.

**Two rules the engine enforces, not the controller:**
1. Live typing uses `config.model`, never `config.preview_model`, and reuses the
   one `Transcriber` already built for the final pass.
2. Live typing is skipped while the formatter is on — a global rewrite cannot be
   applied append-only. The user's formatter setting is not changed; they are told.

**Why `finish` only when `active`:** if nothing settled (a very short recording,
or focus never matched), nothing was typed, so the normal injector path should
run instead and put the whole transcript in.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_controller.py`:

```python
class FakeLive:
    def __init__(self, active=False):
        self.events = []
        self.active = active
        self.finished = None

    def start(self):
        self.events.append("start")

    def finish(self, text):
        self.events.append("finish")
        self.finished = text
        return text

    def undo(self):
        self.events.append("undo")
        return True


def _build_with_live(tmp_path, live):
    inj = FakeInjector()
    ctrl = Controller(
        config=load_config(tmp_path / "c.toml"), recorder=FakeRecorder(),
        transcriber=FakeTranscriber(), injector=inj,
        indicator=FakeIndicator(), notify=lambda *a: None, live=live,
    )
    return ctrl, inj


def test_recording_starts_the_live_typist(tmp_path):
    live = FakeLive()
    ctrl, _ = _build_with_live(tmp_path, live)
    ctrl.on_record()
    assert live.events == ["start"]


def test_finish_replaces_injection_when_live_typing_is_active(tmp_path):
    live = FakeLive(active=True)
    ctrl, inj = _build_with_live(tmp_path, live)
    ctrl.on_record()
    ctrl.on_record()
    assert live.finished == "Ops plus is ready."
    assert inj.injected == []


def test_injection_still_runs_when_nothing_was_typed_live(tmp_path):
    live = FakeLive(active=False)
    ctrl, inj = _build_with_live(tmp_path, live)
    ctrl.on_record()
    ctrl.on_record()
    assert "finish" not in live.events
    assert inj.injected == [("Ops plus is ready.", "type")]


def test_cancel_undoes_live_typing(tmp_path):
    live = FakeLive(active=True)
    ctrl, _ = _build_with_live(tmp_path, live)
    ctrl.on_record()
    ctrl.on_cancel()
    assert "undo" in live.events


def test_history_still_written_with_live_typing(tmp_path, history_file):
    live = FakeLive(active=True)
    ctrl, _ = _build_with_live(tmp_path, live)
    ctrl.on_record()
    ctrl.on_record()
    assert [e.text for e in history.read(history_file)] == ["Ops plus is ready."]
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_controller.py -q`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'live'`

- [ ] **Step 3: Write the controller implementation**

In `src/easytype/controller.py`, add the parameter to `__init__` after
`preview=None`:

```python
                 live=None,
```

and the assignment after `self._preview = preview`:

```python
        self._live = live
```

In `_start`, before the preview worker starts (so the window id is captured
before any transcript can arrive):

```python
        if self._live:
            self._live.start()
```

In `on_cancel`, in the `recording` branch, after `self._stop_preview()`:

```python
                if self._live:
                    self._live.undo()
```

In `process_audio`, replace the injection line:

```python
        if text:
            self.last_transcript = text
            self._record_history(text)
            if self._live and self._live.active:
                self._live.finish(text)
            else:
                self._inj.inject(text, self._cfg.injection_method)
        return text
```

- [ ] **Step 4: Run them to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_controller.py -q`
Expected: PASS.

- [ ] **Step 5: Wire the engine**

In `src/easytype/engine.py`, add to the local imports:

```python
    from easytype.live import LiveTypist
```

Replace everything from `recorder = Recorder(...)` down to the end of the
`Controller(...)` construction with:

```python
    recorder = Recorder(config.audio_device)
    indicator = create_indicator(config)
    injector = get_injector(session, config.type_delay_ms)

    live = None
    preview = None
    preview_transcriber = None

    if config.inject_live and config.formatter_enabled:
        notify("EasyType", "Live typing is off while AI cleanup is on")

    if config.inject_live and not config.formatter_enabled:
        # Live typing reuses the main transcriber: what gets typed must be the
        # quality the user already expects, and a second copy of the same model
        # would cost VRAM for nothing.
        live = LiveTypist(injector, config.dictionary)
        preview = PreviewWorker(recorder, transcriber, live.feed)
    elif config.preview_enabled and not indicator.is_null:
        preview_transcriber = Transcriber(
            config.preview_model or config.model, config.language,
            config.transcribe_device, initial_prompt=config.initial_prompt,
        )
        preview = PreviewWorker(recorder, preview_transcriber, indicator.caption)

    controller = Controller(
        config=config,
        recorder=recorder,
        transcriber=transcriber,
        injector=injector,
        indicator=indicator,
        notify=notify,
        media=MediaController(),
        preview=preview,
        live=live,
        synchronous=False,
    )
```

- [ ] **Step 6: Full suite and commit**

```bash
.venv/bin/python -m pytest -q
git add src/easytype/controller.py src/easytype/engine.py tests/test_controller.py
git commit -m "feat: type dictation into the focused app as you speak"
```

---

### Task 9: Verify live, document, and ship

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Turn it on and restart**

Enable it in the real config, then restart (editable pipx install — code changes
need a restart):

```bash
python3 - <<'EOF'
from pathlib import Path
import tomlkit
p = Path("~/.config/easytype/config.toml").expanduser()
doc = tomlkit.parse(p.read_text())
doc.setdefault("preview", tomlkit.table())["inject_live"] = True
p.write_text(tomlkit.dumps(doc))
print(p.read_text())
EOF

ps -eo pid,cmd | awk '/easytype-gui/ && !/awk/ {print $1}' | xargs -r kill
sleep 3
cd ~ && DISPLAY=:0 XDG_RUNTIME_DIR=/run/user/1000 setsid nohup easytype-gui >/tmp/et-live.log 2>&1 </dev/null &
```

Note the `awk` form rather than `pkill -f easytype-gui`: `pkill` matches the
running shell's own command line and kills the session.

- [ ] **Step 2: Verify by hand**

Open a text editor, click into it, and check each:
- Dictate a long sentence. Words appear in the editor a couple of seconds behind
  your voice; the indicator shows the timer only, no caption box.
- Stop. The final words and the closing period land, and the sentence reads
  correctly end to end.
- Dictate again, and press Esc partway. Everything typed this session is removed.
- Dictate, then click into a different window mid-sentence. Typing stops. Click
  back. Typing resumes without losing words.
- Dictate, click away, then press Esc. Nothing is deleted from the other window;
  the log says how many characters were left behind.
- Dictate a phrase using one of your dictionary rules and confirm the replacement
  is applied in the typed text.
- Untick "Type text into the app as I speak" in Settings → Indicator, Save,
  dictate. Old behavior returns: caption box in the indicator, text injected at
  the end.
- Check `Recent` in the tray still lists the dictations.

Check the log:

```bash
grep -i -E 'live typing|traceback|error' /tmp/et-live.log
```

- [ ] **Step 3: Judge the two known risks**

Both were flagged in the design and can only be settled on real hardware:
- **Keeping up.** If text lags well beyond ~2s or arrives in visible bursts, the
  40ms `type_delay_ms` is the likely cause. Report the observed behavior rather
  than guessing a new number.
- **GPU load.** Run `nvidia-smi` during a long dictation. If `medium.en` once a
  second starves Ollama or the passes take longer than the interval, say so —
  the fallback is a smaller transcription model.

- [ ] **Step 4: Document it**

In `README.md`, add this immediately after the `## Live preview` section:

```markdown
## Typing as you speak

With **Type text into the app as I speak** ticked in Settings → Indicator, words
go straight into whatever window you started dictating in, rather than arriving
all at once when you stop.

A word is typed once two consecutive transcription passes agree on it, so text
lands about two seconds behind your voice and the remainder arrives when you
stop. That delay is what makes it safe: EasyType never backspaces to correct
itself mid-sentence, so it can't damage text already in your document.

- It types **only into the window you started in**. Switch away and it pauses;
  switch back and it resumes.
- **Esc** removes everything it typed — as long as you are still in that window.
  Otherwise it stops and leaves the text where it is.
- It uses your main transcription model, ignoring the preview model setting, so
  what gets typed is the same quality as normal dictation.
- It is unavailable while AI cleanup is on, because that rewrites the whole
  transcript at the end and cannot be applied a few words at a time.
```

- [ ] **Step 5: Full suite, push, and open the PR**

```bash
.venv/bin/python -m pytest -q
git add README.md
git commit -m "docs: document typing as you speak"
git push -u origin live-typing
```

```bash
gh auth switch -h github.com -u jeffharlan >/dev/null 2>&1
gh pr create --title "feat: type dictation into the focused app as you speak" --body "$(cat <<'EOF'
Dictation now lands in the window you are working in, as you speak, instead of
arriving all at once when you stop.

- `live.py` — settles a word once two consecutive passes agree on it, trimmed to
  whole words, then types the new remainder. Append-only while recording.
- Focus-guarded: types only into the window focused at the start, pauses when you
  switch away, resumes when you return. An unknown window id counts as a
  mismatch, so a broken xdotool disables typing rather than writing blind.
- Esc backspaces exactly what was typed, when still in that window.
- `finish` reconciles against the authoritative final transcript, backspacing only
  as far as the two disagree.
- `polish.py` splits out a prefix-stable `polish_stream` so capitalization can be
  applied per chunk instead of to the finished transcript.
- `Transcriber.transcribe` takes a lock: preview and the final pass now share one
  model across threads.
- Off by default; unavailable while AI cleanup is on.

Design: `docs/superpowers/specs/2026-08-14-live-typing-design.md`

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Note: `gh` is signed in as `jeffereyharlan` by default, which cannot open PRs on
this repo, and the active account resets between shells — so the switch and the
`gh` command must run in the same invocation.

- [ ] **Step 6: Wait for CI, merge, restart**

```bash
gh pr checks --watch
```

then, in a single invocation:

```bash
gh auth switch -h github.com -u jeffharlan >/dev/null 2>&1; gh pr merge --squash --delete-branch
```

Afterwards restore the original account and restart the app:

```bash
gh auth switch -h github.com -u jeffereyharlan >/dev/null 2>&1
ps -eo pid,cmd | awk '/easytype-gui/ && !/awk/ {print $1}' | xargs -r kill
sleep 3
cd ~ && DISPLAY=:0 XDG_RUNTIME_DIR=/run/user/1000 setsid nohup easytype-gui >/tmp/et-gui.log 2>&1 </dev/null &
```

- [ ] **Step 7: Confirm main is clean**

Run: `git status --short && git log --oneline -1`
Expected: no changes, squashed commit at the tip.
