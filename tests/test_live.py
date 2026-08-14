from easytype.live import pending_chunk, settled_prefix


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
