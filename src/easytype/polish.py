from __future__ import annotations

import re

_SPACE_BEFORE_PUNCT = re.compile(r"[ \t]+([,.;:!?])")
_REPEATED_SPACE = re.compile(r"[ \t]{2,}")
_STANDALONE_I = re.compile(r"\bi\b")
_FIRST_LETTER = re.compile(r"^(\s*)([a-z])")
_AFTER_SENTENCE = re.compile(r"([.!?]\s+)([a-z])")
_AFTER_BREAK = re.compile(r"(\n[ \t]*)([a-z])")


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
    text = _AFTER_SENTENCE.sub(lambda m: m.group(1) + m.group(2).upper(), text)
    return _AFTER_BREAK.sub(lambda m: m.group(1) + m.group(2).upper(), text)


def polish_text(text: str) -> str:
    """Deterministic sentence polish applied to every transcript: capitalize
    sentence starts and standalone "I", and tidy spacing. Rules, not a model, so
    the mechanical fixes are always correct even when AI cleanup is off.

    No closing period is invented. Measured on small.en, Whisper ends a finished
    sentence itself and leaves a trailing-off one bare, so a bare ending is a
    signal the speaker is not done — forcing a period there broke every dictation
    that stopped mid-thought. Say "period" to insist on one."""
    if not text.strip():
        return text
    return polish_stream(text).rstrip().rstrip(",;:")
