from __future__ import annotations

import subprocess
from collections.abc import Callable
from dataclasses import dataclass

from easytype.chords import HotkeyEngine
from easytype.config import Config
from easytype.controller import Controller


def notify_send(title: str, body: str) -> None:
    subprocess.run(["notify-send", title, body], check=False)


@dataclass
class EngineBundle:
    listener: object
    controller: Controller
    warmup: Callable[[], None]


def build_engine(config: Config, session: str,
                 notify: Callable[[str, str], None] = notify_send) -> EngineBundle:
    """Wire up the dictation engine from a Config. Shared by the headless CLI and
    the GUI supervisor so both build the engine identically."""
    from easytype.indicator import create_indicator
    from easytype.injector import get_injector
    from easytype.listener import Listener
    from easytype.live import LiveTypist
    from easytype.media import MediaController
    from easytype.preview import PreviewWorker
    from easytype.recorder import Recorder
    from easytype.transcriber import Transcriber

    transcriber = Transcriber(config.model, config.language, config.transcribe_device,
                              initial_prompt=config.initial_prompt)
    recorder = Recorder(config.audio_device)
    indicator = create_indicator(config)
    injector = get_injector(session, config.type_delay_ms)

    live = None
    preview = None
    preview_transcriber = None

    if config.inject_live and config.formatter_enabled:
        notify("EasyType", "Live typing is off while AI cleanup is on")

    if config.inject_live and not config.formatter_enabled:
        # Live typing reuses the main transcriber: what gets typed must be the
        # quality the user already expects, and a second copy of the same model
        # would cost VRAM for nothing.
        live = LiveTypist(injector, config.dictionary)
        preview = PreviewWorker(recorder, transcriber, live.feed)
    # No indicator means nowhere to draw, so preview is skipped regardless of the flag.
    elif config.preview_enabled and not indicator.is_null:
        preview_transcriber = Transcriber(
            config.preview_model or config.model, config.language,
            config.transcribe_device, initial_prompt=config.initial_prompt,
        )
        preview = PreviewWorker(recorder, preview_transcriber, indicator.caption)

    controller = Controller(
        config=config,
        recorder=recorder,
        transcriber=transcriber,
        injector=injector,
        indicator=indicator,
        notify=notify,
        media=MediaController(),
        preview=preview,
        live=live,
        synchronous=False,
    )
    engine = HotkeyEngine({
        "record": config.record.keys,
        "cancel": config.cancel.keys,
        "repaste": config.repaste.keys,
    })

    def on_event(outcome):
        if outcome.pressed == "record":
            controller.on_record()
        elif outcome.released == "record":
            controller.on_record_release()
        elif outcome.pressed == "cancel":
            controller.on_cancel()
        elif outcome.pressed == "repaste":
            controller.on_repaste()

    def warmup():
        transcriber.warmup()
        if preview_transcriber is not None:
            preview_transcriber.warmup()

    listener = Listener(engine, controller.enabled_names, on_event)
    return EngineBundle(listener=listener, controller=controller, warmup=warmup)
