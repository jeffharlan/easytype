from easytype.config import DictEntry
from easytype.dictionary import apply_dictionary


def test_smart_is_case_insensitive_and_whole_word():
    entries = [DictEntry("ops plus", "OPS+", "smart")]
    assert apply_dictionary("Check Ops Plus today", entries) == "Check OPS+ today"


def test_smart_does_not_match_inside_word():
    entries = [DictEntry("main", "MAIN", "smart")]
    assert apply_dictionary("remainder", entries) == "remainder"


def test_exact_is_literal_and_case_sensitive():
    entries = [DictEntry("see see", "Claude Code", "exact")]
    assert apply_dictionary("run see see now", entries) == "run Claude Code now"
    assert apply_dictionary("run SEE SEE now", entries) == "run SEE SEE now"


def test_replacement_with_special_chars_is_literal():
    entries = [DictEntry("slash", "/", "smart")]
    assert apply_dictionary("type slash here", entries) == "type / here"


def test_entries_apply_in_order():
    entries = [DictEntry("claw dot md", "claude.md", "smart"), DictEntry("md", "MD", "exact")]
    # "claw dot md" → "claude.md", then exact "md" → "MD" inside it
    assert apply_dictionary("open claw dot md", entries) == "open claude.MD"


def test_no_entries_returns_input():
    assert apply_dictionary("nothing changes", []) == "nothing changes"
