"""Tripwire: trend colors live in crypto, not the global palette."""

from led_ticker.widgets.crypto import _colors as crypto_colors


def test_crypto_trend_colors_exist():
    assert (
        crypto_colors.UP_TREND_COLOR.red,
        crypto_colors.UP_TREND_COLOR.green,
        crypto_colors.UP_TREND_COLOR.blue,
    ) == (46, 200, 46)
    assert (
        crypto_colors.DOWN_TREND_COLOR.red,
        crypto_colors.DOWN_TREND_COLOR.green,
        crypto_colors.DOWN_TREND_COLOR.blue,
    ) == (194, 24, 7)
    assert (
        crypto_colors.NEUTRAL_TREND_COLOR.red,
        crypto_colors.NEUTRAL_TREND_COLOR.green,
        crypto_colors.NEUTRAL_TREND_COLOR.blue,
    ) == (180, 180, 180)
