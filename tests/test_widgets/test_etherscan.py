"""Tests for etherscan ETHERSCAN_API_KEY .env fallback.

Mirrors weather's WEATHERAPI_KEY pattern: update() reads the key from
the env var when no api_key is set in the widget config, an explicit
config api_key wins over the env var, and a missing key raises a clear
ValueError naming ETHERSCAN_API_KEY.
"""

import unittest.mock as mock

import pytest

from led_ticker.widgets.crypto.etherscan import EtherscanGasMonitor

_GAS_ORACLE_JSON = {
    "result": {
        "SafeGasPrice": "10",
        "ProposeGasPrice": "12",
        "FastGasPrice": "15",
    }
}


def _make_session(json_response):
    """Create a mock aiohttp session whose get() yields json_response."""
    session = mock.MagicMock()
    response = mock.AsyncMock()
    response.json.return_value = json_response
    ctx = mock.AsyncMock()
    ctx.__aenter__.return_value = response
    session.get.return_value = ctx
    return session


def _apikey_from_get(session) -> str:
    """Pull params['apikey'] out of the mocked session.get call."""
    _, kwargs = session.get.call_args
    return kwargs["params"]["apikey"]


class TestEtherscanApiKeyEnvFallback:
    async def test_env_key_used_when_no_config_key(self, monkeypatch):
        monkeypatch.setenv("ETHERSCAN_API_KEY", "env-key")
        session = _make_session(_GAS_ORACLE_JSON)
        m = EtherscanGasMonitor(session=session)
        await m.update()
        assert _apikey_from_get(session) == "env-key"

    async def test_config_key_wins_over_env(self, monkeypatch):
        monkeypatch.setenv("ETHERSCAN_API_KEY", "env-key")
        session = _make_session(_GAS_ORACLE_JSON)
        m = EtherscanGasMonitor(session=session, api_key="cfg-key")
        await m.update()
        assert _apikey_from_get(session) == "cfg-key"

    async def test_missing_key_raises_value_error(self, monkeypatch):
        monkeypatch.delenv("ETHERSCAN_API_KEY", raising=False)
        session = _make_session(_GAS_ORACLE_JSON)
        m = EtherscanGasMonitor(session=session)
        with pytest.raises(ValueError, match="ETHERSCAN_API_KEY"):
            await m.update()
