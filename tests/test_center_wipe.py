"""Center wipes: ``wipe_in`` / ``wipe_out`` and their vertical twins.

Task 1 pins the pure span geometry: for every extent (odd and even) and every
front position ``b`` the erased and kept spans partition the axis exactly, so
the two fronts can never leave a 1-px gap or overlap at the center.
"""

from unittest import mock

import pytest

from led_ticker.backends.headless import HeadlessCanvas
from led_ticker.transitions import get_transition_class
from led_ticker.transitions.center_wipe import (
    WipeIn,
    WipeInVertical,
    WipeOut,
    WipeOutVertical,
    center_spans,
    progress_to_b,
    sweep_line_spans,
)

EXTENTS = (15, 16, 159, 160, 256)


def _cover(spans):
    s = set()
    for lo, hi in spans:
        s.update(range(lo, hi))
    return s


@pytest.mark.parametrize("n", EXTENTS)
@pytest.mark.parametrize("inward", [True, False])
def test_spans_partition_every_b(n, inward):
    half = (n + 1) // 2
    for b in range(half + 1):
        erased, kept = center_spans(n, b, inward)
        e, k = _cover(erased), _cover(kept)
        assert e | k == set(range(n)), (n, b, inward)
        assert not (e & k), (n, b, inward)


@pytest.mark.parametrize("n", EXTENTS)
@pytest.mark.parametrize("inward", [True, False])
def test_b_zero_erases_nothing_and_half_erases_all(n, inward):
    assert center_spans(n, 0, inward)[0] == []
    half = (n + 1) // 2
    assert _cover(center_spans(n, half, inward)[0]) == set(range(n))


@pytest.mark.parametrize("n", EXTENTS)
@pytest.mark.parametrize("inward", [True, False])
def test_progress_to_b_caps_where_something_is_still_kept(n, inward):
    """The fronts never swallow the whole axis: at the cap a 1-2 px kept
    sliver remains and the sweep lines cover ALL of it, so the frame before
    the cut is black + sweep colour, never a fully black panel."""
    cap = (n - 1) // 2 if inward else n // 2 - 1
    assert progress_to_b(0.0, n, inward) == 0
    assert progress_to_b(0.999, n, inward) == cap
    assert progress_to_b(1.0, n, inward) == cap
    assert all(0 <= progress_to_b(t / 100, n, inward) <= cap for t in range(101))
    erased, kept = center_spans(n, cap, inward)
    assert erased and kept
    assert _cover(sweep_line_spans(n, cap, inward, thick=2)) == _cover(kept)


def test_inward_spans_shape_even():
    erased, kept = center_spans(160, 10, True)
    assert erased == [(0, 10), (150, 160)]
    assert kept == [(10, 150)]


def test_outward_spans_shape_odd_keeps_center_in_band():
    erased, kept = center_spans(15, 1, False)
    assert erased == [(6, 9)]
    assert kept == [(0, 6), (9, 15)]


@pytest.mark.parametrize("n", EXTENTS)
@pytest.mark.parametrize("inward", [True, False])
def test_sweep_lines_sit_on_kept_side(n, inward):
    half = (n + 1) // 2
    for b in range(half + 1):
        erased, kept = center_spans(n, b, inward)
        lines = _cover(sweep_line_spans(n, b, inward, thick=2))
        assert lines <= _cover(kept), (n, b, inward)
        assert not (lines & _cover(erased))
        if not kept:
            assert lines == set()


@pytest.mark.parametrize("n", EXTENTS)
def test_frame_zero_lines_sit_where_the_fronts_start(n):
    """Family consistency: wipe_left/right/up/down show their line at the
    edge on frame 0; the center wipes show theirs at the fronts' start."""
    assert sweep_line_spans(n, 0, True, thick=2) == [(0, 2), (n - 2, n)]
    c = n // 2
    assert sweep_line_spans(n, 0, False, thick=2) == [(c - 2, c + 2)]


def test_sweep_lines_inward_even_example():
    assert sweep_line_spans(160, 10, True, thick=2) == [(10, 12), (148, 150)]


def test_sweep_lines_outward_even_example():
    assert sweep_line_spans(160, 10, False, thick=2) == [(68, 70), (90, 92)]


# ---------------------------------------------------------------------------
# Task 2: the four registered transitions
# ---------------------------------------------------------------------------

ALL = [WipeIn, WipeOut, WipeInVertical, WipeOutVertical]
NAMES = ["wipe_in", "wipe_out", "wipe_in_vertical", "wipe_out_vertical"]


def _widget():
    w = mock.Mock()
    w.hold_time = 0.0
    w.draw.side_effect = lambda c, cursor_pos=0, **kw: (c, cursor_pos + 40)
    return w


def _filling_widget(w_px: int, h_px: int):
    """A widget that paints every pixel of the (logical) canvas grey."""
    w = mock.Mock()
    w.hold_time = 0.0

    def paint(c, cursor_pos=0, **kw):
        for x in range(w_px):
            for y in range(h_px):
                c.SetPixel(x, y, 9, 9, 9)
        return c, w_px

    w.draw.side_effect = paint
    return w


@pytest.mark.parametrize(("name", "cls"), list(zip(NAMES, ALL, strict=True)))
def test_registered(name, cls):
    assert get_transition_class(name) is cls


@pytest.mark.parametrize("cls", ALL)
def test_t0_draws_outgoing_only_t1_incoming_only(cls):
    canvas = HeadlessCanvas(160, 16)
    out, inc = _widget(), _widget()
    cls().frame_at(0.0, canvas, out, inc)
    assert out.draw.called and not inc.draw.called
    out.reset_mock()
    inc.reset_mock()
    cls().frame_at(1.0, canvas, out, inc)
    assert inc.draw.called and not out.draw.called


@pytest.mark.parametrize("cls", ALL)
def test_outgoing_scroll_pos_forwarded(cls):
    canvas = HeadlessCanvas(160, 16)
    out = _widget()
    cls().frame_at(0.3, canvas, out, _widget(), outgoing_scroll_pos=-37)
    assert out.draw.call_args.kwargs["cursor_pos"] == -37


def test_defaults():
    assert WipeIn.DEFAULT_COLOR == (255, 255, 0)
    assert WipeOut.DEFAULT_COLOR == (255, 0, 0)
    assert WipeInVertical.DEFAULT_COLOR == (255, 255, 0)
    assert WipeOutVertical.DEFAULT_COLOR == (255, 0, 0)
    assert WipeIn.min_frames == 20 and WipeOut.min_frames == 20
    assert WipeInVertical.min_frames == 16 and WipeOutVertical.min_frames == 16
    assert WipeIn(color=(1, 2, 3)).color == (1, 2, 3)


def test_wipe_in_midway_erases_edges_and_paints_lines():
    canvas = HeadlessCanvas(160, 16)
    WipeIn().frame_at(0.5, canvas, _filling_widget(160, 16), _widget())
    b = progress_to_b(0.5, 160, True)
    assert canvas.get_pixel(0, 8) == (0, 0, 0)
    assert canvas.get_pixel(159, 8) == (0, 0, 0)
    assert canvas.get_pixel(b, 8) == (255, 255, 0)  # line on the kept side
    assert canvas.get_pixel(159 - b, 8) == (255, 255, 0)
    assert canvas.get_pixel(80, 8) == (9, 9, 9)  # center still outgoing


@pytest.mark.parametrize("cls", ALL)
def test_midsweep_identity_erases_and_keeps_on_the_declared_axis(cls):
    """Pins AXIS and INWARD per class with a painting widget: erased spans
    are black, kept spans still show the outgoing, lines sit on the kept
    side, all on the declared axis (cycle-2 mutants flipped these silently)."""
    canvas = HeadlessCanvas(160, 16)
    cls(color=(1, 2, 3)).frame_at(0.5, canvas, _filling_widget(160, 16), _widget())
    along_x = cls.AXIS == "x"
    n = 160 if along_x else 16
    b = progress_to_b(0.5, n, cls.INWARD)
    assert b > 0
    erased, kept = center_spans(n, b, cls.INWARD)
    lines = _cover(sweep_line_spans(n, b, cls.INWARD, thick=2))

    def px(i):  # pixel at axis coordinate i, mid cross-extent
        return canvas.get_pixel(i, 8) if along_x else canvas.get_pixel(80, i)

    for lo, hi in erased:
        assert {px(i) for i in range(lo, hi)} == {(0, 0, 0)}, (cls.__name__, lo, hi)
    grey = [i for i in _cover(kept) - lines if px(i) == (9, 9, 9)]
    assert grey, cls.__name__  # outgoing survives on the kept side
    assert {px(i) for i in lines} == {(1, 2, 3)}, cls.__name__  # transition_color
    # Along the OTHER axis, a kept coordinate is untouched end to end: the
    # sweep runs on the declared axis only.
    k = grey[0]
    other_n = 16 if along_x else 160

    def probe(j):
        return canvas.get_pixel(k, j) if along_x else canvas.get_pixel(j, k)

    assert all(probe(j) == (9, 9, 9) for j in range(other_n)), cls.__name__


def test_classes_are_re_exported_from_the_package():
    from led_ticker import transitions as pkg

    for name in ("WipeIn", "WipeOut", "WipeInVertical", "WipeOutVertical"):
        assert getattr(pkg, name) is globals()[name]


def _palette(get, coords):
    return {get(x, y) for x, y in coords}


def test_wipe_out_vertical_near_end_shows_only_black_and_sweep_colour():
    canvas = HeadlessCanvas(160, 16)
    WipeOutVertical().frame_at(0.999, canvas, _filling_widget(160, 16), _widget())
    seen = _palette(canvas.get_pixel, [(x, y) for x in (0, 80, 159) for y in range(16)])
    assert seen == {(0, 0, 0), (255, 0, 0)}, seen  # no outgoing grey, no black-only


def test_wipe_in_near_end_shows_only_black_and_sweep_colour():
    canvas = HeadlessCanvas(160, 16)
    WipeIn().frame_at(0.999, canvas, _filling_widget(160, 16), _widget())
    seen = _palette(canvas.get_pixel, [(x, 8) for x in range(160)])
    assert seen == {(0, 0, 0), (255, 255, 0)}, seen


# ---------------------------------------------------------------------------
# Task 3: banded / scaled canvas coverage (physical-resolution geometry)
# ---------------------------------------------------------------------------


def _banded():
    """256×64 real panel wrapped at scale=2, content_height=16 → 16-row
    letterbox bands at rows 0..15 and 48..63 (same shape as
    TestBandedCanvasFullPanel in test_transitions.py). Both bands carry a
    sentinel so an un-erased band reads as a failure, not as default black."""
    from led_ticker.scaled_canvas import ScaledCanvas

    real = HeadlessCanvas(256, 64)
    for x in range(256):
        for y in (*range(16), *range(48, 64)):
            real.SetPixel(x, y, 100, 100, 100)
    return real, ScaledCanvas(real, scale=2, content_height=16)


BAND_ROWS = (*range(16), *range(48, 64))


def test_wipe_in_midway_erases_both_letterbox_bands_and_lines_span_them():
    real, wrapper = _banded()
    WipeIn().frame_at(0.5, wrapper, _widget(), _widget())
    b = progress_to_b(0.5, 256, True)
    assert b > 0
    erased_cols = (*range(b), *range(256 - b, 256))
    assert all(
        real.get_pixel(x, y) == (0, 0, 0) for x in erased_cols for y in BAND_ROWS
    ), "wipe_in blackout did not reach both letterbox bands"
    # Sweep lines run the full physical height, letterbox rows included.
    for y in (4, 32, 60):
        assert real.get_pixel(b, y) == (255, 255, 0)
        assert real.get_pixel(255 - b, y) == (255, 255, 0)
    # Bands outside the erased spans are untouched (no blanket Clear).
    assert real.get_pixel(128, 4) == (100, 100, 100)
    assert real.get_pixel(128, 60) == (100, 100, 100)


def test_wipe_out_vertical_near_end_erases_letterbox_rows_on_banded_wrapper():
    real, wrapper = _banded()
    WipeOutVertical().frame_at(0.999, wrapper, _widget(), _widget())
    seen = _palette(real.get_pixel, [(x, y) for x in (0, 128, 255) for y in range(64)])
    assert seen == {(0, 0, 0), (255, 0, 0)}, seen


def test_sweep_line_is_two_times_scale_thick_on_scale4():
    from led_ticker.scaled_canvas import ScaledCanvas

    real = HeadlessCanvas(256, 64)
    wrapper = ScaledCanvas(real, scale=4, content_height=16)
    WipeOut().frame_at(0.5, wrapper, _widget(), _widget())
    red_cols = [x for x in range(256) if real.get_pixel(x, 32) == (255, 0, 0)]
    # Two runs of exactly 8 (= 2 * scale) columns, one per front.
    assert len(red_cols) == 16
    left, right = red_cols[:8], red_cols[8:]
    assert left == list(range(left[0], left[0] + 8))
    assert right == list(range(right[0], right[0] + 8))
    # Lines flank the band on the kept side, at full physical height.
    assert real.get_pixel(left[-1] + 1, 32) == (0, 0, 0)
    assert real.get_pixel(right[0] - 1, 32) == (0, 0, 0)
    assert real.get_pixel(left[0], 0) == (255, 0, 0)
    assert real.get_pixel(left[0], 63) == (255, 0, 0)
