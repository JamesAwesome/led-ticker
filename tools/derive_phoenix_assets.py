"""Derive the Firebird phoenix sample assets from the vendored CC0 source.

Source: OpenGameArt "pixel-phoenix" by zonked (CC0). One 20x20 animated transparent
GIF -> the 5 formats the demos need, nearest-neighbor upscaled to 220x220 (crisp pixel
art, matching the retired 220×220 sample footprint). Reproducible from a clean checkout.
Run: `make derive-phoenix` (or `python tools/derive_phoenix_assets.py`).
"""

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "config" / "assets" / "_src" / "phoenix-cc0-no-bg.gif"
OUT = ROOT / "config" / "assets"
SIZE = (220, 220)  # 11x the 20x20 source, nearest-neighbor; retired sample footprint


def _rgba_frames(im: Image.Image) -> list[Image.Image]:
    frames = []
    for i in range(getattr(im, "n_frames", 1)):
        im.seek(i)
        frames.append(im.convert("RGBA").resize(SIZE, Image.NEAREST))
    return frames


def _durations(im: Image.Image, n: int) -> list[int]:
    out = []
    for i in range(n):
        im.seek(i)
        out.append(int(im.info.get("duration", 80)))
    return out


def main() -> None:
    src = Image.open(SRC)
    frames = _rgba_frames(src)
    durs = _durations(Image.open(SRC), len(frames))

    # transparent animated GIF (real 1-bit alpha): quantize each RGBA frame,
    # reserving palette index 255 for transparency (transparent where alpha < 128).
    def to_p_transparent(rgba: Image.Image) -> Image.Image:
        alpha = rgba.getchannel("A")
        # Quantize visible pixels to ≤255 colours (index 255 reserved for transparency)
        pal = rgba.convert("RGB").convert("P", palette=Image.ADAPTIVE, colors=255)
        # Flood index 255 into all pixels where source alpha < 128
        transparent_mask = alpha.point(lambda a: 255 if a < 128 else 0)
        pal.paste(255, mask=transparent_mask)
        pal.info["transparency"] = 255
        return pal

    tframes = [to_p_transparent(f) for f in frames]
    tframes[0].save(
        OUT / "phoenix_transparent.gif",
        save_all=True,
        append_images=tframes[1:],
        duration=durs,
        loop=0,
        transparency=255,
        disposal=2,
        optimize=False,
    )

    # opaque animated GIF: retired transparent sample composited on black
    black = [Image.new("RGBA", SIZE, (0, 0, 0, 255)) for _ in frames]
    oframes = [
        Image.alpha_composite(b, f).convert("RGB")
        for b, f in zip(black, frames, strict=True)
    ]
    oframes[0].save(
        OUT / "phoenix.gif",
        save_all=True,
        append_images=oframes[1:],
        duration=durs,
        loop=0,
        optimize=False,
    )

    # animated WebP (RGBA)
    frames[0].save(
        OUT / "phoenix.webp",
        save_all=True,
        append_images=frames[1:],
        duration=durs,
        loop=0,
        lossless=True,
    )

    # still PNGs from a representative frame (mid-animation reads best)
    mid = frames[len(frames) // 2]
    mid.save(OUT / "phoenix_transparent.png")
    Image.alpha_composite(Image.new("RGBA", SIZE, (0, 0, 0, 255)), mid).convert(
        "RGB"
    ).save(OUT / "phoenix.png")


if __name__ == "__main__":
    main()
