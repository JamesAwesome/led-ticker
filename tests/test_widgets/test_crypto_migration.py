"""Old crypto widget types now live in the led-ticker-crypto plugin."""

import pytest

from led_ticker.app.factories import build_widget_cfg_error_for_type


@pytest.mark.parametrize("old_type", ["coingecko", "coinbase", "etherscan"])
def test_removed_crypto_types_point_at_plugin(old_type):
    msg = build_widget_cfg_error_for_type(old_type)
    assert msg is not None
    assert "led-ticker-crypto" in msg
    assert "crypto.coingecko" in msg


def test_unrelated_unknown_type_has_no_crypto_hint():
    assert build_widget_cfg_error_for_type("definitely_not_a_widget") is None
