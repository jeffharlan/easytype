from easytype.injector import NullInjector, get_injector
from easytype.injector.x11 import X11Injector


def test_get_injector_x11_returns_x11_injector():
    assert isinstance(get_injector("x11"), X11Injector)


def test_get_injector_wayland_returns_null_injector_instead_of_raising():
    # Phase 1 has no working Wayland injector. Wayland runs only ever reach here
    # via --passive (cli.py refuses a real run first), so this must no-op rather
    # than raise, or --passive on Wayland would crash the moment transcription finished.
    injector = get_injector("wayland")
    assert isinstance(injector, NullInjector)


def test_null_injector_inject_does_not_raise():
    NullInjector().inject("hello", "type")
