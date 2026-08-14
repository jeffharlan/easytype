import threading
import time

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


def test_concurrent_transcribes_never_overlap():
    class _ReentrancyDetector:
        def __init__(self):
            self.inside = 0
            self.overlapped = False

        def transcribe(self, audio, **kwargs):
            self.inside += 1
            if self.inside > 1:
                self.overlapped = True
            time.sleep(0.02)
            self.inside -= 1
            return ([_FakeSegment("hello")], object())

    detector = _ReentrancyDetector()
    tx = Transcriber()
    tx._model = detector
    threads = [
        threading.Thread(target=tx.transcribe, args=(np.ones(16000, dtype=np.float32),))
        for _ in range(4)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert detector.overlapped is False


def test_compute_type_cpu():
    assert resolve_compute_type("cpu") == "int8"


def test_compute_type_cuda():
    assert resolve_compute_type("cuda") == "float16"


def test_compute_type_auto():
    assert resolve_compute_type("auto") == "default"
