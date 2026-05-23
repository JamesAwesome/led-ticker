"""Smoke tests for the transitions public registry API."""

from led_ticker.transitions import list_transition_names


def test_list_transition_names_returns_sorted_list():
    names = list_transition_names()
    assert isinstance(names, list)
    assert names == sorted(names)


def test_list_transition_names_includes_core_transitions():
    names = list_transition_names()
    for expected in ("cut", "wipe_left", "push_right", "dissolve", "nyancat"):
        assert expected in names, f"{expected!r} not in registry"


def test_list_transition_names_does_not_include_private():
    names = list_transition_names()
    for name in names:
        assert not name.startswith("_"), f"private name {name!r} leaked into registry"
