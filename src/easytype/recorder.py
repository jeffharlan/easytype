from __future__ import annotations

import numpy as np

SAMPLE_RATE = 16000  # whisper-friendly


class Recorder:
    def __init__(self, device: str = "", sample_rate: int = SAMPLE_RATE):
        self._device = device or None
        self._sr = sample_rate
        self._stream = None
        self._frames: list[np.ndarray] = []

    def start(self) -> None:
        import sounddevice as sd

        self._frames = []

        def callback(indata, frames, time_info, status):
            self._frames.append(indata.copy())

        self._stream = sd.InputStream(
            samplerate=self._sr, channels=1, dtype="float32",
            device=self._device, callback=callback,
        )
        self._stream.start()

    def stop(self) -> np.ndarray:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        if not self._frames:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(self._frames, axis=0).flatten()
