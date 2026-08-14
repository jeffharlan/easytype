from __future__ import annotations

import threading
import time
from collections.abc import Callable, Sequence

import numpy as np

from easytype import history
from easytype.config import Config, DictEntry
from easytype.dictionary import apply_dictionary
from easytype.formatter import format_text
from easytype.polish import polish_text

# How long the on-screen box stays up showing the finished transcript before the
# text is injected. The last words spoken never make it into a mid-recording pass,
# so without this the box never shows the end of what you said.
FINAL_HOLD_S = 2.0


class Controller:
    def __init__(self, *, config: Config, recorder, transcriber, injector, indicator,
                 notify: Callable[[str, str], None],
                 dictionary: Sequence[DictEntry] | None = None,
                 media=None,
                 preview=None,
                 live=None,
                 synchronous: bool = True):
        self._cfg = config
        self._rec = recorder
        self._tx = transcriber
        self._inj = injector
        self._ind = indicator
        self._media = media
        self._preview = preview
        self._live = live
        self._notify = notify
        self._dict = list(dictionary if dictionary is not None else config.dictionary)
        self._sync = synchronous  # tests run inline; real runtime sets False
        self.state = "idle"  # idle | recording | transcribing
        self.last_transcript = ""
        self._lock = threading.RLock()
        self._cap_timer: threading.Timer | None = None
        self._cancelled = False

    # --- chord gating -------------------------------------------------------
    def enabled_names(self) -> set[str]:
        names = {"record", "repaste"}
        if self.state in ("recording", "transcribing"):
            names.add("cancel")
        return names

    # --- hotkey handlers ----------------------------------------------------
    def on_record(self) -> None:
        if self._cfg.capture_mode == "hold":
            if self.state == "idle":
                self._start()
            return
        with self._lock:
            if self.state == "idle":
                self._start()
            elif self.state == "recording":
                self._stop_and_process()

    def on_record_release(self) -> None:
        if self._cfg.capture_mode == "hold" and self.state == "recording":
            self._stop_and_process()

    def on_cancel(self) -> None:
        with self._lock:
            if self.state == "recording":
                self._cancel_timer()
                self._stop_preview()
                if self._live:
                    self._live.undo()
                self._rec.stop()
                self._resume_media()
                self._ind.stop()
                self.state = "idle"
                self._notify("EasyType", "Recording cancelled")
            elif self.state == "transcribing":
                self._cancelled = True

    def on_repaste(self) -> None:
        if self.last_transcript:
            self._inj.inject(self.last_transcript, self._cfg.injection_method)

    def toggle_recording(self) -> None:
        """Manual start/stop for the tray, independent of capture_mode."""
        with self._lock:
            if self.state == "idle":
                self._start()
            elif self.state == "recording":
                self._stop_and_process()

    # --- internals ----------------------------------------------------------
    def _pause_media(self) -> None:
        if self._media and self._cfg.pause_media_while_recording:
            self._media.pause()

    def _resume_media(self) -> None:
        if self._media and self._cfg.pause_media_while_recording:
            self._media.resume()

    def _stop_preview(self) -> None:
        if self._preview:
            self._preview.stop()

    def _start(self) -> None:
        self._cancelled = False
        self.state = "recording"
        self._pause_media()
        self._rec.start()
        if self._live:
            self._live.start()      # capture the window before any transcript lands
        if self._preview:
            self._preview.start()
        self._ind.start(self._cfg.max_recording_duration)
        self._notify("EasyType", "Recording…")
        print("[easytype] recording started")
        self._arm_cap_timer()

    def _arm_cap_timer(self) -> None:
        cap = self._cfg.max_recording_duration
        if cap and cap > 0:
            self._cap_timer = threading.Timer(cap, self._cap_reached)
            self._cap_timer.daemon = True
            self._cap_timer.start()

    def _cancel_timer(self) -> None:
        if self._cap_timer:
            self._cap_timer.cancel()
            self._cap_timer = None

    def _cap_reached(self) -> None:
        with self._lock:
            if self.state == "recording":
                print("[easytype] max duration reached — auto-stopping")
                self._stop_and_process()

    def _stop_and_process(self) -> None:
        self._cancel_timer()
        self.state = "transcribing"
        if self._sync:
            self._finish_recording()
        else:
            threading.Thread(target=self._finish_recording, daemon=True).start()

    def _finish_recording(self) -> None:
        # Runs on a worker thread in the real app so the keyboard event loop never blocks.
        self._stop_preview()
        audio = self._rec.stop()
        self._resume_media()
        print("[easytype] transcribing…")
        # The box stays up through transcription and the hold, so it can show the
        # finished text; process_audio closes the loop before injecting.
        self._ind.status("Transcribing…")
        try:
            text = self.process_audio(audio)
        finally:
            self._ind.stop()
        with self._lock:
            self.state = "idle"
        if text:
            print(f"[easytype] inserted: {text!r}")

    def process_audio(self, audio: np.ndarray) -> str:
        text = self._tx.transcribe(audio)
        text = apply_dictionary(text, self._dict)
        text = format_text(text, self._cfg)
        text = polish_text(text)
        text = text.strip()
        if self._cancelled:
            self._cancelled = False
            return ""
        if text:
            self.last_transcript = text
            self._record_history(text)
            self._hold_final(text)
            if self._live and self._live.active:
                self._live.finish(text)
            else:
                self._inj.inject(text, self._cfg.injection_method)
        return text

    def _hold_final(self, text: str) -> None:
        """Show the finished transcript in the box and pause so it can be read.
        Skipped when there is no box — nothing to look at, nothing to wait for."""
        if self._ind.is_null:
            return
        self._ind.caption(text)
        self._ind.status("Done")
        time.sleep(FINAL_HOLD_S)

    def _record_history(self, text: str) -> None:
        if not self._cfg.history_enabled:
            return
        try:
            history.append(text)
        except Exception as exc:
            print(f"[easytype] history write failed: {exc}")
