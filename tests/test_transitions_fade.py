"""`fade`: snapshot-and-blend crossfade, optional dip through `transition_color`.

Design: docs/superpowers/specs/2026-11-21-fade-design.md. Frames are driven
directly through `frame_at` unless a test says "through the runner"; the
expected image for each endpoint is drawn INDEPENDENTLY into a HeadlessCanvas
so a wrong cursor, geometry or blend factor fails rather than being compared
against itself.
"""

import asyncio
import logging
import random
import unittest.mock as mock

import pytest
from PIL import Image

from led_ticker import colors
from led_ticker.backends.headless import HeadlessCanvas
from led_ticker.render_breaker import RenderBreaker, guard_for_transition
from led_ticker.scaled_canvas import unwrap_to_real
from led_ticker.ticker import _maybe_wrap
from led_ticker.transitions import get_transition_class, run_transition
from led_ticker.transitions.effects import Cut
from led_ticker.transitions.fade import Fade
from led_ticker.transitions.meta import RandomTransition
from led_ticker.widgets.gif import GifPlayer
from led_ticker.widgets.message import TickerMessage
from led_ticker.widgets.two_row import TwoRowMessage

# --- helpers --------------------------------------------------------------------


def _canvas(w=160, h=16, scale=1, ch=16):
    real = HeadlessCanvas(w, h)
    return real, _maybe_wrap(real, scale, ch)


def _msg(text, color=None):
    return TickerMessage(text=text, font_color=color or colors.RED)


def _img(hc: HeadlessCanvas) -> Image.Image:
    im = Image.new("RGB", (hc.width, hc.height))
    im.putdata([hc.get_pixel(x, y) for y in range(hc.height) for x in range(hc.width)])
    return im


def _expected(widget, w, h, scale, ch, bg=None, cursor=0) -> Image.Image:
    hc = HeadlessCanvas(w, h)
    if bg is not None:
        hc.Fill(*bg)
    widget.draw(_maybe_wrap(hc, scale, ch), cursor_pos=cursor)
    return _img(hc)


def _frame(fade, t, canvas, out, inc, **kw):
    kw.setdefault("outgoing_scroll_pos", 0)
    kw.setdefault("incoming_scale", None)
    kw.setdefault("incoming_content_height", 16)
    kw.setdefault("outgoing_bg_color", None)
    kw.setdefault("incoming_bg_color", None)
    unwrap_to_real(canvas).Clear()  # the runner's per-frame reset
    fade.frame_at(t, canvas, out, inc, **kw)
    return _img(unwrap_to_real(canvas))


def _same(a: Image.Image, b: Image.Image) -> bool:
    return a.size == b.size and a.tobytes() == b.tobytes()


def _palette(im: Image.Image) -> set:
    return {c for _n, c in im.getcolors(im.width * im.height)}


def _uniform(im: Image.Image) -> bool:
    return len(_palette(im)) == 1


def _gif(tmp_path):
    p = tmp_path / "fade.gif"
    frames = [
        Image.new("RGB", (24, 12), (200, 40, 40)),
        Image.new("RGB", (24, 12), (40, 200, 40)),
    ]
    frames[0].save(p, save_all=True, append_images=frames[1:], duration=100, loop=0)
    return GifPlayer(path=str(p), fit="letterbox")


def _identity_frame():
    frame = mock.Mock()
    frame.swap.side_effect = lambda c: c
    return frame


# --- registry / constructor ----------------------------------------------------


def test_fade_is_registered():
    assert get_transition_class("fade") is Fade
    assert Fade.min_frames == 8


@pytest.mark.parametrize(
    "shape",
    ["red", ("r", "e", "d"), [255, 0], [255.0, 0, 0], [256, 0, 0], [True, 0, 0]],
)
def test_bad_colour_raises_valueerror(shape):
    with pytest.raises(ValueError, match="transition_color"):
        Fade(color=shape)


@pytest.mark.parametrize("c", [None, (), []])
def test_falsy_colour_is_mix(c):
    assert Fade(color=c).through is None


def test_good_colour_is_dip():
    assert Fade(color=[0, 0, 255]).through == (0, 0, 255)


def test_bad_colour_on_a_section_cuts_through_guarded_builder():
    from led_ticker.app.run import _build_trans_obj_guarded
    from led_ticker.config import TransitionConfig

    assert (
        _build_trans_obj_guarded(TransitionConfig(type="fade", color=("r", "e", "d")))
        is None
    )
    assert isinstance(_build_trans_obj_guarded(TransitionConfig(type="fade")), Fade)


_R74 = """\
    [display]
    rows = 16
    cols = 32
    chain_length = 5
    default_scale = 1

    [transitions]

    [[playlist.section]]
    mode = "slideshow"
    transition = {{ type = "fade", transition_color = {value} }}

    [[playlist.section.widget]]
    type = "message"
    text = "hi"
    """


@pytest.mark.parametrize(
    ("toml_value", "py_value"),
    [
        ('"red"', "red"),
        ("[255, 0]", [255, 0]),
        ("[255.0, 0, 0]", [255.0, 0, 0]),
        ("[256, 0, 0]", [256, 0, 0]),
        ("[true, 0, 0]", [True, 0, 0]),
        ("[]", []),
        ("[0, 0, 0]", [0, 0, 0]),
    ],
)
async def test_constructor_and_rule74_agree(tmp_path, toml_value, py_value):
    """Validate never constructs a core non-meta slot; the only thing keeping
    rule 74's errors and `Fade.__init__`'s refusals in step is this test."""
    import textwrap

    from led_ticker.validate import validate_config

    p = tmp_path / "config.toml"
    p.write_text(textwrap.dedent(_R74.format(value=toml_value)))
    result = await validate_config(p)
    rule74_error = any(i.rule == 74 for i in result.errors)
    try:
        Fade(color=tuple(py_value))
        ctor_raises = False
    except ValueError:
        ctor_raises = True
    assert rule74_error == ctor_raises, (toml_value, result.errors)


# --- endpoints (message pair and gif -> message pair) ----------------------------


def _pairs(tmp_path):
    return {
        "message": (_msg("OLD NEWS", colors.RED), _msg("NEW", colors.GREEN)),
        "gif": (_gif(tmp_path), _msg("NEW", colors.GREEN)),
    }


@pytest.mark.parametrize("pair", ["message", "gif"])
def test_t0_equals_outgoing_at_scroll_pos(tmp_path, pair):
    out, inc = _pairs(tmp_path)[pair]
    real, canvas = _canvas()
    got = _frame(Fade(), 0.0, canvas, out, inc, outgoing_scroll_pos=-30)
    assert _same(got, _expected(out, 160, 16, 1, 16, cursor=-30))
    if pair == "message":  # a cursor_pos=0 slip must fail
        assert not _same(got, _expected(out, 160, 16, 1, 16, cursor=0))


@pytest.mark.parametrize("pair", ["message", "gif"])
def test_t1_equals_incoming(tmp_path, pair):
    out, inc = _pairs(tmp_path)[pair]
    real, canvas = _canvas()
    f = Fade()
    _frame(f, 0.0, canvas, out, inc)
    got = _frame(f, 1.0, canvas, out, inc)
    assert _same(got, _expected(inc, 160, 16, 1, 16))


@pytest.mark.parametrize("pair", ["message", "gif"])
def test_mid_frame_is_blend(tmp_path, pair):
    out, inc = _pairs(tmp_path)[pair]
    real, canvas = _canvas()
    f = Fade()
    got = _frame(f, 0.5, canvas, out, inc)
    exp = Image.blend(
        _expected(out, 160, 16, 1, 16), _expected(inc, 160, 16, 1, 16), 0.5
    )
    assert _same(got, exp)


def test_mix_quarter_is_blend_025():
    out, inc = _msg("OLD", colors.RED), _msg("NEW", colors.GREEN)
    real, canvas = _canvas()
    got = _frame(Fade(), 0.25, canvas, out, inc)
    exp = Image.blend(
        _expected(out, 160, 16, 1, 16), _expected(inc, 160, 16, 1, 16), 0.25
    )
    assert _same(got, exp)


# --- dip --------------------------------------------------------------------------


def test_dip_black_midpoint_is_black_everywhere():
    out, inc = _msg("OLD", colors.RED), _msg("NEW", colors.GREEN)
    real, canvas = _canvas()
    f = Fade(color=(0, 0, 0))
    assert not _uniform(_frame(f, 0.0, canvas, out, inc))  # both sides are lit
    assert not _uniform(_frame(f, 1.0, canvas, out, inc))
    mid = _frame(f, 0.5, canvas, out, inc)
    assert _palette(mid) == {(0, 0, 0)}


def test_dip_nonblack_midpoint_is_through_colour():
    out, inc = _msg("OLD", colors.RED), _msg("NEW", colors.GREEN)
    real, canvas = _canvas()
    mid = _frame(Fade(color=(0, 0, 255)), 0.5, canvas, out, inc)
    assert _palette(mid) == {(0, 0, 255)}


def test_dip_quarter_is_half_out_half_through():
    out, inc = _msg("OLD", colors.RED), _msg("NEW", colors.GREEN)
    real, canvas = _canvas()
    got = _frame(Fade(color=(0, 0, 0)), 0.25, canvas, out, inc)
    through = Image.new("RGB", (160, 16), (0, 0, 0))
    assert _same(got, Image.blend(_expected(out, 160, 16, 1, 16), through, 0.5))


def test_dip_three_quarter_is_half_through_half_in():
    out, inc = _msg("OLD", colors.RED), _msg("NEW", colors.GREEN)
    real, canvas = _canvas()
    got = _frame(Fade(color=(0, 0, 0)), 0.75, canvas, out, inc)
    through = Image.new("RGB", (160, 16), (0, 0, 0))
    assert _same(got, Image.blend(through, _expected(inc, 160, 16, 1, 16), 0.5))


def test_mix_never_paints_a_solid_frame():
    out, inc = _msg("OLD", colors.RED), _msg("NEW", colors.GREEN)
    real, canvas = _canvas()
    f = Fade()
    for i in range(1, 10):
        assert not _uniform(_frame(f, i / 10, canvas, out, inc)), i


# --- clamp / bg ------------------------------------------------------------------


def test_t_above_one_and_below_zero_clamp_to_endpoints():
    out, inc = _msg("OLD", colors.RED), _msg("NEW", colors.GREEN)
    real, canvas = _canvas()
    f = Fade()
    assert _same(_frame(f, 1.2, canvas, out, inc), _expected(inc, 160, 16, 1, 16))
    assert _same(_frame(f, -0.1, canvas, out, inc), _expected(out, 160, 16, 1, 16))


def test_distinct_bgs_show_under_snapshots():
    out, inc = _msg("OLD", colors.RED), _msg("NEW", colors.GREEN)
    real, canvas = _canvas()
    f = Fade()
    kw = {"outgoing_bg_color": (10, 0, 0), "incoming_bg_color": (0, 0, 10)}
    t0 = _frame(f, 0.0, canvas, out, inc, **kw)
    t1 = _frame(f, 1.0, canvas, out, inc, **kw)
    assert _same(t0, _expected(out, 160, 16, 1, 16, bg=(10, 0, 0)))
    assert _same(t1, _expected(inc, 160, 16, 1, 16, bg=(0, 0, 10)))
    assert t0.getpixel((159, 15)) == (10, 0, 0)  # an unlit corner shows each bg
    assert t1.getpixel((159, 15)) == (0, 0, 10)


def test_none_bg_is_black():
    out, inc = _msg("OLD", colors.RED), _msg("NEW", colors.GREEN)
    real, canvas = _canvas()
    assert _frame(Fade(), 0.0, canvas, out, inc).getpixel((159, 15)) == (0, 0, 0)


# --- geometry --------------------------------------------------------------------


def test_cross_scale_incoming_at_incoming_geometry_and_outgoing_at_live():
    out, inc = _msg("OLD", colors.RED), _msg("NEW", colors.GREEN)
    real, canvas = _canvas(256, 64, 4, 16)
    f = Fade()
    kw = {"incoming_scale": 2, "incoming_content_height": 16}
    t0 = _frame(f, 0.0, canvas, out, inc, **kw)
    t1 = _frame(f, 1.0, canvas, out, inc, **kw)
    assert _same(t0, _expected(out, 256, 64, 4, 16))  # live geometry
    assert _same(t1, _expected(inc, 256, 64, 2, 16))  # incoming geometry
    assert not _same(t0, _expected(out, 256, 64, 2, 16))  # both-at-incoming slip fails
    assert not _same(t1, _expected(inc, 256, 64, 4, 16))


def test_same_scale_cross_content_height():
    """A two_row incoming: its band layout follows canvas.height, so the
    20-row and 16-row draws differ (a single-row message centres identically
    at either height and cannot tell the two apart)."""
    out = _msg("OLD", colors.RED)
    inc = TwoRowMessage(top_text="TOP", bottom_text="BOTTOM")
    exp20 = _expected(inc, 256, 64, 1, 20)
    exp16 = _expected(inc, 256, 64, 1, 16)
    assert not _same(exp20, exp16)  # precondition: distinguishable geometries
    real, canvas = _canvas(256, 64, 1, 16)
    t1 = _frame(
        Fade(), 1.0, canvas, out, inc, incoming_scale=1, incoming_content_height=20
    )
    assert _same(t1, exp20)


def test_incoming_scale_none_uses_live_wrapper():
    out, inc = _msg("OLD", colors.RED), _msg("NEW", colors.GREEN)
    real, canvas = _canvas(256, 64, 4, 16)
    t1 = _frame(Fade(), 1.0, canvas, out, inc, incoming_scale=None)
    assert _same(t1, _expected(inc, 256, 64, 4, 16))


def test_unwrapped_canvas_snapshots_directly():
    """160x16 at scale 1 with a 16-row band: `_maybe_wrap` returns the raw
    canvas, so there is no wrapper to read geometry from."""
    out, inc = _msg("OLD", colors.RED), _msg("NEW", colors.GREEN)
    real = HeadlessCanvas(160, 16)
    f = Fade()
    assert _same(_frame(f, 0.0, real, out, inc), _expected(out, 160, 16, 1, 16))
    assert _same(_frame(f, 1.0, real, out, inc), _expected(inc, 160, 16, 1, 16))


# --- lazy snapshot / release ------------------------------------------------------


class _Counting:
    def __init__(self, color):
        self.color = color
        self.draws = 0

    def draw(self, canvas, cursor_pos=0, **kw):
        self.draws += 1
        canvas.SetPixel(1, 1, *self.color)
        return canvas, 10


def test_draw_runs_once_per_widget_per_firing():
    out, inc = _Counting((255, 0, 0)), _Counting((0, 255, 0))
    real, canvas = _canvas()
    f = Fade()
    for i in range(21):
        _frame(f, i / 20, canvas, out, inc)
    assert out.draws == 1 and inc.draws == 1


def test_end_firing_releases_and_next_firing_resnapshots():
    out, inc = _msg("ONE", colors.RED), _msg("NEW", colors.GREEN)
    real, canvas = _canvas()
    f = Fade()
    _frame(f, 0.0, canvas, out, inc)
    f.end_firing()
    assert f._out_img is None and f._in_img is None
    out.text = "TWO"
    got = _frame(f, 0.0, canvas, out, inc)
    assert _same(got, _expected(_msg("TWO", colors.RED), 160, 16, 1, 16))


def test_without_end_firing_the_snapshot_is_stale():
    """The `is` cache key alone is not a release; `end_firing` is."""
    out, inc = _msg("ONE", colors.RED), _msg("NEW", colors.GREEN)
    real, canvas = _canvas()
    f = Fade()
    _frame(f, 0.0, canvas, out, inc)
    out.text = "TWO"
    got = _frame(f, 0.0, canvas, out, inc)
    assert _same(got, _expected(_msg("ONE", colors.RED), 160, 16, 1, 16))


async def test_aba_through_seeded_random_pool_resnapshots(no_sleep):
    """Through the runner with breaker=None (the guards ARE the widgets, so an
    A-B-A firing sequence reuses the `is` cache key); the meta wrapper must
    forward end_firing or firing 3 replays firing 1's snapshot."""
    seed = next(s for s in range(50) if random.Random(s).randrange(2) == 0)
    fade = Fade()
    pool = RandomTransition(
        [fade, Cut()], [None, None], ["fade", "cut"], rng=random.Random(seed)
    )
    assert pool.current_name == "fade"
    a, b = _msg("ONE", colors.RED), _msg("NEW", colors.GREEN)
    real, canvas = _canvas()
    frame = _identity_frame()
    await run_transition(
        canvas, frame, a, b, transition=pool, duration=0.1, breaker=None
    )
    assert pool.current_name == "cut"
    await run_transition(
        canvas, frame, b, a, transition=pool, duration=0.1, breaker=None
    )
    assert pool.current_name == "fade"
    a.text = "TWO"
    seen = []
    orig = fade.frame_at

    def spy(t, c, o, i, **kw):
        r = orig(t, c, o, i, **kw)
        if not seen:
            seen.append(_img(unwrap_to_real(c)))
        return r

    fade.frame_at = spy  # type: ignore[method-assign]
    await run_transition(
        canvas, frame, a, b, transition=pool, duration=0.1, breaker=None
    )
    assert _same(seen[0], _expected(_msg("TWO", colors.RED), 160, 16, 1, 16))


async def test_cancel_mid_fade_releases_snapshots(no_sleep):
    """Through a `random` pool with `fade` current (Review Focus 2): the
    runner's `finally` reaches the wrapper, which forwards to the fade and
    then advances the pick."""
    out, inc = _msg("OLD", colors.RED), _msg("NEW", colors.GREEN)
    real, canvas = _canvas()
    f = Fade()
    seed = next(s for s in range(50) if random.Random(s).randrange(2) == 0)
    pool = RandomTransition(
        [f, Cut()], [None, None], ["fade", "cut"], rng=random.Random(seed)
    )
    assert pool.current_name == "fade"

    async def driver():
        await run_transition(
            canvas, _identity_frame(), out, inc, transition=pool, duration=1.0
        )

    task = asyncio.create_task(driver())
    for _ in range(4):
        await asyncio.sleep(0)
    assert f._out_img is not None  # mid-firing, snapshot held
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert f._out_img is None and f._in_img is None
    assert pool.current_name == "cut"  # the pick advanced too


# --- breaker ----------------------------------------------------------------------


class _PaintThenRaise:
    def draw(self, canvas, cursor_pos=0, **kw):
        for x in range(10):
            canvas.SetPixel(x, 0, 255, 255, 255)
        raise ValueError("mid-draw")


class _BadChannel:
    def draw(self, canvas, cursor_pos=0, **kw):
        canvas.SetPixel(0, 0, 255.0, 0, 0)  # a float the real SetPixel rejects
        return canvas, 1


class _MissingMethod:
    def draw(self, canvas, cursor_pos=0, **kw):
        canvas.NoSuchMethod()
        return canvas, 1


class _DrawsNothing:
    def draw(self, canvas, cursor_pos=0, **kw):
        return canvas, 0


def test_paint_then_raise_trips_and_completes_to_bg():
    out, inc = _msg("OLD", colors.RED), _PaintThenRaise()
    br = RenderBreaker()
    real, canvas = _canvas()
    f = Fade()
    g_out, g_inc = guard_for_transition(out, br), guard_for_transition(inc, br)
    t1 = _frame(f, 1.0, canvas, g_out, g_inc, incoming_bg_color=(0, 0, 10))
    assert br.is_disabled(inc)
    assert _palette(t1) == {(0, 0, 10)}  # none of the partial paint survives


def test_bad_channel_value_trips_at_conversion():
    out, inc = _msg("OLD", colors.RED), _BadChannel()
    br = RenderBreaker()
    real, canvas = _canvas()
    g_out, g_inc = guard_for_transition(out, br), guard_for_transition(inc, br)
    t1 = _frame(Fade(), 1.0, canvas, g_out, g_inc)
    assert br.is_disabled(inc)
    assert _palette(t1) == {(0, 0, 0)}


def test_bad_channel_value_without_breaker_raises():
    out, inc = _msg("OLD", colors.RED), _BadChannel()
    real, canvas = _canvas()
    with pytest.raises(TypeError):
        _frame(Fade(), 1.0, canvas, out, inc)


def test_snapshot_widget_missing_canvas_method_trips_and_completes():
    out, inc = _MissingMethod(), _msg("NEW", colors.GREEN)
    br = RenderBreaker()
    real, canvas = _canvas()
    g_out, g_inc = guard_for_transition(out, br), guard_for_transition(inc, br)
    f = Fade()
    t0 = _frame(f, 0.0, canvas, g_out, g_inc)
    assert br.is_disabled(out)
    assert _palette(t0) == {(0, 0, 0)}
    assert _same(_frame(f, 1.0, canvas, g_out, g_inc), _expected(inc, 160, 16, 1, 16))


def test_incoming_that_draws_nothing_fades_to_bg():
    """A guard around a widget that draws nothing (schedule-filtered incoming,
    Review Focus 4): t = 1 is the incoming bg, no stale pixels, nothing tripped."""
    out, inc = _msg("OLD", colors.RED), _DrawsNothing()
    br = RenderBreaker()
    real, canvas = _canvas()
    g_out, g_inc = guard_for_transition(out, br), guard_for_transition(inc, br)
    t1 = _frame(Fade(), 1.0, canvas, g_out, g_inc, incoming_bg_color=(0, 5, 0))
    assert _palette(t1) == {(0, 5, 0)}
    assert not br.disabled


def test_malformed_section_bg_is_dropped_not_raised(caplog):
    """A section bg reaches the runner un-validated: float channels are
    coerced, an out-of-range channel is dropped with a WARNING; neither
    raises out of frame_at nor trips a healthy widget."""
    out, inc = _msg("OLD", colors.RED), _msg("NEW", colors.GREEN)
    br = RenderBreaker()
    real, canvas = _canvas()
    g_out, g_inc = guard_for_transition(out, br), guard_for_transition(inc, br)
    f = Fade()
    with caplog.at_level(logging.WARNING, logger="led_ticker.transitions.fade"):
        kw = {"outgoing_bg_color": (99.0, 60, 138), "incoming_bg_color": (300, 0, 0)}
        t0 = _frame(f, 0.0, canvas, g_out, g_inc, **kw)
        t1 = _frame(f, 1.0, canvas, g_out, g_inc, **kw)
    assert not br.disabled
    assert t0.getpixel((159, 15)) == (99, 60, 138)  # coerced
    assert t1.getpixel((159, 15)) == (0, 0, 0)  # dropped -> black
    assert sum("bg colour" in r.getMessage() for r in caplog.records) == 1


def test_dip_through_cache_is_keyed_on_panel_size():
    out, inc = _msg("OLD", colors.RED), _msg("NEW", colors.GREEN)
    f = Fade(color=(0, 0, 255))
    small_real, small = _canvas(160, 16)
    big_real, big = _canvas(256, 64, 4, 16)
    assert _palette(_frame(f, 0.5, small, out, inc)) == {(0, 0, 255)}
    f.end_firing()
    mid = _frame(f, 0.5, big, out, inc)
    assert mid.size == (256, 64) and _palette(mid) == {(0, 0, 255)}


# --- per-frame path on a spy canvas -----------------------------------------------


class _SpyCanvas:
    """NOT a HeadlessCanvas (whose SetImage is per-pixel SetPixel): records the
    one SetImage call per frame and refuses any direct pixel write."""

    def __init__(self, w=160, h=16):
        self.width, self.height = w, h
        self.images = []

    def Clear(self):
        pass

    def Fill(self, r, g, b):
        pass

    def SetImage(self, image, offset_x=0, offset_y=0):
        self.images.append((image, offset_x, offset_y))

    def SetPixel(self, *a):
        raise AssertionError("fade must not SetPixel per frame")

    def SubFill(self, *a):
        raise AssertionError("fade must not SubFill per frame")


@pytest.mark.parametrize("color", [None, (0, 0, 0), (0, 0, 255)])
def test_one_setimage_rgb_full_size_no_setpixel_per_frame(color):
    out, inc = _msg("OLD", colors.RED), _msg("NEW", colors.GREEN)
    spy = _SpyCanvas()
    f = Fade(color=color)
    for i in range(11):
        f.frame_at(i / 10, spy, out, inc, outgoing_scroll_pos=0, incoming_scale=None)
    assert len(spy.images) == 11
    for image, ox, oy in spy.images:
        assert image.mode == "RGB"
        assert image.size == (160, 16)
        assert (ox, oy) == (0, 0)


# --- runner integration --------------------------------------------------------


class _CountingFade(Fade):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.calls = 0

    def frame_at(self, t, canvas, outgoing, incoming, **kw):
        self.calls += 1
        return super().frame_at(t, canvas, outgoing, incoming, **kw)


async def test_min_frames_floor_is_tick_relative(no_sleep):
    """`min_frames = 8` is 8 ticks: 0.4 s at 20 fps, 0.13 s at 60 fps."""
    out, inc = _msg("OLD", colors.RED), _msg("NEW", colors.GREEN)
    real, canvas = _canvas()
    f = _CountingFade()
    await run_transition(
        canvas,
        _identity_frame(),
        out,
        inc,
        transition=f,
        duration=0.1,
        scroll_speed=1 / 60,
    )
    assert f.calls == 9  # max(int(0.1 * 60) = 6, 8) + 1 endpoint frame


async def test_runner_cross_scale_entry_ends_on_incoming_geometry(no_sleep):
    """Through the runner: bigsign 4 -> 2 entry; the returned wrapper is the
    incoming one and the last frame equals the incoming at scale 2."""
    out, inc = _msg("OLD", colors.RED), _msg("NEW", colors.GREEN)
    real, canvas = _canvas(256, 64, 4, 16)
    result = await run_transition(
        canvas,
        _identity_frame(),
        out,
        inc,
        transition=Fade(),
        duration=0.5,
        incoming_scale=2,
        incoming_content_height=16,
    )
    assert result.scale == 2
    assert _same(_img(real), _expected(inc, 256, 64, 2, 16))


async def test_debug_lines(caplog, no_sleep):
    out, inc = _msg("OLD", colors.RED), _msg("NEW", colors.GREEN)
    real, canvas = _canvas()
    with caplog.at_level(logging.DEBUG, logger="led_ticker.transitions.fade"):
        await run_transition(
            canvas, _identity_frame(), out, inc, transition=Fade(), duration=0.5
        )
    msgs = [
        r.getMessage()
        for r in caplog.records
        if r.name == "led_ticker.transitions.fade"
    ]
    assert sum(m.startswith("fade: snapshot 160x16 in ") for m in msgs) == 1
    assert sum(m.startswith("fade: firing done, 11 frames, ") for m in msgs) == 1


def test_frame_at_with_no_kwargs_at_all():
    """A programmatic caller passing none of the runner kwargs still gets a
    frame (`.get` defaults, the ColorFlash precedent)."""
    out, inc = _msg("OLD", colors.RED), _msg("NEW", colors.GREEN)
    real = HeadlessCanvas(160, 16)
    Fade().frame_at(0.0, real, out, inc)
    assert _same(_img(real), _expected(out, 160, 16, 1, 16))
