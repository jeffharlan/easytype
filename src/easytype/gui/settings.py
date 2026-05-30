from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFormLayout, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QMessageBox, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem,
    QTabWidget, QVBoxLayout, QWidget,
)

from easytype import autostart
from easytype.config import (
    apply_settings_to_doc, load_config, load_doc, save_doc, set_dictionary_in_doc,
)
from easytype.keycodes import conflict_note, describe_chord

MODELS = ["tiny.en", "base.en", "small.en", "medium.en", "large-v3"]
LANGS = ["en", "es", "fr", "de", "it", "pt", "nl"]
COMPUTE = ["auto", "cuda", "cpu"]
POSITIONS = ["top-left", "top-center", "top-right", "bottom-left", "bottom-center", "bottom-right"]


def _input_device_names() -> list[str]:
    try:
        import sounddevice as sd
        return [d["name"] for d in sd.query_devices() if d.get("max_input_channels", 0) > 0]
    except Exception:
        return []


class HotkeyRow(QWidget):
    """Current-description + clash note + Set button that captures a chord live."""
    captured = Signal(object)            # emitted (list[int]) from the engine thread

    def __init__(self, supervisor):
        super().__init__()
        self._sup = supervisor
        self.keys: list[int] = []
        self.description = ""
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        self._desc = QLabel("—")
        self._note = QLabel("")
        self._note.setObjectName("conflict")
        self._set = QPushButton("Set")
        self._set.clicked.connect(self._begin)
        row.addWidget(self._desc, 1)
        row.addWidget(self._note, 1)
        row.addWidget(self._set)
        self.captured.connect(self._on_captured)    # delivered on the GUI thread

    def set_value(self, keys, description):
        self.keys = list(keys)
        self.description = description
        self._desc.setText(description or "—")
        self._note.setText("")

    def _begin(self):
        if self._sup.state == "stopped":
            self._note.setText("Start dictation first to set a hotkey")
            return
        self._set.setText("Press keys…")
        self._set.setEnabled(False)
        self._sup.begin_hotkey_capture(lambda keys: self.captured.emit(keys))

    def _on_captured(self, keys):
        self.keys = list(keys)
        self.description = describe_chord(keys)
        self._desc.setText(self.description or "—")
        self._note.setText(conflict_note(keys) or "")
        self._set.setText("Set")
        self._set.setEnabled(True)


class SettingsWindow(QDialog):
    def __init__(self, supervisor, on_saved=None):
        super().__init__()
        self._sup = supervisor
        self._on_saved = on_saved
        self.setWindowTitle("EasyType — Settings")
        self.resize(480, 440)

        tabs = QTabWidget()
        tabs.addTab(self._recording_tab(), "Recording")
        tabs.addTab(self._audio_tab(), "Audio & Transcription")
        tabs.addTab(self._typing_tab(), "Typing")
        tabs.addTab(self._ai_tab(), "AI cleanup")
        tabs.addTab(self._dictionary_tab(), "Dictionary")
        tabs.addTab(self._indicator_tab(), "Indicator")
        tabs.addTab(self._advanced_tab(), "Advanced")

        save = QPushButton("Save")
        save.setObjectName("primary")
        save.clicked.connect(self._save)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.close)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(cancel)
        buttons.addWidget(save)

        root = QVBoxLayout(self)
        root.addWidget(tabs)
        root.addLayout(buttons)
        self._load()

    def _recording_tab(self):
        w = QWidget(); form = QFormLayout(w)
        self.capture_mode = QComboBox(); self.capture_mode.addItems(["toggle", "hold"])
        self.max_duration = QSpinBox(); self.max_duration.setRange(0, 3600); self.max_duration.setSuffix(" s")
        self.record_row = HotkeyRow(self._sup)
        self.cancel_row = HotkeyRow(self._sup)
        self.repaste_row = HotkeyRow(self._sup)
        form.addRow("Mode", self.capture_mode)
        form.addRow("Max length", self.max_duration)
        form.addRow("Record", self.record_row)
        form.addRow("Cancel", self.cancel_row)
        form.addRow("Repaste", self.repaste_row)
        return w

    def _audio_tab(self):
        w = QWidget(); form = QFormLayout(w)
        self.audio_device = QComboBox()
        self.audio_device.addItem("Default", "")
        for name in _input_device_names():
            self.audio_device.addItem(name, name)
        self.model = QComboBox(); self.model.setEditable(True); self.model.addItems(MODELS)
        self.language = QComboBox(); self.language.setEditable(True); self.language.addItems(LANGS)
        self.transcribe_device = QComboBox(); self.transcribe_device.addItems(COMPUTE)
        form.addRow("Microphone", self.audio_device)
        form.addRow("Model", self.model)
        form.addRow("Language", self.language)
        form.addRow("Compute", self.transcribe_device)
        return w

    def _typing_tab(self):
        w = QWidget(); form = QFormLayout(w)
        self.injection_method = QComboBox(); self.injection_method.addItems(["type", "paste"])
        self.type_delay = QSpinBox(); self.type_delay.setRange(0, 500); self.type_delay.setSuffix(" ms")
        form.addRow("Insert via", self.injection_method)
        form.addRow("Keystroke delay", self.type_delay)
        return w

    def _ai_tab(self):
        w = QWidget(); form = QFormLayout(w)
        self.formatter_enabled = QCheckBox("Clean up transcripts with a model")
        self.formatter_backend = QComboBox(); self.formatter_backend.addItems(["ollama", "openai"])
        self.ollama_model = QLineEdit()
        self.ollama_url = QLineEdit()
        self.formatter_enabled.toggled.connect(self._sync_ai_enabled)
        form.addRow(self.formatter_enabled)
        form.addRow("Backend", self.formatter_backend)
        form.addRow("Ollama model", self.ollama_model)
        form.addRow("Ollama URL", self.ollama_url)
        return w

    def _indicator_tab(self):
        w = QWidget(); form = QFormLayout(w)
        self.indicator_enabled = QCheckBox("Show the on-screen recording indicator")
        self.indicator_position = QComboBox(); self.indicator_position.addItems(POSITIONS)
        self.indicator_count = QComboBox(); self.indicator_count.addItems(["up", "down"])
        form.addRow(self.indicator_enabled)
        form.addRow("Position", self.indicator_position)
        form.addRow("Count", self.indicator_count)
        return w

    def _dictionary_tab(self):
        w = QWidget(); layout = QVBoxLayout(w)
        layout.addWidget(QLabel(
            "Fix words the transcriber gets wrong. Matching is whole-word, any case."
        ))
        self.dict_table = QTableWidget(0, 2)
        self.dict_table.setHorizontalHeaderLabels(["When you hear", "Type instead"])
        self.dict_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.dict_table)
        add = QPushButton("Add"); add.clicked.connect(lambda: self._dict_add_row("", ""))
        remove = QPushButton("Remove"); remove.clicked.connect(self._dict_remove_row)
        row = QHBoxLayout(); row.addWidget(add); row.addWidget(remove); row.addStretch(1)
        layout.addLayout(row)
        return w

    def _dict_add_row(self, hears, replace):
        r = self.dict_table.rowCount()
        self.dict_table.insertRow(r)
        self.dict_table.setItem(r, 0, QTableWidgetItem(hears))
        self.dict_table.setItem(r, 1, QTableWidgetItem(replace))

    def _dict_remove_row(self):
        r = self.dict_table.currentRow()
        if r >= 0:
            self.dict_table.removeRow(r)

    def _dict_entries(self):
        entries = []
        for r in range(self.dict_table.rowCount()):
            hears = self.dict_table.item(r, 0)
            replace = self.dict_table.item(r, 1)
            hears = hears.text().strip() if hears else ""
            replace = replace.text().strip() if replace else ""
            if hears and replace:
                entries.append((hears, replace))
        return entries

    def _advanced_tab(self):
        w = QWidget(); form = QFormLayout(w)
        self.start_on_login = QCheckBox("Start EasyType automatically when you log in")
        self.keyboard_device = QLineEdit()
        self.keyboard_device.setPlaceholderText("blank = auto-detect")
        form.addRow(self.start_on_login)
        form.addRow("Keyboard device", self.keyboard_device)
        return w

    def _sync_ai_enabled(self, on):
        for wdg in (self.formatter_backend, self.ollama_model, self.ollama_url):
            wdg.setEnabled(on)

    def _load(self):
        c = load_config()
        self.capture_mode.setCurrentText(c.capture_mode)
        self.max_duration.setValue(c.max_recording_duration)
        self.record_row.set_value(c.record.keys, c.record.description)
        self.cancel_row.set_value(c.cancel.keys, c.cancel.description)
        self.repaste_row.set_value(c.repaste.keys, c.repaste.description)
        idx = self.audio_device.findData(c.audio_device)
        self.audio_device.setCurrentIndex(idx if idx >= 0 else 0)
        self.model.setCurrentText(c.model)
        self.language.setCurrentText(c.language)
        self.transcribe_device.setCurrentText(c.transcribe_device)
        self.injection_method.setCurrentText(c.injection_method)
        self.type_delay.setValue(c.type_delay_ms)
        self.formatter_enabled.setChecked(c.formatter_enabled)
        self.formatter_backend.setCurrentText(c.formatter_backend)
        self.ollama_model.setText(c.ollama_model)
        self.ollama_url.setText(c.ollama_url)
        self.indicator_enabled.setChecked(c.indicator_enabled)
        self.indicator_position.setCurrentText(c.indicator_position)
        self.indicator_count.setCurrentText(c.indicator_count)
        self.keyboard_device.setText(c.keyboard_device)
        self.start_on_login.setChecked(autostart.is_enabled())
        self.dict_table.setRowCount(0)
        for entry in c.dictionary:
            self._dict_add_row(entry.hears, entry.replace)
        self._sync_ai_enabled(c.formatter_enabled)

    def _values(self):
        return {
            "capture_mode": self.capture_mode.currentText(),
            "max_recording_duration": self.max_duration.value(),
            "record_keys": self.record_row.keys, "record_description": self.record_row.description,
            "cancel_keys": self.cancel_row.keys, "cancel_description": self.cancel_row.description,
            "repaste_keys": self.repaste_row.keys, "repaste_description": self.repaste_row.description,
            "audio_device": self.audio_device.currentData() or "",
            "model": self.model.currentText(),
            "language": self.language.currentText(),
            "transcribe_device": self.transcribe_device.currentText(),
            "injection_method": self.injection_method.currentText(),
            "type_delay_ms": self.type_delay.value(),
            "formatter_enabled": self.formatter_enabled.isChecked(),
            "formatter_backend": self.formatter_backend.currentText(),
            "ollama_model": self.ollama_model.text(),
            "ollama_url": self.ollama_url.text(),
            "indicator_enabled": self.indicator_enabled.isChecked(),
            "indicator_position": self.indicator_position.currentText(),
            "indicator_count": self.indicator_count.currentText(),
            "keyboard_device": self.keyboard_device.text(),
        }

    def _save(self):
        try:
            doc = load_doc()
            apply_settings_to_doc(doc, self._values())
            set_dictionary_in_doc(doc, self._dict_entries())
            save_doc(doc)
            autostart.set_enabled(self.start_on_login.isChecked())
        except Exception as exc:
            QMessageBox.critical(self, "EasyType", f"Could not save settings:\n{exc}")
            return
        self._sup.reload()
        if self._on_saved:
            self._on_saved()
        self.close()
