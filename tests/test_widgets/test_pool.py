import unittest.mock as mock

import pytest

from led_ticker.colors import BLUE, GREEN, ORANGE, RED
from led_ticker.widget import Widget
from led_ticker.widgets.message import SegmentMessage
from led_ticker.widgets.pool import (
    DIM,
    PoolMonitor,
    _build_flux,
    _c_to_display,
    _fmt_temp,
    _parse_scalar_csv,
    _trend_arrow,
    _zone_color,
)


class TestZoneColor:
    @pytest.mark.parametrize(
        "f,expected",
        [
            (60.0, BLUE),
            (69.9, BLUE),
            (70.0, GREEN),
            (79.9, GREEN),
            (80.0, ORANGE),
            (89.9, ORANGE),
            (90.0, RED),
            (95.0, RED),
        ],
    )
    def test_zones(self, f, expected):
        assert _zone_color(f) is expected


class TestTrendArrow:
    def test_up_when_above_deadband(self):
        glyph, _ = _trend_arrow(now_f=82.0, past_f=81.0, ascii_only=True)
        assert glyph == "^"

    def test_down_when_below_deadband(self):
        glyph, _ = _trend_arrow(now_f=80.0, past_f=81.0, ascii_only=True)
        assert glyph == "v"

    def test_steady_within_deadband(self):
        glyph, _ = _trend_arrow(now_f=81.2, past_f=81.0, ascii_only=True)
        assert glyph == "-"

    def test_steady_when_past_missing(self):
        glyph, _ = _trend_arrow(now_f=81.0, past_f=None, ascii_only=True)
        assert glyph == "-"


class TestUnits:
    def test_c_to_fahrenheit(self):
        assert _c_to_display(25.0, "imperial") == pytest.approx(77.0)

    def test_c_to_metric_passthrough(self):
        assert _c_to_display(25.0, "metric") == pytest.approx(25.0)

    def test_fmt_temp_rounds_and_suffixes(self):
        # No degree symbol — hires Inter at small font_size drops U+00B0
        # to '?'. Consistent with the weather widget's bare 'F'/'C'.
        assert _fmt_temp(81.6, "imperial") == "82F"
        assert _fmt_temp(25.4, "metric") == "25C"


SAMPLE_CSV = (
    "#datatype,string,long,dateTime:RFC3339,double,string,string\r\n"
    ",result,table,_time,_value,_field,_measurement\r\n"
    ",_result,0,2026-05-27T15:00:00Z,27.5,temperature_C,mqtt_consumer\r\n"
    "\r\n"
)

EMPTY_CSV = "\r\n"


class TestParseScalarCsv:
    def test_parses_value_and_time(self):
        value, ts = _parse_scalar_csv(SAMPLE_CSV)
        assert value == pytest.approx(27.5)
        assert ts == "2026-05-27T15:00:00Z"

    def test_empty_returns_none(self):
        assert _parse_scalar_csv(EMPTY_CSV) == (None, None)


class TestBuildFlux:
    def test_includes_bucket_field_and_filter(self):
        flux = _build_flux(
            bucket="pool_temps",
            sensor_id="123",
            range_start="-7d",
            agg="mean",
        )
        assert 'from(bucket: "pool_temps")' in flux
        assert 'r._field == "temperature_C"' in flux
        assert 'r.id == "123"' in flux
        assert "|> mean()" in flux
        assert "range(start: -7d)" in flux

    def test_omits_sensor_filter_when_none(self):
        flux = _build_flux(
            bucket="pool_temps",
            sensor_id=None,
            range_start="-1h",
            agg="last",
        )
        assert "r.id ==" not in flux
        assert "|> last()" in flux

    def test_inserts_group_before_aggregation(self):
        """`group()` must precede the aggregation step so a multi-sensor
        bucket returns a single GLOBAL aggregate row, not one per series.
        Without this, the CSV parser picks the first series's aggregate,
        which depends on tag-value sort order and on which sensors have
        data in the query range — surfacing as inconsistent values between
        today/7-day (where one sensor dominates) and season (where multiple
        do). Tripwire: drop the `group()` and this test catches it before
        hardware regresses.
        """
        flux = _build_flux(
            bucket="pool_temps",
            sensor_id=None,
            range_start="-7d",
            agg="max",
        )
        # group() comes after filter() and before the aggregation.
        group_idx = flux.find("|> group()")
        max_idx = flux.find("|> max()")
        filter_idx = flux.find("|> filter")
        assert group_idx != -1, "expected `|> group()` in Flux query"
        assert max_idx != -1
        assert filter_idx < group_idx < max_idx


# ---------------------------------------------------------------------------
# PoolMonitor widget tests
# ---------------------------------------------------------------------------


def _monitor(**kw):
    """PoolMonitor without network; env + session mocked."""
    return PoolMonitor(
        session=mock.Mock(),
        influxdb_url="http://influx:8086",
        influxdb_org="pool",
        influxdb_bucket="pool_temps",
        influxdb_token="tok",
        **kw,
    )


class TestBuildScreens:
    def test_title_and_three_stories(self):
        m = _monitor(title="POOL TEMPS", units="imperial")
        m._build_ticker_screens(
            current_c=27.78,
            current_age_s=10.0,
            past_c=27.2,
            today_min_c=25.6,
            today_max_c=28.9,
            d7_mean_c=26.7,
            d7_min_c=24.4,
            d7_max_c=28.9,
            season_min_c=21.7,
            season_max_c=31.1,
        )
        assert m.feed_title.segments[0][0] == "POOL TEMPS"
        assert len(m.feed_stories) == 3
        for s in m.feed_stories:
            assert isinstance(s, SegmentMessage)

    def test_widget_font_threads_into_feed_title_and_stories(self):
        """Custom `font` configured on the widget must reach every
        SegmentMessage (title + 3 stories + placeholder). Without this
        wiring, bigsign configs that specify `font = "Inter-Regular"`
        would silently fall back to FONT_DEFAULT (BDF), producing the
        chunky-text-misplaced bug fixed alongside config.pool_longboi.toml.
        """
        sentinel_font = object()  # Font is duck-typed downstream
        m = _monitor(font=sentinel_font)
        m._build_ticker_screens(
            current_c=27.78,
            current_age_s=10.0,
            past_c=27.2,
            today_min_c=25.6,
            today_max_c=28.9,
            d7_mean_c=26.7,
            d7_min_c=24.4,
            d7_max_c=28.9,
            season_min_c=21.7,
            season_max_c=31.1,
        )
        assert m.feed_title.font is sentinel_font
        for s in m.feed_stories:
            assert s.font is sentinel_font

    def test_widget_font_threads_into_placeholder(self):
        """Placeholder screens (shown on initial fetch / failure) must
        also carry the configured font."""
        sentinel_font = object()
        m = _monitor(font=sentinel_font)
        m._set_placeholder()
        assert m.feed_title.font is sentinel_font
        assert m.feed_stories[0].font is sentinel_font

    def test_today_screen_has_temp_and_arrow(self):
        m = _monitor(units="imperial")
        m._build_ticker_screens(
            current_c=27.78,
            current_age_s=10.0,
            past_c=27.2,
            today_min_c=25.6,
            today_max_c=28.9,
            d7_mean_c=26.7,
            d7_min_c=24.4,
            d7_max_c=28.9,
            season_min_c=21.7,
            season_max_c=31.1,
        )
        today = m.feed_stories[0]
        texts = "".join(t for t, _ in today.segments)
        assert "82F" in texts  # 27.78C -> 82F (no degree symbol — see _fmt_temp)
        assert "^" in texts  # rising (27.78 > 27.2 by >0.5F)

    def test_stale_dims_temp(self):
        m = _monitor(units="imperial", stale_after=900)
        m._build_ticker_screens(
            current_c=27.78,
            current_age_s=1800.0,
            past_c=27.2,
            today_min_c=25.6,
            today_max_c=28.9,
            d7_mean_c=26.7,
            d7_min_c=24.4,
            d7_max_c=28.9,
            season_min_c=21.7,
            season_max_c=31.1,
        )
        today = m.feed_stories[0]
        # segments[0] is the "Pool 24h " label; the temp is segment 1.
        temp_color = today.segments[1][1]
        assert temp_color is DIM

    def test_season_label_spelled_out(self):
        m = _monitor(units="imperial")
        m._build_ticker_screens(
            current_c=27.78,
            current_age_s=10.0,
            past_c=27.2,
            today_min_c=25.6,
            today_max_c=28.9,
            d7_mean_c=26.7,
            d7_min_c=24.4,
            d7_max_c=28.9,
            season_min_c=21.7,
            season_max_c=31.1,
        )
        season = m.feed_stories[2]
        texts = "".join(t for t, _ in season.segments)
        assert "Season" in texts

    def test_label_color_threads_into_every_label_segment(self):
        """The configurable `label_color` (default white, set to e.g.
        icy cyan in config.pool_longboi.toml) must reach every prefix-
        label and separator segment across all three screens. Without
        this wiring, a config like `label_color = [130, 220, 255]`
        would silently fall back to white.
        """
        sentinel_color = object()  # Color is duck-typed by SegmentMessage
        m = _monitor(label_color=sentinel_color)
        m._build_ticker_screens(
            current_c=27.78,
            current_age_s=10.0,
            past_c=27.2,
            today_min_c=25.6,
            today_max_c=28.9,
            d7_mean_c=26.7,
            d7_min_c=24.4,
            d7_max_c=28.9,
            season_min_c=21.7,
            season_max_c=31.1,
        )
        # today: segments[0]=Pool24h label, segments[4]="/" separator
        today_segments = m.feed_stories[0].segments
        assert today_segments[0][1] is sentinel_color
        assert today_segments[4][1] is sentinel_color
        # 7-day: segments[0]=Pool7D label, segments[2]=spacer, segments[4]="/"
        d7_segments = m.feed_stories[1].segments
        assert d7_segments[0][1] is sentinel_color
        assert d7_segments[2][1] is sentinel_color
        assert d7_segments[4][1] is sentinel_color
        # season: segments[0]=PoolSeasonHI label, segments[2]="  LO " label
        season_segments = m.feed_stories[2].segments
        assert season_segments[0][1] is sentinel_color
        assert season_segments[2][1] is sentinel_color

    def test_label_color_threads_into_placeholder(self):
        sentinel_color = object()
        m = _monitor(label_color=sentinel_color)
        m._set_placeholder()
        # Placeholder story: both segments use label_color.
        for _text, color in m.feed_stories[0].segments:
            assert color is sentinel_color

    def test_every_screen_carries_pool_prefix(self):
        """Each cycle screen leads with a 'Pool ...' label so users
        sharing the panel with other widgets can tell at a glance what
        data they're looking at. Tripwire — if a future refactor drops
        the labels, this catches it before reaching hardware.
        """
        m = _monitor(units="imperial")
        m._build_ticker_screens(
            current_c=27.78,
            current_age_s=10.0,
            past_c=27.2,
            today_min_c=25.6,
            today_max_c=28.9,
            d7_mean_c=26.7,
            d7_min_c=24.4,
            d7_max_c=28.9,
            season_min_c=21.7,
            season_max_c=31.1,
        )
        today_texts = "".join(t for t, _ in m.feed_stories[0].segments)
        d7_texts = "".join(t for t, _ in m.feed_stories[1].segments)
        season_texts = "".join(t for t, _ in m.feed_stories[2].segments)
        assert "Pool 24h" in today_texts
        assert "Pool 7D" in d7_texts
        assert "Pool Season" in season_texts

    def test_missing_values_render_dashes(self):
        m = _monitor(units="imperial")
        m._build_ticker_screens(
            current_c=27.78,
            current_age_s=10.0,
            past_c=27.2,
            today_min_c=None,
            today_max_c=None,
            d7_mean_c=26.7,
            d7_min_c=24.4,
            d7_max_c=28.9,
            season_min_c=21.7,
            season_max_c=31.1,
        )
        today_texts = "".join(t for t, _ in m.feed_stories[0].segments)
        assert "--" in today_texts

    def test_metric_units_pick_correct_zone(self):
        from led_ticker.colors import ORANGE

        m = _monitor(units="metric")
        # 28°C = 82.4°F — should be the ORANGE (warm) zone.
        m._build_ticker_screens(
            current_c=28.0,
            current_age_s=10.0,
            past_c=27.5,
            today_min_c=25.0,
            today_max_c=29.0,
            d7_mean_c=27.0,
            d7_min_c=24.0,
            d7_max_c=29.0,
            season_min_c=21.0,
            season_max_c=31.0,
        )
        today = m.feed_stories[0]
        # segments[0] is the "Pool 24h " label; the temp is segment 1
        # and carries the zone color.
        assert today.segments[1][1] is ORANGE
        assert "28C" in today.segments[1][0]


class TestConformance:
    def test_stories_are_widgets(self):
        m = _monitor()
        m._build_ticker_screens(
            current_c=27.78,
            current_age_s=10.0,
            past_c=None,
            today_min_c=25.6,
            today_max_c=28.9,
            d7_mean_c=26.7,
            d7_min_c=24.4,
            d7_max_c=28.9,
            season_min_c=21.7,
            season_max_c=31.1,
        )
        assert isinstance(m.feed_title, Widget)
        assert all(isinstance(s, Widget) for s in m.feed_stories)


class TestMissingToken:
    async def test_start_raises_without_token(self, monkeypatch):
        monkeypatch.delenv("INFLUXDB_TOKEN", raising=False)
        with pytest.raises(ValueError, match="INFLUXDB_TOKEN"):
            await PoolMonitor.start(session=mock.Mock())


class TestSensorIdValidation:
    async def test_invalid_sensor_id_rejected(self, monkeypatch):
        monkeypatch.setenv("INFLUXDB_TOKEN", "tok")
        with pytest.raises(ValueError, match="Invalid sensor_id"):
            await PoolMonitor.start(session=mock.Mock(), sensor_id='abc"def')


class TestTwoRowLayout:
    """Pool widget two_row layout: title + 4 stories using TwoRowMessage."""

    def test_layout_defaults_to_ticker(self):
        m = _monitor()
        assert m.layout == "ticker"

    def test_layout_two_row_field_accepts_value(self):
        m = _monitor(layout="two_row")
        assert m.layout == "two_row"

    @pytest.mark.asyncio
    async def test_layout_two_row_dispatch_uses_build_two_row_screens(self):
        """When layout=two_row, update() routes to the two_row builder,
        not the ticker builder. Patches the two builders at the class
        level (mock.patch.object works on attrs slotted classes — the
        slots constraint only blocks NEW attributes on instances)."""
        m = _monitor(layout="two_row")

        async def _fake_query(range_start, agg):
            return 27.0, "2026-05-28T00:00:00Z"

        with (
            mock.patch.object(PoolMonitor, "_query", side_effect=_fake_query),
            mock.patch.object(PoolMonitor, "_build_two_row_screens") as two_row_builder,
            mock.patch.object(PoolMonitor, "_build_ticker_screens") as ticker_builder,
        ):
            await m.update()

        two_row_builder.assert_called_once()
        ticker_builder.assert_not_called()

    @pytest.mark.asyncio
    async def test_layout_ticker_dispatch_uses_build_ticker_screens(self):
        """Default layout=ticker routes to the ticker builder. Tripwire
        against a regression where a future change inverts the dispatch.
        """
        m = _monitor()  # default layout = "ticker"

        async def _fake_query(range_start, agg):
            return 27.0, "2026-05-28T00:00:00Z"

        with (
            mock.patch.object(PoolMonitor, "_query", side_effect=_fake_query),
            mock.patch.object(PoolMonitor, "_build_two_row_screens") as two_row_builder,
            mock.patch.object(PoolMonitor, "_build_ticker_screens") as ticker_builder,
        ):
            await m.update()

        ticker_builder.assert_called_once()
        two_row_builder.assert_not_called()

    def test_top_font_field_default_is_none(self):
        m = _monitor()
        assert m.top_font is None

    def test_bottom_font_field_default_is_none(self):
        m = _monitor()
        assert m.bottom_font is None

    def test_top_row_height_field_default_is_none(self):
        m = _monitor()
        assert m.top_row_height is None

    def test_per_row_fields_accept_overrides(self):
        sentinel_font = object()
        m = _monitor(
            top_font=sentinel_font,
            bottom_font=sentinel_font,
            top_row_height=4,
        )
        assert m.top_font is sentinel_font
        assert m.bottom_font is sentinel_font
        assert m.top_row_height == 4

    def _build(self, **overrides):
        """Run _build_two_row_screens with defaults; allow per-test overrides."""
        m = _monitor(layout="two_row", **overrides.pop("monitor_kwargs", {}))
        args = dict(
            current_c=27.78,
            current_age_s=10.0,
            past_c=27.2,
            today_min_c=25.6,
            today_max_c=28.9,
            d7_mean_c=26.7,
            d7_min_c=24.4,
            d7_max_c=28.9,
            season_min_c=21.7,
            season_max_c=31.1,
        )
        args.update(overrides)
        m._build_two_row_screens(**args)
        return m

    def test_yields_title_plus_four_stories(self):
        m = self._build()
        assert m.feed_title is not None
        assert len(m.feed_stories) == 4

    def test_title_is_two_row_message(self):
        from led_ticker.widgets.two_row import TwoRowMessage

        m = self._build()
        assert isinstance(m.feed_title, TwoRowMessage)

    def test_all_stories_are_two_row_messages(self):
        from led_ticker.widgets.two_row import TwoRowMessage

        m = self._build()
        for s in m.feed_stories:
            assert isinstance(s, TwoRowMessage)

    def test_title_screen_text(self):
        m = self._build()
        assert m.feed_title.top_text == "POOL"
        assert m.feed_title.bottom_text == "TEMPS"

    def test_today_screen_text(self):
        m = self._build()
        today = m.feed_stories[0]
        assert today.top_text == "POOL 24H"
        assert today.bottom_text == "82F"  # 27.78C -> 82F

    def test_seven_day_screen_text(self):
        m = self._build()
        d7 = m.feed_stories[1]
        assert d7.top_text == "POOL 7D AVG"
        assert d7.bottom_text == "80"  # 26.7C -> 80F

    def test_season_hi_screen_text(self):
        m = self._build()
        season_hi = m.feed_stories[2]
        assert season_hi.top_text == "POOL SEASON HI"
        assert season_hi.bottom_text == "88"  # 31.1C -> 88F

    def test_season_lo_screen_text(self):
        m = self._build()
        season_lo = m.feed_stories[3]
        assert season_lo.top_text == "POOL SEASON LO"
        assert season_lo.bottom_text == "71"  # 21.7C -> 71F

    def test_today_bottom_color_is_zone_color(self):
        from led_ticker.widgets.pool import _zone_color

        m = self._build()
        today = m.feed_stories[0]
        # TwoRowMessage wraps raw Color in _ConstantColor; unwrap via ._color.
        assert today.bottom_color._color is _zone_color(82.0)

    def test_today_bottom_color_when_stale(self):
        from led_ticker.widgets.pool import DIM

        m = self._build(current_age_s=10_000.0)  # well past stale_after=900
        today = m.feed_stories[0]
        assert today.bottom_color._color is DIM

    def test_seven_day_bottom_color_is_avg(self):
        from led_ticker.widgets.pool import AVG_COLOR

        m = self._build()
        assert m.feed_stories[1].bottom_color._color is AVG_COLOR

    def test_season_hi_bottom_color_is_hi(self):
        from led_ticker.widgets.pool import HI_COLOR

        m = self._build()
        assert m.feed_stories[2].bottom_color._color is HI_COLOR

    def test_season_lo_bottom_color_is_lo(self):
        from led_ticker.widgets.pool import LO_COLOR

        m = self._build()
        assert m.feed_stories[3].bottom_color._color is LO_COLOR

    def test_label_color_threads_to_every_top(self):
        sentinel = object()
        m = self._build(monitor_kwargs={"label_color": sentinel})
        # TwoRowMessage wraps raw Color in _ConstantColor; unwrap via ._color.
        assert m.feed_title.top_color._color is sentinel
        for s in m.feed_stories:
            assert s.top_color._color is sentinel

    def test_no_trend_arrow_in_today_screen(self):
        m = self._build()
        today = m.feed_stories[0]
        # The bottom row must be just the temp value — no ^/v/- arrow glyph.
        assert today.bottom_text == "82F"  # exact match

    def test_per_row_fields_thread_to_two_row_message(self):
        sentinel_font_top = object()
        sentinel_font_bottom = object()
        m = self._build(
            monitor_kwargs={
                "top_font": sentinel_font_top,
                "bottom_font": sentinel_font_bottom,
                "top_row_height": 4,
            }
        )
        today = m.feed_stories[0]
        assert today.top_font is sentinel_font_top
        assert today.bottom_font is sentinel_font_bottom
        assert today.top_row_height == 4

    def test_feed_stories_type_accepts_both_message_types(self):
        """feed_stories must accept SegmentMessage (ticker) or
        TwoRowMessage (two_row) — Container Protocol conformance
        depends on the field's declared type."""
        from led_ticker.widgets.message import SegmentMessage
        from led_ticker.widgets.two_row import TwoRowMessage

        m = self._build()
        for s in m.feed_stories:
            assert isinstance(s, SegmentMessage | TwoRowMessage)


# Container Protocol conformance for PoolMonitor is asserted in
# tests/test_widget_protocol.py::test_container_protocol_recognizes_pool_monitor
# alongside the MLB / RSS / standings conformance tests. The 2026-05-28
# Container refactor removed the per-type isinstance tuple from app/run.py,
# so an older test that searched the run.py source for "PoolMonitor" no
# longer applies — structural Protocol conformance is the new contract.
