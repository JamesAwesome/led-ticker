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
