from easytype.chords import HotkeyEngine, trigger_key

KEY_LEFTCTRL, KEY_SPACE, KEY_ESC, KEY_F8, KEY_BACKSLASH, KEY_A, KEY_RIGHTCTRL = 29, 57, 1, 66, 43, 30, 97


def test_trigger_is_non_modifier():
    assert trigger_key((KEY_LEFTCTRL, KEY_SPACE)) == KEY_SPACE
    assert trigger_key((KEY_BACKSLASH, KEY_LEFTCTRL)) == KEY_BACKSLASH


def test_trigger_all_modifiers_is_last():
    assert trigger_key((KEY_RIGHTCTRL,)) == KEY_RIGHTCTRL


def make_engine():
    return HotkeyEngine({"record": (KEY_LEFTCTRL, KEY_SPACE), "cancel": (KEY_ESC,), "repaste": (KEY_F8,)})


def test_ctrl_space_fires_and_swallows_only_space():
    eng = make_engine()
    enabled = {"record", "cancel", "repaste"}
    o1 = eng.feed(KEY_LEFTCTRL, 1, enabled)   # ctrl down → forwarded
    assert o1.swallow is False and o1.pressed is None
    o2 = eng.feed(KEY_SPACE, 1, enabled)      # space down while ctrl held → fire+swallow
    assert o2.swallow is True and o2.pressed == "record"
    o3 = eng.feed(KEY_SPACE, 0, enabled)      # space up → swallowed (no leak)
    assert o3.swallow is True
    o4 = eng.feed(KEY_LEFTCTRL, 0, enabled)   # ctrl up → forwarded
    assert o4.swallow is False


def test_lone_keys_pass_through():
    eng = make_engine()
    enabled = {"record", "cancel", "repaste"}
    assert eng.feed(KEY_A, 1, enabled).swallow is False
    assert eng.feed(KEY_A, 0, enabled).swallow is False


def test_space_without_ctrl_does_not_fire():
    eng = make_engine()
    enabled = {"record", "cancel", "repaste"}
    o = eng.feed(KEY_SPACE, 1, enabled)
    assert o.swallow is False and o.pressed is None


def test_cancel_only_active_when_enabled():
    eng = make_engine()
    # cancel NOT enabled → Esc passes through, no fire
    o = eng.feed(KEY_ESC, 1, {"record", "repaste"})
    assert o.swallow is False and o.pressed is None
    eng.feed(KEY_ESC, 0, {"record", "repaste"})
    # cancel enabled → Esc fires and is swallowed
    o2 = eng.feed(KEY_ESC, 1, {"record", "cancel", "repaste"})
    assert o2.swallow is True and o2.pressed == "cancel"


def test_hold_release_reported():
    eng = make_engine()
    enabled = {"record", "cancel", "repaste"}
    eng.feed(KEY_LEFTCTRL, 1, enabled)
    eng.feed(KEY_SPACE, 1, enabled)
    out = eng.feed(KEY_SPACE, 0, enabled)
    assert out.released == "record"


def test_repeat_of_swallowed_trigger_is_swallowed():
    eng = make_engine()
    enabled = {"record", "cancel", "repaste"}
    eng.feed(KEY_LEFTCTRL, 1, enabled)
    eng.feed(KEY_SPACE, 1, enabled)
    out = eng.feed(KEY_SPACE, 2, enabled)  # autorepeat
    assert out.swallow is True and out.pressed is None
