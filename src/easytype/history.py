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
