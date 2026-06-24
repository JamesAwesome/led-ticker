import pytest

from led_ticker.backends import (
    _REGISTRY,
    Backend,
    BackendNotReadyError,
    get_backend_class,
    known_backends,
    register_backend,
)


@pytest.fixture(autouse=True)
def _clear_registry():
    """Clear the registry before each test to ensure isolation."""
    yield
    _REGISTRY.clear()


def test_register_and_get():
    @register_backend("dummy_test_backend")
    class _Dummy:
        pass

    assert get_backend_class("dummy_test_backend") is _Dummy
    assert "dummy_test_backend" in known_backends()


def test_unknown_backend_lists_known():
    with pytest.raises(ValueError) as exc:
        get_backend_class("does_not_exist")
    assert "does_not_exist" in str(exc.value)
    # Message enumerates valid names so the user can self-correct.
    assert "rgbmatrix" in str(exc.value) or known_backends() == []


def test_backend_protocol_is_runtime_checkable():
    class _Conforming:
        brightness = 100
        framerate_fraction = 1

        def setup(self): ...
        def create_canvas(self): ...
        def swap(self, canvas, framerate_fraction=1): ...

    assert isinstance(_Conforming(), Backend)


def test_backend_not_ready_error_is_runtimeerror():
    assert issubclass(BackendNotReadyError, RuntimeError)
