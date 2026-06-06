"""Tripwire for the Custom emoji how-to (examples/plugins/example_emoji).

The 'Custom emoji' page's code blocks are this plugin; this test keeps the
shipped example (and therefore the docs) honest against the real emoji API.
"""

import shutil
from pathlib import Path

import pytest

import led_ticker.pixel_emoji as pe
from led_ticker import _plugin_loader as L

EXAMPLE_DIR = (
    Path(__file__).resolve().parents[2] / "examples" / "plugins" / "example_emoji"
)


@pytest.fixture
def loaded(tmp_path):
    """Load examples/plugins/example_emoji into an isolated dir."""
    L.reset_plugins()
    pdir = tmp_path / "plugins"
    pdir.mkdir()
    shutil.copytree(EXAMPLE_DIR, pdir / "example_emoji")
    try:
        result = L.load_plugins(pdir, entry_points_enabled=False)
        assert "example_emoji" in {i.namespace for i in result.loaded}, result.failed
        yield
    finally:
        L.reset_plugins()


def test_low_res_heart_registered(loaded):
    data = pe.EMOJI_REGISTRY.get("example_emoji.heart")
    assert data is not None, "low-res emoji example_emoji.heart was not registered"
    assert len(data) == 40, f"expected a 40-pixel heart, got {len(data)}"
    # the bottom point of the heart (row 6, x in {3,4})
    assert (3, 6, 220, 40, 60) in data


def test_hires_heart_registered(loaded):
    assert "example_emoji.heart" in pe.HIRES_REGISTRY
