"""Typewriter reveals a renderable emoji as ONE keystroke.

Regression: the reveal sliced the raw string, so ``:jack_o_lantern:``
typed out as literal ``:jack_o_lan…`` text (a half-typed slug isn't a
renderable token) and only snapped to the sprite once the closing colon
landed. A renderable ``:slug:`` (and each Unicode-emoji run) is now one
reveal unit; a NON-renderable ``:nope:`` still types char by char,
matching how it renders (as literal text).
"""

import math
import textwrap
from pathlib import Path

import pytest

from led_ticker.animations import Typewriter, animation_total_chars
from led_ticker.pixel_emoji import _parse_segments
from led_ticker.validate import validate_config


def _reveals(text: str) -> list[str]:
    """Every distinct visible_text over a full reveal at 1 frame/char."""
    tw = Typewriter(frames_per_char=1)
    out: list[str] = []
    for frame in range(len(text) + 2):
        v = tw.frame_for(frame, text, 256, 0).visible_text
        if not out or out[-1] != v:
            out.append(v)
    return out


class TestRevealUnits:
    def test_curated_slug_is_one_keystroke(self) -> None:
        assert _reveals(":moon: HI") == [":moon:", ":moon: ", ":moon: H", ":moon: HI"]

    def test_pack_slug_never_shows_partial_token(self) -> None:
        text = ":jack_o_lantern: HAPPY HALLOWEEN :jack_o_lantern:"
        for visible in _reveals(text):
            # Every revealed prefix parses with no literal-colon slug debris.
            for seg_type, value in _parse_segments(visible):
                if seg_type == "text":
                    assert ":jack" not in value, visible

    def test_unrenderable_slug_types_char_by_char(self) -> None:
        # Renders as literal text, so it types as literal text.
        assert _reveals(":nope:")[:3] == [":", ":n", ":no"]

    def test_unicode_emoji_with_modifier_is_atomic(self) -> None:
        # 👍🏽 is two codepoints; slicing between them would draw a bare 👍.
        assert _reveals("A👍🏽B") == ["A", "A👍🏽", "A👍🏽B"]

    def test_plain_text_unchanged(self) -> None:
        assert _reveals("ABC") == ["A", "AB", "ABC"]

    def test_chars_per_frame_counts_units(self) -> None:
        tw = Typewriter(chars_per_frame=2, frames_per_char=1)
        assert tw.frame_for(0, ":moon:AB", 256, 0).visible_text == ":moon:A"


class TestUnitCount:
    def test_counts_emoji_as_one(self) -> None:
        tw = Typewriter()
        assert animation_total_chars(tw, ":moon: HI") == 4
        assert animation_total_chars(tw, ":jack_o_lantern: HI") == 4
        assert animation_total_chars(tw, "A👍🏽B") == 3
        assert animation_total_chars(tw, ":nope:") == 6

    def test_non_typewriter_falls_back_to_raw_len(self) -> None:
        assert animation_total_chars(object(), ":moon: HI") == len(":moon: HI")

    def test_done_frame_matches_full_reveal(self) -> None:
        """frames_to_rest's 'done' frame is exactly the first frame
        frame_for shows the full text — for emoji text too."""
        tw = Typewriter(frames_per_char=3)
        text = ":jack_o_lantern: BOO :ghost:"
        total = animation_total_chars(tw, text)
        done = 3 * (math.ceil(total / 1) - 1)
        assert tw.frames_to_rest(done, total) == 0
        assert tw.frames_to_rest(done - 1, total) == 1
        assert tw.frame_for(done, text, 256, 0).visible_text == text
        assert tw.frame_for(done - 1, text, 256, 0).visible_text != text


class TestWidgetSettleCount:
    def test_message_animation_count_is_units(self) -> None:
        from led_ticker.widgets.message import TickerMessage

        w = TickerMessage(text=":moon: HI", animation=Typewriter())
        assert w._effect_total_chars("animation") == 4

    def test_default_animation_count_is_units(self) -> None:
        """Image widgets ride FrameAwareBase's default count."""
        import attrs

        from led_ticker.widgets._frame_aware import FrameAwareBase

        @attrs.define
        class _W(FrameAwareBase):
            text: str = ":moon: HI"
            animation: Typewriter = attrs.Factory(Typewriter)

        assert _W()._effect_total_chars("animation") == 4


_SLUG_TEXT = ":jack_o_lantern: HI :jack_o_lantern:"  # 36 raw chars, 5 units


@pytest.mark.parametrize(("hold", "fires"), [(3.0, False), (0.5, True)])
async def test_rule61_counts_emoji_as_one(
    tmp_path: Path, hold: float, fires: bool
) -> None:
    """Raw count: 36 chars -> 5.25 s (would fire at 3.0). Units: 5 -> 0.6 s."""
    p = tmp_path / "config.toml"
    p.write_text(
        textwrap.dedent(f"""\
            [display]
            rows = 32
            cols = 64
            chain_length = 8
            default_scale = 1

            [[playlist.section]]
            mode = "slideshow"
            hold_time = {hold}

            [[playlist.section.widget]]
            type = "message"
            text = "{_SLUG_TEXT}"
            animation = "typewriter"
        """)
    )
    result = await validate_config(p)
    assert bool([w for w in result.warnings if w.rule == 61]) is fires


class TestArgValidation:
    """A non-positive step crashed draw() (IndexError) or froze/instant-
    revealed — reject it at construction (= config-load error)."""

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"chars_per_frame": 0},
            {"chars_per_frame": -1},
            {"frames_per_char": 0},
            {"frames_per_char": -3},
            {"chars_per_frame": True},
            {"frames_per_char": 1.5},
        ],
    )
    def test_rejects_non_positive_int(self, kwargs) -> None:
        with pytest.raises(ValueError, match="positive integer"):
            Typewriter(**kwargs)

    async def test_validate_reports_bad_step(self, tmp_path: Path) -> None:
        p = tmp_path / "config.toml"
        p.write_text(
            textwrap.dedent("""\
                [display]
                rows = 16
                cols = 32
                chain_length = 5

                [[playlist.section]]
                mode = "slideshow"

                [[playlist.section.widget]]
                type = "message"
                text = "HELLO"
                animation = {style = "typewriter", chars_per_frame = -1}
            """)
        )
        result = await validate_config(p)
        assert any("chars_per_frame" in e.message for e in result.errors), result.errors


class TestWidgetEmojiGate:
    """Reveal units follow the WIDGET's own emoji gate. message / image
    single-row branch on the raw template's emoji cache, so a token whose
    resolved value looks like a slug draws as LITERAL text — and must
    type as literal text, one char per keystroke."""

    @staticmethod
    def _token_registry(value: str) -> None:
        from led_ticker.sources import DataRegistry, StaticSource, set_data_registry

        reg = DataRegistry()
        src = StaticSource(id="x", value=value)
        src.refresh()
        reg.add(src)
        set_data_registry(reg)

    def test_message_token_value_slug_types_per_char(self) -> None:
        from led_ticker.widgets.message import TickerMessage

        self._token_registry(":taco:9")
        w = TickerMessage(
            text="Lunch :x:", animation=Typewriter(frames_per_char=1), center=False
        )
        assert w._has_emoji is False
        full = w._resolve_into_full_text()
        assert full == "Lunch :taco:9"
        tw = w.animation
        assert isinstance(tw, Typewriter)
        assert tw.frame_for(6, full, 160, 0, inline_emoji=False).visible_text == (
            "Lunch :"
        )
        assert w._effect_total_chars("animation") == len(full)

    def test_message_draw_reveals_token_value_per_char(self) -> None:
        """The draw path itself reaches the gate (not just the count)."""
        from rgbmatrix import _StubCanvas

        from led_ticker.widgets.message import TickerMessage

        self._token_registry(":taco:9")
        seen: list[str] = []

        class _Spy(Typewriter):
            def frame_for(self, *a, **kw):
                f = super().frame_for(*a, **kw)
                seen.append(f.visible_text)
                return f

        w = TickerMessage(
            text="Lunch :x:", animation=_Spy(frames_per_char=1), center=False
        )
        w._frame_count = 6
        w.draw(_StubCanvas(width=160, height=16))
        assert seen[-1] == "Lunch :"

    def test_image_settle_count_uses_resolved_text_and_gate(self, tmp_path) -> None:
        from PIL import Image

        from led_ticker.widgets.still import StillImage

        img = tmp_path / "x.png"
        Image.new("RGB", (4, 4), (255, 0, 0)).save(img)
        w = StillImage(
            path=img, text=":moon: HI", text_align="left", animation=Typewriter()
        )
        assert w._effect_total_chars("animation") == 4

        self._token_registry(":taco:9")
        w2 = StillImage(
            path=img, text="Lunch :x:", text_align="left", animation=Typewriter()
        )
        w2._resolve_overlay_text(locked=False)
        assert w2._resolved_text_single == "Lunch :taco:9"
        assert w2._has_emoji() is False
        # Per-char over the RESOLVED text (not the 9-char raw template).
        assert w2._effect_total_chars("animation") == len("Lunch :taco:9")


class _CountingAnim:
    """Plugin-style animation that declares count_units."""

    restart_on_visit = True

    def __init__(self) -> None:
        pass

    def frame_for(self, frame, full_text, canvas_width, text_width):
        from led_ticker.animations import AnimationFrame

        return AnimationFrame(visible_text=full_text)

    def count_units(self, text: str) -> int:
        return 100

    def frames_to_rest(self, frame: int, total_chars: int) -> int:
        return total_chars  # 1 frame per unit → 100 units = 5.0 s


async def test_rule62_routes_through_count_units(tmp_path: Path) -> None:
    from led_ticker.animations import _ANIMATION_REGISTRY

    _ANIMATION_REGISTRY["teststub.counting"] = _CountingAnim
    try:
        p = tmp_path / "config.toml"
        p.write_text(
            textwrap.dedent("""\
                [display]
                rows = 16
                cols = 32
                chain_length = 5

                [[playlist.section]]
                mode = "slideshow"
                hold_time = 3.0

                [[playlist.section.widget]]
                type = "message"
                text = "HI"
                animation = {style = "teststub.counting"}
            """)
        )
        result = await validate_config(p)
        issues = [w for w in result.warnings if w.rule == 62]
        # raw len("HI") = 2 → 0.1 s (no fire); count_units 100 → 5.0 s (fires)
        assert len(issues) == 1 and "~5.0" in issues[0].message, result.warnings
    finally:
        del _ANIMATION_REGISTRY["teststub.counting"]
