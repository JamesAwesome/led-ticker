import pytest

from led_ticker.app.factories import build_frame_from_config
from led_ticker.backends import _REGISTRY, get_backend_class
from led_ticker.backends.headless import HeadlessBackend, HeadlessCanvas
from led_ticker.backends.rgbmatrix import RgbMatrixBackend
from led_ticker.config import DisplayConfig


@pytest.fixture
def _isolate_backend_registry():
    """Snapshot/restore the backend registry so a test that registers a plugin
    backend doesn't leak into other tests."""
    saved = dict(_REGISTRY)
    yield
    _REGISTRY.clear()
    _REGISTRY.update(saved)


def test_unknown_backend_errors_loudly_listing_known():
    with pytest.raises(ValueError) as ei:
        get_backend_class("telnet")  # bare — plugin backends are namespaced
    msg = str(ei.value)
    assert "unknown backend 'telnet'" in msg
    assert "known backends" in msg  # lists what IS available so the user self-corrects


def test_default_backend_is_rgbmatrix():
    assert DisplayConfig().backend == "rgbmatrix"


def test_build_selects_headless():
    d = DisplayConfig(backend="headless", cols=32, chain_length=5, rows=16)
    frame = build_frame_from_config(d)
    assert isinstance(frame.backend, HeadlessBackend)


def test_build_selects_rgbmatrix_by_default():
    frame = build_frame_from_config(DisplayConfig())
    assert isinstance(frame.backend, RgbMatrixBackend)


def test_build_selects_registered_plugin_backend(_isolate_backend_registry):
    """A namespaced plugin backend, once registered, is constructed by
    build_frame_from_config via the shared headless-style ctor — proving the
    generic (non-hardcoded) construction path picks the resolved class."""
    from led_ticker.backends import register_backend

    @register_backend("acme.x")
    class _AcmeBackend:
        brightness = 100

        def __init__(self, width, height, *, pixel_mapper_config=""):
            self._w, self._h = width, height

        def setup(self):
            return None

        def create_canvas(self):
            return HeadlessCanvas(width=self._w, height=self._h)

        def swap(self, canvas):
            return HeadlessCanvas(width=self._w, height=self._h)

    d = DisplayConfig(backend="acme.x", cols=32, chain_length=5, rows=16)
    frame = build_frame_from_config(d)
    assert isinstance(frame.backend, _AcmeBackend)


def test_reset_plugins_clears_dotted_backend_but_keeps_builtins(
    _isolate_backend_registry,
):
    """reset_plugins() drops namespaced (dotted) backend registrations while the
    bare built-ins (headless / rgbmatrix) survive."""
    from led_ticker._plugin_loader import reset_plugins
    from led_ticker.backends import known_backends, register_backend

    @register_backend("acme.telnet")
    class _Plugin:
        pass

    assert "acme.telnet" in known_backends()
    reset_plugins()
    after = known_backends()
    assert "acme.telnet" not in after  # dotted plugin entry cleared
    assert "headless" in after and "rgbmatrix" in after  # bare built-ins survive


@pytest.mark.asyncio
async def test_validate_rejects_unknown_backend(tmp_path):
    from led_ticker.validate import validate_config

    cfg = tmp_path / "config.toml"
    cfg.write_text(
        '[display]\nbackend = "nope"\n\n'
        '[[playlist.section]]\nmode = "forever_scroll"\n'
        '[[playlist.section.widget]]\ntype = "message"\ntext = "hi"\n'
    )
    result = await validate_config(cfg)
    assert any("nope" in issue.message for issue in result.errors)
