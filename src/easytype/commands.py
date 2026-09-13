from __future__ import annotations

import re

SCRATCH_PHRASE = "scratch that"

# Longest first: a shorter phrase must never consume the opening words of a
# longer one ("new line" inside "new paragraph" would, if the order flipped).
SWAPS: tuple[tuple[str, str], ...] = (
    ("exclamation point", "!"),
    ("question mark", "?"),
    ("new paragraph", "\n\n"),
    ("new line", "\n"),
    ("newline", "\n"),
    ("period", "."),
    ("comma", ","),
)


def _phrase(phrase: str) -> re.Pattern[str]:
    """Whole-phrase, case-insensitive, trailing punctuation absorbed. Whisper
    routinely returns "New paragraph." rather than the bare words, so the period
    it added has to disappear with the phrase or it lands in the document."""
    return re.compile(r"\b" + re.escape(phrase) + r"\b[.,!?]*", re.IGNORECASE)


_SWAP_PATTERNS = tuple((_phrase(p), out) for p, out in SWAPS)
_SCRATCH_PATTERN = _phrase(SCRATCH_PHRASE)


def apply_commands(text: str) -> str:
    for pattern, out in _SWAP_PATTERNS:
        text = pattern.sub(lambda _m, o=out: o, text)
    return text


def split_scratch(text: str) -> tuple[str, bool]:
    """What survives "scratch that", and whether the dictation before this one
    should go too. Nothing spoken ahead of the first "scratch that" means the
    correction was aimed at what is already on screen, not at this dictation."""
    matches = list(_SCRATCH_PATTERN.finditer(text))
    if not matches:
        return text, False
    tail = text[matches[-1].end():].strip()
    return tail, not text[: matches[0].start()].strip()
