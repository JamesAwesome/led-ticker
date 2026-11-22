"""`random` / `auto` pick-ahead meta-transitions (`transitions/meta.py`).

The wrapper holds pre-built children and the index of the NEXT firing; the
runner's one-time reads (`min_frames`, `scale_switch_at`, `duration_override`)
therefore describe the child that will actually run. `frame_at` is pure
delegation; only `end_firing()` advances.
"""

import logging
import random

import pytest

from led_ticker.transitions import (
    DEFAULT_SCALE_SWITCH_AT,
    AutoTransition,
    RandomTransition,
    get_transition_class,
    list_transition_names,
)
from led_ticker.transitions.meta import HARD_EXCLUDED, default_pool_names

FIFTEEN = [
    "color_flash",
    "dissolve",
    "push_down",
    "push_left",
    "push_right",
    "push_up",
    "split",
    "wipe_down",
    "wipe_in",
    "wipe_in_vertical",
    "wipe_left",
    "wipe_out",
    "wipe_out_vertical",
    "wipe_right",
    "wipe_up",
]


class _Child:
    """Child stub with optional runner attrs and a frame_at recorder."""

    constructed = 0

    def __init__(self, min_frames=None, scale_switch_at=None):
        type(self).constructed += 1
        self.calls: list[float] = []
        if min_frames is not None:
            self.min_frames = min_frames
        if scale_switch_at is not None:
            self.scale_switch_at = scale_switch_at

    def frame_at(self, t, canvas, outgoing, incoming, **kw):
        self.calls.append(t)
        return canvas


def _kids(n=3):
    return [
        _Child(min_frames=10 * (i + 1), scale_switch_at=0.1 * (i + 1)) for i in range(n)
    ]


def _names(n=3):
    return [f"c{i}" for i in range(n)]


def test_registry_has_random_and_auto():
    assert get_transition_class("random") is RandomTransition
    assert get_transition_class("auto") is AutoTransition
    assert {"random", "auto"} <= set(list_transition_names())


def test_hard_excluded_set():
    assert (
        frozenset(
            {
                "cut",
                "scroll",
                "random",
                "auto",
                "push_random",
                "push_alternating",
                "wipe_random",
                "wipe_alternating",
            }
        )
        == HARD_EXCLUDED
    )


def test_default_pool_names_are_the_fifteen():
    assert default_pool_names() == FIFTEEN
    assert not (set(FIFTEEN) & HARD_EXCLUDED)


@pytest.mark.parametrize("cls", [RandomTransition, AutoTransition])
def test_pool_below_two_raises(cls):
    with pytest.raises(ValueError, match="at least 2"):
        cls([_Child()], [None], ["a"])


@pytest.mark.parametrize("cls", [RandomTransition, AutoTransition])
def test_mismatched_lengths_raise(cls):
    with pytest.raises(ValueError):
        cls(_kids(2), [None], _names(2))


def test_auto_starts_at_zero_and_cycles_in_order():
    a = AutoTransition(_kids(3), [None, 1.0, None], _names(3))
    seen = []
    for _ in range(6):
        seen.append(a.current_index)
        a.end_firing()
    assert seen == [0, 1, 2, 0, 1, 2]


def test_properties_track_current_child():
    kids = _kids(3)
    a = AutoTransition(kids, [None, 1.5, 2.5], _names(3))
    for _ in range(9):
        i = a.current_index
        assert a.min_frames == kids[i].min_frames
        assert a.scale_switch_at == kids[i].scale_switch_at
        assert a.duration_override == [None, 1.5, 2.5][i]
        assert a.current_name == f"c{i}"
        a.end_firing()


def test_properties_default_when_child_lacks_attrs():
    a = AutoTransition([_Child(), _Child()], [None, None], _names(2))
    assert a.min_frames == 0
    assert a.scale_switch_at == DEFAULT_SCALE_SWITCH_AT


def test_frame_at_is_pure_delegation_and_never_advances():
    kids = _kids(2)
    a = AutoTransition(kids, [None, None], _names(2))
    for t in (0.0, 0.5, 1.0, 1.0, 0.0):
        a.frame_at(t, "canvas", None, None, outgoing_scroll_pos=3)
    assert a.current_index == 0
    assert kids[0].calls == [0.0, 0.5, 1.0, 1.0, 0.0] and kids[1].calls == []


def test_random_never_repeats_index_over_200_firings():
    r = RandomTransition(_kids(4), [None] * 4, _names(4), rng=random.Random(3))
    seq = []
    for _ in range(200):
        seq.append(r.current_index)
        r.end_firing()
    assert all(a != b for a, b in zip(seq, seq[1:], strict=False))
    assert set(seq) == {0, 1, 2, 3}


def test_random_with_two_members_alternates():
    r = RandomTransition(_kids(2), [None, None], _names(2), rng=random.Random(1))
    seq = []
    for _ in range(10):
        seq.append(r.current_index)
        r.end_firing()
    assert seq == [seq[0], 1 - seq[0]] * 5


def test_random_rng_kwarg_makes_first_pick_deterministic():
    a = RandomTransition(_kids(5), [None] * 5, _names(5), rng=random.Random(7))
    b = RandomTransition(_kids(5), [None] * 5, _names(5), rng=random.Random(7))
    assert a.current_index == b.current_index
    a.end_firing()
    b.end_firing()
    assert a.current_index == b.current_index


def test_pick_logged_at_construction_and_each_end_firing(caplog):
    with caplog.at_level(logging.DEBUG, logger="led_ticker.transitions.meta"):
        a = AutoTransition(_kids(3), [None, 2.0, None], _names(3))
        for _ in range(4):
            a.end_firing()
    lines = [r.message for r in caplog.records if "transition auto[" in r.message]
    assert len(lines) == 5
    assert "next = c0 (index 0, duration section)" in lines[0]
    assert "next = c1 (index 1, duration 2.00s)" in lines[1]
    tags = {line.split("[")[1].split("]")[0] for line in lines}
    assert len(tags) == 1 and len(tags.pop()) == 4


def test_children_are_not_constructed_by_the_wrapper():
    _Child.constructed = 0
    kids = _kids(3)
    assert _Child.constructed == 3
    r = RandomTransition(kids, [None] * 3, _names(3), rng=random.Random(0))
    for _ in range(50):
        r.frame_at(0.5, "c", None, None)
        r.end_firing()
    assert _Child.constructed == 3


# --- end_firing forwards to the child that ran (fade design, "Meta wrapper") ---


class _HookChild(_Child):
    def __init__(self, raise_on_end=False):
        super().__init__()
        self.ends = 0
        self.raise_on_end = raise_on_end

    def end_firing(self):
        self.ends += 1
        if self.raise_on_end:
            raise RuntimeError("hook boom")


def test_end_firing_forwards_to_the_child_that_ran_not_the_next_pick():
    kids = [_HookChild(), _HookChild()]
    a = AutoTransition(kids, [None, None], ["a", "b"])
    assert a.current_index == 0
    a.end_firing()
    assert kids[0].ends == 1 and kids[1].ends == 0
    assert a.current_index == 1
    a.end_firing()
    assert kids[0].ends == 1 and kids[1].ends == 1


async def test_end_firing_runs_exactly_once_per_firing_through_the_runner(
    canvas, mock_frame, make_widget, no_sleep
):
    import random

    from led_ticker.transitions import run_transition

    kids = [_HookChild(), _HookChild()]
    r = RandomTransition(kids, [None, None], ["a", "b"], rng=random.Random(1))
    ran = kids[r.current_index]
    await run_transition(
        canvas, mock_frame, make_widget(), make_widget(), transition=r, duration=0.1
    )
    assert ran.ends == 1
    assert sum(k.ends for k in kids) == 1


def test_raising_child_hook_still_advances_the_pick():
    kids = [_HookChild(raise_on_end=True), _HookChild()]
    a = AutoTransition(kids, [None, None], ["a", "b"])
    with pytest.raises(RuntimeError, match="hook boom"):
        a.end_firing()  # the runner swallows + logs this; the wrapper must not
    assert a.current_index == 1  # the pick advanced despite the raise


def test_child_without_hook_is_unchanged():
    kids = _kids(2)
    a = AutoTransition(kids, [None, None], _names(2))
    a.end_firing()
    a.end_firing()
    a.end_firing()
    assert a.current_index == 1  # 0 -> 1 -> 0 -> 1, no AttributeError
