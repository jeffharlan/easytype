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
