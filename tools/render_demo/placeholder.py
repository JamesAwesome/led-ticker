"""Synthesize placeholder assets for missing files referenced by demo configs.

Demo configs may point at customer-IP brand assets that aren't checked
into the repo. Rather than skip these demos, we generate visually
obvious stand-ins so the configs still render.

- Image / single-frame: solid dark-lavender block with the missing path
  text rendered on top in small white.
- GIF: same block with a 3-frame subtle pulse so motion-aware widgets
  still tick.
- Font: not handled here — the renderer detects font references and
  rewrites them to Inter-Regular separately.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

# Brand-neutral dark lavender. Visible but obviously a placeholder.
_BG = (60, 50, 90)
_LIGHT = (75, 65, 110)


def _draw_label(img: Image.Image, text: str) -> None:
    draw = ImageDraw.Draw(img)
    # Use the default PIL font (small bitmap). It's fine for placeholder labels.
    try:
        font = ImageFont.load_default()
    except OSError:
        font = None
    # Fit within the image; truncate if needed.
    max_chars = max(8, img.width // 6)
    label = text if len(text) <= max_chars else "…" + text[-(max_chars - 1) :]
    draw.text((2, 2), "PLACEHOLDER", fill=(255, 255, 255), font=font)
    draw.text((2, 12), label, fill=(220, 220, 220), font=font)


def make_image_placeholder(
    out_path: Path, *, width: int, height: int, missing_path: str
) -> None:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (width, height), _BG)
    _draw_label(img, missing_path)
    img.save(out_path)


def make_gif_placeholder(
    out_path: Path, *, width: int, height: int, missing_path: str
) -> None:
    """3-frame placeholder. Pulse alternates background slightly so
    widget code that reads loops × frame_count behaves naturally."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    frames = []
    for bg in (_BG, _LIGHT, _BG):
        frame = Image.new("RGB", (width, height), bg)
        _draw_label(frame, missing_path)
        frames.append(frame)
    frames[0].save(
        out_path,
        save_all=True,
        append_images=frames[1:],
        duration=200,
        loop=0,
    )


def _asset_resolves(value: str, config_dir: Path) -> bool:
    """Check whether a path string resolves to an existing file.

    Tries: absolute path, and relative to config_dir.
    """
    p = Path(value)
    if p.is_absolute() and p.exists():
        return True
    return (config_dir / p).exists()


def rewrite_config_for_missing_assets(
    config: dict[str, Any], *, config_dir: Path, placeholder_dir: Path
) -> dict[str, Any]:
    """Walk every widget in the config; for each image/gif widget whose
    `path` doesn't resolve to a real file, generate a placeholder and
    rewrite the path to point at it.

    Returns a deep-copy with substitutions; original `config` is untouched.
    Default placeholder dimensions: 256×64 (bigsign panel), which most
    `fit` modes will scale appropriately for whatever panel the demo
    actually configures.
    """
    config_dir = Path(config_dir)
    placeholder_dir = Path(placeholder_dir)
    placeholder_dir.mkdir(parents=True, exist_ok=True)

    new_cfg = copy.deepcopy(config)
    sections = (new_cfg.get("playlist") or {}).get("section") or []
    for section in sections:
        for widget in section.get("widget") or []:
            wtype = widget.get("type")
            path = widget.get("path")
            if not path or wtype not in ("image", "gif"):
                continue
            if _asset_resolves(path, config_dir):
                # Rewrite relative paths to absolute so they still resolve
                # when the engine loads the config from a temp directory.
                p = Path(path)
                if not p.is_absolute():
                    widget["path"] = str((config_dir / p).resolve())
                continue
            slug = path.replace("/", "_").replace("\\", "_")
            if wtype == "image":
                ph_path = placeholder_dir / f"{slug}.png"
                make_image_placeholder(ph_path, width=256, height=64, missing_path=path)
            else:
                ph_path = placeholder_dir / f"{slug}.gif"
                make_gif_placeholder(ph_path, width=256, height=64, missing_path=path)
            widget["path"] = str(ph_path)
    return new_cfg
