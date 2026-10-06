"""Two-phase config-image emoji registration (stage/commit/abort)."""

import pytest

from led_ticker import pixel_emoji
from led_ticker.pixel_emoji import (
    HiResEmoji,
    abort_image_emoji,
    commit_image_emoji,
    stage_image_emoji,
)

_LOWRES = [(0, 0, 255, 0, 0), (1, 1, 0, 255, 0)]
_HIRES = HiResEmoji(
    pixels=tuple((x, y, 200, 200, 200) for x in range(4) for y in range(4)),
    physical_size=32,
    physical_width=4,
)


@pytest.fixture(autouse=True)
def _clean_registration():
    """Never leak staged/committed image slugs between tests."""
    abort_image_emoji()
    _wipe_committed()
    yield
    abort_image_emoji()
    _wipe_committed()


def _wipe_committed():
    for slug in list(pixel_emoji._CONFIG_IMAGE_SLUGS):
        pixel_emoji.EMOJI_REGISTRY.pop(slug, None)
        pixel_emoji.HIRES_REGISTRY.pop(slug, None)
    pixel_emoji._CONFIG_IMAGE_SLUGS.clear()


class TestStageCommit:
    def test_stage_alone_does_not_touch_registries(self):
        stage_image_emoji("cart.logo", _LOWRES, _HIRES)
        assert "cart.logo" not in pixel_emoji._get_registry()
        assert "cart.logo" not in pixel_emoji.HIRES_REGISTRY

    def test_commit_lands_both_forms_and_parse_gate_accepts(self):
        stage_image_emoji("cart.logo", _LOWRES, _HIRES)
        commit_image_emoji()
        assert pixel_emoji._get_registry()["cart.logo"] == _LOWRES
        assert pixel_emoji.HIRES_REGISTRY["cart.logo"] is _HIRES
        # lowres form present -> the 3-place parse gate accepts unchanged
        assert pixel_emoji.has_renderable_emoji("hi :cart.logo: there")

    def test_recommit_replaces_previous_set(self):
        stage_image_emoji("a", _LOWRES, _HIRES)
        commit_image_emoji()
        stage_image_emoji("b", _LOWRES, _HIRES)
        commit_image_emoji()
        reg = pixel_emoji._get_registry()
        assert "b" in reg and "a" not in reg  # old set swapped out

    def test_abort_drops_pending_keeps_committed(self):
        stage_image_emoji("keep", _LOWRES, _HIRES)
        commit_image_emoji()
        stage_image_emoji("drop", _LOWRES, _HIRES)
        abort_image_emoji()
        reg = pixel_emoji._get_registry()
        assert "keep" in reg and "drop" not in reg  # atomic reload semantics

    def test_commit_refuses_non_image_collision(self, caplog):
        # 'taco' is a curated slug — commit must skip it, log, and keep curated.
        curated = pixel_emoji._get_registry()["taco"]
        stage_image_emoji("taco", _LOWRES, _HIRES)
        commit_image_emoji()
        assert pixel_emoji._get_registry()["taco"] is curated
        assert "taco" not in pixel_emoji._CONFIG_IMAGE_SLUGS
