from collections import namedtuple

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
