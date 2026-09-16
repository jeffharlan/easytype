from easytype.injector import NullInjector, get_injector
from easytype.injector.wayland import WaylandInjector
from easytype.injector.x11 import X11Injector


def test_get_injector_x11_returns_x11_injector():
    assert isinstance(get_injector("x11"), X11Injector)


def test_get_injector_wayland_returns_wayland_injector():
    assert isinstance(get_injector("wayland"), WaylandInjector)


def test_get_injector_unknown_session_returns_null_injector_instead_of_raising():
    # No session marker means no injection backend to pick. Recording and
    # transcription still work, so this must no-op rather than raise or guess.
    injector = get_injector("unknown")
    assert isinstance(injector, NullInjector)


def test_null_injector_inject_does_not_raise():
    NullInjector().inject("hello", "type")


def test_null_injector_answers_the_window_and_typing_calls():
    """Wayland --passive builds a NullInjector. The controller asks it for the
    focused window on every start, and LiveTypist types through it, so a missing
    method there is a crash on the first hotkey press rather than a quiet no-op."""
    n = NullInjector()
    assert n.active_window() == ""
    n.type_text("hello", 10)
    n.backspace(3)
