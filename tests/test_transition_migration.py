"""Transition migration map + explain_unknown_transition precedence:
migration entry → plugin hint → difflib typo suggestion."""

import pytest

from led_ticker import transitions
from led_ticker.transitions import (
    explain_unknown_transition,
    get_transition_class,
)


def test_shipped_migration_map_is_empty():
    """Entries land per-extraction (the crypto precedent). A live entry
    for a transition still present in core would be unreachable."""
    assert transitions._TRANSITION_MIGRATION == {}


def test_migration_entry_wins(monkeypatch):
    monkeypatch.setitem(
        transitions._TRANSITION_MIGRATION,
        "nyancat",
        (
            "transition 'nyancat' now ships in led-ticker-arcade as 'arcade.nyancat'.",
            'Install led-ticker-arcade and use transition = "arcade.nyancat".',
        ),
    )
    msg, fix = explain_unknown_transition("nyancat")
    assert "led-ticker-arcade" in msg
    assert "arcade.nyancat" in fix


def test_namespaced_unknown_gets_plugin_hint():
    msg, fix = explain_unknown_transition("arcade.nyancat")
    assert msg == "unknown transition 'arcade.nyancat'"
    assert "arcade" in fix
    assert "requirements-plugins.txt" in fix


def test_typo_gets_difflib_suggestion():
    msg, fix = explain_unknown_transition("wipe_leftt")
    assert "wipe_leftt" in msg
    assert "wipe_left" in msg  # did-you-mean
    assert "docs.ledticker.dev/transitions/" in fix


def test_unknown_with_no_close_match_has_no_suggestion():
    msg, _ = explain_unknown_transition("zzzzzzz")
    assert "did you mean" not in msg


def test_get_transition_class_raises_rich_message_for_namespaced():
    with pytest.raises(ValueError) as exc:
        get_transition_class("arcade.nyancat")
    assert "arcade" in str(exc.value)
    assert "requirements-plugins.txt" in str(exc.value)


def test_get_transition_class_still_resolves_known():
    assert get_transition_class("push_left").__name__  # a real registered one
