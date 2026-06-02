import os
import selectors
import threading
import time
from collections import namedtuple

import easytype.listener as listener_mod
from easytype.chords import HotkeyEngine
from easytype.listener import Listener

# Real evdev numeric values for the types/codes the listener inspects.
EV_SYN, EV_KEY, EV_MSC = 0, 1, 4
SYN_REPORT, MSC_SCAN = 0, 4
KEY_A, KEY_R, KEY_LEFTCTRL = 30, 19, 29

Ev = namedtuple("Ev", "type code value")


class StubEcodes:
    EV_KEY = EV_KEY


class FakeUInput:
    """Records the virtual-device call stream so tests can assert that the
    listener replays the kernel's report grouping without injecting extra syns."""
    def __init__(self):
        self.events = []   # (type, code, value) per write_event
        self.syns = 0      # explicit syn() calls — must stay 0
    def write_event(self, event):
        self.events.append((event.type, event.code, event.value))
    def syn(self):
        self.syns += 1


def make_listener(chords):
    fired = []
    lis = Listener(HotkeyEngine(chords), lambda: set(chords), fired.append)
    fake = FakeUInput()
    lis._ui = fake
    return lis, fake, fired


def feed(lis, events):
    for e in events:
        lis._handle(e, StubEcodes)


def test_normal_keypress_replayed_as_one_atomic_report():
    """A plain letter's [MSC_SCAN, KEY, SYN] group is forwarded verbatim with no
    extra syns — the stream's own SYN flushes the report."""
    lis, fake, _ = make_listener({})
    feed(lis, [
        Ev(EV_MSC, MSC_SCAN, 0x70004),
        Ev(EV_KEY, KEY_A, 1),
        Ev(EV_SYN, SYN_REPORT, 0),
    ])
    assert fake.syns == 0
    assert fake.events == [
        (EV_MSC, MSC_SCAN, 0x70004),
        (EV_KEY, KEY_A, 1),
        (EV_SYN, SYN_REPORT, 0),
    ]


def test_swallowed_hotkey_drops_key_but_keeps_report_framing():
    """A swallowed hotkey key is not replayed, but its surrounding MSC_SCAN/SYN
    still flow so the report stays well-framed — and still no extra syns."""
    lis, fake, fired = make_listener({"record": (KEY_LEFTCTRL, KEY_R)})
    feed(lis, [Ev(EV_MSC, MSC_SCAN, 0x700e0), Ev(EV_KEY, KEY_LEFTCTRL, 1), Ev(EV_SYN, SYN_REPORT, 0)])
    feed(lis, [Ev(EV_MSC, MSC_SCAN, 0x70015), Ev(EV_KEY, KEY_R, 1), Ev(EV_SYN, SYN_REPORT, 0)])

    assert fake.syns == 0
    assert (EV_KEY, KEY_LEFTCTRL, 1) in fake.events   # modifier passes through
    assert (EV_KEY, KEY_R, 1) not in fake.events       # trigger is swallowed
    assert (EV_MSC, MSC_SCAN, 0x70015) in fake.events  # its scancode still flushes
    assert [o.pressed for o in fired if o.pressed] == ["record"]


class FakeDevice:
    """Selector-registerable stand-in backed by a real pipe fd so a real
    DefaultSelector reports it readable; read() runs the injected behavior."""
    def __init__(self, path, on_read):
        self.path = path
        self._on_read = on_read
        self._r, self._w = os.pipe()
        self.closed = False
        self.grabbed = False

    def fileno(self):
        return self._r

    def make_readable(self):
        os.write(self._w, b"\x00")

    def read(self):
        try:
            os.read(self._r, 64)
        except OSError:
            pass
        return self._on_read()

    def grab(self):
        self.grabbed = True

    def close(self):
        self.closed = True
        for fd in (self._r, self._w):
            try:
                os.close(fd)
            except OSError:
                pass


def _wait_until(predicate, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and not predicate():
        time.sleep(0.01)
    return predicate()


def test_loop_recovers_when_grabbed_device_disappears(monkeypatch):
    """ENODEV mid-read must not kill the listener thread: the dead device is
    dropped and a re-discovered keyboard is grabbed and the loop carries on."""
    def vanish():
        raise OSError(19, "No such device")

    dying = FakeDevice("/dev/input/event0", vanish)
    replacement = FakeDevice("/dev/input/event1", lambda: [])
    monkeypatch.setattr(listener_mod, "open_devices", lambda override: [replacement])

    lis = Listener(HotkeyEngine({}), set, lambda outcome: None)
    lis._devices = [dying]
    lis._grabbed = True
    lis._stop_r, lis._stop_w = os.pipe()

    t = threading.Thread(target=lis._loop, args=(StubEcodes,), daemon=True)
    t.start()
    dying.make_readable()

    assert _wait_until(lambda: replacement in lis._devices)
    lis.stop()
    t.join(timeout=2.0)

    assert not t.is_alive()           # thread survived the device loss
    assert dying.closed               # dead device released
    assert replacement.grabbed        # replacement re-grabbed
    assert dying not in lis._devices
    os.close(lis._stop_r)
    os.close(lis._stop_w)
    replacement.close()


def test_find_keyboards_excludes_our_own_virtual_device(monkeypatch):
    """The injection device has letter keys too; if find_keyboards() returned it
    the listener would grab it and read back everything it types — a feedback loop."""
    import sys
    import types

    from easytype.listener import VIRTUAL_KBD_NAME, find_keyboards

    class FakeInput:
        def __init__(self, path, name):
            self.path, self.name, self.closed = path, name, False
        def capabilities(self):
            return {1: [30, 44]}      # EV_KEY -> [KEY_A, KEY_Z]
        def close(self):
            self.closed = True

    real = FakeInput("/dev/input/event3", "AT Translated Set 2 keyboard")
    ours = FakeInput("/dev/input/event25", VIRTUAL_KBD_NAME)
    devs = {real.path: real, ours.path: ours}

    fake_evdev = types.ModuleType("evdev")
    fake_evdev.ecodes = types.SimpleNamespace(EV_KEY=1, KEY_A=30, KEY_Z=44)
    fake_evdev.list_devices = lambda: list(devs)
    fake_evdev.InputDevice = lambda p: devs[p]
    monkeypatch.setitem(sys.modules, "evdev", fake_evdev)

    found = find_keyboards()

    assert real in found
    assert ours not in found
    assert ours.closed                # filtered-out device is released, not leaked


def test_idle_rescan_regrabs_returning_kbd_while_another_survives(monkeypatch):
    """The reported bug: when one of several grabbed keyboards drops and returns,
    it must be re-grabbed even though a surviving keyboard keeps the list non-empty."""
    survivor = FakeDevice("/dev/input/event3", lambda: [])
    newcomer = FakeDevice("/dev/input/event26", lambda: [])
    # open_devices re-reports the survivor (a fresh handle, same path) plus the
    # returning keyboard, exactly as a real rescan would after a re-enumeration.
    monkeypatch.setattr(listener_mod, "open_devices",
                        lambda override: [FakeDevice("/dev/input/event3", lambda: []), newcomer])

    lis = Listener(HotkeyEngine({}), set, lambda outcome: None)
    lis._devices = [survivor]
    lis._grabbed = True
    sel = selectors.DefaultSelector()
    sel.register(survivor, selectors.EVENT_READ)

    lis._grab_new_keyboards(sel)

    assert survivor in lis._devices and newcomer in lis._devices
    assert newcomer.grabbed           # returning keyboard re-grabbed despite the survivor
    assert not survivor.grabbed       # survivor already held — left untouched, not double-grabbed
    sel.close()
    survivor.close()
    newcomer.close()
