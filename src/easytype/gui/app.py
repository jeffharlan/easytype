from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QRectF
from PySide6.QtGui import QAction, QBrush, QColor, QCursor, QFont, QIcon, QPainter, QPen, QPixmap
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from easytype import preflight
from easytype.config import load_config, load_doc, save_doc
from easytype.supervisor import EngineSupervisor

_LOCK_NAME = "easytype-gui-singleton"
_STYLE = Path(__file__).with_name("style.qss")

_STATUS_LABELS = {
    "recording": "Recording…", "transcribing": "Transcribing…",
    "idle": "Idle", "stopped": "Stopped", "disabled": "Disabled (Wayland)",
}


def make_icon(active: bool) -> QIcon:
    pm = QPixmap(64, 64)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(QColor("#f59e0b")))
    p.drawRoundedRect(QRectF(4, 4, 56, 56), 14, 14)
    p.setPen(QColor("#241a06"))
    font = QFont("Sans", 34)
    font.setBold(True)
    p.setFont(font)
    p.drawText(pm.rect(), Qt.AlignCenter, "E")
    if active:
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor("#ffffff"), 4))
        p.drawRoundedRect(QRectF(3, 3, 58, 58), 15, 15)
    p.end()
    return QIcon(pm)


def _already_running() -> bool:
    sock = QLocalSocket()
    sock.connectToServer(_LOCK_NAME)
    running = sock.waitForConnected(150)
    sock.close()
    return running


class TrayApp:
    def __init__(self, app: QApplication):
        self._app = app
        self._idle_icon = make_icon(False)
        self._active_icon = make_icon(True)
        self._settings_window = None

        session = preflight.detect_session()
        self._wayland = session == "wayland"
        grab = self._decide_grab()
        self._passive = not self._wayland and not grab
        self._sup = EngineSupervisor(session=session, grab=grab)

        if self._wayland:
            QMessageBox.warning(
                None, "EasyType",
                "EasyType dictation needs an X11 session; Wayland isn't supported yet.\n"
                "You can still edit Settings, but dictation won't run.",
            )
        else:
            self._sup.start()

        self._mode = str(load_config().capture_mode)

        self._tray = QSystemTrayIcon(self._idle_icon)
        self._build_menu()
        self._tray.show()

        self._timer = QTimer()
        self._timer.timeout.connect(self._refresh)
        self._timer.start(200)
        self._refresh()

    def _decide_grab(self) -> bool:
        issues = preflight.check()
        blocking = [i for i in issues if not i.ok and not i.name.startswith("python3-tk")]
        return not blocking

    def _build_menu(self):
        menu = QMenu()
        self._status_action = QAction("Idle")
        self._status_action.setEnabled(False)
        menu.addAction(self._status_action)
        menu.addSeparator()

        self._toggle_rec = QAction("Start dictation")
        self._toggle_rec.triggered.connect(self._sup.toggle_recording)
        menu.addAction(self._toggle_rec)

        self._mode_action = QAction("Switch to Hold mode")
        self._mode_action.triggered.connect(self._switch_mode)
        menu.addAction(self._mode_action)
        menu.addSeparator()

        settings = QAction("Settings…")
        settings.triggered.connect(self._open_settings)
        menu.addAction(settings)

        quit_action = QAction("Quit")
        quit_action.triggered.connect(self._quit)
        menu.addAction(quit_action)

        self._menu = menu
        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._on_activated)
        self._update_mode_label()

    def _on_activated(self, reason):
        # A left-click (Trigger) doesn't open the context menu by default; pop it
        # ourselves so a single click on the tray icon shows the menu.
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._menu.popup(QCursor.pos())

    def _update_mode_label(self):
        self._mode_action.setText(
            "Switch to Hold mode" if self._mode == "toggle" else "Switch to Toggle mode"
        )

    def _switch_mode(self):
        self._mode = "hold" if self._mode == "toggle" else "toggle"
        doc = load_doc()
        doc["capture_mode"] = self._mode
        save_doc(doc)
        self._update_mode_label()
        if not self._wayland:
            self._sup.reload()

    def _open_settings(self):
        from easytype.gui.settings import SettingsWindow
        if self._settings_window is None:
            self._settings_window = SettingsWindow(self._sup, on_saved=self._after_save)
        self._settings_window.show()
        self._settings_window.raise_()
        self._settings_window.activateWindow()

    def _after_save(self):
        self._mode = str(load_config().capture_mode)
        self._update_mode_label()

    def _refresh(self):
        state = "disabled" if self._wayland else self._sup.state
        label = _STATUS_LABELS.get(state, state)
        self._status_action.setText(label)
        active = state in ("recording", "transcribing")
        self._tray.setIcon(self._active_icon if active else self._idle_icon)
        self._toggle_rec.setText("Stop dictation" if active else "Start dictation")
        suffix = " · passive" if self._passive else ""
        self._tray.setToolTip(f"EasyType — {label}{suffix}")

    def _quit(self):
        self._timer.stop()
        self._sup.stop()
        self._app.quit()


def _missing_xcb_cursor() -> bool:
    """Qt 6.5+'s xcb plugin needs libxcb-cursor0, which PySide6 doesn't bundle;
    without it Qt aborts the process at QApplication(). True on X11 when it's absent."""
    import ctypes.util

    return (
        sys.platform == "linux"
        and os.environ.get("XDG_SESSION_TYPE") == "x11"
        and ctypes.util.find_library("xcb-cursor") is None
    )


def main() -> None:
    if _missing_xcb_cursor():
        sys.stderr.write(
            "EasyType GUI needs the system library libxcb-cursor0.\n"
            "Install it:  sudo apt install libxcb-cursor0\n"
        )
        raise SystemExit(1)
    app = QApplication(sys.argv)
    app.setApplicationName("EasyType")
    if _already_running():
        print("EasyType is already running.")
        return
    server = QLocalServer()
    QLocalServer.removeServer(_LOCK_NAME)
    server.listen(_LOCK_NAME)
    app._easytype_server = server               # keep a strong reference

    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.critical(None, "EasyType", "No system tray is available on this desktop.")
        return

    app.setWindowIcon(make_icon(False))
    if _STYLE.exists():
        app.setStyleSheet(_STYLE.read_text())
    app.setQuitOnLastWindowClosed(False)        # closing Settings must not kill the tray

    tray = TrayApp(app)
    app._easytype_tray = tray                     # keep a strong reference
    sys.exit(app.exec())
