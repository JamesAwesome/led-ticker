import pytest

from led_ticker.app.factories import build_frame_from_config
from led_ticker.backends import get_backend_class
from led_ticker.backends.headless import HeadlessBackend
from led_ticker.backends.rgbmatrix import RgbMatrixBackend
from led_ticker.config import DisplayConfig


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
