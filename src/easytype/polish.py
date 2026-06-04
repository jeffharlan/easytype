from __future__ import annotations

import re

_SPACE_BEFORE_PUNCT = re.compile(r"\s+([,.;:!?])")
_REPEATED_SPACE = re.compile(r"[ \t]{2,}")
_STANDALONE_I = re.compile(r"\bi\b")
_FIRST_LETTER = re.compile(r"^(\s*)([a-z])")
_AFTER_SENTENCE = re.compile(r"([.!?]\s+)([a-z])")


def polish_text(text: str) -> str:
    """Deterministic sentence polish applied to every transcript: capitalize
    sentence starts and standalone "I", and tidy spacing. Rules, not a model, so
    the mechanical fixes are always correct even when AI cleanup is off."""
    if not text.strip():
        return text
    text = _SPACE_BEFORE_PUNCT.sub(r"\1", text)
    text = _REPEATED_SPACE.sub(" ", text)
    text = _STANDALONE_I.sub("I", text)
    text = _FIRST_LETTER.sub(lambda m: m.group(1) + m.group(2).upper(), text)
    text = _AFTER_SENTENCE.sub(lambda m: m.group(1) + m.group(2).upper(), text)
    text = text.rstrip()
    if text and text[-1] not in ".!?":
        text = text.rstrip(",;:") + "."
    return text
