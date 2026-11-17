"""Center wipes: ``wipe_in`` / ``wipe_out`` and their vertical twins.

Task 1 pins the pure span geometry: for every extent (odd and even) and every
front position ``b`` the erased and kept spans partition the axis exactly, so
the two fronts can never leave a 1-px gap or overlap at the center.
"""

import pytest

from led_ticker.transitions.center_wipe import (
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
def test_progress_to_b_endpoints(n):
    half = (n + 1) // 2
    assert progress_to_b(0.0, n) == 0
    assert progress_to_b(0.999, n) == half
    assert progress_to_b(1.0, n) == half
    assert all(0 <= progress_to_b(t / 100, n) <= half for t in range(101))


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
        if b == 0 or not kept:
            assert lines == set()


def test_sweep_lines_inward_even_example():
    assert sweep_line_spans(160, 10, True, thick=2) == [(10, 12), (148, 150)]


def test_sweep_lines_outward_even_example():
    assert sweep_line_spans(160, 10, False, thick=2) == [(68, 70), (90, 92)]
