from easytype.polish import polish_stream, polish_text


def test_polish_stream_adds_no_closing_period():
    assert polish_stream("check the camera counts") == "Check the camera counts"


def test_polish_stream_preserves_a_trailing_space():
    assert polish_stream("check the camera ") == "Check the camera "


def test_polish_stream_capitalizes_sentence_starts_and_standalone_i():
    assert polish_stream("i said hello. then i left") == "I said hello. Then I left"


def test_polish_stream_is_prefix_stable_over_whole_words():
    full = "i said hello. then i left the site"
    whole = polish_stream(full)
    words = full.split(" ")
    for i in range(1, len(words)):
        prefix = " ".join(words[:i]) + " "
        assert whole.startswith(polish_stream(prefix)), f"broke at {prefix!r}"


def test_polish_stream_on_empty_text():
    assert polish_stream("   ") == "   "


def test_capitalizes_first_letter():
    assert polish_text("hello there") == "Hello there."


def test_capitalizes_after_period():
    assert polish_text("hello there. how are you") == "Hello there. How are you."


def test_capitalizes_after_question_and_exclamation():
    assert polish_text("really? yes! great") == "Really? Yes! Great."


def test_capitalizes_standalone_i():
    assert polish_text("then i left") == "Then I left."


def test_capitalizes_i_contractions():
    assert polish_text("i'm sure i'll go and i've seen what i'd want") == (
        "I'm sure I'll go and I've seen what I'd want."
    )


def test_leaves_i_inside_words_alone():
    assert polish_text("this list is fine") == "This list is fine."


def test_removes_space_before_punctuation():
    assert polish_text("wait , then stop .") == "Wait, then stop."


def test_collapses_double_spaces():
    assert polish_text("too   many    spaces") == "Too many spaces."


def test_adds_terminal_period_when_missing():
    assert polish_text("send the proposal") == "Send the proposal."


def test_keeps_existing_terminal_punctuation():
    assert polish_text("are you ready?") == "Are you ready?"
    assert polish_text("watch out!") == "Watch out!"


def test_replaces_trailing_comma_with_period():
    assert polish_text("first this, then that,") == "First this, then that."


def test_empty_string_unchanged():
    assert polish_text("") == ""
    assert polish_text("   ") == "   "


def test_already_correct_text_unchanged():
    assert polish_text("Send the proposal Wednesday.") == "Send the proposal Wednesday."
