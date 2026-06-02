import pytest

from led_ticker.app.factories import _run_validate_config


def test_validate_config_messages_raise():
    class W:
        @classmethod
        def validate_config(cls, cfg):
            return ["text is required"] if not cfg.get("text") else []

    with pytest.raises(ValueError, match="text is required"):
        _run_validate_config(W, {}, "acme.thing")


def test_validate_config_empty_list_is_ok():
    class W:
        @classmethod
        def validate_config(cls, cfg):
            return []

    _run_validate_config(W, {"text": "hi"}, "acme.thing")  # no raise


def test_validate_config_absent_is_ok():
    class W:  # no validate_config defined
        pass

    _run_validate_config(W, {"anything": 1}, "acme.thing")  # no raise


def test_validate_config_receives_a_copy_not_the_live_cfg():
    seen = {}

    class W:
        @classmethod
        def validate_config(cls, cfg):
            cfg["injected"] = True  # must not leak back to caller's dict
            seen.update(cfg)
            return []

    live = {"text": "hi"}
    _run_validate_config(W, live, "acme.thing")
    assert "injected" not in live  # caller's dict untouched
    assert seen.get("injected") is True


def test_validate_config_raising_is_wrapped(caplog):
    class W:
        @classmethod
        def validate_config(cls, cfg):
            raise RuntimeError("kaboom")

    with pytest.raises(ValueError, match="validate_config raised"):
        _run_validate_config(W, {}, "acme.thing")
