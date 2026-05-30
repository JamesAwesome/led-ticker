"""Tests for the BusyLight overlay service."""

from pathlib import Path

from rgbmatrix import _StubCanvas

from led_ticker.busy_light import BusyLight


def test_file_path_expands_user():
    busy = BusyLight(file_path="~/.busy")
    assert busy.file_path == Path.home() / ".busy"


async def test_update_busy_when_file_exists(tmp_path):
    f = tmp_path / ".busy"
    f.write_text("")
    busy = BusyLight(file_path=str(f))
    await busy.update()
    assert busy.is_busy is True


async def test_update_not_busy_when_file_absent(tmp_path):
    busy = BusyLight(file_path=str(tmp_path / ".busy"))
    await busy.update()
    assert busy.is_busy is False


def _lit(canvas):
    return {
        (x, y)
        for y in range(canvas.height)
        for x in range(canvas.width)
        if canvas.get_pixel(x, y) != (0, 0, 0)
    }


def test_paint_top_right_block_when_busy():
    canvas = _StubCanvas(width=64, height=32)
    busy = BusyLight(
        file_path="/nonexistent", corner="top_right", color=(255, 0, 0), size=4
    )
    busy.is_busy = True
    busy.paint(canvas)
    assert _lit(canvas) == {(x, y) for x in range(60, 64) for y in range(0, 4)}
    assert canvas.get_pixel(63, 0) == (255, 0, 0)


def test_paint_each_corner():
    cases = {
        "top_left": {(x, y) for x in range(0, 4) for y in range(0, 4)},
        "top_right": {(x, y) for x in range(60, 64) for y in range(0, 4)},
        "bottom_left": {(x, y) for x in range(0, 4) for y in range(28, 32)},
        "bottom_right": {(x, y) for x in range(60, 64) for y in range(28, 32)},
    }
    for corner, expected in cases.items():
        canvas = _StubCanvas(width=64, height=32)
        busy = BusyLight(file_path="/x", corner=corner, color=(1, 2, 3), size=4)
        busy.is_busy = True
        busy.paint(canvas)
        assert _lit(canvas) == expected, corner


def test_paint_nothing_when_not_busy():
    canvas = _StubCanvas(width=64, height=32)
    busy = BusyLight(file_path="/x", size=4)
    busy.is_busy = False
    busy.paint(canvas)
    assert _lit(canvas) == set()


def test_size_clamps_to_canvas_bounds():
    canvas = _StubCanvas(width=8, height=8)
    busy = BusyLight(file_path="/x", corner="top_left", size=100)
    busy.is_busy = True
    busy.paint(canvas)  # must not raise / paint out of range
    assert _lit(canvas) == {(x, y) for x in range(8) for y in range(8)}


async def test_registered_hook_paints_dot_through_frame_swap(tmp_path):
    """End-to-end: a BusyLight.paint hook on a real LedFrame lights the
    corner when busy and clears it when not, through frame.swap()."""
    from led_ticker.frame import LedFrame

    f = tmp_path / ".busy"
    busy = BusyLight(file_path=str(f), corner="top_right", color=(255, 0, 0), size=4)
    frame = LedFrame(led_cols=64, led_rows=32)
    frame.overlay_hooks.append(busy.paint)

    canvas = frame.get_clean_canvas()
    f.write_text("")  # go busy
    await busy.update()
    frame.swap(canvas)  # paint hook runs on `canvas` before SwapOnVSync
    assert canvas.get_pixel(canvas.width - 1, 0) == (255, 0, 0)

    f.unlink()  # not busy
    await busy.update()
    canvas2 = frame.get_clean_canvas()
    frame.swap(canvas2)
    lit = [
        (x, y)
        for y in range(canvas2.height)
        for x in range(canvas2.width)
        if canvas2.get_pixel(x, y) != (0, 0, 0)
    ]
    assert lit == []


def test_set_busy_true_then_false():
    busy = BusyLight(file_path="/x")
    busy.set_busy(True)
    assert busy.is_busy is True
    busy.set_busy(False)
    assert busy.is_busy is False


def test_set_busy_no_ttl_leaves_no_deadline():
    busy = BusyLight(file_path="/x")  # ttl_seconds defaults to 0.0
    busy.set_busy(True, now=100.0)
    assert busy._busy_until is None


def test_ttl_arms_deadline_and_expires():
    busy = BusyLight(file_path="/x", ttl_seconds=30.0)
    busy.set_busy(True, now=100.0)
    assert busy._busy_until == 130.0
    busy.tick_ttl(now=129.0)  # before deadline
    assert busy.is_busy is True
    busy.tick_ttl(now=130.0)  # at deadline
    assert busy.is_busy is False
    assert busy._busy_until is None


def test_ttl_refresh_extends_deadline():
    busy = BusyLight(file_path="/x", ttl_seconds=30.0)
    busy.set_busy(True, now=100.0)
    busy.set_busy(True, now=120.0)  # refresh
    assert busy._busy_until == 150.0
    busy.tick_ttl(now=149.0)
    assert busy.is_busy is True


def test_set_busy_false_clears_deadline():
    busy = BusyLight(file_path="/x", ttl_seconds=30.0)
    busy.set_busy(True, now=100.0)
    busy.set_busy(False, now=110.0)
    assert busy.is_busy is False
    assert busy._busy_until is None


def test_tick_ttl_noop_when_no_deadline():
    busy = BusyLight(file_path="/x")
    busy.is_busy = True
    busy.tick_ttl(now=999.0)  # no deadline armed → must not clear
    assert busy.is_busy is True


def test_per_request_ttl_overrides_config():
    busy = BusyLight(file_path="/x", ttl_seconds=30.0)
    busy.set_busy(True, now=100.0, ttl=5.0)
    assert busy._busy_until == 105.0  # per-request 5, not config 30


def test_per_request_ttl_when_no_config_default():
    busy = BusyLight(file_path="/x")  # ttl_seconds=0
    busy.set_busy(True, now=100.0, ttl=5.0)
    assert busy._busy_until == 105.0
    busy.tick_ttl(now=105.0)
    assert busy.is_busy is False


def test_set_busy_ttl_zero_override_stays_on_and_clears_prior_deadline():
    busy = BusyLight(file_path="/x", ttl_seconds=30.0)
    busy.set_busy(True, now=100.0, ttl=5.0)  # armed at 105
    busy.set_busy(True, now=101.0, ttl=0.0)  # explicit ttl=0 → on indefinitely
    assert busy._busy_until is None
    assert busy.is_busy is True
