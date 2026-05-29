from __future__ import annotations

import numpy as np


def resolve_compute_type(device: str) -> str:
    return {"cpu": "int8", "cuda": "float16"}.get(device, "default")


class Transcriber:
    def __init__(self, model: str = "base.en", language: str = "en", device: str = "auto"):
        self._model_name = model
        self._language = language
        self._device = device
        self._model = None

    def _ensure_model(self):
        if self._model is None:
            from faster_whisper import WhisperModel
            self._model = WhisperModel(
                self._model_name, device=self._device,
                compute_type=resolve_compute_type(self._device),
            )
        return self._model

    def transcribe(self, audio: np.ndarray) -> str:
        if audio.size == 0:
            return ""
        model = self._ensure_model()
        segments, _info = model.transcribe(audio, language=self._language, beam_size=5)
        return "".join(seg.text for seg in segments).strip()
