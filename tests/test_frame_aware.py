"""Tests for the _FrameAware mixin."""

from __future__ import annotations

import attrs
import pytest

from led_ticker.widgets._frame_aware import _FrameAware


@attrs.define
class _Dummy(_FrameAware):
    """Minimal subclass to exercise the mixin."""


@attrs.define
class _SimpleWidget(_FrameAware):
    """Minimal subclass for visit-ownership tests."""


class TestFrameAware:
    def test_initial_frame_count_is_zero(self):
        d = _Dummy()
        assert d._frame_count == 0

    def test_advance_increments(self):
        d = _Dummy()
        d.advance_frame()
        assert d._frame_count == 1
        d.advance_frame()
        d.advance_frame()
        assert d._frame_count == 3

    def test_pause_freezes_advance(self):
        d = _Dummy()
        d.advance_frame()
        d.pause_frame()
        d.advance_frame()
        d.advance_frame()
        assert d._frame_count == 1

    def test_resume_re_enables_advance(self):
        d = _Dummy()
        d.pause_frame()
        d.advance_frame()
        d.resume_frame()
        d.advance_frame()
        assert d._frame_count == 1

    def test_reset_zeroes_count(self):
        d = _Dummy()
        d.advance_frame()
        d.advance_frame()
        d.advance_frame()
        d.reset_frame()
        assert d._frame_count == 0

    def test_reset_does_not_clear_pause(self):
        """reset_frame is for visit boundaries; pause state belongs to
        transition boundaries and should not be cleared by a reset."""
        d = _Dummy()
        d.pause_frame()
        d.reset_frame()
        d.advance_frame()
        # Still paused after reset → advance should NOT increment
        assert d._frame_count == 0


class TestEffectFrames:
    """Per-effect frame counter behavior. The mixin tracks one
    counter per effect attribute (`font_color`, `top_color`,
    `bottom_color`, `border`, `animation`). Each counter follows
    its effect's `restart_on_visit` policy: True (default) zeros on
    `reset_frame()`; False keeps climbing for continuous phase."""

    def _make_widget_with_effects(self, **effects):
        """Construct a `_Dummy` subclass with the requested effect
        attributes. Effect classes inline so each test is self-
        contained."""

        @attrs.define
        class _WithEffects(_FrameAware):
            font_color: object = attrs.field(default=None, kw_only=True)
            border: object = attrs.field(default=None, kw_only=True)
            animation: object = attrs.field(default=None, kw_only=True)

        return _WithEffects(**effects)

    def test_advance_increments_per_effect_counter(self):
        """Per-effect counter climbs in lockstep with `_frame_count`."""

        class _Border:
            restart_on_visit = False

        widget = self._make_widget_with_effects(border=_Border())
        for _ in range(5):
            widget.advance_frame()
        assert widget._frame_count == 5
        assert widget._effect_frames["border"] == 5

    def test_reset_zeros_only_opted_in_effects(self):
        """Continuous-phase effects (restart_on_visit=False) keep
        their counter; restart-on-visit effects zero theirs."""

        class _Typewriter:
            restart_on_visit = True

        class _RainbowBorder:
            restart_on_visit = False

        widget = self._make_widget_with_effects(
            animation=_Typewriter(),
            border=_RainbowBorder(),
        )
        for _ in range(7):
            widget.advance_frame()
        assert widget._effect_frames["animation"] == 7
        assert widget._effect_frames["border"] == 7

        widget.reset_frame()
        assert widget._frame_count == 0
        # Restart-on-visit effect: zeroed
        assert widget._effect_frames["animation"] == 0
        # Continuous-phase effect: unchanged
        assert widget._effect_frames["border"] == 7

    def test_pause_freezes_all_counters(self):
        """Paused widget = all counters frozen, both primary and
        per-effect."""

        class _Border:
            restart_on_visit = False

        widget = self._make_widget_with_effects(border=_Border())
        widget.advance_frame()  # counters at 1
        widget.pause_frame()
        for _ in range(10):
            widget.advance_frame()
        assert widget._frame_count == 1
        assert widget._effect_frames["border"] == 1

    def test_frame_for_falls_back_to_frame_count(self):
        """Lookup of an attr_name not in the dict returns
        `_frame_count`. Covers the case where a test sets
        `_frame_count` directly without going through `advance_frame`."""

        class _Border:
            restart_on_visit = False

        widget = self._make_widget_with_effects(border=_Border())
        widget._frame_count = 42  # direct write, no advance_frame
        # `_effect_frames` is empty (no advance has populated it yet)
        assert widget._effect_frames == {}
        # frame_for falls back to _frame_count
        assert widget.frame_for("border") == 42

    def test_unknown_effect_class_resets_by_default(self):
        """Effect class without a `restart_on_visit` attribute uses
        the `getattr` default of True — same as the engine-side
        gate did in PR #11. Back-compat for any third-party effect."""

        class _CustomEffect:
            pass  # no restart_on_visit attribute

        widget = self._make_widget_with_effects(font_color=_CustomEffect())
        for _ in range(3):
            widget.advance_frame()
        assert widget._effect_frames["font_color"] == 3

        widget.reset_frame()
        # No restart_on_visit attribute → defaults to True → zeroes
        assert widget._effect_frames["font_color"] == 0


class TestFrameAwareGuard:
    def test_properly_decorated_subclass_constructs_fine(self):
        @attrs.define
        class GoodWidget(_FrameAware):
            name: str = attrs.field(default="")

        w = GoodWidget()
        assert w._frame_count == 0

    def test_undecorated_subclass_raises_on_instantiation(self):
        class BadWidget(_FrameAware):
            name: str = attrs.field(default="")

        with pytest.raises(TypeError, match="attrs.define"):
            BadWidget()

    def test_frame_aware_itself_can_be_instantiated(self):
        """_FrameAware() itself must not trigger the guard."""
        fa = _FrameAware()
        assert fa._frame_count == 0


class TestEffectAttrsCompleteness:
    """Tripwire: every `_FrameAware` subclass field whose annotation
    references a known effect protocol (`ColorProvider`, `BorderEffect`,
    `Animation`) — or whose name is one of the conventional `Any | None`
    effect slots (`border`, `animation`) — must be registered in
    `_FrameAware._EFFECT_ATTRS`. Catches a future widget that adds a
    new effect-typed field but forgets the registration: without this
    test the omission is silent, the per-effect counter is never
    advanced, `frame_for(name)` falls through to `_frame_count`, and
    a continuous-phase effect on the new field reverts to reset-per-
    visit behavior.
    """

    # Names of effect protocols we recognize in field type annotations.
    # Adding a new effect Protocol type (e.g. `BackgroundEffect`)
    # requires updating BOTH this set AND `_FrameAware._EFFECT_ATTRS`
    # for the new field — neither half catches an omission of the
    # other. Without the protocol-name update here, the test still
    # passes on a real registration miss (the field's annotation
    # mentions a Protocol the test doesn't know about, so the
    # `annotation_match` predicate returns False and the field is
    # skipped). Slow-leak failure mode by design — keep the two
    # in lockstep.
    EFFECT_PROTOCOL_NAMES: frozenset[str] = frozenset(
        {"ColorProvider", "BorderEffect", "Animation"}
    )
    # Conventional `Any | None` slot names — these are recognized by
    # field name because the runtime types are intentionally `Any` to
    # avoid widget code importing the Protocol at module-load time.
    # Same lockstep rule applies: a new conventional slot name needs
    # to be added here AND in `_FrameAware._EFFECT_ATTRS`.
    CONVENTIONAL_EFFECT_NAMES: frozenset[str] = frozenset({"border", "animation"})

    def _all_frame_aware_subclasses(self) -> set[type]:
        """Recursive walk of `_FrameAware.__subclasses__()`. Forces
        widget-module imports first so subclasses get registered."""
        # Ensure every widget module is imported so `__subclasses__`
        # sees every concrete subclass.
        import led_ticker.widgets  # noqa: F401

        seen: set[type] = set()
        stack = list(_FrameAware.__subclasses__())
        while stack:
            cls = stack.pop()
            if cls in seen:
                continue
            seen.add(cls)
            stack.extend(cls.__subclasses__())
        return seen

    def _annotation_mentions_effect(self, annotation: object) -> bool:
        """True when the annotation string mentions a known effect
        protocol. `attrs.fields()` exposes annotations as strings under
        `from __future__ import annotations`, so a substring match is
        sufficient and avoids resolving forward references."""
        text = str(annotation) if annotation is not None else ""
        return any(name in text for name in self.EFFECT_PROTOCOL_NAMES)

    def test_every_effect_typed_field_is_registered(self):
        """The actual tripwire."""
        registered = _FrameAware._EFFECT_ATTRS
        failures: list[str] = []

        for cls in self._all_frame_aware_subclasses():
            if not attrs.has(cls):
                continue
            for field in attrs.fields(cls):
                if field.name.startswith("_"):
                    continue
                annotation_match = self._annotation_mentions_effect(field.type)
                conventional_match = field.name in self.CONVENTIONAL_EFFECT_NAMES
                if not (annotation_match or conventional_match):
                    continue
                if field.name in registered:
                    continue
                reason = (
                    "annotation mentions effect protocol"
                    if annotation_match
                    else "conventional effect-slot name"
                )
                failures.append(
                    f"{cls.__module__}.{cls.__name__}.{field.name} "
                    f"(type={field.type!r}, {reason}) is not in "
                    f"_FrameAware._EFFECT_ATTRS"
                )

        assert not failures, (
            "Effect-typed fields must be registered in "
            "`_FrameAware._EFFECT_ATTRS` so their per-effect counter "
            "is advanced. Missing registrations:\n  " + "\n  ".join(failures)
        )

    def test_predicate_recognizes_color_provider_annotation(self):
        """Self-test for `_annotation_mentions_effect`: positive
        match on the canonical idiom `Color | ColorProvider`."""
        assert self._annotation_mentions_effect("Color | ColorProvider")
        assert self._annotation_mentions_effect("ColorProvider | None")
        assert self._annotation_mentions_effect("BorderEffect | None")
        assert self._annotation_mentions_effect("Animation")

    def test_predicate_skips_non_effect_annotations(self):
        """Self-test: bare `Color`, `Font`, `int` — the field types
        used for non-effect knobs — must NOT match. Without this,
        a regression in the predicate could pass the tripwire by
        matching too much (or too little)."""
        assert not self._annotation_mentions_effect("Color")
        assert not self._annotation_mentions_effect("Color | None")
        assert not self._annotation_mentions_effect("Font")
        assert not self._annotation_mentions_effect("int")
        assert not self._annotation_mentions_effect("Any | None")
        assert not self._annotation_mentions_effect(None)


class TestVisitOwnership:
    """Tests for _FrameAware visit-ownership tracking (Large #4)."""

    def test_advance_frame_no_visit_id_is_unchecked(self):
        """Calling advance_frame() without visit_id works as before."""
        w = _SimpleWidget()
        w.advance_frame()
        assert w._frame_count == 1

    def test_advance_frame_same_visit_id_allowed(self):
        """Multiple advance_frame calls with the same visit_id are fine."""
        w = _SimpleWidget()
        w.advance_frame(visit_id=1)
        w.advance_frame(visit_id=1)
        assert w._frame_count == 2

    def test_advance_frame_different_visit_id_raises(self):
        """advance_frame with a new visit_id when one is already claimed raises."""
        w = _SimpleWidget()
        w.advance_frame(visit_id=1)
        with pytest.raises(RuntimeError, match="claimed by visit_id"):
            w.advance_frame(visit_id=2)

    def test_reset_frame_clears_visit_owner(self):
        """reset_frame() releases the visit claim so a new visit_id can take over."""
        w = _SimpleWidget()
        w.advance_frame(visit_id=1)
        w.reset_frame()
        w.advance_frame(visit_id=2)
        assert w._frame_count == 1

    def test_advance_frame_no_visit_id_after_claimed_does_not_raise(self):
        """Callers that don't pass visit_id bypass the ownership check."""
        w = _SimpleWidget()
        w.advance_frame(visit_id=1)
        w.advance_frame()  # no visit_id — must not raise
        assert w._frame_count == 2

    def test_visit_owner_is_none_initially(self):
        w = _SimpleWidget()
        assert w._visit_owner is None
