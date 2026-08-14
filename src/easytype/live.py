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
