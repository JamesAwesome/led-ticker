"""LensTextRenderer unit tests. The message-widget lens suite remains the
behavioral net for the extraction; these pin the renderer's own contract."""

import pytest

from led_ticker.animations import LensSpec
from led_ticker.backends.headless import HeadlessCanvas
from led_ticker.fonts import FONT_DEFAULT
from led_ticker.lens_render import LensTextRenderer
from led_ticker.scaled_canvas import ScaledCanvas


def _lens(magnify=1.3, edge_squeeze=0.6):
    return LensSpec(magnify=magnify, edge_squeeze=edge_squeeze, profile="cosine")


class TestLensTextRenderer:
    def test_paint_strip_receives_strip_target_and_blit_hits_canvas(self):
        canvas = HeadlessCanvas(160, 16)
        r = LensTextRenderer()
        calls = []

        def paint(target, x_logical, baseline, hires_downscale):
            calls.append((x_logical, baseline, hires_downscale))
            # light a solid block so the blit has something to map
            for x in range(0, 60):
                for y in range(4, 12):
                    target.SetPixel(x, y, 255, 255, 255)

        r.draw(
            canvas,
            _lens(),
            font=FONT_DEFAULT,
            cursor_pos=0,
            owner_name="T",
            paint_strip=paint,
        )
        assert len(calls) == 1
        assert calls[0][2] == 1.0  # scale 1 -> no hires downscale
        assert canvas._pixels, "lens blit painted nothing"

    def test_strip_cache_reused_across_draws(self):
        canvas = HeadlessCanvas(160, 16)
        r = LensTextRenderer()
        targets = []

        for _ in range(2):
            r.draw(
                canvas,
                _lens(),
                font=FONT_DEFAULT,
                cursor_pos=0,
                owner_name="T",
                paint_strip=lambda t, x, b, h: targets.append(t),
            )
        assert targets[0] is targets[1], "strip target rebuilt despite same dims"

    def test_vertical_fit_raises_with_owner_name(self):
        canvas = HeadlessCanvas(160, 8)  # short panel: 1.3 x 12 > 8
        r = LensTextRenderer()

        with pytest.raises(ValueError, match="MyWidget.*magnify"):
            r.draw(
                canvas,
                _lens(),
                font=FONT_DEFAULT,
                cursor_pos=0,
                owner_name="MyWidget",
                paint_strip=lambda *a: None,
            )

    def test_scaled_canvas_uses_reduced_render_scale(self):
        real = HeadlessCanvas(256, 64)
        canvas = ScaledCanvas(real, scale=4, content_height=16)
        r = LensTextRenderer()
        seen = {}

        def paint(target, x_logical, baseline, hires_downscale):
            seen["scale"] = getattr(target, "scale", 1)
            seen["down"] = hires_downscale

        r.draw(
            canvas,
            _lens(),
            font=FONT_DEFAULT,
            cursor_pos=0,
            owner_name="T",
            paint_strip=paint,
        )
        assert seen["scale"] == 2  # render_scale = max(1, 4 // 2)
        assert seen["down"] == 0.5  # render_scale / scale

    def test_blit_wrapper_rebinds_to_new_real_across_calls(self):
        """CLAUDE.md constraint #10 pin: `_lens_blit_dst`'s cached
        `_lens_blit_wrapper` must rebind `.real` to the CURRENT real
        canvas on every call, not just the first. On hardware this is
        the pulsing-flicker regression — a cached wrapper stuck on the
        first back buffer would paint every other tick's lens blit onto
        a buffer that's no longer live.

        Uses two DIFFERENT `HeadlessCanvas` reals (simulating swap-driven
        back-buffer rotation) each wrapped in a scale>1 `ScaledCanvas` so
        the wrapper path is exercised (not the scale-1 direct-blit
        shortcut, where `_lens_blit_dst` returns `canvas` untouched)."""
        from led_ticker.scaled_canvas import unwrap_to_real

        real1 = HeadlessCanvas(256, 64)
        real2 = HeadlessCanvas(256, 64)
        canvas1 = ScaledCanvas(real1, scale=4, content_height=16)
        canvas2 = ScaledCanvas(real2, scale=4, content_height=16)
        r = LensTextRenderer()

        def paint(target, x_logical, baseline, hires_downscale):
            for x in range(0, 60):
                for y in range(4, 12):
                    target.SetPixel(x, y, 255, 255, 255)

        r.draw(
            canvas1,
            _lens(),
            font=FONT_DEFAULT,
            cursor_pos=0,
            owner_name="T",
            paint_strip=paint,
        )
        assert real1._pixels, "first draw painted nothing onto real1"
        pixels_after_first_draw = dict(real1._pixels)

        r.draw(
            canvas2,
            _lens(),
            font=FONT_DEFAULT,
            cursor_pos=0,
            owner_name="T",
            paint_strip=paint,
        )

        assert real2._pixels, (
            "second draw's blit did not land on real2 — the cached blit "
            "wrapper's .real was not rebound to the current back buffer"
        )
        assert real1._pixels == pixels_after_first_draw, (
            "second draw's blit bled into real1 — the cached blit wrapper "
            "is still pointing at the first (now-stale) back buffer"
        )
        assert r._lens_blit_wrapper.real is unwrap_to_real(canvas2), (
            "cached blit wrapper's .real must point at the CURRENT real "
            "canvas after every draw() call"
        )
