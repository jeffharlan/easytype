from __future__ import annotations

import grp
import os
import shutil
from dataclasses import dataclass

REQUIRED_BINARIES_X11 = ("xdotool", "xclip", "notify-send")
REQUIRED_BINARIES_WAYLAND = ("ydotool", "wl-copy", "wl-paste", "notify-send")


@dataclass(frozen=True)
class Issue:
    name: str
    ok: bool
    fix: str


def binaries_for(session: str) -> tuple[str, ...]:
    return REQUIRED_BINARIES_WAYLAND if session == "wayland" else REQUIRED_BINARIES_X11


def detect_session() -> str:
    if os.environ.get("WAYLAND_DISPLAY") or os.environ.get("XDG_SESSION_TYPE") == "wayland":
        return "wayland"
    if os.environ.get("XDG_SESSION_TYPE") == "x11" or os.environ.get("DISPLAY"):
        return "x11"
    return "unknown"


# Debian/Ubuntu package that provides each binary, where it differs from the
# binary's own name (notify-send ships in libnotify-bin; wl-copy and wl-paste
# both ship in wl-clipboard).
_APT_PACKAGE = {
    "notify-send": "libnotify-bin",
    "wl-copy": "wl-clipboard",
    "wl-paste": "wl-clipboard",
}


def gather_issues(*, groups, uinput_writable, binaries, tk_ok, session: str = "x11",
                  ydotoold_running: bool = True) -> list[Issue]:
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
    for name in binaries_for(session):
        pkg = _APT_PACKAGE.get(name, name)
        issues.append(Issue(
            name, binaries.get(name, False),
            f"Install {name}:\n    sudo apt install {pkg}",
        ))
    if session == "wayland":
        issues.append(Issue(
            "ydotoold running", ydotoold_running,
            "Start the ydotool daemon (needed for ydotool to type/click at all):\n"
            "    systemctl --user enable --now ydotool",
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


def _ydotoold_running() -> bool:
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    socket_path = os.environ.get("YDOTOOL_SOCKET", f"{runtime_dir}/.ydotool_socket")
    return os.path.exists(socket_path)


def check(session: str | None = None) -> list[Issue]:
    session = session if session is not None else detect_session()
    return gather_issues(
        groups=_current_groups(),
        uinput_writable=_uinput_writable(),
        binaries={b: shutil.which(b) is not None for b in binaries_for(session)},
        tk_ok=_tk_available(),
        session=session,
        ydotoold_running=_ydotoold_running(),
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
