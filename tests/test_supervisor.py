import threading
import time
import types

from easytype.supervisor import EngineSupervisor


class FakeListener:
    def __init__(self):
        self._go = threading.Event()
        self.stopped = False
        self.capture_cb = None
        self.ran = False

    def run(self, *, device_override="", grab=True):
        self.ran = True
        self._go.wait(timeout=5)             # block like the real evdev loop

    def stop(self):
        self.stopped = True
        self._go.set()

    def begin_capture(self, on_captured):
        self.capture_cb = on_captured


class FakeController:
    def __init__(self):
        self.state = "idle"
        self.toggled = 0

    def toggle_recording(self):
        self.toggled += 1

    def on_cancel(self):
        ...


class FakeBundle:
    def __init__(self):
        self.listener = FakeListener()
        self.controller = FakeController()
        self.warmed = False

    def warmup(self):
        self.warmed = True


def _fake_config():
    return types.SimpleNamespace(keyboard_device="")


def _wait(predicate, timeout=2.0):
    deadline = time.time() + timeout
    while not predicate() and time.time() < deadline:
        time.sleep(0.005)


def test_start_runs_engine_then_stop_joins():
    made = []
    sup = EngineSupervisor(session="x11",
                           builder=lambda cfg: made.append(FakeBundle()) or made[-1],
                           config_loader=_fake_config)
    sup.start()
    _wait(lambda: made and made[0].listener.ran)
    assert made[0].listener.ran is True
    assert sup.state == "idle"
    sup.stop()
    assert made[0].listener.stopped is True
    assert sup.state == "stopped"


def test_reload_rebuilds_engine_from_fresh_config():
    builds = []
    sup = EngineSupervisor(session="x11",
                           builder=lambda cfg: builds.append(FakeBundle()) or builds[-1],
                           config_loader=_fake_config)
    sup.start()
    _wait(lambda: builds and builds[0].listener.ran)
    sup.reload()
    assert len(builds) == 2
    assert builds[0].listener.stopped is True
    sup.stop()


def test_toggle_and_capture_delegate_to_engine():
    b = FakeBundle()
    sup = EngineSupervisor(session="x11", builder=lambda cfg: b, config_loader=_fake_config)
    sup.start()
    _wait(lambda: b.listener.ran)
    sup.toggle_recording()
    assert b.controller.toggled == 1
    cb = lambda keys: None
    sup.begin_hotkey_capture(cb)
    assert b.listener.capture_cb is cb
    sup.stop()
