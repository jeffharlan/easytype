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
    from easytype.recorder import Recorder
    from easytype.transcriber import Transcriber

    transcriber = Transcriber(config.model, config.language, config.transcribe_device)
    controller = Controller(
        config=config,
        recorder=Recorder(config.audio_device),
        transcriber=transcriber,
        injector=get_injector(session, config.type_delay_ms),
        indicator=create_indicator(config),
        notify=notify,
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

    listener = Listener(engine, controller.enabled_names, on_event)
    return EngineBundle(listener=listener, controller=controller, warmup=transcriber.warmup)
