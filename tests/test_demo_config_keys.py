"""Tripwire: demo TOMLs must use only recognized [display] keys.

The config loader silently ignores unknown keys in [display] (tomllib parses
them; load_config only reads the fields it knows). So a stale/renamed key like
`chain` (renamed to `chain_length`) does NOT raise — it's dropped, and the demo
silently renders at the wrong size (one panel wide instead of the full chain).
That bug shipped across ~85 demo TOMLs whose committed gifs predated the rename.

This test compares every demo TOML's [display] table against the DisplayConfig
dataclass field set, so any future renamed/typo'd display key fails loudly here
instead of at the next maintainer's `make build-demos`.
"""

import dataclasses
import tomllib
from pathlib import Path

import pytest

from led_ticker.config import DisplayConfig

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEMO_DIRS = ("docs/site/demos", "docs/site/demos-pinned", "docs/site/demos-long")

_DISPLAY_FIELDS = {f.name for f in dataclasses.fields(DisplayConfig)}


def _demo_tomls() -> list[Path]:
    out: list[Path] = []
    for d in _DEMO_DIRS:
        out.extend(sorted((_REPO_ROOT / d).glob("*.toml")))
    return out


def test_demo_tomls_exist():
    # Guards against the glob silently matching nothing (e.g. a path rename),
    # which would make the parametrized test vacuously pass.
    assert _demo_tomls(), "no demo TOMLs found — did the demo dirs move?"


@pytest.mark.parametrize("toml_path", _demo_tomls(), ids=lambda p: p.name)
def test_demo_display_keys_are_recognized(toml_path: Path):
    data = tomllib.loads(toml_path.read_text())
    display = data.get("display", {})
    unknown = sorted(k for k in display if k not in _DISPLAY_FIELDS)
    assert not unknown, (
        f"{toml_path.relative_to(_REPO_ROOT)} uses unrecognized [display] "
        f"key(s) {unknown}; the loader silently ignores these. Did a field get "
        f"renamed? (e.g. chain -> chain_length). Valid keys: "
        f"{sorted(_DISPLAY_FIELDS)}"
    )
