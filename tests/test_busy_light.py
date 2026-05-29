"""Tests for the BusyLight overlay service."""

from pathlib import Path

from rgbmatrix import _StubCanvas

from led_ticker.busy_light import BusyLight


def test_file_path_expands_user():
    busy = BusyLight(file_path="~/.busy")
    assert busy.file_path == Path.home() / ".busy"


def test_update_busy_when_file_exists(tmp_path):
    import asyncio

    f = tmp_path / ".busy"
    f.write_text("")
    busy = BusyLight(file_path=str(f))
    asyncio.run(busy.update())
    assert busy.is_busy is True


def test_update_not_busy_when_file_absent(tmp_path):
    import asyncio

    busy = BusyLight(file_path=str(tmp_path / ".busy"))
    asyncio.run(busy.update())
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
