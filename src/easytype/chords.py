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
