"""Factory seam for `random` / `auto`: pool resolution and child configs.

`_resolve_pool` is the runtime authority (validate rule 73 reuses it), so
every refusal here is a `ValueError` with a message a user can act on, and
every accepted shape builds children exactly once per wrapper.
"""

import pytest

from led_ticker.app.factories import (
    _build_trans_obj,
    _child_transition_cfg,
    _pool_member_key,
    _resolve_pool,
    _resolve_pool_members,
)
from led_ticker.config import TransitionConfig
from led_ticker.transitions import (
    _TRANSITION_REGISTRY,
    AutoTransition,
    RandomTransition,
    default_pool_names,
    register_transition,
)

FIFTEEN = default_pool_names()


class _ColorsStub:
    built = 0

    def __init__(self, colors=None, knob=1):
        type(self).built += 1
        self.colors = colors
        self.knob = knob

    def frame_at(self, t, canvas, outgoing, incoming, **kw):
        return canvas


class _ColorStub:
    def __init__(self, color=None):
        self.color = color

    def frame_at(self, t, canvas, outgoing, incoming, **kw):
        return canvas


class _NeedsStub:
    def __init__(self, needed):
        self.needed = needed

    def frame_at(self, t, canvas, outgoing, incoming, **kw):
        return canvas


@pytest.fixture(autouse=True)
def _stubs():
    register_transition("testmeta.colors")(_ColorsStub)
    register_transition("testmeta.color")(_ColorStub)
    register_transition("testmeta.needs")(_NeedsStub)
    yield
    for name in ("testmeta.colors", "testmeta.color", "testmeta.needs"):
        _TRANSITION_REGISTRY.pop(name, None)


def _cfg(type="random", extra=None, **kw):
    return TransitionConfig(type=type, extra=extra or {}, **kw)


def _types(resolved):
    return [c.type for c, _d, _n in resolved]


# --- default pool ---------------------------------------------------------


def test_bare_random_builds_default_pool_of_fifteen():
    resolved = _resolve_pool(_cfg())
    assert _types(resolved) == FIFTEEN
    assert [d for _c, d, _n in resolved] == [None] * 15
    obj = _build_trans_obj(_cfg())
    assert isinstance(obj, RandomTransition)


def test_bare_auto_builds_in_sorted_order():
    obj = _build_trans_obj(_cfg("auto"))
    assert isinstance(obj, AutoTransition)
    assert [obj._names[i] for i in range(15)] == FIFTEEN


def test_exclude_removes_named_members():
    resolved = _resolve_pool(_cfg(extra={"exclude": ["dissolve", "color_flash"]}))
    assert _types(resolved) == [
        n for n in FIFTEEN if n not in ("dissolve", "color_flash")
    ]


def test_pool_refuses_exclude_below_two():
    with pytest.raises(ValueError, match="1 distinct"):
        _resolve_pool(_cfg(extra={"exclude": FIFTEEN[1:]}))


def test_exclude_name_not_in_pool_is_a_no_op():
    resolved = _resolve_pool(
        _cfg(extra={"pool": ["wipe_in", "wipe_out"], "exclude": ["dissolve"]})
    )
    assert _types(resolved) == ["wipe_in", "wipe_out"]


# --- explicit pool --------------------------------------------------------


def test_explicit_pool_strings_and_tables():
    resolved = _resolve_pool(
        _cfg(
            duration=0.5,
            extra={
                "pool": ["wipe_in", "push_up", {"type": "dissolve", "duration": 3.0}]
            },
        )
    )
    assert _types(resolved) == ["wipe_in", "push_up", "dissolve"]
    assert [d for _c, d, _n in resolved] == [None, None, 3.0]
    assert resolved[2][0].duration == 3.0 and resolved[0][0].duration == 0.5


def test_entry_duration_reaches_wrapper_duration_override():
    obj = _build_trans_obj(
        _cfg("auto", extra={"pool": [{"type": "wipe_in", "duration": 2.5}, "wipe_out"]})
    )
    assert obj.duration_override == 2.5
    obj.end_firing()
    assert obj.duration_override is None


def test_auto_keeps_pool_order():
    obj = _build_trans_obj(
        _cfg("auto", extra={"pool": ["wipe_out", "dissolve", "wipe_in"]})
    )
    assert [obj._names[i] for i in range(3)] == ["wipe_out", "dissolve", "wipe_in"]


# --- refusals: shape ------------------------------------------------------


@pytest.mark.parametrize(
    "extra", [{"pool": "wipe_in"}, {"pool": 5}, {"exclude": "dissolve"}]
)
def test_pool_refuses_non_list_pool_or_exclude(extra):
    with pytest.raises(ValueError, match="must be a list"):
        _resolve_pool(_cfg(extra=extra))


@pytest.mark.parametrize(
    "entry",
    [
        5,
        {"duration": 1.0},
        {"type": 5},
        ["wipe_in"],
        {"type": ["x"]},
        {"type": {"a": 1}},
    ],
)
def test_pool_refuses_malformed_entry(entry):
    with pytest.raises(ValueError, match="pool entry"):
        _resolve_pool(_cfg(extra={"pool": [entry, "wipe_out"]}))


def test_pool_refuses_non_str_exclude_element():
    with pytest.raises(ValueError, match="exclude"):
        _resolve_pool(_cfg(extra={"exclude": [5]}))


def test_pool_refuses_unregistered_exclude_name():
    with pytest.raises(ValueError, match="disolve"):
        _resolve_pool(_cfg(extra={"exclude": ["disolve"]}))


def test_pool_refuses_unregistered_type():
    with pytest.raises(ValueError, match="unknown transition"):
        _resolve_pool(_cfg(extra={"pool": ["wipe_in", "no_such"]}))


def test_pool_refuses_stray_extra_keys():
    with pytest.raises(ValueError, match="pool and exclude only"):
        _resolve_pool(_cfg(extra={"pool": ["wipe_in", "wipe_out"], "weighting": 1}))


@pytest.mark.parametrize(
    "member",
    [
        "cut",
        "scroll",
        "push_random",
        "push_alternating",
        "wipe_random",
        "wipe_alternating",
    ],
)
def test_pool_refuses_hard_excluded(member):
    with pytest.raises(ValueError, match="cannot be a pool member"):
        _resolve_pool(_cfg(extra={"pool": ["wipe_in", member]}))


@pytest.mark.parametrize(
    "member", ["random", "auto", {"type": "random", "pool": ["wipe_in"]}]
)
def test_pool_refuses_nesting(member):
    with pytest.raises(ValueError, match="cannot nest"):
        _resolve_pool(_cfg(extra={"pool": ["wipe_in", member]}))


# --- refusals: entry keys -------------------------------------------------


@pytest.mark.parametrize(
    "key,value",
    [
        ("easing", "ease_out"),
        ("transition_fps", 30),
        ("separator", "x"),
        ("separator_color", [1, 2, 3]),
        ("separator_font", "f"),
        ("separator_font_size", 8),
        ("separator_size", 2),
    ],
)
def test_pool_refuses_section_level_key_on_entry(key, value):
    with pytest.raises(ValueError, match=key):
        _resolve_pool(
            _cfg(extra={"pool": ["wipe_in", {"type": "wipe_out", key: value}]})
        )


def test_pool_refuses_transition_colors_on_core_entry():
    with pytest.raises(ValueError, match="transition_color"):
        _resolve_pool(
            _cfg(
                extra={
                    "pool": [
                        "wipe_in",
                        {"type": "wipe_out", "transition_colors": [[1, 2, 3]]},
                    ]
                }
            )
        )


def test_pool_refuses_unknown_key_on_core_entry_with_did_you_mean():
    with pytest.raises(ValueError, match="did you mean transition_color"):
        _resolve_pool(
            _cfg(extra={"pool": ["wipe_in", {"type": "wipe_out", "color": [1, 2, 3]}]})
        )
    with pytest.raises(ValueError, match="did you mean transition_colors"):
        _resolve_pool(
            _cfg(
                extra={"pool": ["wipe_in", {"type": "wipe_out", "colors": [[1, 2, 3]]}]}
            )
        )


@pytest.mark.parametrize(
    "bad", ["red", [255, 0], [255.0, 0, 0], [True, True, True], 255]
)
def test_pool_refuses_bad_entry_color(bad):
    with pytest.raises(ValueError, match="0-255"):
        _resolve_pool(
            _cfg(
                extra={
                    "pool": ["wipe_in", {"type": "wipe_out", "transition_color": bad}]
                }
            )
        )


@pytest.mark.parametrize(
    "bad", ["3.0", True, 0, -1, 0.0, float("inf"), float("nan"), 3601, 1e308]
)
def test_pool_refuses_bad_entry_duration(bad):
    with pytest.raises(ValueError, match="duration"):
        _resolve_pool(
            _cfg(extra={"pool": ["wipe_in", {"type": "wipe_out", "duration": bad}]})
        )


# --- dedupe ---------------------------------------------------------------


def test_pool_dedupes_identical_entries_below_two():
    with pytest.raises(ValueError, match="1 distinct"):
        _resolve_pool(_cfg(extra={"pool": ["wipe_in", "wipe_in"]}))


def test_pool_dedupes_string_and_type_only_table():
    parent = _cfg(duration=0.5)
    a = _child_transition_cfg(parent, "wipe_in")
    b = _child_transition_cfg(parent, {"type": "wipe_in"})
    assert _pool_member_key(a, None) == _pool_member_key(b, None)
    with pytest.raises(ValueError, match="1 distinct"):
        _resolve_pool(_cfg(extra={"pool": ["wipe_in", {"type": "wipe_in"}]}))


def test_pool_dedupes_behaviour_identical_members():
    """int vs float duration, and a table duration equal to the parent's,
    describe the same member — keyed on the resolved child, not the repr."""
    with pytest.raises(ValueError, match="1 distinct"):
        _resolve_pool(
            _cfg(
                extra={
                    "pool": [
                        {"type": "dissolve", "duration": 3},
                        {"type": "dissolve", "duration": 3.0},
                    ]
                }
            )
        )
    # a table pinning the parent's own duration is the SAME member
    with pytest.raises(ValueError, match="1 distinct"):
        _resolve_pool(
            _cfg(
                duration=0.5,
                extra={"pool": ["dissolve", {"type": "dissolve", "duration": 0.5}]},
            )
        )
    members = _resolve_pool_members(
        _cfg(
            duration=0.5,
            extra={"pool": ["dissolve", {"type": "dissolve", "duration": 0.6}]},
        )
    )
    assert len({k for *_rest, k in members}) == 2


def test_inherited_parent_colour_is_shape_checked_on_children():
    """A malformed colour on the random/auto SLOT reaches every child via the
    clone; the resolver must refuse it (rule 74 grades the parent by what its
    own constructor reads, which is nothing)."""
    with pytest.raises(ValueError, match="0-255"):
        _resolve_pool(_cfg(color=("r", "e", "d")))
    with pytest.raises(ValueError, match="0-255"):
        _resolve_pool(
            _cfg(colors=[(1, 2)], extra={"pool": ["testmeta.colors", "wipe_in"]})
        )


def test_pool_refuses_absurd_entry_duration():
    with pytest.raises(ValueError, match="at most 3600"):
        _resolve_pool(
            _cfg(extra={"pool": ["wipe_in", {"type": "wipe_out", "duration": 1e308}]})
        )


# --- colours --------------------------------------------------------------


def test_parent_color_reaches_core_children_even_with_parent_colors():
    parent = _cfg(color=(1, 2, 3), colors=[(4, 5, 6), (7, 8, 9)])
    for child_cfg, _d, _n in _resolve_pool(parent):
        assert child_cfg.color == (1, 2, 3) and child_cfg.colors is None
    obj = _build_trans_obj(parent)
    wipe_in = obj._children[obj._names.index("wipe_in")]
    assert wipe_in.color == (1, 2, 3)


def test_entry_transition_color_overrides_inherited():
    parent = _cfg(color=(1, 2, 3), colors=[(4, 5, 6)])
    child = _child_transition_cfg(
        parent, {"type": "wipe_in", "transition_color": [9, 9, 9]}
    )
    assert child.color == (9, 9, 9) and child.colors is None
    assert child.type_specified and child.extra == {}


def test_dotted_child_declaring_colors_gets_inherited_list():
    parent = _cfg(color=(1, 2, 3), colors=[(4, 5, 6), (7, 8, 9)])
    child = _child_transition_cfg(parent, "testmeta.colors")
    assert child.colors == [(4, 5, 6), (7, 8, 9)]
    obj = _build_trans_obj(
        _cfg(colors=[(4, 5, 6)], extra={"pool": ["testmeta.colors", "wipe_in"]})
    )
    assert obj._children[0].colors == [(4, 5, 6)]


def test_dotted_color_only_child_gets_parent_color_not_list():
    parent = _cfg(color=(1, 2, 3), colors=[(4, 5, 6)])
    child = _child_transition_cfg(parent, "testmeta.color")
    assert child.color == (1, 2, 3) and child.colors is None
    obj = _build_trans_obj(
        _cfg(
            color=(1, 2, 3),
            colors=[(4, 5, 6)],
            extra={"pool": ["testmeta.color", "wipe_in"]},
        )
    )
    assert obj._children[0].color == (1, 2, 3)


def test_dotted_entry_own_transition_colors_on_color_only_child_raises():
    with pytest.raises(
        ValueError, match="takes transition_color, not transition_colors"
    ):
        _child_transition_cfg(
            _cfg(), {"type": "testmeta.color", "transition_colors": [[1, 2, 3]]}
        )


def test_dotted_entry_own_transition_colors_on_colors_child_is_kept():
    child = _child_transition_cfg(
        _cfg(color=(1, 2, 3)),
        {"type": "testmeta.colors", "transition_colors": [[7, 7, 7]]},
    )
    assert child.colors == [(7, 7, 7)] and child.color is None


def test_dotted_entry_extra_kwargs_reach_constructor():
    obj = _build_trans_obj(
        _cfg(
            "auto", extra={"pool": [{"type": "testmeta.colors", "knob": 42}, "wipe_in"]}
        )
    )
    assert obj._children[0].knob == 42


def test_dotted_child_build_failure_fails_the_wrapper():
    with pytest.raises(ValueError, match="needed"):
        _build_trans_obj(_cfg(extra={"pool": ["testmeta.needs", "wipe_in"]}))


# --- build once / caching -------------------------------------------------


def test_children_built_once_across_fifty_firings():
    _ColorsStub.built = 0
    obj = _build_trans_obj(_cfg(extra={"pool": ["testmeta.colors", "testmeta.color"]}))
    for _ in range(50):
        obj.frame_at(0.5, "c", None, None)
        obj.end_firing()
    assert _ColorsStub.built == 1


def test_cached_trans_obj_rebuilds_meta_on_new_cfg():
    from led_ticker.app.run import _cached_trans_obj

    cache: dict = {}
    cfg_a = _cfg()
    first = _cached_trans_obj(cache, cfg_a)
    assert _cached_trans_obj(cache, cfg_a) is first
    assert _cached_trans_obj(cache, _cfg()) is not first


class _BothStub:
    def __init__(self, color=None, colors=None):
        self.color = color
        self.colors = colors

    def frame_at(self, t, canvas, outgoing, incoming, **kw):
        return canvas


def test_entry_transition_color_clears_inherited_colors_on_a_both_child():
    """A dotted child that declares BOTH color and colors: an entry's own
    transition_color must beat the parent's inherited list (the dotted path
    forwards colors first)."""
    register_transition("testmeta.both")(_BothStub)
    try:
        child = _child_transition_cfg(
            _cfg(color=(1, 2, 3), colors=[(4, 5, 6)]),
            {"type": "testmeta.both", "transition_color": [9, 9, 9]},
        )
        assert child.color == (9, 9, 9) and child.colors is None
        obj = _build_trans_obj(
            _cfg(
                colors=[(4, 5, 6)],
                extra={
                    "pool": [
                        {"type": "testmeta.both", "transition_color": [9, 9, 9]},
                        "wipe_in",
                    ]
                },
            )
        )
        assert obj._children[0].color == (9, 9, 9) and obj._children[0].colors is None
    finally:
        _TRANSITION_REGISTRY.pop("testmeta.both", None)


async def test_factory_built_auto_pick_ahead_end_to_end(make_widget, no_sleep):
    """Composition pin: a factory-built `auto` over a sweep and a dissolve,
    driven through run_transition twice on a cross-scale entry. The runner's
    one-time reads (min_frames, duration_override, scale_switch_at) must match
    the child that actually draws: the sweep re-wraps only on its final frame,
    the dissolve at 0.5 with its own 1.0 s duration."""
    from unittest import mock

    from led_ticker.backends.headless import HeadlessCanvas
    from led_ticker.scaled_canvas import ScaledCanvas
    from led_ticker.transitions import run_transition

    obj = _build_trans_obj(
        _cfg(
            "auto",
            duration=0.5,
            extra={"pool": ["wipe_left", {"type": "dissolve", "duration": 1.0}]},
        )
    )
    seen: dict[str, list[tuple[float, int, int]]] = {"wipe_left": [], "dissolve": []}
    for child, name in zip(obj._children, ("wipe_left", "dissolve"), strict=True):

        def _rec(t, canvas, outgoing, incoming, _name=name, **kw):
            seen[_name].append((t, getattr(canvas, "scale", 1), kw["duration_ms"]))
            return canvas

        child.frame_at = _rec
    real = HeadlessCanvas(256, 64)
    frame = mock.Mock()
    frame.swap.side_effect = lambda c: HeadlessCanvas(256, 64)
    for _ in range(2):
        await run_transition(
            ScaledCanvas(real, scale=2),
            frame,
            make_widget(40),
            make_widget(40),
            transition=obj,
            duration=0.5,
            scroll_speed=0.05,
            incoming_scale=4,
        )
    wl, dz = seen["wipe_left"], seen["dissolve"]
    assert len(wl) == 41 and wl[0][2] == 500  # min_frames 40 floors the sweep
    assert [sc for _t, sc, _d in wl][:-1] == [2] * 40 and wl[-1][1] == 4
    assert len(dz) == 21 and dz[0][2] == 1000  # the child's own 1.0 s
    first_scale4 = next(t for t, sc, _d in dz if sc == 4)
    assert first_scale4 == 0.5
