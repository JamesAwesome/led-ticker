"""Smoke test: run submodule importable."""


def test_run_submodule_importable():
    import inspect

    from led_ticker.app.run import run

    assert inspect.iscoroutinefunction(run)


def test_run_still_on_app_module():
    import inspect

    from led_ticker.app import run

    assert inspect.iscoroutinefunction(run)
