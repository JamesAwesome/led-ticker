"""Extracted / retired widget types: coingecko, calendar, rss_feed and weather
all live in the led-ticker-plugins monorepo now (crypto.coingecko, calendar.events,
rss.feed, weather.current); coinbase/etherscan retired. The config-load migration
hint is per-type."""

import pytest

from led_ticker.app.factories import build_widget_cfg_error_for_type


@pytest.mark.parametrize("old_type", ["coingecko", "coinbase", "etherscan"])
def test_removed_crypto_types_have_a_hint(old_type):
    result = build_widget_cfg_error_for_type(old_type)
    assert result is not None
    msg, suggested_fix = result
    assert old_type in msg
    assert msg and suggested_fix


def test_coingecko_points_at_the_plugin():
    msg, suggested_fix = build_widget_cfg_error_for_type("coingecko")
    assert "led-ticker-plugins" in msg
    assert "crypto.coingecko" in msg
    assert "crypto.coingecko" in suggested_fix


def test_coinbase_is_retired_but_notes_the_price_ticker_alternative():
    msg, suggested_fix = build_widget_cfg_error_for_type("coinbase")
    assert "retired" in msg
    # coinbase is a price ticker, so the closest alternative is surfaced —
    # with the new required symbol_id called out.
    assert "crypto.coingecko" in msg
    assert "symbol_id" in msg


def test_etherscan_is_retired_with_no_false_replacement():
    msg, suggested_fix = build_widget_cfg_error_for_type("etherscan")
    assert "retired" in msg
    # etherscan is a gas widget, NOT a price ticker — it must not be told to
    # use crypto.coingecko.
    assert "crypto.coingecko" not in msg
    assert "crypto.coingecko" not in suggested_fix


def test_unrelated_unknown_type_has_no_hint():
    assert build_widget_cfg_error_for_type("definitely_not_a_widget") is None


# --- Calendar ---


def test_bare_calendar_type_raises_migration_to_plugin():
    result = build_widget_cfg_error_for_type("calendar")
    assert result is not None
    message, fix = result
    assert "led-ticker-plugins" in message
    assert "calendar.events" in fix


def test_bare_rss_feed_type_raises_migration_to_plugin():
    result = build_widget_cfg_error_for_type("rss_feed")
    assert result is not None
    message, fix = result
    assert "led-ticker-plugins" in message
    assert "rss.feed" in fix


def test_bare_weather_type_raises_migration_to_plugin():
    result = build_widget_cfg_error_for_type("weather")
    assert result is not None
    message, fix = result
    assert "led-ticker-plugins" in message
    assert "weather.current" in fix


def test_crypto_migration_still_works_after_rename():
    assert build_widget_cfg_error_for_type("coingecko") is not None


def test_feeds_rss_plugin_era_name_migrates_to_rss_feed():
    # `feeds.rss` was the led-ticker-feeds-plugin name (now archived). A stale
    # config must be told to RENAME to `rss.feed`, not to install the gone
    # `feeds` plugin.
    result = build_widget_cfg_error_for_type("feeds.rss")
    assert result is not None
    message, fix = result
    assert "rss.feed" in fix
    assert "install feeds" not in fix.lower()


def test_feeds_weather_plugin_era_name_migrates_to_weather_current():
    result = build_widget_cfg_error_for_type("feeds.weather")
    assert result is not None
    message, fix = result
    assert "weather.current" in fix
    assert "install feeds" not in fix.lower()
