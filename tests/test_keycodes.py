from easytype.keycodes import describe_chord, conflict_note


def test_describe_chord_ctrl_space():
    assert describe_chord([29, 57]) == "Ctrl+Space"


def test_describe_chord_ctrl_backslash():
    assert describe_chord([29, 43]) == "Ctrl+\\"


def test_describe_chord_single_key():
    assert describe_chord([66]) == "F8"


def test_conflict_note_ctrl_space_mentions_ibus():
    note = conflict_note([29, 57])
    assert note is not None and "IBus" in note


def test_conflict_note_ctrl_backslash_mentions_sigquit():
    note = conflict_note([29, 43])
    assert note is not None and "SIGQUIT" in note


def test_conflict_note_none_for_unknown():
    assert conflict_note([66]) is None
