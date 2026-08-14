import numpy as np

from easytype.recorder import Recorder


def _frames(*values):
    return [np.full((1, 1), v, dtype=np.float32) for v in values]


# These tests set _frames directly rather than driving a real InputStream:
# sounddevice needs a real audio device, which CI does not have.


def test_snapshot_returns_buffered_audio():
    rec = Recorder()
    rec._frames = _frames(1.0, 2.0)
    assert rec.snapshot().tolist() == [1.0, 2.0]


def test_snapshot_does_not_consume_the_buffer():
    rec = Recorder()
    rec._frames = _frames(1.0, 2.0)
    rec.snapshot()
    rec._frames.extend(_frames(3.0))
    assert rec.snapshot().tolist() == [1.0, 2.0, 3.0]


def test_snapshot_with_nothing_buffered_is_empty():
    rec = Recorder()
    assert rec.snapshot().size == 0


def test_stop_still_returns_the_full_buffer():
    rec = Recorder()
    rec._frames = _frames(1.0, 2.0, 3.0)
    assert rec.stop().tolist() == [1.0, 2.0, 3.0]
