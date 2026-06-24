from led_ticker._build import build_ref


def test_build_ref_reads_env(monkeypatch):
    monkeypatch.setenv("LED_TICKER_BUILD_REF", "feat/x@abc1234")
    assert build_ref() == "feat/x@abc1234"


def test_build_ref_defaults_unknown(monkeypatch):
    monkeypatch.delenv("LED_TICKER_BUILD_REF", raising=False)
    assert build_ref() == "unknown"
