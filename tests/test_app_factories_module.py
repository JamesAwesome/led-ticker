"""Smoke test: factories submodule importable and public names accessible."""


def test_factories_submodule_importable():
    import itertools

    from led_ticker.app.factories import (
        RANDOM_COLOR,
        RUN_MODES,
        _build_widget,
        build_frame_from_config,
    )

    assert isinstance(RANDOM_COLOR, itertools.cycle)
    assert callable(_build_widget)
    assert callable(build_frame_from_config)
    assert isinstance(RUN_MODES, dict)


def test_factory_names_still_on_app_module():
    """Backwards-compat: factory names remain importable from led_ticker.app."""
    from led_ticker.app import (
        _build_widget,
        build_frame_from_config,
    )

    assert callable(_build_widget)
    assert callable(build_frame_from_config)
