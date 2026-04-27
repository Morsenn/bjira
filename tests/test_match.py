import pytest
from bjira._match import match_transition, resolve_link_type, AmbiguousMatch, NoMatch


TRANSITIONS = [
    {"id": "1421", "name": "Backlog"},
    {"id": "1501", "name": "Development: In progress"},
    {"id": "1511", "name": "Development: Done"},
    {"id": "1481", "name": "Decomposition: In progress"},
    {"id": "1381", "name": "Fixed"},
]


def test_match_by_exact_numeric_id():
    assert match_transition("1501", TRANSITIONS) == "1501"


def test_match_by_exact_name():
    assert match_transition("Development: In progress", TRANSITIONS) == "1501"


def test_match_by_case_insensitive_substring():
    assert match_transition("dev in pro", TRANSITIONS) == "1501"


def test_match_case_insensitive_exact():
    assert match_transition("fixed", TRANSITIONS) == "1381"


def test_ambiguous_substring_raises():
    with pytest.raises(AmbiguousMatch) as exc:
        match_transition("development", TRANSITIONS)
    assert "1501" in str(exc.value)
    assert "1511" in str(exc.value)


def test_no_match_raises():
    with pytest.raises(NoMatch):
        match_transition("totallynotathing", TRANSITIONS)


def test_exact_name_wins_over_substring():
    assert match_transition("Backlog", TRANSITIONS) == "1421"


def test_numeric_id_not_in_list_raises():
    with pytest.raises(NoMatch):
        match_transition("9999", TRANSITIONS)


LINK_TYPES = [
    {"name": "Blocks", "inward": "blocked by", "outward": "blocks"},
    {"name": "Relates", "inward": "relates to", "outward": "relates to"},
    {"name": "Duplicate", "inward": "is duplicated by", "outward": "duplicates"},
]


def test_resolve_link_type_exact():
    assert resolve_link_type("Blocks", LINK_TYPES) == "Blocks"


def test_resolve_link_type_case_insensitive():
    assert resolve_link_type("blocks", LINK_TYPES) == "Blocks"
    assert resolve_link_type("BLOCKS", LINK_TYPES) == "Blocks"


def test_resolve_link_type_unknown_raises():
    with pytest.raises(NoMatch) as exc:
        resolve_link_type("notarealtype", LINK_TYPES)
    assert "Blocks" in str(exc.value)
