import pytest

from led_ticker.backends import BackendNotReadyError
from led_ticker.backends.headless import HeadlessBackend
from led_ticker.frame import LedFrame


def _frame():
    return LedFrame(backend=HeadlessBackend(160, 16))


def test_create_canvas_before_setup_raises():
    f = _frame()
    with pytest.raises(BackendNotReadyError):
        f.create_canvas()


def test_swap_before_setup_raises():
    f = _frame()
    with pytest.raises(BackendNotReadyError):
        f.swap(object())


def test_brightness_before_setup_raises():
    f = _frame()
    with pytest.raises(BackendNotReadyError):
        _ = f.brightness
    with pytest.raises(BackendNotReadyError):
        f.brightness = 50


def test_create_canvas_after_setup():
    f = _frame()
    f.setup()
    c = f.create_canvas()
    assert (c.width, c.height) == (160, 16)


def test_swap_returns_different_object_and_records(monkeypatch):
    import led_ticker.status_board as sb

    calls = []
    monkeypatch.setattr(sb, "record_swap", lambda: calls.append(1))
    f = _frame()
    f.setup()
    front = f.get_clean_canvas()
    back = f.swap(front)
    assert back is not front
    assert calls  # record_swap fired inside swap


def test_overlay_hooks_run_in_swap():
    f = _frame()
    f.setup()
    painted = []
    f.overlay_hooks.append(lambda canvas: painted.append(canvas))
    c = f.get_clean_canvas()
    f.swap(c)
    assert painted == [c]


def test_brightness_forwards_after_setup():
    f = _frame()
    f.setup()
    f.brightness = 42
    assert f.brightness == 42
