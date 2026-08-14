from __future__ import annotations

import threading

from easytype.recorder import SAMPLE_RATE

PREVIEW_INTERVAL = 1.0      # seconds between passes, not a deadline for one
MIN_PREVIEW_SECONDS = 0.5   # below this there is nothing worth transcribing


class PreviewWorker:
    """Re-transcribes the growing audio buffer while recording and hands each
    transcript to `on_text`. It does not know whether that becomes a caption or
    keystrokes — the engine decides that once, when it wires the sink."""

    def __init__(self, recorder, transcriber, on_text, interval: float = PREVIEW_INTERVAL):
        self._rec = recorder
        self._tx = transcriber
        self._on_text = on_text
        self._interval = interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Returns promptly. A pass still in flight finishes on its own and
        discards its result, so the final transcription is never held up."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=0.2)
        self._thread = None

    def _loop(self) -> None:
        while not self._stop.is_set():
            self._pass()
            self._stop.wait(self._interval)

    def _pass(self) -> None:
        try:
            audio = self._rec.snapshot()
            if audio.size < MIN_PREVIEW_SECONDS * SAMPLE_RATE:
                return
            text = self._tx.transcribe(audio)
        except Exception as exc:
            print(f"[easytype] preview pass failed: {exc}")
            return
        if text.strip() and not self._stop.is_set():
            self._on_text(text)
