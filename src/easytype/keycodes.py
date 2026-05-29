from __future__ import annotations

# Friendly names for the keys we expect in hotkeys; falls back to evdev's KEY_ name.
_FRIENDLY = {
    29: "Ctrl", 97: "Ctrl", 56: "Alt", 100: "Alt", 42: "Shift", 54: "Shift",
    125: "Super", 126: "Super", 57: "Space", 1: "Esc", 43: "\\",
    66: "F8", 67: "F9",
}

# Informational only: chord (sorted) -> human note. Never used to block.
_CONFLICTS = {
    (29, 57): "Ctrl+Space normally toggles the IBus input method. EasyType's consume "
              "feature swallows it, so the toggle won't fire while EasyType runs.",
    (29, 43): "Ctrl+\\ normally sends SIGQUIT in a terminal. EasyType's consume feature "
              "swallows it, so no SIGQUIT will fire while EasyType runs.",
}


def _name(code: int) -> str:
    if code in _FRIENDLY:
        return _FRIENDLY[code]
    try:
        from evdev import ecodes
        raw = ecodes.KEY[code]
        label = raw[0] if isinstance(raw, list) else raw
        return label.replace("KEY_", "").title()
    except Exception:
        return f"key{code}"


def describe_chord(keys: list[int]) -> str:
    return "+".join(_name(k) for k in keys)


def conflict_note(keys: list[int]) -> str | None:
    return _CONFLICTS.get(tuple(sorted(keys)))
