import numpy as np

from easytype.transcriber import Transcriber, resolve_compute_type


class _FakeSegment:
    def __init__(self, text):
        self.text = text


class _FakeModel:
    def __init__(self):
        self.calls = []

    def transcribe(self, audio, **kwargs):
        self.calls.append(kwargs)
        return ([_FakeSegment("hello")], object())


def test_initial_prompt_passed_to_model():
    fake = _FakeModel()
    tx = Transcriber(initial_prompt="Claude Code, CrewNexus, ConnectWise")
    tx._model = fake
    tx.transcribe(np.ones(16000, dtype=np.float32))
    assert fake.calls[0]["initial_prompt"] == "Claude Code, CrewNexus, ConnectWise"


def test_no_initial_prompt_passes_none():
    fake = _FakeModel()
    tx = Transcriber()
    tx._model = fake
    tx.transcribe(np.ones(16000, dtype=np.float32))
    assert fake.calls[0]["initial_prompt"] is None


def test_compute_type_cpu():
    assert resolve_compute_type("cpu") == "int8"


def test_compute_type_cuda():
    assert resolve_compute_type("cuda") == "float16"


def test_compute_type_auto():
    assert resolve_compute_type("auto") == "default"
