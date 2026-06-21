import logging

from led_ticker.config import resolve_secret_token


def test_env_wins_over_config(monkeypatch):
    monkeypatch.setenv("LED_TICKER_TEST_TOK", "from-env")
    result = resolve_secret_token("LED_TICKER_TEST_TOK", "from-config", label="x")
    assert result == "from-env"


def test_config_fallback_when_env_unset(monkeypatch, caplog):
    monkeypatch.delenv("LED_TICKER_TEST_TOK", raising=False)
    with caplog.at_level(logging.WARNING):
        out = resolve_secret_token(
            "LED_TICKER_TEST_TOK", "from-config", label="web.token"
        )
    assert out == "from-config"
    assert any(
        "web.token" in r.message and "LED_TICKER_TEST_TOK" in r.message
        for r in caplog.records
    )


def test_empty_when_neither_set(monkeypatch, caplog):
    monkeypatch.delenv("LED_TICKER_TEST_TOK", raising=False)
    with caplog.at_level(logging.WARNING):
        out = resolve_secret_token("LED_TICKER_TEST_TOK", "", label="web.token")
    assert out == ""
    assert caplog.records == []  # no warning when there's nothing to migrate
