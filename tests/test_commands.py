from easytype.commands import apply_commands, split_scratch


def test_spoken_punctuation_becomes_characters():
    assert apply_commands("we need three cameras comma two readers period") == (
        "we need three cameras , two readers ."
    )


def test_question_and_exclamation():
    assert apply_commands("is that right question mark") == "is that right ?"
    assert apply_commands("watch out exclamation point") == "watch out !"


def test_new_line_and_new_paragraph():
    assert apply_commands("first new line second") == "first \n second"
    assert apply_commands("first new paragraph second") == "first \n\n second"


def test_newline_said_as_one_word_is_the_same_command():
    assert apply_commands("first newline second") == "first \n second"


def test_matching_ignores_case():
    assert apply_commands("that is all Period") == "that is all ."


def test_trailing_punctuation_whisper_attached_is_absorbed():
    # Whisper very often returns "New paragraph." rather than a bare phrase.
    assert apply_commands("New paragraph. Then this") == "\n\n Then this"
    assert apply_commands("done period.") == "done ."


def test_a_command_word_inside_a_longer_word_is_left_alone():
    assert apply_commands("the periodic table") == "the periodic table"
    assert apply_commands("commatose") == "commatose"


def test_new_paragraph_wins_over_new_line():
    # "new line" is a substring risk only if the longer phrase is matched second.
    assert "\n\n" in apply_commands("stop new paragraph go")


def test_text_with_no_commands_is_untouched():
    assert apply_commands("the camera counts are fine.") == "the camera counts are fine."


def test_split_scratch_returns_everything_when_the_phrase_is_absent():
    assert split_scratch("the camera counts") == ("the camera counts", False)


def test_split_scratch_drops_what_came_before_the_phrase():
    assert split_scratch("three cameras scratch that four cameras") == ("four cameras", False)


def test_split_scratch_at_the_start_also_clears_the_dictation_before():
    assert split_scratch("scratch that") == ("", True)
    assert split_scratch("Scratch that.") == ("", True)


def test_split_scratch_uses_the_last_occurrence():
    assert split_scratch("a scratch that b scratch that c") == ("c", False)


def test_split_scratch_at_the_start_keeps_what_follows_it():
    assert split_scratch("scratch that four cameras") == ("four cameras", True)
