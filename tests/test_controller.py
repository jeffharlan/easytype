import numpy as np

from easytype.config import load_config, DictEntry
from easytype.controller import Controller


class FakeRecorder:
    def __init__(self): self.started = False
    def start(self): self.started = True
    def stop(self): self.started = False; return np.zeros(10, dtype=np.float32)


class FakeTranscriber:
    def transcribe(self, audio): return "ops plus is ready"


class FakeInjector:
    def __init__(self): self.injected = []
    def inject(self, text, method): self.injected.append((text, method))


class FakeIndicator:
    is_null = True
    def start(self, cap): ...
    def stop(self): ...


def build(tmp_path, **over):
    c = load_config(tmp_path / "c.toml")
    inj = FakeInjector()
    ctrl = Controller(
        config=c, recorder=FakeRecorder(), transcriber=FakeTranscriber(),
        injector=inj, indicator=FakeIndicator(), notify=lambda *a: None,
    )
    return ctrl, inj


def test_pipeline_applies_dictionary_before_inject(tmp_path):
    c = load_config(tmp_path / "c.toml")
    inj = FakeInjector()
    ctrl = Controller(
        config=c, recorder=FakeRecorder(), transcriber=FakeTranscriber(),
        injector=inj, indicator=FakeIndicator(), notify=lambda *a: None,
        dictionary=[DictEntry("ops plus", "OPS+", "smart")],
    )
    text = ctrl.process_audio(np.zeros(10, dtype=np.float32))
    assert text == "OPS+ is ready."
    assert inj.injected == [("OPS+ is ready.", "type")]


def test_toggle_starts_then_stops(tmp_path):
    ctrl, inj = build(tmp_path)
    assert ctrl.state == "idle"
    ctrl.on_record()       # start
    assert ctrl.state == "recording"
    ctrl.on_record()       # stop → process synchronously in test mode
    assert ctrl.state == "idle"
    assert inj.injected and inj.injected[0][0] == "Ops plus is ready."


def test_repaste_reinjects_last(tmp_path):
    ctrl, inj = build(tmp_path)
    ctrl.on_record(); ctrl.on_record()
    inj.injected.clear()
    ctrl.on_repaste()
    assert inj.injected == [("Ops plus is ready.", "type")]


def test_cancel_during_recording_discards(tmp_path):
    ctrl, inj = build(tmp_path)
    ctrl.on_record()
    ctrl.on_cancel()
    assert ctrl.state == "idle"
    assert inj.injected == []


def test_enabled_names_excludes_cancel_when_idle(tmp_path):
    ctrl, _ = build(tmp_path)
    assert "cancel" not in ctrl.enabled_names()
    ctrl.on_record()
    assert "cancel" in ctrl.enabled_names()


def test_cancel_during_transcribing_suppresses_inject(tmp_path):
    ctrl, inj = build(tmp_path)
    ctrl.on_record()              # recording
    ctrl.state = "transcribing"   # simulate mid-transcription
    ctrl.on_cancel()              # flags cancellation
    text = ctrl.process_audio(np.zeros(10, dtype=np.float32))
    assert text == ""
    assert inj.injected == []


def test_toggle_recording_starts_then_stops(tmp_path):
    ctrl, inj = build(tmp_path)
    assert ctrl.state == "idle"
    ctrl.toggle_recording()
    assert ctrl.state == "recording"
    ctrl.toggle_recording()                       # synchronous in test mode
    assert ctrl.state == "idle"
    assert inj.injected and inj.injected[0][0] == "Ops plus is ready."


def test_toggle_recording_noop_while_transcribing(tmp_path):
    ctrl, inj = build(tmp_path)
    ctrl.toggle_recording()                       # recording
    ctrl.state = "transcribing"
    ctrl.toggle_recording()                       # must do nothing
    assert ctrl.state == "transcribing"
