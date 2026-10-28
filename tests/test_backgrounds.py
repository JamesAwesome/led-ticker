"""`background = ...` — a full-panel effect painted BEHIND a widget's content.

Sibling of `border` (same shape, same effect-counter / fast-path contract),
painted before it. Core ships no built-in styles; plugins register them via
`api.background(name)`.
Design: docs/superpowers/specs/2026-10-28-background-effects-design.md
"""

from typing import Any
from unittest import mock

import attrs
import pytest

from led_ticker.backgrounds import (
    _BACKGROUND_REGISTRY,
    BackgroundEffect,
    BackgroundEffectBase,
)


class _Recorder(BackgroundEffectBase):
    """Background that logs (canvas, frame) per paint and stamps one pixel."""

    frame_invariant = False
    restart_on_visit = False

    def __init__(self, density: int = 1) -> None:
        self.kwargs = {"density": density}
        self.calls: list[tuple[Any, int]] = []

    def paint(self, canvas: Any, frame_count: int) -> None:
        self.calls.append((canvas, frame_count))
        canvas.SetPixel(0, 0, 1, 2, 3)


class _StaticRecorder(_Recorder):
    frame_invariant = True


@attrs.define
class _PlainWidget:
    """A registered widget WITHOUT a `background` field — the gate target.
    (Every core widget is a host now, so the non-host case needs a fake.)"""

    text: str = ""

    def draw(self, canvas: Any, cursor_pos: int = 0, **kw: Any) -> tuple[Any, int]:
        return canvas, cursor_pos


@pytest.fixture
def registered(monkeypatch):
    from led_ticker.widgets import _WIDGET_REGISTRY

    monkeypatch.setitem(_BACKGROUND_REGISTRY, "acme.stars", _Recorder)
    monkeypatch.setitem(_BACKGROUND_REGISTRY, "acme.static", _StaticRecorder)
    monkeypatch.setitem(_WIDGET_REGISTRY, "acme.plain", _PlainWidget)
    yield


# ---------------------------------------------------------------------------
# Protocol / base
# ---------------------------------------------------------------------------


class TestProtocol:
    def test_registry_starts_empty_in_core(self) -> None:
        assert _BACKGROUND_REGISTRY == {}

    def test_base_enforces_frame_invariant(self) -> None:
        with pytest.raises(TypeError, match="frame_invariant"):

            class Bad(BackgroundEffectBase):  # noqa: F841
                def paint(self, canvas: Any, frame_count: int) -> None: ...

    def test_recorder_satisfies_protocol(self) -> None:
        fx: BackgroundEffect = _Recorder()
        assert fx.frame_invariant is False


# ---------------------------------------------------------------------------
# Plugin surface
# ---------------------------------------------------------------------------


class TestPluginSurface:
    def test_api_background_commits_to_registry(self) -> None:
        from led_ticker import _plugin_loader as L
        from led_ticker.plugin import PluginAPI

        api = PluginAPI(namespace="acme")
        api.background("stars")(_Recorder)
        assert L._REGISTRY_MAP["backgrounds"] is _BACKGROUND_REGISTRY
        L._commit(api, L.PluginInfo(namespace="acme", source="test"))
        try:
            assert _BACKGROUND_REGISTRY["acme.stars"] is _Recorder
        finally:
            _BACKGROUND_REGISTRY.pop("acme.stars", None)

    def test_exported_from_public_surface(self) -> None:
        from led_ticker import plugin

        assert plugin.BackgroundEffect is BackgroundEffect
        assert plugin.BackgroundEffectBase is BackgroundEffectBase
        assert "BackgroundEffect" in plugin.__all__
        assert "BackgroundEffectBase" in plugin.__all__

    def test_catalog_knows_the_surface(self) -> None:
        from led_ticker.plugins_catalog import _SURFACE_KINDS, PluginProvides

        assert "backgrounds" in _SURFACE_KINDS
        assert PluginProvides(backgrounds=("acme.stars",)).all_names() == (
            "acme.stars",
        )


# ---------------------------------------------------------------------------
# Coercion
# ---------------------------------------------------------------------------


class TestCoercion:
    def test_none_passthrough(self) -> None:
        from led_ticker.app.coercion import _coerce_background

        assert _coerce_background(None) is None

    def test_instance_passthrough(self) -> None:
        from led_ticker.app.coercion import _coerce_background

        fx = _Recorder()
        assert _coerce_background(fx) is fx

    def test_string_shorthand_resolves_registry(self, registered) -> None:
        from led_ticker.app.coercion import _coerce_background

        assert isinstance(_coerce_background("acme.stars"), _Recorder)

    def test_inline_table_passes_kwargs(self, registered) -> None:
        from led_ticker.app.coercion import _coerce_background

        fx = _coerce_background({"style": "acme.stars", "density": 3})
        assert isinstance(fx, _Recorder)
        assert fx.kwargs == {"density": 3}

    def test_unknown_style_is_config_error_with_plugin_hint(self) -> None:
        from led_ticker.app.coercion import _coerce_background

        with pytest.raises(ValueError, match="unknown background style") as ei:
            _coerce_background("nope.thing")
        assert "plugin" in str(ei.value)

    def test_table_without_style_is_config_error(self) -> None:
        from led_ticker.app.coercion import _coerce_background

        with pytest.raises(ValueError, match="style"):
            _coerce_background({"density": 3})

    def test_bad_type_is_config_error(self) -> None:
        from led_ticker.app.coercion import _coerce_background

        with pytest.raises(ValueError, match="background"):
            _coerce_background(42)


# ---------------------------------------------------------------------------
# Config-load gate (factories)
# ---------------------------------------------------------------------------


_HOSTS = ["message", "countdown", "countup", "two_row", "gif", "image", "clock"]


class TestFactoryGate:
    def test_dispatch_types_match_border(self) -> None:
        from led_ticker.app.factories import _DISPATCH_APPLICABLE_TYPES, FIELD_HINTS

        assert (
            _DISPATCH_APPLICABLE_TYPES["background"]
            == (_DISPATCH_APPLICABLE_TYPES["border"])
        )
        assert "background" in FIELD_HINTS

    @pytest.mark.asyncio
    async def test_rejected_on_data_widget(self, registered) -> None:
        from led_ticker.app.factories import validate_widget_cfg

        cfg = {"type": "acme.plain", "text": "x", "background": "acme.stars"}
        with pytest.raises(ValueError, match="background is only valid on"):
            await validate_widget_cfg(cfg, session=None)

    @pytest.mark.asyncio
    async def test_accepted_on_message(self, registered) -> None:
        from led_ticker.app.factories import validate_widget_cfg

        cfg = {"type": "message", "text": "hi", "background": "acme.stars"}
        await validate_widget_cfg(cfg, session=None)
        assert isinstance(cfg["background"], _Recorder)

    @pytest.mark.asyncio
    async def test_validate_rule_number(self, registered, tmp_path) -> None:
        import textwrap

        from led_ticker.validate import validate_config

        p = tmp_path / "c.toml"
        p.write_text(
            textwrap.dedent("""\
            [display]
            rows = 16
            cols = 32
            chain_length = 5

            [[playlist.section]]
            name = "s"
            [[playlist.section.widget]]
            type = "acme.plain"
            text = "x"
            background = "acme.stars"
            """)
        )
        result = await validate_config(p)
        assert not result.valid
        assert any(e.rule == 72 for e in result.errors)

    def test_frame_aware_has_counter(self) -> None:
        from led_ticker.widgets._frame_aware import FrameAwareBase

        assert "background" in FrameAwareBase._EFFECT_ATTRS

    @pytest.mark.parametrize("wtype", _HOSTS)
    def test_every_border_host_declares_background(self, wtype: str) -> None:
        from led_ticker.widgets import get_widget_class

        cls = get_widget_class(wtype)
        names = {a.name for a in attrs.fields(cls)}
        assert "border" in names and "background" in names


# ---------------------------------------------------------------------------
# Paint order
# ---------------------------------------------------------------------------


class _OrderCanvas:
    """Canvas stub that records a label per paint call via SetPixel color."""

    width = 160
    height = 16

    def __init__(self) -> None:
        self.events: list[str] = []
        self.real = self

    def SetPixel(self, x: int, y: int, r: int, g: int, b: int) -> None:  # noqa: N802
        self.events.append(
            {(1, 2, 3): "background", (9, 9, 9): "border"}.get((r, g, b), "text")
        )

    def Clear(self) -> None:  # noqa: N802
        self.events.append("clear")

    def Fill(self, r: int, g: int, b: int) -> None:  # noqa: N802
        self.events.append("fill")


class _StampBorder:
    frame_invariant = True

    def paint(self, canvas: Any, frame_count: int) -> None:
        canvas.SetPixel(0, 0, 9, 9, 9)


def _first_index(events: list[str], label: str) -> int:
    return events.index(label)


class TestPaintOrderTextWidgets:
    @pytest.mark.parametrize(
        "make",
        [
            lambda: __import__(
                "led_ticker.widgets.message", fromlist=["TickerMessage"]
            ).TickerMessage(text="HI"),
            lambda: __import__(
                "led_ticker.widgets.two_row", fromlist=["TwoRowMessage"]
            ).TwoRowMessage(top_text="A", bottom_text="B"),
            lambda: __import__("led_ticker.widgets.clock", fromlist=["Clock"]).Clock(),
        ],
        ids=["message", "two_row", "clock"],
    )
    def test_background_then_border_then_text(self, make) -> None:
        widget = make()
        bg = _Recorder()
        widget.background = bg
        widget.border = _StampBorder()
        canvas = _OrderCanvas()
        widget.advance_frame()
        widget.draw(canvas, 0)
        ev = canvas.events
        assert "background" in ev and "border" in ev and "text" in ev
        assert (
            _first_index(ev, "background")
            < _first_index(ev, "border")
            < _first_index(ev, "text")
        )
        # Painted with the per-effect counter, not the raw frame count.
        assert bg.calls[0][1] == widget.frame_for("background")

    def test_countdown_background_before_text(self) -> None:
        import datetime

        from led_ticker.widgets.count import TickerCountdown

        target = (datetime.date.today() + datetime.timedelta(days=3)).isoformat()
        widget = TickerCountdown(text="XMAS", countdown_date=target)
        widget.background = _Recorder()
        widget.border = _StampBorder()
        canvas = _OrderCanvas()
        widget.draw(canvas, 0)
        ev = canvas.events
        assert (
            _first_index(ev, "background")
            < _first_index(ev, "border")
            < _first_index(ev, "text")
        )


class TestPaintOrderImageWidgets:
    @pytest.fixture
    def img(self, tmp_path):
        from PIL import Image

        p = tmp_path / "x.png"
        Image.new("RGB", (4, 4), (200, 0, 0)).save(p)
        return p

    async def test_still_no_text_background_under_image(self, img, mock_frame) -> None:
        from led_ticker.widgets.still import StillImage

        still = StillImage(path=img, hold_time=0.1)
        bg = _Recorder()
        still.background = bg
        canvas = mock_frame.swap.return_value
        with (
            mock.patch.object(StillImage, "_paint_image") as paint_image,
            mock.patch("asyncio.sleep", new=mock.AsyncMock()),
        ):
            manager = mock.Mock()
            manager.attach_mock(paint_image, "image")
            bg_mock = mock.Mock(side_effect=bg.paint)
            manager.attach_mock(bg_mock, "background")
            still.background = mock.Mock(frame_invariant=False, paint=bg_mock)
            await still._play_no_text(canvas, mock_frame)
        names = [c[0] for c in manager.mock_calls]
        assert "background" in names and "image" in names
        assert names.index("background") < names.index("image")

    async def test_still_animated_background_forces_slow_path(
        self, img, mock_frame
    ) -> None:
        from led_ticker.widgets.still import StillImage

        still = StillImage(path=img, hold_time=0.5)
        still.background = _Recorder()  # frame_invariant=False
        with mock.patch("asyncio.sleep", new=mock.AsyncMock()) as slp:
            await still._play_no_text(mock_frame.swap.return_value, mock_frame)
        assert mock_frame.swap.call_count > 1
        assert slp.call_count > 1

    async def test_still_static_background_keeps_fast_path(
        self, img, mock_frame
    ) -> None:
        from led_ticker.widgets.still import StillImage

        still = StillImage(path=img, hold_time=0.5)
        still.background = _StaticRecorder()
        with mock.patch("asyncio.sleep", new=mock.AsyncMock()) as slp:
            await still._play_no_text(mock_frame.swap.return_value, mock_frame)
        assert mock_frame.swap.call_count == 1
        assert slp.call_count == 1

    async def test_text_overlay_animated_background_forces_per_tick(
        self, img, mock_frame
    ) -> None:
        from led_ticker.widgets.still import StillImage

        still = StillImage(path=img, text="HI", text_align="left", hold_time=0.5)
        still.background = _Recorder()
        with (
            mock.patch.object(StillImage, "_render_tick") as render,
            mock.patch("asyncio.sleep", new=mock.AsyncMock()),
        ):
            await still._play_with_text(
                mock_frame.swap.return_value, mock_frame, n_ticks=10
            )
        assert render.call_count == 10

    async def test_text_overlay_background_painted_before_image(
        self, img, mock_frame
    ) -> None:
        from led_ticker.widgets.still import StillImage

        still = StillImage(path=img, text="HI", text_align="left", hold_time=0.1)
        manager = mock.Mock()
        bg = mock.Mock(frame_invariant=False)
        manager.attach_mock(bg.paint, "background")
        still.background = bg
        with (
            mock.patch.object(StillImage, "_paint_image") as paint_image,
            mock.patch("asyncio.sleep", new=mock.AsyncMock()),
        ):
            manager.attach_mock(paint_image, "image")
            await still._play_with_text(
                mock_frame.swap.return_value, mock_frame, n_ticks=2
            )
        names = [c[0] for c in manager.mock_calls]
        assert names[:2] == ["background", "image"]

    async def test_two_row_overlay_background_painted_before_image(
        self, img, mock_frame
    ) -> None:
        from led_ticker.fonts import FONT_SMALL
        from led_ticker.widgets.still import StillImage

        still = StillImage(
            path=img, top_text="@", bottom_text="x", font=FONT_SMALL, hold_time=0.1
        )
        manager = mock.Mock()
        bg = mock.Mock(frame_invariant=False)
        manager.attach_mock(bg.paint, "background")
        still.background = bg
        with (
            mock.patch.object(StillImage, "_paint_image") as paint_image,
            mock.patch("asyncio.sleep", new=mock.AsyncMock()),
        ):
            manager.attach_mock(paint_image, "image")
            await still._play_with_two_row_text(
                mock_frame.swap.return_value, mock_frame, n_ticks=2
            )
        names = [c[0] for c in manager.mock_calls]
        assert names[:2] == ["background", "image"]

    async def test_gif_no_text_background_before_image(
        self, tmp_path, mock_frame
    ) -> None:
        from PIL import Image

        from led_ticker.widgets.gif import GifPlayer

        p = tmp_path / "a.gif"
        frames = [Image.new("RGB", (4, 4), c) for c in [(255, 0, 0), (0, 255, 0)]]
        frames[0].save(p, save_all=True, append_images=frames[1:], duration=100, loop=0)
        gif = GifPlayer(path=p, play_count=1)
        manager = mock.Mock()
        bg = mock.Mock(frame_invariant=False)
        manager.attach_mock(bg.paint, "background")
        gif.background = bg
        with (
            mock.patch.object(GifPlayer, "_paint_image") as paint_image,
            mock.patch("asyncio.sleep", new=mock.AsyncMock()),
        ):
            manager.attach_mock(paint_image, "image")
            await gif._play_no_text(mock_frame.swap.return_value, mock_frame, 1)
        names = [c[0] for c in manager.mock_calls]
        assert names[:2] == ["background", "image"]
