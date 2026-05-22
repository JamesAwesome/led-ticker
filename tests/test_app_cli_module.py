"""Smoke test: cli submodule importable; main accessible from app."""


def test_cli_submodule_importable():
    from led_ticker.app.cli import _setup_logging, main

    assert callable(main)
    assert callable(_setup_logging)


def test_main_still_on_app_module():
    """Entry point led_ticker.app:main must remain accessible."""
    from led_ticker.app import main

    assert callable(main)
