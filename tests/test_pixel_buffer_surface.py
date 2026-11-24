"""`rotate.PixelBuffer` as a snapshot target for transitions (fade design
`2026-11-21-fade-design.md`, "PixelBuffer surface").

Part 1: the canvas-contract methods (`Clear`, `Fill`, `SetImage`) match
`HeadlessCanvas` pixel for pixel. Part 2: every core widget type draws into a
wrapped `PixelBuffer` through the transition draw guard without tripping and
pixel-identical to the same draw on a `HeadlessCanvas` — the tripwire a
snapshotting transition relies on.
"""

from typing import Any

from PIL import Image

from led_ticker.backends.headless import HeadlessCanvas
from led_ticker.rotate import PixelBuffer


def _same(buf: PixelBuffer, hc: HeadlessCanvas) -> bool:
    assert (buf.width, buf.height) == (hc.width, hc.height)
    for y in range(buf.height):
        for x in range(buf.width):
            if (buf.get(x, y) or (0, 0, 0)) != hc.get_pixel(x, y):
                return False
    return True


def _pair(w: int = 8, h: int = 4) -> tuple[PixelBuffer, HeadlessCanvas]:
    return PixelBuffer(w, h), HeadlessCanvas(w, h)


def _rgb(w: int, h: int, seed: int = 1) -> Image.Image:
    img = Image.new("RGB", (w, h))
    img.putdata(
        [
            ((x * 37 + seed) % 256, (y * 59) % 256, (x * y) % 256)
            for y in range(h)
            for x in range(w)
        ]
    )
    return img


# --- Part 1: contract methods ---------------------------------------------


def test_fill_sets_every_slot_and_full_extent():
    buf = PixelBuffer(8, 4)
    buf.Fill(1, 2, 3)
    assert all(buf.get(x, y) == (1, 2, 3) for y in range(4) for x in range(8))
    assert buf.lit_extent == (0, 0, 8, 4)


def test_clear_is_clear():
    buf = PixelBuffer(8, 4)
    buf.Fill(1, 2, 3)
    buf.Clear()
    assert all(buf.get(x, y) is None for y in range(4) for x in range(8))
    assert buf.lit_extent is None


def test_setimage_fast_path_matches_headless():
    buf, hc = _pair()
    img = _rgb(8, 4)
    buf.SetImage(img, 0, 0)
    hc.SetImage(img, 0, 0)
    assert _same(buf, hc)


def test_setimage_offset_matches_headless():
    buf, hc = _pair()
    img = _rgb(4, 2)
    buf.SetImage(img, 2, 1)
    hc.SetImage(img, 2, 1)
    assert _same(buf, hc)
    assert buf.get(0, 0) is None  # untouched slots stay transparent


def test_setimage_partial_clip_matches_headless():
    buf, hc = _pair()
    img = _rgb(6, 3)
    buf.SetImage(img, 5, 2)  # overhangs both edges; must not raise
    hc.SetImage(img, 5, 2)
    assert _same(buf, hc)


def test_setimage_rgba_alpha_zero_is_black():
    buf, hc = _pair(2, 1)
    img = Image.new("RGBA", (2, 1))
    img.putdata([(200, 100, 50, 0), (10, 20, 30, 255)])
    buf.SetImage(img, 0, 0)
    hc.SetImage(img, 0, 0)
    assert buf.get(0, 0) == (0, 0, 0)
    assert buf.get(1, 0) == (10, 20, 30)
    assert _same(buf, hc)


def test_setimage_fast_path_extent_is_full():
    buf = PixelBuffer(8, 4)
    buf.SetImage(_rgb(8, 4), 0, 0)
    assert buf.lit_extent == (0, 0, 8, 4)


def test_setimage_slow_path_extent_tracks_pixels():
    buf = PixelBuffer(8, 4)
    buf.SetImage(_rgb(2, 2), 3, 1)
    assert buf.lit_extent == (3, 1, 5, 3)


def test_setimage_full_size_at_offset_takes_the_slow_path():
    """The fast path must require offset (0, 0): a panel-size image blitted at
    (1, 0) lands shifted and clipped, exactly like HeadlessCanvas."""
    buf, hc = _pair()
    img = _rgb(8, 4)
    buf.SetImage(img, 1, 0)
    hc.SetImage(img, 1, 0)
    assert _same(buf, hc)
    assert buf.get(0, 0) is None


def test_setimage_smaller_rgb_at_origin_takes_the_slow_path():
    """The fast path must require the image to be buffer-sized: a 4x2 RGB at
    the origin must not replace the pixel list (get() would IndexError)."""
    buf, hc = _pair()
    img = _rgb(4, 2)
    buf.SetImage(img, 0, 0)
    hc.SetImage(img, 0, 0)
    assert _same(buf, hc)
    assert buf.get(7, 3) is None
    assert buf.lit_extent == (0, 0, 4, 2)


def test_setimage_fast_path_values_are_ints_not_bytes_slices():
    """The fast path must store plain int tuples so `get()` and the fade's
    bytes conversion see the same shape the slow path stores."""
    buf = PixelBuffer(2, 1)
    img = Image.new("RGB", (2, 1))
    img.putdata([(1, 2, 3), (4, 5, 6)])
    buf.SetImage(img)
    assert buf.get(0, 0) == (1, 2, 3) and buf.get(1, 0) == (4, 5, 6)
    assert all(type(c) is int for c in buf.get(1, 0))  # type: ignore[union-attr]


# --- Part 2: every core widget snapshots pixel-exact --------------------------

import datetime as _dt  # noqa: E402

import pytest  # noqa: E402

from led_ticker import colors  # noqa: E402
from led_ticker.borders import ConstantBorder  # noqa: E402
from led_ticker.fonts import resolve_font  # noqa: E402
from led_ticker.render_breaker import RenderBreaker, guard_for_transition  # noqa: E402
from led_ticker.ticker import _maybe_wrap  # noqa: E402
from led_ticker.widgets.clock import Clock  # noqa: E402
from led_ticker.widgets.count import TickerCountdown, TickerCountup  # noqa: E402
from led_ticker.widgets.gif import GifPlayer  # noqa: E402
from led_ticker.widgets.message import TickerMessage  # noqa: E402
from led_ticker.widgets.still import StillImage  # noqa: E402
from led_ticker.widgets.two_row import TwoRowMessage  # noqa: E402

WIDGETS = ["clock", "countdown", "countup", "gif", "image", "message", "two_row"]
# (real width, real height, scale, content_height): smallsign, bigsign,
# bigsign at scale 1 with a 16-row band, a scale-2 panel.
GEOMETRIES = [(160, 16, 1, 16), (256, 64, 4, 16), (256, 64, 1, 16), (128, 64, 2, 16)]

_FROZEN = _dt.datetime(2026, 11, 22, 10, 30, 15)


class _FrozenDatetime(_dt.datetime):
    @classmethod
    def now(cls, tz=None):  # type: ignore[override]
        return _FROZEN if tz is None else _FROZEN.replace(tzinfo=tz)


@pytest.fixture
def frozen_time(monkeypatch):
    """clock / countdown / countup read the wall clock at draw time; two draws
    must not straddle a boundary."""
    monkeypatch.setattr("led_ticker.widgets.clock.datetime", _FrozenDatetime)
    monkeypatch.setattr(
        "led_ticker.widgets.count._CountWidget._today", lambda self: _FROZEN.date()
    )


def _image_files(tmp_path):
    gif = tmp_path / "snap.gif"
    frames = [Image.new("RGBA", (24, 12), (200, 40, 40, 255)) for _ in range(2)]
    frames[1].putpixel((0, 0), (0, 0, 0, 0))  # one transparent pixel
    frames[0].save(gif, save_all=True, append_images=frames[1:], duration=100, loop=0)
    png = tmp_path / "snap.png"
    Image.new("RGB", (20, 10), (30, 200, 60)).save(png)
    return gif, png


def _build(name: str, scale: int, tmp_path):
    font = resolve_font("Inter-Regular", 24) if scale >= 2 else None
    text_kw: dict[str, Any] = {"font": font} if font is not None else {}
    # No bg_color on any widget: no core draw() paints it (the engine's
    # reset_canvas does), so it would exercise nothing here. Border and hires
    # font DO paint through draw().
    border = ConstantBorder(colors.GREEN)
    if name == "message":
        return TickerMessage(
            text="Hi :star: there",
            font_color=colors.RED,
            border=border,
            **text_kw,
        )
    if name == "two_row":
        return TwoRowMessage(
            top_text="Top :star:", bottom_text="Bottom row", border=border
        )
    if name == "clock":
        return Clock(border=border, **text_kw)
    if name == "countdown":
        return TickerCountdown(
            text="Days left", countdown_date="2030-01-01", border=border
        )
    if name == "countup":
        return TickerCountup(
            text="Days since", countup_date="2020-01-01", border=border
        )
    gif, png = _image_files(tmp_path)
    # No bg_color on the image widgets: their draw() calls _paint_full only
    # (bg_color is consulted in play(), which the compositing path never runs).
    if name == "gif":
        return GifPlayer(path=str(gif), fit="letterbox")
    return StillImage(path=str(png), fit="letterbox")


@pytest.mark.parametrize(
    "geom", GEOMETRIES, ids=lambda g: f"{g[0]}x{g[1]}s{g[2]}h{g[3]}"
)
@pytest.mark.parametrize("name", WIDGETS)
@pytest.mark.parametrize("cursor", [0, -30])
def test_every_core_widget_snapshots_into_pixelbuffer(
    name, geom, cursor, tmp_path, frozen_time
):
    """(a) the transition draw guard never trips on a PixelBuffer target and
    (b) the buffer equals a HeadlessCanvas drawn the same way, pixel for pixel
    (a stride or mode bug in the SetImage fast path would ship green on a
    trips-only assertion and garble every image section's fade)."""
    w, h, scale, ch = geom
    breaker = RenderBreaker()
    widget = _build(name, scale, tmp_path)
    buf, hc = PixelBuffer(w, h), HeadlessCanvas(w, h)
    guard = guard_for_transition(widget, breaker)
    guard.draw(_maybe_wrap(buf, scale, ch), cursor_pos=cursor)
    assert not breaker.is_disabled(widget), breaker.disabled
    widget.draw(_maybe_wrap(hc, scale, ch), cursor_pos=cursor)
    assert _same(buf, hc)
    assert buf.lit_extent is not None  # the widget actually painted something
