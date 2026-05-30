from __future__ import annotations

from dataclasses import dataclass

# evdev modifier keycodes
MODIFIERS = frozenset({29, 97, 56, 100, 42, 54, 125, 126})
# 29=LCTRL 97=RCTRL 56=LALT 100=RALT 42=LSHIFT 54=RSHIFT 125=LMETA 126=RMETA

# Left/right variants of a modifier are interchangeable: pressing either Ctrl
# satisfies a hotkey that names Ctrl. Map each right-variant to its left canonical.
_CANON = {97: 29, 100: 56, 54: 42, 126: 125}


def _canon(code: int) -> int:
    return _CANON.get(code, code)


def trigger_key(chord: tuple[int, ...]) -> int:
    non_mods = [k for k in chord if k not in MODIFIERS]
    return non_mods[-1] if non_mods else chord[-1]


@dataclass(frozen=True)
class KeyOutcome:
    swallow: bool
    pressed: str | None = None   # chord name whose trigger just went down (mods held)
    released: str | None = None  # chord name whose trigger just went up


class HotkeyEngine:
    """Pure consume/match engine. Feed raw key events; get swallow + fire decisions.
    Left/right modifier variants are treated as equivalent when matching."""

    def __init__(self, chords: dict[str, tuple[int, ...]]):
        self._chords = {name: tuple(keys) for name, keys in chords.items()}
        self._triggers = {name: trigger_key(keys) for name, keys in self._chords.items()}
        self._mods = {
            name: frozenset(_canon(k) for k in keys if k != self._triggers[name])
            for name, keys in self._chords.items()
        }
        self._held: set[int] = set()
        self._swallowed: set[int] = set()      # trigger codes we are actively swallowing
        self._active: dict[int, str] = {}       # trigger code -> chord name currently firing

    def _fire_candidate(self, code: int, enabled: set[str]) -> str | None:
        held_canon = {_canon(h) for h in self._held}
        for name in self._chords:
            if name not in enabled:
                continue
            if _canon(self._triggers[name]) != _canon(code):
                continue
            if self._mods[name] <= held_canon:
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


class ChordCollector:
    """Records the first-press order of a key chord and reports completion once
    every pressed key is released. Shared by the CLI `--set-hotkey` capture and
    the GUI's in-window 'Set' capture."""

    def __init__(self) -> None:
        self._pressed: list[int] = []   # first-press order
        self._seen: set[int] = set()
        self._down: set[int] = set()
        self._done = False

    def feed(self, code: int, value: int) -> bool:
        if value == 1:                  # key down
            if code not in self._seen:
                self._seen.add(code)
                self._pressed.append(code)
            self._down.add(code)
        elif value == 0:                # key up
            self._down.discard(code)
            if self._pressed and not self._down:
                self._done = True
        return self._done

    @property
    def keys(self) -> list[int]:
        return list(self._pressed)
