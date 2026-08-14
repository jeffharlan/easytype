import numpy as np

from easytype.preview import MIN_PREVIEW_SECONDS, PreviewWorker
from easytype.recorder import SAMPLE_RATE


class FakeRecorder:
    def __init__(self, seconds=2.0):
        self.audio = np.zeros(int(SAMPLE_RATE * seconds), dtype=np.float32)

    def snapshot(self):
        return self.audio


class FakeTranscriber:
    def __init__(self, text="preview text"):
        self.text = text
        self.calls = 0

    def transcribe(self, audio):
        self.calls += 1
        return self.text


class Collector:
    def __init__(self):
        self.texts = []

    def __call__(self, text):
        self.texts.append(text)


def _worker(recorder=None, transcriber=None, on_text=None):
    return PreviewWorker(
        recorder or FakeRecorder(),
        transcriber or FakeTranscriber(),
        on_text or Collector(),
        interval=0.01,
    )


def test_a_pass_publishes_the_transcribed_snapshot():
    sink = Collector()
    worker = _worker(on_text=sink)
    worker._pass()
    assert sink.texts == ["preview text"]


def test_audio_below_the_minimum_is_not_transcribed():
    tx = FakeTranscriber()
    sink = Collector()
    worker = _worker(recorder=FakeRecorder(seconds=MIN_PREVIEW_SECONDS / 2),
                     transcriber=tx, on_text=sink)
    worker._pass()
    assert tx.calls == 0
    assert sink.texts == []


def test_empty_transcript_is_not_published():
    sink = Collector()
    worker = _worker(transcriber=FakeTranscriber(text="   "), on_text=sink)
    worker._pass()
    assert sink.texts == []


def test_a_pass_finishing_after_stop_publishes_nothing():
    sink = Collector()
    worker = _worker(on_text=sink)
    worker.stop()          # a pass already in flight must not publish its result
    worker._pass()
    assert sink.texts == []


def test_a_transcriber_failure_does_not_propagate():
    class Boom:
        def transcribe(self, audio):
            raise RuntimeError("cuda out of memory")

    worker = _worker(transcriber=Boom())
    worker._pass()          # must not raise


def test_start_then_stop_leaves_no_live_thread():
    worker = _worker()
    worker.start()
    worker.stop()
    assert worker._thread is None


def test_start_is_idempotent():
    worker = _worker()
    worker.start()
    first = worker._thread
    worker.start()
    assert worker._thread is first
    worker.stop()
