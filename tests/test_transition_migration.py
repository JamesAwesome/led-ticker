"""Transition migration map + explain_unknown_transition precedence:
migration entry → plugin hint → difflib typo suggestion."""

import pytest

from led_ticker import transitions
from led_ticker.transitions import (
    explain_unknown_transition,
    get_transition_class,
)

_VARIANT = {"": "forward", "_reverse": "reverse", "_alternating": "alternating"}


@pytest.mark.parametrize(
    ("family", "suffix"),
    [
        (family, suffix)
        for family in ("pacman", "sailor_moon", "nyancat", "pokeball")
        for suffix in ("", "_reverse", "_alternating")
    ],
)
def test_bare_sprite_transition_migrates_to_monorepo(family, suffix):
    name = f"{family}{suffix}"
    new = f"{family}.{_VARIANT[suffix]}"
    message, fix = explain_unknown_transition(name)
    assert "led-ticker-plugins monorepo" in message
    assert new in message
    # the fix names the new type + the per-plugin monorepo install line
    assert new in fix
    assert f"subdirectory=plugins/{family}" in fix
    assert f"@{family}-v0.1.0" in fix


def test_unrelated_unknown_transition_has_no_monorepo_hint():
    message, _fix = explain_unknown_transition("definitely_not_a_transition")
    assert "led-ticker-plugins monorepo" not in message


@pytest.mark.parametrize(
    "family,suffix",
    [
        (fam, suf)
        for fam in ("pacman", "sailor_moon", "nyancat", "pokeball")
        for suf in ("", "_reverse", "_alternating")
    ],
)
def test_arcade_plugin_era_transition_migrates_to_split_name(family, suffix):
    # `arcade.nyancat_alternating` was the led-ticker-arcade-plugin name (now
    # archived). A stale config must be told to use the split name
    # `nyancat.alternating`, not to install the gone `arcade` plugin.
    name = f"arcade.{family}{suffix}"
    new = f"{family}.{_VARIANT[suffix]}"
    message, fix = explain_unknown_transition(name)
    assert new in fix
    assert f"subdirectory=plugins/{family}" in fix
    assert "install arcade" not in fix.lower()


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
    assert "plugin install" in fix


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
    assert "plugin install" in str(exc.value)


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
