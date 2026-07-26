"""Phase 2: the animation table, tick, and lifecycle."""

import pytest

from led_ticker import pixel_emoji
from led_ticker.pixel_emoji import (
    HiResEmoji,
    _ImageAnimation,
    abort_image_emoji,
    commit_image_emoji,
    frame_index_for,
    has_animated_emoji,
    stage_image_emoji,
    suspend_image_emoji,
    tick_image_animations,
)


def _hires(w=4):
    return HiResEmoji(
        pixels=tuple((x, y, 200, 0, 0) for x in range(w) for y in range(4)),
        physical_size=32,
        physical_width=w,
    )


_LOW = [(0, 0, 255, 0, 0)]


def _anim(n=3, dur=100):
    frames = tuple(_hires() for _ in range(n))
    cum = tuple(dur * (i + 1) for i in range(n))
    return _ImageAnimation(hires_frames=frames, cumulative_ms=cum, total_ms=cum[-1])


@pytest.fixture(autouse=True)
def _clean():
    abort_image_emoji()
    for slug in list(pixel_emoji._CONFIG_IMAGE_SLUGS):
        pixel_emoji.EMOJI_REGISTRY.pop(slug, None)
        pixel_emoji.HIRES_REGISTRY.pop(slug, None)
    pixel_emoji._CONFIG_IMAGE_SLUGS.clear()
    pixel_emoji._IMAGE_ANIMATIONS.clear()
    pixel_emoji._ANIM_LAST_INDEX.clear()
    yield


class TestFrameIndexFor:
    def test_table_driven(self):
        anim = _anim(3, 100)  # cum (100, 200, 300)
        for elapsed, expect in (
            (0, 0),
            (99, 0),
            (100, 1),
            (199, 1),
            (250, 2),
            (299, 2),
        ):
            assert frame_index_for(anim, elapsed) == expect, elapsed

    def test_wraps_at_total(self):
        anim = _anim(3, 100)
        assert frame_index_for(anim, 300 % anim.total_ms) == 0


class TestLifecycle:
    def test_commit_lands_table_and_frame0(self):
        anim = _anim()
        stage_image_emoji("me.p", _LOW, anim.hires_frames[0], animation=anim)
        commit_image_emoji()
        assert pixel_emoji._IMAGE_ANIMATIONS["me.p"] is anim
        assert pixel_emoji.HIRES_REGISTRY["me.p"] is anim.hires_frames[0]

    def test_commit_purges_dead_entry_on_animated_to_static(self):
        anim = _anim()
        stage_image_emoji("me.p", _LOW, anim.hires_frames[0], animation=anim)
        commit_image_emoji()
        # reload: same slug, now STATIC (no animation record)
        static = _hires()
        stage_image_emoji("me.p", _LOW, static)
        commit_image_emoji()
        assert "me.p" not in pixel_emoji._IMAGE_ANIMATIONS  # table purged
        assert pixel_emoji.HIRES_REGISTRY["me.p"] is static

    def test_abort_drops_pending_animation(self):
        stage_image_emoji("me.p", _LOW, _hires(), animation=_anim())
        abort_image_emoji()
        commit_image_emoji()
        assert "me.p" not in pixel_emoji._IMAGE_ANIMATIONS

    def test_suspend_restore_round_trips_table(self):
        anim = _anim()
        stage_image_emoji("me.p", _LOW, anim.hires_frames[0], animation=anim)
        commit_image_emoji()
        snap = suspend_image_emoji()
        assert "me.p" not in pixel_emoji._IMAGE_ANIMATIONS  # suspended
        abort_image_emoji()
        for slug, (lowres, hires, animation) in snap.items():
            stage_image_emoji(slug, lowres, hires, animation=animation)
        commit_image_emoji()
        assert pixel_emoji._IMAGE_ANIMATIONS["me.p"] is anim


class TestTick:
    def test_tick_swaps_on_index_change_only(self, monkeypatch):
        anim = _anim(2, 100)  # frames at [0,100) and [100,200)
        stage_image_emoji("me.p", _LOW, anim.hires_frames[0], animation=anim)
        commit_image_emoji()
        t = {"now": pixel_emoji._ANIM_EPOCH_MS + 50}  # inside frame 0
        monkeypatch.setattr(pixel_emoji, "_now_ms", lambda: t["now"])
        tick_image_animations()
        before = pixel_emoji.HIRES_REGISTRY["me.p"]
        tick_image_animations()  # same frame -> no write
        assert pixel_emoji.HIRES_REGISTRY["me.p"] is before
        t["now"] += 100  # into frame 1
        tick_image_animations()
        assert pixel_emoji.HIRES_REGISTRY["me.p"] is anim.hires_frames[1]

    def test_lowres_never_swapped(self, monkeypatch):
        anim = _anim(2, 100)
        stage_image_emoji("me.p", _LOW, anim.hires_frames[0], animation=anim)
        commit_image_emoji()
        low_before = pixel_emoji._get_registry()["me.p"]
        t = {"now": pixel_emoji._ANIM_EPOCH_MS + 150}
        monkeypatch.setattr(pixel_emoji, "_now_ms", lambda: t["now"])
        tick_image_animations()
        assert pixel_emoji._get_registry()["me.p"] is low_before  # hires-only

    def test_empty_table_is_cheap_noop(self):
        tick_image_animations()  # must not raise, nothing registered


class TestHasAnimatedEmoji:
    def test_true_only_for_animated_slugs(self):
        anim = _anim()
        stage_image_emoji("me.p", _LOW, anim.hires_frames[0], animation=anim)
        stage_image_emoji("me.s", _LOW, _hires())  # static
        commit_image_emoji()
        assert has_animated_emoji("x :me.p: y")
        assert not has_animated_emoji("x :me.s: y")
        assert not has_animated_emoji("no tokens here")
