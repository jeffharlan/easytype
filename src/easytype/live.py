from __future__ import annotations

from collections.abc import Sequence

from easytype.config import DictEntry
from easytype.dictionary import apply_dictionary
from easytype.polish import polish_stream

# Live chunks are small and frequent, so keystroke delay is a direct tax on how far
# behind your voice the text lands. Measured on X11/GTK: 40ms costs ~21ms per
# character, 10ms costs ~6ms, and text arrives intact at both.
LIVE_TYPE_DELAY_MS = 10


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
            self._inj.type_text(chunk, LIVE_TYPE_DELAY_MS)
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
            self._inj.type_text(tail, LIVE_TYPE_DELAY_MS)
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
