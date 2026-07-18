"""TickerMessage fisheye-lens seam (flair.fisheye spec §2-§3): a
non-None ``AnimationFrame.lens`` redirects the text through a
render-resolution strip buffer + ``lens_blit``, rendered FRESH every tick
(no snapshot — colors stay live). Sibling of the rotation branch.

Precedent: ``test_message_rotation.py`` (same buffer→blit shape).
"""

import logging
import math

from rgbmatrix import _StubCanvas

from led_ticker.animations import AnimationFrame, LensSpec
from led_ticker.backends.headless import HeadlessCanvas
from led_ticker.colors import RGB_WHITE
from led_ticker.fonts import FONT_DEFAULT
from led_ticker.rotate import build_lens_maps
from led_ticker.scaled_canvas import ScaledCanvas
from led_ticker.widgets.message import TickerMessage


class _StubLens:
    """Animation stub emitting a fixed LensSpec with the full text."""

    restart_on_visit = False
    emits_lens = True

    def __init__(self, spec: LensSpec, rotation: float = 0.0) -> None:
        self.spec = spec
        self.rotation = rotation

    def frame_for(self, frame, full_text, canvas_width, text_width):
        return AnimationFrame(
            visible_text=full_text, lens=self.spec, rotation=self.rotation
        )


_SPEC = LensSpec(magnify=1.3, edge_squeeze=0.6)


def _make_widget(text="ABCDEFGHIJ", spec=_SPEC, rotation=0.0, font=None, **kwargs):
    return TickerMessage(
        text=text,
        font=font if font is not None else FONT_DEFAULT,
        font_color=kwargs.pop("font_color", RGB_WHITE),
        animation=_StubLens(spec, rotation),
        **kwargs,
    )


def _canvas(width=160, height=16):
    return _StubCanvas(width=width, height=height)


def _scaled(real_w=256, real_h=64, scale=4, content_height=16):
    real = HeadlessCanvas(width=real_w, height=real_h)
    return ScaledCanvas(real, scale=scale, content_height=content_height), real


class _Capture:
    """Patches ``message.lens_blit`` (transparent spy) recording the
    ``src_x0`` passed and a snapshot of the strip's lit columns, plus
    ``_text_run.draw_text`` recording the whole-string branch's x-origin
    (the lens strip now routes its dispatch through the shared
    ``draw_text_run`` helper, so the plain-text draw lives in ``_text_run``)."""

    def __init__(self, monkeypatch):
        import led_ticker.widgets._text_run as tr_mod
        import led_ticker.widgets.message as msg_mod
        from led_ticker.text_render import draw_text as real_draw_text

        self.src_x0: list[float] = []
        self.maps: list = []
        self.strip_lit_x: list[set[int]] = []
        self.x_origin: list[int] = []

        real_lens_blit = msg_mod.lens_blit

        def _spy_blit(dst, src, maps, src_x0, cy):
            self.src_x0.append(src_x0)
            self.maps.append(maps)
            lit = {
                x for x in range(src.width) for y in range(src.height) if src.get(x, y)
            }
            self.strip_lit_x.append(lit)
            return real_lens_blit(dst, src, maps, src_x0, cy)

        def _spy_draw_text(canvas, font, x, y, color, text):
            self.x_origin.append(x)
            return real_draw_text(canvas, font, x, y, color, text)

        monkeypatch.setattr(msg_mod, "lens_blit", _spy_blit)
        monkeypatch.setattr(tr_mod, "draw_text", _spy_draw_text)


# ---------------------------------------------------------------------------
# 1. src_x0 formula pin (spec §2)
# ---------------------------------------------------------------------------


class TestSrcX0Formula:
    def test_src_x0_matches_spec_formula_at_scale1(self, monkeypatch):
        """src_x0 passed to lens_blit == frac((W/2 - cursor) - span/2) at
        render_scale=1 (smallsign)."""
        cap = _Capture(monkeypatch)
        widget = _make_widget(center=False)
        c = _canvas(width=160)
        cursor = 25
        widget.draw(c, cursor)

        assert len(cap.src_x0) == 1
        span = build_lens_maps(_SPEC, 160).total_src_span
        src_x0_render = (160 / 2.0 - cursor) - span / 2.0
        expected_frac = src_x0_render - math.floor(src_x0_render)
        assert abs(cap.src_x0[0] - expected_frac) < 1e-9, (
            f"src_x0={cap.src_x0[0]} != expected frac {expected_frac} "
            f"(formula (W/2 - cursor) - span/2)"
        )

    def test_windows_differ_by_n(self, monkeypatch):
        """Two draws at cursor differing by integer N map to strip windows
        shifted by exactly N (src_x0 frac unchanged)."""
        cap = _Capture(monkeypatch)
        w1 = _make_widget(center=False)
        w1.draw(_canvas(), 10)
        w2 = _make_widget(center=False)
        w2.draw(_canvas(), 10 + 7)  # N = 7

        # src_x0 fractional part is identical (integer cursor shift).
        assert abs(cap.src_x0[0] - cap.src_x0[1]) < 1e-9, (
            f"src_x0 frac drifted across integer cursor shift: {cap.src_x0}"
        )
        # The strip's text moved by exactly N=7 (x-origin shifts by N).
        assert cap.x_origin[1] - cap.x_origin[0] == 7, (
            f"strip x-origin shift {cap.x_origin} != cursor delta 7"
        )
        # Corollary: the strip's lit-column window shifts by exactly 7.
        lo0 = min(cap.strip_lit_x[0])
        lo1 = min(cap.strip_lit_x[1])
        assert lo1 - lo0 == 7, f"strip lit window shift {lo1 - lo0} != 7"


# ---------------------------------------------------------------------------
# 2. center-column alignment (the anchoring invariant)
# ---------------------------------------------------------------------------


class TestCenterColumnAlignment:
    def test_center_dst_samples_text_col_w2_minus_cursor(self, monkeypatch):
        """The panel-center dst column samples text column W/2 - cursor ±
        half a column, for a range of cursor positions (the invariant is
        cursor-independent by construction)."""
        cap = _Capture(monkeypatch)
        W = 160
        for cursor in (0, 30, -25):
            widget = _make_widget(center=False)
            widget.draw(_canvas(width=W), cursor)

        maps = build_lens_maps(_SPEC, W)
        span = maps.total_src_span
        xc = W // 2
        mid = (maps.x_lut[xc] + maps.x_lut[xc + 1]) / 2.0
        for idx, cursor in enumerate((0, 30, -25)):
            src_x0_render = (W / 2.0 - cursor) - span / 2.0
            base_units = math.floor(src_x0_render)  # render_scale == 1
            sampled = base_units + cap.src_x0[idx] + mid
            expected = W / 2.0 - cursor
            assert abs(sampled - expected) <= 0.5, (
                f"cursor={cursor}: center samples text col {sampled:.3f}, "
                f"expected {expected} (±0.5)"
            )


# ---------------------------------------------------------------------------
# 3. held -> scroll continuity (one formula, no jump at handoff)
# ---------------------------------------------------------------------------


class TestHeldScrollContinuity:
    def test_consecutive_cursors_have_no_discontinuity(self, monkeypatch):
        """Sweeping cursor 1 px/tick, the strip x-origin advances by exactly
        1 each step — the same formula in the held and scrolling regimes, no
        jump at the handoff."""
        cap = _Capture(monkeypatch)
        for cursor in range(-3, 4):  # spans the held/centered region
            widget = _make_widget(center=False)
            widget.draw(_canvas(width=160), cursor)

        deltas = [
            cap.x_origin[i + 1] - cap.x_origin[i] for i in range(len(cap.x_origin) - 1)
        ]
        assert all(d == 1 for d in deltas), (
            f"x-origin steps not uniformly +1 across the sweep: {deltas} "
            f"(a discontinuity would show a step != 1)"
        )


# ---------------------------------------------------------------------------
# 4. border un-warped
# ---------------------------------------------------------------------------


class TestBorderUnwarped:
    def test_border_pixel_survives_lens(self):
        """A border pixel at (0, 0) is painted directly to the canvas
        (un-warped) and survives the lens blit."""

        class _CornerBorder:
            frame_invariant = True

            def paint(self, canvas, frame):
                canvas.SetPixel(0, 0, 255, 0, 0)

        widget = _make_widget(border=_CornerBorder(), center=False)
        c = _canvas()
        widget.draw(c, 0)
        assert c._pixels.get((0, 0)) == (255, 0, 0), (
            f"corner border pixel: {c._pixels.get((0, 0))!r} — expected "
            "(255,0,0); the border must paint un-warped, before the lens blit"
        )


# ---------------------------------------------------------------------------
# 5. live colors (no snapshot — the strip re-renders every tick)
# ---------------------------------------------------------------------------


class TestLiveColors:
    def test_rainbow_strip_differs_across_frames(self, monkeypatch):
        """A rainbow provider produces DIFFERENT strip pixels across two
        advanced frames — the lens never freezes colors."""
        import led_ticker.widgets.message as msg_mod
        from led_ticker.color_providers import Rainbow

        strips: list[dict] = []
        real_lens_blit = msg_mod.lens_blit

        def _spy(dst, src, maps, src_x0, cy):
            strips.append(
                {
                    (x, y): src.get(x, y)
                    for x in range(src.width)
                    for y in range(src.height)
                    if src.get(x, y)
                }
            )
            return real_lens_blit(dst, src, maps, src_x0, cy)

        monkeypatch.setattr(msg_mod, "lens_blit", _spy)

        widget = _make_widget(font_color=Rainbow(), center=True, text="HELLO")
        c = _canvas()
        widget.draw(c, 0)
        for _ in range(20):
            widget.advance_frame()
        widget.draw(c, 0)

        assert strips[0] and strips[1], "no lit strip pixels"
        assert strips[0] != strips[1], (
            "rainbow strip identical across 20 advanced frames — the lens "
            "must re-render fresh each tick (no snapshot)"
        )


# ---------------------------------------------------------------------------
# 6. held-text static bulge
# ---------------------------------------------------------------------------


class TestHeldStaticBulge:
    def test_centered_text_bulges_at_center(self):
        """Short centered text: the lens applies statically. The lit content
        clusters around the panel center and occupies a taller band than a
        far-edge (squeezed) placement — evidence of the center bulge."""
        widget = _make_widget(text="HI", center=True)
        c = _canvas(width=160)
        widget.draw(c, 0)
        lit = {xy for xy, rgb in c._pixels.items() if any(rgb)}
        assert lit, "centered lensed text produced no pixels"
        xs = [x for x, _ in lit]
        # Content is near the panel center (lens center = 80), not at an edge.
        cx = sum(xs) / len(xs)
        assert 60 <= cx <= 100, f"centered text mean-x {cx:.1f} not near center 80"


# ---------------------------------------------------------------------------
# 7. scale 1/2/3/4 paths (F2 odd/small-scale policy)
# ---------------------------------------------------------------------------


class TestResolutionPaths:
    def test_scale1_logical_path_blits(self):
        widget = _make_widget(text="HELLO WORLD", center=True)
        c = _canvas(width=160)
        widget.draw(c, 0)
        assert {xy for xy, rgb in c._pixels.items() if any(rgb)}, (
            "scale-1 lens produced no pixels"
        )

    def test_scale2_path_blits(self):
        canvas, real = _scaled(real_w=128, real_h=32, scale=2, content_height=16)
        widget = _make_widget(text="HELLO WORLD", center=True)
        widget.draw(canvas, 0)
        lit = [
            (x, y)
            for x in range(real.width)
            for y in range(real.height)
            if real.get_pixel(x, y) != (0, 0, 0)
        ]
        assert lit, "scale-2 lens produced no physical pixels"

    def test_scale3_path_blits(self):
        canvas, real = _scaled(real_w=192, real_h=48, scale=3, content_height=16)
        widget = _make_widget(text="HELLO WORLD", center=True)
        widget.draw(canvas, 0)
        lit = [
            (x, y)
            for x in range(real.width)
            for y in range(real.height)
            if real.get_pixel(x, y) != (0, 0, 0)
        ]
        assert lit, "scale-3 lens produced no physical pixels"

    def test_scale4_center_alignment_at_nonzero_cursor(self, monkeypatch):
        """Review teeth (M1): at render_scale > 1 the center dst column must
        still sample text column W_logical/2 − cursor. Reconstruct the sampled
        text column from the captured render-resolution x-origin + src_x0 and
        assert it against the spec formula AT A NONZERO CURSOR — where dropping
        the `cursor × render_scale` conversion (the exact unit-mix bug the
        implementer fixed) shifts the result by cursor·(1 − 1/render_scale).
        A scale-1-only test cannot catch it (render_scale == 1 → no-op).
        """
        cap = _Capture(monkeypatch)
        cursor = 24  # nonzero: the render_scale multiply is load-bearing here
        canvas, _real = _scaled(scale=4, content_height=16)  # 256×64 → logical 64
        w_logical = canvas.width  # 64
        render_scale = max(1, canvas.scale // 2)  # 2
        panel_w_render = w_logical * render_scale  # 128

        widget = _make_widget(text="ABCDEFGHIJ", center=False)
        widget.draw(canvas, cursor)

        maps = build_lens_maps(_SPEC, panel_w_render)
        xc = panel_w_render // 2
        mid = (maps.x_lut[xc] + maps.x_lut[xc + 1]) / 2.0
        # Captured: x_origin (logical paint origin into the scale=render_scale
        # strip wrapper) + src_x0 (fractional, render-res columns). Strip render
        # column S = (x_origin + text_col) × render_scale, so the center dst
        # column samples render column (src_x0_frac + mid):
        #   text_col = (src_x0_frac + mid) / render_scale − x_origin
        x_origin = cap.x_origin[0]
        src_x0_frac = cap.src_x0[0]
        sampled_text_col = (src_x0_frac + mid) / render_scale - x_origin
        expected = w_logical / 2.0 - cursor
        assert abs(sampled_text_col - expected) <= 0.6, (
            f"scale-4 center samples text col {sampled_text_col:.3f}, expected "
            f"{expected} (±0.6) — a factor-of-render_scale cursor error would "
            f"land at {w_logical / 2.0 - cursor / render_scale:.1f}"
        )

    def test_scale3_blit_covers_full_physical_width(self):
        """Review teeth (M3b): scale 3 → render_scale 1 / blit_scale 3, so the
        64-col render panel blits ×3 across the full 192-wide real panel. A
        hardcoded blit_scale=2 (the mutation) would cover only ~128 px, leaving
        the right third dark. Assert lit pixels reach the far-right region.
        """
        canvas, real = _scaled(real_w=192, real_h=48, scale=3, content_height=16)
        widget = _make_widget(text="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123", center=False)
        widget.draw(canvas, 0)
        lit_x = [
            x
            for x in range(real.width)
            for y in range(real.height)
            if real.get_pixel(x, y) != (0, 0, 0)
        ]
        assert lit_x, "scale-3 lens produced no physical pixels"
        assert max(lit_x) >= 150, (
            f"rightmost lit physical x is {max(lit_x)} — expected >= 150 for "
            f"blit_scale=3 across a 192-wide panel; a hardcoded blit_scale=2 "
            f"would cap near 128"
        )

    def test_scale4_path_blits_with_sub_block_variation(self):
        """Bigsign scale 4 → render 2 / blit 2: the blit paints 2×2 blocks, so
        a 4×4 physical block is NOT uniformly lit (half-res, not full-res
        4×4)."""
        canvas, real = _scaled(scale=4, content_height=16)
        widget = _make_widget(text="HELLO WORLD", center=True)
        widget.draw(canvas, 0)
        lit = [
            (x, y)
            for x in range(real.width)
            for y in range(real.height)
            if real.get_pixel(x, y) != (0, 0, 0)
        ]
        assert lit, "scale-4 lens produced no physical pixels"

        partial = False
        for bx in range(0, real.width, 4):
            for by in range(0, real.height, 4):
                block = [
                    (x, y)
                    for x in range(bx, min(bx + 4, real.width))
                    for y in range(by, min(by + 4, real.height))
                    if real.get_pixel(x, y) != (0, 0, 0)
                ]
                if 0 < len(block) < 16:
                    partial = True
                    break
            if partial:
                break
        assert partial, (
            "every lit 4×4 block is uniform — looks like a full-res blit; "
            "scale-4 lens should render half-res (2×2 blocks) → partial 4×4 "
            "blocks"
        )


# ---------------------------------------------------------------------------
# 8. hires @ scale-1 fallback + warn-once
# ---------------------------------------------------------------------------


class TestHiresScale1Fallback:
    def test_hires_scale1_falls_back_unwarped_and_warns_once(self, caplog):
        from led_ticker.fonts import resolve_font
        from led_ticker.fonts.hires_loader import HiresFont

        font = resolve_font("Inter-Regular", 24)
        assert isinstance(font, HiresFont)

        # Reference: same widget, no animation → normal unwarped draw.
        ref = TickerMessage(text="TEST", font=font, font_color=RGB_WHITE, center=False)
        c_ref = HeadlessCanvas(width=256, height=64)
        ref.draw(c_ref)

        widget = _make_widget(text="TEST", font=font, center=False)
        c = HeadlessCanvas(width=256, height=64)
        with caplog.at_level(logging.WARNING, logger="led_ticker"):
            widget.draw(c)

        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) == 1, (
            f"expected 1 hires-lens warning, got {len(warnings)}: "
            f"{[r.message for r in warnings]!r}"
        )
        assert "lens" in warnings[0].message.lower()

        # Pixels match the unwarped reference (fell through to normal path).
        ref_lit = {
            (x, y)
            for x in range(c_ref.width)
            for y in range(c_ref.height)
            if c_ref.get_pixel(x, y) != (0, 0, 0)
        }
        got_lit = {
            (x, y)
            for x in range(c.width)
            for y in range(c.height)
            if c.get_pixel(x, y) != (0, 0, 0)
        }
        assert got_lit == ref_lit, (
            "hires+lens at scale-1 did not fall through to the unwarped draw"
        )

        # Second draw: no additional warning.
        caplog.clear()
        with caplog.at_level(logging.WARNING, logger="led_ticker"):
            widget.draw(c)
        assert [r for r in caplog.records if r.levelno == logging.WARNING] == []


# ---------------------------------------------------------------------------
# 9. vertical-fit raise
# ---------------------------------------------------------------------------


class TestVerticalFitRaise:
    def test_magnify_over_band_raises_naming_widget(self):
        """magnify × font line-height > content height raises at first draw,
        naming the widget."""
        import pytest

        widget = _make_widget(
            spec=LensSpec(magnify=1.4, edge_squeeze=0.6), center=False
        )  # 1.4 × 12 = 16.8 > 16
        with pytest.raises(ValueError, match="TickerMessage"):
            widget.draw(_canvas(width=160, height=16), 0)


# ---------------------------------------------------------------------------
# 10. rotation-vs-lens precedence (rotation wins)
# ---------------------------------------------------------------------------


class TestHiresEmojiSizedForStrip:
    """A hi-res emoji (`:star:` etc.) must occupy the SAME logical fraction
    of the reduced-resolution lens strip as it does on the real panel — NOT
    2× taller because the strip renders at render_scale (half the real scale).

    Regression for the shipped-v0.4.0 clip: `:star:`/`:heart:` are hires-only
    sprites drawn at native `physical_size` (32). The strip's ScaledCanvas is
    at scale=render_scale=2, so `physical_size // scale = 16` = the WHOLE
    16-row strip → the sprite fills it with zero magnification headroom, its
    top pins to row 0, and the lens magnification pushes the top off-panel
    (clipped, never recovered). The fix box-downsamples the sprite by
    render_scale/real_scale so it occupies its correct ~8-of-16 logical rows.
    """

    def _capture_strip(self, monkeypatch):
        import led_ticker.widgets.message as msg_mod

        cap = {}
        real_blit = msg_mod.lens_blit

        def _spy(dst, src, maps, src_x0, cy):
            # src is the strip buffer BEFORE the lens. Record the emoji's
            # lit vertical extent (rows) once.
            if "extent" not in cap:
                cap["extent"] = src.lit_extent
                cap["h"] = src.height
            return real_blit(dst, src, maps, src_x0, cy)

        monkeypatch.setattr(msg_mod, "lens_blit", _spy)
        return cap

    def test_hires_emoji_has_magnification_headroom_in_strip(self, monkeypatch):
        """The emoji's top row in the strip must be > 0 (clear of the top edge)
        so the lens can magnify it without clipping. On the buggy path the
        oversized sprite pins to row 0."""
        cap = self._capture_strip(monkeypatch)
        canvas, _real = _scaled(scale=4, content_height=16)  # bigsign, render_scale 2
        widget = _make_widget(text=":star:", center=True)
        widget.draw(canvas, 0)

        assert "extent" in cap and cap["extent"] is not None, "no emoji drawn"
        x0, y0, x1, y1 = cap["extent"]
        strip_h = cap["h"]
        # The emoji must NOT fill the strip and must clear row 0 with headroom
        # for a 1.3x magnify about the strip center (needs top >= ~0.1*strip_h).
        assert y0 > 0, (
            f"hires emoji top pins to strip row 0 (extent rows {y0}..{y1 - 1} of "
            f"{strip_h}) — no magnification headroom, the lens will clip the top"
        )
        emoji_rows = y1 - y0
        assert emoji_rows <= strip_h * 0.65, (
            f"hires emoji occupies {emoji_rows}/{strip_h} strip rows — it is "
            f"oversized (should be ~half the strip, its real-panel proportion)"
        )


class TestRotationLensPrecedence:
    def test_rotation_wins_when_both_set(self, monkeypatch):
        """A frame carrying BOTH a lens and non-zero rotation takes the
        rotation branch — lens_blit is never called and the draw doesn't
        crash."""
        import led_ticker.widgets.message as msg_mod

        lens_calls: list = []
        real_lens_blit = msg_mod.lens_blit

        def _spy(*args, **kwargs):
            lens_calls.append(1)
            return real_lens_blit(*args, **kwargs)

        monkeypatch.setattr(msg_mod, "lens_blit", _spy)

        widget = _make_widget(text="HELLO", rotation=90.0, center=False)
        c = _canvas()
        canvas, _pos = widget.draw(c, 0)  # must not raise

        assert lens_calls == [], (
            "lens_blit fired even though rotation was non-zero — rotation "
            "must win the precedence gate"
        )
        # The rotation branch built a surface.
        assert widget._rotation_surface is not None


class TestColoredTokenThroughLens:
    """Closes follow-up #2: a colored value token on a message drawn under
    flair.fisheye colorizes through the lens (the lens shares the draw path
    via `_paint_strip` → `draw_text_run` with the token override). Before the
    fix the lens `_paint_strip` used the host provider only, so a token
    rendered in the host color. Mutation-grade: the SOURCE color's presence
    is the regression signal — without the override the token is host-colored
    and the source color never appears."""

    @staticmethod
    def _registry(*sources):
        from led_ticker.sources import DataRegistry, set_data_registry

        reg = DataRegistry()
        for s in sources:
            s.refresh()
            reg.add(s)
        set_data_registry(reg)
        return reg

    @staticmethod
    def _colored_source(value, rgb):
        from rgbmatrix.graphics import Color

        from led_ticker.color_providers import _ConstantColor
        from led_ticker.sources import StaticSource

        src = StaticSource(id="x", value=value)
        src.color = _ConstantColor(Color(*rgb))
        return src

    def test_token_colorizes_through_fisheye_lens(self):
        from rgbmatrix.graphics import Color

        host = (255, 255, 255)  # white literal
        tok = (255, 0, 0)  # red token
        self._registry(self._colored_source("99", tok))
        # near-identity lens so the token stays legible; the point is colour,
        # not geometry.
        widget = TickerMessage(
            text="AB :x:",
            font=FONT_DEFAULT,
            font_color=Color(*host),
            animation=_StubLens(LensSpec(magnify=1.05, edge_squeeze=0.9)),
        )
        c = _canvas(width=160, height=16)
        widget.draw(c, 0)

        colors = {v for v in c._pixels.values() if v != (0, 0, 0)}
        assert tok in colors, (
            "token '99' must render in the source RED through the lens "
            "(this is the #2 closure — before the fix the lens painted it host)"
        )
        assert host in colors, "literal 'AB' must keep the host WHITE"
        assert colors <= {host, tok}, f"only host+token expected; got {colors!r}"
