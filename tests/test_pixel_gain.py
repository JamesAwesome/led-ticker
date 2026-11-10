"""AnimationFrame.pixel_gain seam + gain proxy (twinkle plumbing).

Precedence: rotation > lens > pixel_gain. Border/background never route
through the proxy.
"""

from unittest import mock

from led_ticker.animations import AnimationFrame
from led_ticker.backends.headless import HeadlessCanvas
from led_ticker.borders import ConstantBorder
from led_ticker.colors import RGB_WHITE
from led_ticker.fonts import FONT_DEFAULT
from led_ticker.pixel_gain import GainCanvas, with_pixel_gain
from led_ticker.scaled_canvas import ScaledCanvas, unwrap_to_real
from led_ticker.widgets.message import TickerMessage


def test_default_is_none():
    assert AnimationFrame(visible_text="x").pixel_gain is None


def test_gain_scales_setpixel():
    real = HeadlessCanvas(8, 8)
    with_pixel_gain(real, lambda x, y: 0.5).SetPixel(1, 1, 200, 100, 0)
    assert real.get_pixel(1, 1) == (100, 50, 0)


def test_gain_clamped():
    real = HeadlessCanvas(8, 8)
    with_pixel_gain(real, lambda x, y: 2.0).SetPixel(1, 1, 200, 100, 0)
    assert real.get_pixel(1, 1) == (200, 100, 0)
    real.SetPixel(2, 2, 7, 8, 9)
    with_pixel_gain(real, lambda x, y: -1).SetPixel(2, 2, 200, 100, 0)
    assert real.get_pixel(2, 2) == (7, 8, 9)  # skipped, not blacked out


def test_zero_gain_setpixel_preserves_background():
    real = HeadlessCanvas(8, 8)
    real.Fill(0, 0, 255)
    with_pixel_gain(real, lambda x, y: 0.0).SetPixel(3, 3, 255, 255, 255)
    assert real.get_pixel(3, 3) == (0, 0, 255)


def test_zero_gain_subfill_preserves_background():
    real = HeadlessCanvas(8, 8)
    real.Fill(0, 0, 255)
    GainCanvas(real, lambda x, y: 0.0).SubFill(0, 0, 2, 2, 255, 255, 255)
    assert real.get_pixel(0, 0) == (0, 0, 255)
    assert real.get_pixel(1, 1) == (0, 0, 255)


def test_gain_reaches_bdf_scaled_path():
    real = HeadlessCanvas(64, 64)
    scaled = ScaledCanvas(real, scale=4, content_height=16)
    calls = []

    def gain(x, y):
        calls.append((x, y))
        return 0.5

    wrapped = with_pixel_gain(scaled, gain)
    wrapped.SetPixel(2, 3, 200, 100, 0)
    rx, ry = 2 * 4, 3 * 4 + scaled.y_offset_real
    assert calls == [(rx, ry)]
    lit = {
        (x, y)
        for x in range(64)
        for y in range(64)
        if real.get_pixel(x, y) != (0, 0, 0)
    }
    assert lit == {(rx + dx, ry + dy) for dx in range(4) for dy in range(4)}
    assert all(real.get_pixel(x, y) == (100, 50, 0) for x, y in lit)


def test_subfill_is_gained():
    real = HeadlessCanvas(8, 8)
    GainCanvas(real, lambda x, y: 0.5).SubFill(0, 0, 2, 2, 200, 0, 0)
    for xy in ((0, 0), (1, 0), (0, 1), (1, 1)):
        assert real.get_pixel(*xy) == (100, 0, 0)


def test_gain_reaches_hires_path():
    scaled = ScaledCanvas(HeadlessCanvas(64, 64), scale=4, content_height=16)
    assert isinstance(
        unwrap_to_real(with_pixel_gain(scaled, lambda x, y: 1.0)), GainCanvas
    )


def test_plain_canvas_returns_gain_canvas():
    assert isinstance(
        with_pixel_gain(HeadlessCanvas(8, 8), lambda x, y: 1.0), GainCanvas
    )


def test_nested_wrapper():
    real = HeadlessCanvas(64, 64)
    inner = ScaledCanvas(real, scale=2, content_height=32)
    outer = ScaledCanvas(inner, scale=2, content_height=16)
    wrapped = with_pixel_gain(outer, lambda x, y: 0.5)
    assert isinstance(unwrap_to_real(wrapped), GainCanvas)
    assert isinstance(wrapped, ScaledCanvas) and isinstance(wrapped.real, ScaledCanvas)
    wrapped.SetPixel(1, 1, 200, 0, 0)
    # caller's wrappers untouched
    assert outer.real is inner and inner.real is real

    ref = HeadlessCanvas(64, 64)
    ScaledCanvas(
        ScaledCanvas(ref, scale=2, content_height=32), scale=2, content_height=16
    ).SetPixel(1, 1, 100, 0, 0)
    assert real._pixels == ref._pixels
    assert real.count_nonzero() > 0


def _text_widget(animation=None, center=False, **kw):
    return TickerMessage(
        text="HELLO",
        font=FONT_DEFAULT,
        font_color=RGB_WHITE,
        animation=animation,
        center=center,
        **kw,
    )


class _Stub:
    restart_on_visit = True

    def __init__(self, **frame_kw):
        self.frame_kw = frame_kw

    def frame_for(self, frame, full_text, canvas_width, text_width):
        return AnimationFrame(visible_text=full_text, **self.frame_kw)


def test_message_text_twinkles_border_does_not():
    border = ConstantBorder((0, 0, 255))
    c = HeadlessCanvas(160, 16)
    # non-centered: text starts at x=0 and collides with the left border
    # column; gain-0 text must leave those border pixels intact.
    _text_widget(_Stub(pixel_gain=lambda x, y: 0.0), border=border).draw(c)
    assert all(v == (0, 0, 255) for v in c._pixels.values() if v != (0, 0, 0))
    # border fully present, no text pixels inside the perimeter
    ref = HeadlessCanvas(160, 16)
    border.paint(ref, 0)
    assert {k: v for k, v in c._pixels.items() if v != (0, 0, 0)} == {
        k: v for k, v in ref._pixels.items() if v != (0, 0, 0)
    }


def test_message_byte_identical_without_gain():
    a = HeadlessCanvas(160, 16)
    b = HeadlessCanvas(160, 16)
    _text_widget(_Stub()).draw(a)
    _text_widget().draw(b)
    assert a._pixels == b._pixels
    assert a.count_nonzero() > 0


def test_message_gain_dims_text():
    a = HeadlessCanvas(160, 16)
    _text_widget(_Stub(pixel_gain=lambda x, y: 0.5)).draw(a)
    vals = {v for v in a._pixels.values() if v != (0, 0, 0)}
    assert vals == {
        (
            round(RGB_WHITE.red * 0.5),
            round(RGB_WHITE.green * 0.5),
            round(RGB_WHITE.blue * 0.5),
        )
    }


def test_rotation_ignores_gain():
    a = HeadlessCanvas(160, 16)
    b = HeadlessCanvas(160, 16)
    _text_widget(_Stub(rotation=90.0, pixel_gain=lambda x, y: 0.0)).draw(a)
    _text_widget(_Stub(rotation=90.0)).draw(b)
    assert a._pixels == b._pixels
    assert a.count_nonzero() > 0


def test_lens_ignores_gain():
    from led_ticker.animations import LensSpec

    spec = LensSpec(magnify=1.3, edge_squeeze=0.6)
    real_a = HeadlessCanvas(256, 64)
    real_b = HeadlessCanvas(256, 64)
    ca = ScaledCanvas(real_a, scale=4, content_height=16)
    cb = ScaledCanvas(real_b, scale=4, content_height=16)
    _text_widget(_Stub(lens=spec, pixel_gain=lambda x, y: 0.0)).draw(ca)
    _text_widget(_Stub(lens=spec)).draw(cb)
    assert real_a._pixels == real_b._pixels
    assert real_a.count_nonzero() > 0


class TestImageOverlay:
    async def _lit(self, tmp_path, text, animation):
        from PIL import Image

        from led_ticker.widgets.still import StillImage

        img = tmp_path / "x.png"
        Image.new("RGB", (4, 4), (255, 0, 0)).save(img)
        w = StillImage(
            path=img,
            text=text,
            text_align="right",
            image_align="left",
            animation=animation,
            font_color=(255, 255, 255),
        )
        real = HeadlessCanvas(width=64, height=16)
        w._load(64, 16)
        frame = mock.Mock()
        frame.swap.return_value = real
        with mock.patch("asyncio.sleep", new=mock.AsyncMock()):
            await w._play_with_text(real, frame, n_ticks=1)
        return dict(real._pixels)

    async def test_image_overlay_text_twinkles(self, tmp_path):
        plain = await self._lit(tmp_path, "HI", None)
        gained = await self._lit(tmp_path, "HI", _Stub(pixel_gain=lambda x, y: 0.0))
        no_text = await self._lit(tmp_path, "", None)

        def nz(d):
            return {k: v for k, v in d.items() if v != (0, 0, 0)}

        assert (255, 255, 255) in set(plain.values())
        assert nz(gained) == nz(no_text)
        assert nz(gained)  # image pixels intact
