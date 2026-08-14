from easytype.config import DictEntry
from easytype.live import LiveTypist, pending_chunk, settled_prefix


class FakeInjector:
    def __init__(self, window="win-1"):
        self.window = window
        self.typed = []
        self.backspaces = []

    def active_window(self):
        return self.window

    def type_text(self, text):
        self.typed.append(text)

    def backspace(self, count):
        self.backspaces.append(count)


def test_settled_prefix_holds_back_the_last_agreed_word():
    # "camera" is agreed but sits at the boundary — it could still become "cameras".
    assert settled_prefix("check the camera", "check the camera counts") == "check the "


def test_settled_prefix_grows_as_passes_agree_on_more():
    # Always one word behind the agreed region: "counts" is agreed but withheld.
    assert settled_prefix(
        "check the camera counts", "check the camera counts at the site"
    ) == "check the camera "


def test_settled_prefix_is_empty_when_the_transcript_was_rewritten():
    assert settled_prefix("recognize speech", "wreck a nice beach") == ""


def test_settled_prefix_ignores_a_case_flip_on_the_opening_word():
    assert settled_prefix("Check the camera", "check the camera counts") == "check the "


def test_settled_prefix_emits_the_newer_spelling():
    settled = settled_prefix("Check the camera", "check the camera counts")
    assert settled.startswith("c")


def test_settled_prefix_with_no_complete_shared_word():
    assert settled_prefix("checking", "checkers") == ""


def test_settled_prefix_on_first_pass_has_nothing_to_agree_with():
    assert settled_prefix("", "check the camera") == ""


def test_pending_chunk_returns_what_is_not_yet_typed():
    assert pending_chunk("check the camera counts ", "check the ") == "camera counts "


def test_pending_chunk_is_empty_when_nothing_is_new():
    assert pending_chunk("check the ", "check the ") == ""


def test_pending_chunk_refuses_to_patch_a_changed_earlier_word():
    assert pending_chunk("wreck a nice beach ", "recognize ") == ""


def test_feed_types_each_settled_chunk_exactly_once():
    inj = FakeInjector()
    typist = LiveTypist(inj)
    typist.start()
    typist.feed("check the camera")
    typist.feed("check the camera counts")
    typist.feed("check the camera counts at the site")
    assert "".join(inj.typed) == "Check the camera "
    assert inj.backspaces == []


def test_feed_types_nothing_on_the_first_pass():
    inj = FakeInjector()
    typist = LiveTypist(inj)
    typist.start()
    typist.feed("check the camera")
    assert inj.typed == []


def test_multi_word_dictionary_rule_spanning_a_chunk_boundary():
    inj = FakeInjector()
    typist = LiveTypist(inj, dictionary=[DictEntry("ops plus", "OPS+", "smart")])
    typist.start()
    typist.feed("ops plus is")
    typist.feed("ops plus is ready")
    typist.feed("ops plus is ready now")
    assert "".join(inj.typed) == "OPS+ is "


def test_feed_does_not_type_when_focus_moved():
    inj = FakeInjector()
    typist = LiveTypist(inj)
    typist.start()
    inj.window = "win-2"
    typist.feed("check the camera")
    typist.feed("check the camera counts")
    assert inj.typed == []


def test_feed_resumes_when_focus_returns():
    inj = FakeInjector()
    typist = LiveTypist(inj)
    typist.start()
    inj.window = "win-2"
    typist.feed("check the camera")
    typist.feed("check the camera counts")
    inj.window = "win-1"
    typist.feed("check the camera counts at the site")
    assert "".join(inj.typed) == "Check the camera "


def test_feed_never_types_when_the_window_id_is_unknown():
    inj = FakeInjector(window="")
    typist = LiveTypist(inj)
    typist.start()
    typist.feed("check the camera")
    typist.feed("check the camera counts")
    assert inj.typed == []


def test_active_is_false_until_something_is_typed():
    inj = FakeInjector()
    typist = LiveTypist(inj)
    typist.start()
    assert typist.active is False
    typist.feed("check the camera")
    typist.feed("check the camera counts")
    assert typist.active is True


def test_finish_appends_the_remainder_and_the_closing_period():
    inj = FakeInjector()
    typist = LiveTypist(inj)
    typist.start()
    typist.feed("check the camera")
    typist.feed("check the camera counts")          # typed "Check the "
    inj.typed.clear()
    typist.finish("Check the camera counts.")
    assert inj.backspaces == []
    assert "".join(inj.typed) == "camera counts."


def test_finish_backspaces_only_back_to_the_divergence():
    inj = FakeInjector()
    typist = LiveTypist(inj)
    typist.start()
    typist.feed("check the camera counts")
    typist.feed("check the camera counts at")       # typed "Check the camera "
    inj.typed.clear()
    # The final pass settled on "cameras": the two agree through "Check the camera"
    # and diverge one character later, so exactly one character is taken back.
    typist.finish("Check the cameras on site.")
    assert inj.backspaces == [1]
    assert "".join(inj.typed) == "s on site."


def test_finish_types_nothing_when_focus_moved():
    inj = FakeInjector()
    typist = LiveTypist(inj)
    typist.start()
    typist.feed("check the camera")
    typist.feed("check the camera counts")
    inj.typed.clear()
    inj.window = "win-2"
    typist.finish("Check the camera counts.")
    assert inj.typed == []
    assert inj.backspaces == []


def test_undo_backspaces_exactly_what_was_typed():
    inj = FakeInjector()
    typist = LiveTypist(inj)
    typist.start()
    typist.feed("check the camera")
    typist.feed("check the camera counts")
    assert typist.undo() is True
    assert inj.backspaces == [len("Check the ")]
    assert typist.active is False


def test_undo_does_nothing_when_focus_moved():
    inj = FakeInjector()
    typist = LiveTypist(inj)
    typist.start()
    typist.feed("check the camera")
    typist.feed("check the camera counts")
    inj.window = "win-2"
    assert typist.undo() is False
    assert inj.backspaces == []


def test_undo_with_nothing_typed_is_a_noop():
    inj = FakeInjector()
    typist = LiveTypist(inj)
    typist.start()
    assert typist.undo() is True
    assert inj.backspaces == []


def test_start_clears_state_from_the_previous_recording():
    inj = FakeInjector()
    typist = LiveTypist(inj)
    typist.start()
    typist.feed("check the camera")
    typist.feed("check the camera counts")
    typist.start()
    assert typist.active is False
    inj.typed.clear()
    typist.feed("different words entirely")
    typist.feed("different words entirely now")
    assert "".join(inj.typed) == "Different words "
