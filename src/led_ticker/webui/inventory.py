"""Inventory enumeration for the web UI: fonts, assets, emoji.

Pure functions over the filesystem + the core emoji registries. Plugin
emoji are NOT visible here (the sidecar never loads plugins) — they arrive
via status.json's plugins[].names and are merged in the browser.
Must never import rgbmatrix (covered by tests/test_webui_purity.py).
"""

from importlib import resources
from pathlib import Path
from typing import Any

ASSET_CAP = 500
_ASSET_SUFFIXES = {".gif", ".png", ".jpg", ".jpeg", ".webp", ".bmp"}


def _user_fonts(config_dir: Path) -> list[str]:
    try:
        return sorted(
            p.name
            for p in (config_dir / "fonts").iterdir()
            if p.is_file() and not p.name.startswith(".")
        )
    except OSError:
        return []


def _bundled_fonts() -> list[str]:
    names: list[str] = []
    try:
        pkg = resources.files("led_ticker.fonts")
        for entry in pkg.iterdir():
            if entry.name.endswith(".bdf"):
                names.append(entry.name)
        try:
            hires = pkg / "hires"
            for entry in hires.iterdir():
                if entry.is_file():
                    names.append(f"hires/{entry.name}")
        except OSError:
            pass
    except OSError:
        pass
    return sorted(names)


def _assets(config_dir: Path) -> tuple[list[dict[str, Any]], bool]:
    found: list[dict[str, Any]] = []
    truncated = False
    try:
        for p in sorted(config_dir.rglob("*")):
            if p.suffix.lower() not in _ASSET_SUFFIXES or not p.is_file():
                continue
            if len(found) >= ASSET_CAP:
                truncated = True
                break
            found.append(
                {"path": str(p.relative_to(config_dir)), "bytes": p.stat().st_size}
            )
    except OSError:
        pass
    return found, truncated


def _emoji() -> dict[str, list[str]]:
    from led_ticker import pixel_emoji  # noqa: PLC0415

    core = sorted(pixel_emoji._get_registry())  # noqa: SLF001 — materializing accessor per CLAUDE.md
    hires_only = sorted(set(pixel_emoji.HIRES_REGISTRY) - set(core))
    return {"core": core, "hires_only": hires_only}


def build_inventory(config_dir: Path) -> dict[str, Any]:
    assets, truncated = _assets(config_dir)
    return {
        "fonts": {"user": _user_fonts(config_dir), "bundled": _bundled_fonts()},
        "assets": assets,
        "assets_truncated": truncated,
        "emoji": _emoji(),
    }
