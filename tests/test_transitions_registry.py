"""Smoke tests for the transitions public registry API."""

from led_ticker.transitions import list_transition_names


def test_list_transition_names_returns_sorted_list():
    names = list_transition_names()
    assert isinstance(names, list)
    assert names == sorted(names)


def test_list_transition_names_includes_core_transitions():
    names = list_transition_names()
    for expected in ("cut", "wipe_left", "push_right", "dissolve"):
        assert expected in names, f"{expected!r} not in registry"


def test_sprite_trail_transitions_not_in_core_registry():
    """Sprite-trail transitions were extracted to the led-ticker-plugins
    monorepo; they must NOT appear in core."""
    names = list_transition_names()
    for removed in ("nyancat", "pokeball", "pacman", "sailor_moon"):
        assert removed not in names, (
            f"{removed!r} is still in core — should ship in the "
            f"led-ticker-plugins monorepo ({removed} package)"
        )


def test_list_transition_names_does_not_include_private():
    names = list_transition_names()
    for name in names:
        assert not name.startswith("_"), f"private name {name!r} leaked into registry"
