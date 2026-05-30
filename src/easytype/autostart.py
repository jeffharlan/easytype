from __future__ import annotations

from pathlib import Path

AUTOSTART_PATH = Path("~/.config/autostart/easytype.desktop").expanduser()

_DESKTOP_ENTRY = """\
[Desktop Entry]
Type=Application
Name=EasyType
Comment=Local voice dictation (system tray)
Exec=easytype-gui
Icon=easytype
Terminal=false
Categories=Utility;Accessibility;
X-GNOME-Autostart-enabled=true
"""


def is_enabled(path: Path = AUTOSTART_PATH) -> bool:
    return path.exists()


def set_enabled(on: bool, path: Path = AUTOSTART_PATH) -> None:
    if on:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_DESKTOP_ENTRY)
    elif path.exists():
        path.unlink()
