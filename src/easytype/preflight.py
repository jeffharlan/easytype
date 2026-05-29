from __future__ import annotations

import grp
import os
import shutil
from dataclasses import dataclass

REQUIRED_BINARIES = ("xdotool", "xclip", "notify-send")


@dataclass(frozen=True)
class Issue:
    name: str
    ok: bool
    fix: str


def detect_session() -> str:
    if os.environ.get("WAYLAND_DISPLAY") or os.environ.get("XDG_SESSION_TYPE") == "wayland":
        return "wayland"
    if os.environ.get("XDG_SESSION_TYPE") == "x11" or os.environ.get("DISPLAY"):
        return "x11"
    return "unknown"


def gather_issues(*, groups, uinput_writable, binaries, tk_ok) -> list[Issue]:
    issues: list[Issue] = []
    issues.append(Issue(
        "input group", "input" in groups,
        "Add yourself to the 'input' group, then log out and back in:\n"
        "    sudo usermod -aG input $USER",
    ))
    issues.append(Issue(
        "/dev/uinput access", uinput_writable,
        "Allow access to /dev/uinput via a udev rule, then reload:\n"
        "    echo 'KERNEL==\"uinput\", GROUP=\"input\", MODE=\"0660\"' "
        "| sudo tee /etc/udev/rules.d/99-easytype-uinput.rules\n"
        "    sudo modprobe uinput\n"
        "    sudo udevadm control --reload-rules && sudo udevadm trigger",
    ))
    for name in REQUIRED_BINARIES:
        issues.append(Issue(
            name, binaries.get(name, False),
            f"Install {name}:\n    sudo apt install {name}",
        ))
    issues.append(Issue(
        "python3-tk (recording indicator)", tk_ok,
        "Install Tkinter for the on-screen timer (optional — falls back to notifications):\n"
        "    sudo apt install python3-tk",
    ))
    return issues


def _current_groups() -> list[str]:
    names = [grp.getgrgid(gid).gr_name for gid in os.getgroups()]
    try:
        names.append(grp.getgrgid(os.getgid()).gr_name)
    except KeyError:
        pass
    return names


def _uinput_writable() -> bool:
    return os.access("/dev/uinput", os.W_OK)


def _tk_available() -> bool:
    try:
        import tkinter  # noqa: F401
        return True
    except Exception:
        return False


def check() -> list[Issue]:
    return gather_issues(
        groups=_current_groups(),
        uinput_writable=_uinput_writable(),
        binaries={b: shutil.which(b) is not None for b in REQUIRED_BINARIES},
        tk_ok=_tk_available(),
    )


def format_report(issues: list[Issue]) -> str:
    lines = ["EasyType preflight:\n"]
    for i in issues:
        mark = "OK  " if i.ok else "FAIL"
        lines.append(f"  [{mark}] {i.name}")
        if not i.ok:
            for fixline in i.fix.splitlines():
                lines.append(f"         {fixline}")
    blocking = [i for i in issues if not i.ok and i.name != "python3-tk (recording indicator)"]
    if blocking:
        lines.append("\nGrab mode needs the FAIL items above. Until then, run with --passive.")
    else:
        lines.append("\nAll required checks passed.")
    return "\n".join(lines)
