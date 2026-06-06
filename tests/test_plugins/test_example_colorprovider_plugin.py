"""Tripwire for the Custom color provider how-to's example plugin.

Keeps examples/plugins/example_colorprovider (the page's code) honest against
the real ColorProvider surface.
"""

import shutil
from pathlib import Path

import pytest

from led_ticker import _plugin_loader as L
from led_ticker.color_providers import _PROVIDER_REGISTRY

EXAMPLE_DIR = (
    Path(__file__).resolve().parents[2]
    / "examples"
    / "plugins"
    / "example_colorprovider"
)


@pytest.fixture
def pulse_cls(tmp_path):
    L.reset_plugins()
    pdir = tmp_path / "plugins"
    pdir.mkdir()
    shutil.copytree(EXAMPLE_DIR, pdir / "example_colorprovider")
    try:
        result = L.load_plugins(pdir, entry_points_enabled=False)
        loaded = {i.namespace for i in result.loaded}
        assert "example_colorprovider" in loaded, result.failed
        yield _PROVIDER_REGISTRY["example_colorprovider.pulse"]
    finally:
        L.reset_plugins()


def test_pulse_registers_with_flags(pulse_cls):
    assert pulse_cls.__name__ == "Pulse"
    assert pulse_cls.per_char is False
    assert pulse_cls.frame_invariant is False


def test_pulse_animates_across_frames(pulse_cls):
    p = pulse_cls()
    c0 = p.color_for(0, 0, 1)
    c5 = p.color_for(5, 0, 1)
    assert (c0.red, c0.green, c0.blue) != (c5.red, c5.green, c5.blue)


def test_pulse_accepts_color_config(pulse_cls):
    g = pulse_cls(color=[0, 100, 0], speed=6).color_for(0, 0, 1).green
    assert 0 < g <= 100
