from __future__ import annotations

import argparse
import signal
import subprocess
import sys
import threading

from easytype import preflight
from easytype.config import DEFAULT_CONFIG_PATH, load_config, load_doc, save_doc, set_hotkey_in_doc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="easytype", description="Local voice dictation for Linux")
    parser.add_argument("--passive", action="store_true", help="Run without grabbing the keyboard")
    parser.add_argument("--check", action="store_true", help="Run preflight checks and exit")
    parser.add_argument(
        "--set-hotkey", nargs="?", const="record", choices=["record", "cancel", "repaste"],
        help="Interactively capture a hotkey, then save it",
    )
    return parser


def _notify(title: str, body: str) -> None:
    subprocess.run(["notify-send", title, body], check=False)


def _raise_keyboard_interrupt(signum, frame):
    raise KeyboardInterrupt


def cmd_check() -> int:
    issues = preflight.check()
    print(preflight.format_report(issues))
    blocking = [i for i in issues if not i.ok and not i.name.startswith("python3-tk")]
    return 1 if blocking else 0


def cmd_set_hotkey(name: str) -> int:
    import selectors

    from evdev import ecodes

    from easytype.chords import ChordCollector
    from easytype.keycodes import conflict_note, describe_chord
    from easytype.listener import open_devices

    print(f"Press the key or combination you want for '{name}', then release.")
    devices = open_devices("")
    collector = ChordCollector()
    try:
        sel = selectors.DefaultSelector()
        for d in devices:
            sel.register(d, selectors.EVENT_READ)
        done = False
        while not done:
            for key, _ in sel.select():
                for ev in key.fileobj.read():
                    if ev.type == ecodes.EV_KEY and collector.feed(ev.code, ev.value):
                        done = True
    finally:
        for d in devices:
            d.close()
    pressed = collector.keys

    desc = describe_chord(pressed)
    note = conflict_note(pressed)
    if note:
        print(f"\nNote: {note}")
    doc = load_doc()
    set_hotkey_in_doc(doc, name, pressed, desc)
    save_doc(doc)
    print(f"Saved {name} hotkey: {desc}  (codes {pressed}) -> {DEFAULT_CONFIG_PATH}")
    return 0


def cmd_run(passive: bool) -> int:
    config = load_config()
    session = preflight.detect_session()

    if session == "wayland":
        print(
            "EasyType Phase 1 supports X11 only — Wayland text injection isn't "
            "implemented yet.\nSee the README (Troubleshooting) for status."
        )
        return 1

    issues = preflight.check()
    blocking = [i for i in issues if not i.ok and not i.name.startswith("python3-tk")]
    grab = not passive
    if blocking and not passive:
        print(preflight.format_report(issues))
        print("\nFalling back to --passive (no consume) because grab prerequisites are missing.")
        grab = False

    from easytype.chords import HotkeyEngine
    from easytype.controller import Controller
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
        notify=_notify,
        synchronous=False,
    )
    threading.Thread(target=transcriber.warmup, daemon=True).start()
    print("[easytype] warming up the transcription model in the background…")

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

    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, _raise_keyboard_interrupt)

    print(f"[easytype] session={session}  mode={config.capture_mode}  "
          f"record={config.record.description}  grab={grab}")
    try:
        listener.run(device_override=config.keyboard_device, grab=grab)
    except KeyboardInterrupt:
        print("\n[easytype] shutting down…")
    finally:
        listener.cleanup()
    return 0


def main() -> None:
    args = build_parser().parse_args()
    if args.check:
        sys.exit(cmd_check())
    if args.set_hotkey:
        sys.exit(cmd_set_hotkey(args.set_hotkey))
    sys.exit(cmd_run(args.passive))


if __name__ == "__main__":
    main()
