"""Tests for led_ticker.widgets.weather."""

import unittest.mock as mock

import pytest

from led_ticker.widget import Widget
from led_ticker.widgets.weather import WeatherWidget


@pytest.fixture(autouse=True)
def _set_weather_api_key(monkeypatch):
    monkeypatch.setenv("WEATHERAPI_KEY", "test-key-12345")


@pytest.fixture
def weather_widget():
    """A WeatherWidget with pre-set data (no network needed)."""
    w = WeatherWidget(
        session=mock.Mock(),
        location="40.7,-74.0",
        message="NYC",
    )
    w.current_temp = 72
    w.weather = "Clear"
    return w


class TestWeatherWidget:
    def test_conforms_to_widget_protocol(self, weather_widget):
        assert isinstance(weather_widget, Widget)

    def test_post_init_imperial(self):
        w = WeatherWidget(
            session=mock.Mock(),
            location="New York",
            message="Test",
            units="imperial",
        )
        assert w.unit_symbol == "F"

    def test_post_init_metric(self):
        w = WeatherWidget(
            session=mock.Mock(),
            location="London",
            message="Test",
            units="metric",
        )
        assert w.unit_symbol == "C"

    def test_location_dict_converted_to_string(self):
        """TOML gives location as dict; __attrs_post_init__ converts it."""
        w = WeatherWidget(
            session=mock.Mock(),
            location={"lat": 40.7, "lon": -74.0},
            message="NYC",
        )
        assert w.location == "40.7,-74.0"

    def test_location_string_passthrough(self):
        w = WeatherWidget(
            session=mock.Mock(),
            location="New York",
            message="NYC",
        )
        assert w.location == "New York"

    def test_draw_returns_canvas(self, canvas, weather_widget):
        result_canvas, cursor_pos = weather_widget.draw(canvas)
        assert result_canvas is canvas
        assert cursor_pos > 0

    def test_draw_centered(self, canvas, weather_widget):
        _, cursor_pos = weather_widget.draw(canvas)
        assert cursor_pos == 160

    def test_draw_uncentered(self, canvas):
        w = WeatherWidget(
            session=mock.Mock(),
            location="NYC",
            message="NYC",
            center=False,
        )
        w.current_temp = 72
        w.weather = "Clear"
        _, cursor_pos = w.draw(canvas)
        assert cursor_pos > 0
        assert cursor_pos < 160


def test_weather_bg_color_default_is_none(monkeypatch):
    monkeypatch.setenv("WEATHERAPI_KEY", "test-key")
    from led_ticker.widgets.weather import WeatherWidget

    w = WeatherWidget(session=mock.Mock(), location="London", message="London")
    assert w.bg_color is None


def test_weather_bg_color_accepts_color(monkeypatch):
    monkeypatch.setenv("WEATHERAPI_KEY", "test-key")
    from rgbmatrix.graphics import Color

    from led_ticker.widgets.weather import WeatherWidget

    w = WeatherWidget(
        session=mock.Mock(),
        location="London",
        message="London",
        bg_color=Color(5, 10, 15),
    )
    assert w.bg_color.red == 5


class TestWeatherColorProvider:
    """WeatherWidget materializes Color from font_color (provider) and
    font_color_temp (provider). Both wrap Color into _ConstantColor in
    post_init so draw is uniform."""

    def test_font_color_wrapped_to_constant_provider_in_post_init(self):
        from rgbmatrix.graphics import Color

        from led_ticker.color_providers import _ConstantColor
        from led_ticker.widgets.weather import WeatherWidget

        w = WeatherWidget(
            session=mock.Mock(),
            message="NYC",
            location="NYC",
            font_color=Color(255, 0, 0),
        )
        assert isinstance(w.font_color, _ConstantColor)

    def test_font_color_temp_wrapped_to_constant_provider(self):
        from rgbmatrix.graphics import Color

        from led_ticker.color_providers import _ConstantColor
        from led_ticker.widgets.weather import WeatherWidget

        w = WeatherWidget(
            session=mock.Mock(),
            message="NYC",
            location="NYC",
            font_color_temp=Color(0, 255, 0),
        )
        assert isinstance(w.font_color_temp, _ConstantColor)

    def test_provider_passed_through_unchanged(self):
        from led_ticker.color_providers import Rainbow
        from led_ticker.widgets.weather import WeatherWidget

        provider = Rainbow()
        w = WeatherWidget(
            session=mock.Mock(), message="NYC", location="NYC", font_color=provider
        )
        assert w.font_color is provider

    def test_advance_frame_increments_count(self):
        from led_ticker.widgets.weather import WeatherWidget

        w = WeatherWidget(session=mock.Mock(), message="NYC", location="NYC")
        assert w._frame_count == 0
        w.advance_frame()
        assert w._frame_count == 1


class _TrackingProvider:
    per_char = True

    def __init__(self) -> None:
        self.calls: list[tuple[int, int, int]] = []

    def color_for(self, frame, char_index, total_chars):
        from rgbmatrix.graphics import Color

        self.calls.append((frame, char_index, total_chars))
        return Color(255, 255, 255)


class TestWeatherPerCharProviderDispatch:
    """Tripwire: WeatherWidget renders three text segments (label,
    condition, temp). Per-char providers (Rainbow, Gradient) must
    iterate chars on each segment — not materialize once at idx=0
    which collapses the whole label/temp to a single sweeping hue.

    Mirrors C1/C2 fixes for image widgets and TickerCountdown.
    """

    def test_label_per_char_provider_iterates_chars(self):
        from rgbmatrix import _StubCanvas

        from led_ticker.widgets.weather import WeatherWidget

        provider = _TrackingProvider()
        w = WeatherWidget(
            session=mock.Mock(),
            message="Brooklyn",
            location="Brooklyn",
            font_color=provider,
            show_icon=False,  # also exercises the condition draw branch
        )
        w.current_temp = 64
        w.unit_symbol = "F"
        w.weather = "Sunny"
        canvas = _StubCanvas(width=160, height=16)

        w.draw(canvas)

        # label_text = "Brooklyn: " (10 chars). Without the fix, len = 1
        # call. With the fix, label takes the per-char path → 10 calls
        # for label + N for the condition text "Sunny ". Combined call
        # count must exceed 10.
        assert len(provider.calls) >= 10, (
            f"Expected per-char iteration across label + condition; "
            f"got {len(provider.calls)} call(s). Weather is "
            f"materializing the provider once at char_index=0 instead "
            f"of dispatching to draw_text_per_char."
        )
        char_indices = [c[1] for c in provider.calls]
        assert 0 in char_indices and 1 in char_indices and 2 in char_indices, (
            f"Expected indices to include 0,1,2 for per-char render; "
            f"got {sorted(set(char_indices))[:5]}"
        )

    def test_temp_per_char_provider_iterates_chars(self):
        """font_color_temp is a separate provider for the temperature
        value. Should also dispatch per-char."""
        from rgbmatrix import _StubCanvas

        from led_ticker.widgets.weather import WeatherWidget

        temp_provider = _TrackingProvider()
        w = WeatherWidget(
            session=mock.Mock(),
            message="NYC",
            location="NYC",
            font_color_temp=temp_provider,
        )
        w.current_temp = 64
        w.unit_symbol = "F"
        w.weather = "Sunny"
        canvas = _StubCanvas(width=160, height=16)

        w.draw(canvas)

        # temp_text = "64F" → 3 chars expected. Without fix: 1 call.
        assert len(temp_provider.calls) == 3, (
            f"Expected 3 per-char calls for temp '64F'; got "
            f"{len(temp_provider.calls)}. Temp provider not dispatched "
            f"per-char."
        )
        assert [c[1] for c in temp_provider.calls] == [0, 1, 2]


class TestWeatherWidgetHiresOnScaledCanvas:
    """Tripwire for the weather widget's hires-on-bigsign path.

    Regression: pre-fix, draw_weather_icon called canvas.SetPixel on
    the lowres 8x8 sprite. On a ScaledCanvas at scale=4 the wrapper
    block-expanded each pixel into a 4x4 square — chunky 32x32 output
    instead of using the available 32x32 hires sprite. The fix routes
    icon draw through pixel_emoji.draw_emoji_at so HIRES_REGISTRY
    sprites paint at native resolution to the underlying real canvas.
    """

    def test_draw_uses_hires_sprite_on_scaled_canvas(self, monkeypatch):
        """On a ScaledCanvas (bigsign), the weather widget paints the
        hires sun sprite directly to the real canvas via _draw_hires_emoji
        — bypassing the wrapper's 4x4 block expansion. We assert by
        hooking _draw_hires_emoji and confirming it was called for the
        weather icon."""
        monkeypatch.setenv("WEATHERAPI_KEY", "test-key")
        from rgbmatrix import RGBMatrix, RGBMatrixOptions

        from led_ticker import pixel_emoji
        from led_ticker.scaled_canvas import ScaledCanvas
        from led_ticker.widgets.weather import WeatherWidget

        opts = RGBMatrixOptions()
        opts.cols = 64
        opts.rows = 32
        opts.chain_length = 8
        opts.parallel = 1
        opts.pixel_mapper_config = "U-mapper"
        real = RGBMatrix(options=opts).CreateFrameCanvas()
        sc = ScaledCanvas(real, scale=4)

        calls: list[str] = []
        original = pixel_emoji._draw_hires_emoji

        def spy(canvas, hires, ix, iy):
            calls.append("hires")
            return original(canvas, hires, ix, iy)

        monkeypatch.setattr(pixel_emoji, "_draw_hires_emoji", spy)

        w = WeatherWidget(session=mock.Mock(), location="NYC", message="NYC")
        w.current_temp = 72
        w.weather = "Clear"  # -> "sun" -> SUN_HIRES exists
        w.draw(sc)

        assert calls, (
            "Expected pixel_emoji._draw_hires_emoji to fire for the weather "
            "icon on a ScaledCanvas. The widget is still using the old "
            "lowres-blit path."
        )

    def test_draw_uses_lowres_for_partly_cloudy_on_scaled_canvas(self, monkeypatch):
        """partly_cloudy has no hires variant — ensure the widget takes
        the lowres path (no _draw_hires_emoji call) and doesn't crash.
        Tripwire: if a hires variant is added in a future commit, this
        fires noisily so the addition is acknowledged in the same PR."""
        monkeypatch.setenv("WEATHERAPI_KEY", "test-key")
        from rgbmatrix import RGBMatrix, RGBMatrixOptions

        from led_ticker import pixel_emoji
        from led_ticker.scaled_canvas import ScaledCanvas
        from led_ticker.widgets.weather import WeatherWidget

        opts = RGBMatrixOptions()
        opts.cols = 64
        opts.rows = 32
        opts.chain_length = 8
        opts.parallel = 1
        opts.pixel_mapper_config = "U-mapper"
        real = RGBMatrix(options=opts).CreateFrameCanvas()
        sc = ScaledCanvas(real, scale=4)

        calls: list[str] = []
        original = pixel_emoji._draw_hires_emoji

        def spy(canvas, hires, ix, iy):
            calls.append("hires")
            return original(canvas, hires, ix, iy)

        monkeypatch.setattr(pixel_emoji, "_draw_hires_emoji", spy)

        w = WeatherWidget(session=mock.Mock(), location="NYC", message="NYC")
        w.current_temp = 72
        w.weather = "Partly cloudy"
        result_canvas, cursor_pos = w.draw(sc)
        assert cursor_pos > 0
        assert not calls, (
            "Expected the lowres path. partly_cloudy has no HIRES_REGISTRY "
            "entry, so _draw_hires_emoji should not have fired. If a hires "
            "variant was added, update this test to expect calls."
        )
