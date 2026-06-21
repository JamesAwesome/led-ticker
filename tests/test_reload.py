import os
import time

from led_ticker import reload as rl
from led_ticker.config import load_config


def _write(path, body):
    path.write_text(body)
    return path


_MIN = '[display]\nrows = 16\ncols = 32\n\n[[playlist.section]]\nmode = "swap"\n'


def test_watcher_no_change_when_unchanged(tmp_path):
    p = _write(tmp_path / "c.toml", _MIN)
    w = rl.ConfigWatcher(p)
    assert w.changed() is False


def test_watcher_detects_content_change(tmp_path):
    p = _write(tmp_path / "c.toml", _MIN)
    w = rl.ConfigWatcher(p)
    p.write_text(_MIN + "\n# edited\n")
    os.utime(p, (time.time() + 5, time.time() + 5))  # ensure mtime advances
    assert w.changed() is True


def test_watcher_ignores_noop_touch(tmp_path):
    p = _write(tmp_path / "c.toml", _MIN)
    w = rl.ConfigWatcher(p)
    os.utime(p, (time.time() + 5, time.time() + 5))  # mtime bump, identical bytes
    assert w.changed() is False


def test_watcher_disabled_never_changes(tmp_path):
    p = _write(tmp_path / "c.toml", _MIN)
    w = rl.ConfigWatcher(p, enabled=False)
    p.write_text(_MIN + "\n# edited\n")
    os.utime(p, (time.time() + 5, time.time() + 5))
    assert w.changed() is False


def test_watcher_missing_file_no_change(tmp_path):
    p = _write(tmp_path / "c.toml", _MIN)
    w = rl.ConfigWatcher(p)
    p.unlink()
    assert w.changed() is False  # no raise


def test_watcher_vanished_then_restored_is_detected(tmp_path):
    """A file deleted mid-check must not advance _last_mtime; a later
    restore with new content must still be detected on the next poll."""
    p = _write(tmp_path / "c.toml", _MIN)
    w = rl.ConfigWatcher(p)
    # Simulate: file vanishes between stat and hash (unlink after we grab a new mtime)
    p.unlink()
    assert w.changed() is False  # vanished → no advance
    # Restore with different content and a future mtime
    _write(p, _MIN + "\n# restored\n")
    os.utime(p, (time.time() + 10, time.time() + 10))
    assert w.changed() is True  # restored file detected


async def test_load_and_validate_valid(tmp_path):
    p = _write(tmp_path / "c.toml", _MIN)
    cfg, errors, transient = await rl.load_and_validate(p)
    assert cfg is not None and errors == [] and transient is False


async def test_load_and_validate_invalid_returns_string_errors(tmp_path):
    # A config that fails validation: rule 1 (content_height × scale > panel height).
    # rows=8 → panel_h=8; content_height=20 → 20 > 8 → error.
    # Uses [[playlist.section]] (the correct TOML key load_config reads).
    bad = (
        "[display]\nrows = 8\ncols = 32\n\n"
        '[[playlist.section]]\nmode = "swap"\ncontent_height = 20\n'
    )
    p = _write(tmp_path / "c.toml", bad)
    cfg, errors, transient = await rl.load_and_validate(p)
    assert cfg is None and transient is False
    assert errors and all(isinstance(e, str) for e in errors)
    # Contract: errors are formatted as "location: message"
    assert any(":" in e for e in errors)


async def test_load_and_validate_missing_file_is_transient(tmp_path):
    cfg, errors, transient = await rl.load_and_validate(tmp_path / "gone.toml")
    assert cfg is None and errors == [] and transient is True


def test_nonreloadable_changed_hardware_field(tmp_path):
    a = load_config(_write(tmp_path / "a.toml", _MIN))
    b_toml = '[display]\nrows = 32\ncols = 32\n\n[[playlist.section]]\nmode = "swap"\n'
    b = load_config(_write(tmp_path / "b.toml", b_toml))
    assert "display.rows" in rl.nonreloadable_changed(a, b)


def test_nonreloadable_changed_section_only_is_empty(tmp_path):
    a = load_config(_write(tmp_path / "a.toml", _MIN))
    extra = '[[playlist.section.widgets]]\ntype = "message"\ntext = "hi"\n'
    b = load_config(_write(tmp_path / "b.toml", _MIN + extra))
    # Both configs have a real section; only sections differ, not display.
    assert a.sections and b.sections, "fixture must produce non-empty sections"
    assert rl.nonreloadable_changed(a, b) == []


def test_nonreloadable_changed_brightness_is_reloadable(tmp_path):
    a = load_config(_write(tmp_path / "a.toml", _MIN))
    b_toml = (
        "[display]\nrows = 16\ncols = 32\nbrightness = 50\n\n"
        '[[playlist.section]]\nmode = "swap"\n'
    )
    b = load_config(_write(tmp_path / "b.toml", b_toml))
    assert "display.brightness" not in rl.nonreloadable_changed(a, b)


def test_every_frame_field_is_restart_required():
    """Drift guard: every display.* field build_frame_from_config consumes must be
    restart-required (NOT in RELOADABLE_DISPLAY_FIELDS), so a future frame field can
    never be silently treated as hot-reloadable."""
    from dataclasses import fields

    from led_ticker.config import DisplayConfig

    frame_fields = {
        "rows",
        "cols",
        "chain_length",
        "parallel",
        "pixel_mapper_config",
        "gpio_slowdown",
        "hardware_mapping",
        "pwm_bits",
        "pwm_lsb_nanoseconds",
        "pwm_dither_bits",
        "show_refresh_rate",
        "disable_hardware_pulsing",
        "rp1_pio",
        "limit_refresh_rate_hz",
        "multiplexing",
        "row_address_type",
        "panel_type",
        "led_rgb_sequence",
    }
    declared = {f.name for f in fields(DisplayConfig)}
    # every frame field must actually exist on DisplayConfig (catches renames)
    assert frame_fields <= declared, frame_fields - declared
    # and none of them may be reloadable
    assert frame_fields.isdisjoint(rl.RELOADABLE_DISPLAY_FIELDS)
