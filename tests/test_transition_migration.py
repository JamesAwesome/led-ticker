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
        "oldname",
        (
            "transition 'oldname' now ships in led-ticker-exampleplugin"
            " as 'exampleplugin.oldname'.",
            "Install led-ticker-exampleplugin and use"
            ' transition = "exampleplugin.oldname".',
        ),
    )
    msg, fix = explain_unknown_transition("oldname")
    assert "led-ticker-exampleplugin" in msg
    assert "exampleplugin.oldname" in fix


def test_namespaced_unknown_gets_plugin_hint():
    msg, fix = explain_unknown_transition("exampleplugin.thing")
    assert msg == "unknown transition 'exampleplugin.thing'"
    assert "exampleplugin" in fix
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
        get_transition_class("exampleplugin.thing")
    assert "exampleplugin" in str(exc.value)
    assert "requirements-plugins.txt" in str(exc.value)


def test_get_transition_class_still_resolves_known():
    assert get_transition_class("push_left").__name__  # a real registered one


def test_migration_wins_over_plugin_hint_for_namespaced_key(monkeypatch):
    # A namespaced key in the migration map must return the migration
    # tuple, NOT the generic "looks like a plugin" hint — pins the
    # migration→hint precedence ordering.
    monkeypatch.setitem(
        transitions._TRANSITION_MIGRATION,
        "exampleplugin.oldname",
        ("migrated message", "migrated fix"),
    )
    msg, fix = explain_unknown_transition("exampleplugin.oldname")
    assert msg == "migrated message"
    assert fix == "migrated fix"


def test_get_transition_class_raises_migration_message(monkeypatch):
    monkeypatch.setitem(
        transitions._TRANSITION_MIGRATION,
        "oldname",
        (
            "transition 'oldname' now ships in led-ticker-exampleplugin.",
            "Install led-ticker-exampleplugin.",
        ),
    )
    with pytest.raises(ValueError) as exc:
        get_transition_class("oldname")
    assert "led-ticker-exampleplugin" in str(exc.value)
