"""Lazy loader for the standard-emoji hires pack.

`emoji_pack.bin` bakes ~1,400 single-codepoint standard emoji (32×32,
derived from Noto Emoji — © Google, Apache 2.0; see THIRD_PARTY_NOTICES.md)
into one committed asset. Format (little-endian):

    magic b"LTEP" | u16 version=1 | u32 count
    count × ( u8 slug_len | ascii slug | u32 codepoint | u32 off | u32 len )
    payloads: zlib( raw (x, y, r, g, b) u8 quints )

The INDEX loads on first use (never at import). Each SPRITE decodes on
first display and is cached — Pi memory scales with emoji actually shown,
not pack size. A missing/corrupt pack logs once and behaves as absent:
the curated registries still work; a broken asset must never crash the
app. Writer + reader live together so the packer (tools/gen_emoji_pack.py)
cannot drift from the runtime. Curated registries always win — resolution
order is enforced in pixel_emoji, not here.
"""

import logging
import struct
import zlib
from pathlib import Path
from typing import TYPE_CHECKING

from led_ticker._types import PixelData

if TYPE_CHECKING:
    # Deferred at runtime (see `get_sprite`) to avoid a circular import —
    # pixel_emoji imports this module at module level. Under TYPE_CHECKING
    # only, so pyright can resolve the "HiResEmoji | None" return type.
    from led_ticker.pixel_emoji import HiResEmoji

logger = logging.getLogger(__name__)

PACK_MAGIC = b"LTEP"
PACK_VERSION = 1
_DEFAULT_PATH = Path(__file__).parent / "assets" / "emoji_pack.bin"

# Module state: None = not attempted; {} after a failed load (pack absent).
_index: dict[str, tuple[int, int]] | None = None  # slug -> (offset, length)
_cp_to_slug: dict[int, str] = {}
_path_loaded: Path | None = None
_sprite_cache: dict[str, HiResEmoji] = {}
_load_failed_logged = False


def _reset_for_tests() -> None:
    global _index, _path_loaded, _load_failed_logged
    _index = None
    _cp_to_slug.clear()
    _path_loaded = None
    _sprite_cache.clear()
    _load_failed_logged = False


def write_pack(
    entries: list[tuple[str, int, list[tuple[int, int, int, int, int]]]],
    path: Path,
) -> None:
    """Write a pack. Entries: (slug, codepoint, pixels). Sorted by slug so
    the asset is deterministic for a given input set."""
    entries = sorted(entries, key=lambda e: e[0])
    payloads = []
    for _slug, _cp, pixels in entries:
        raw = bytes(b for px in pixels for b in px)
        payloads.append(zlib.compress(raw, 9))
    index_size = sum(1 + len(s.encode("ascii")) + 12 for s, _, _ in entries)
    off = 4 + 2 + 4 + index_size
    parts = [PACK_MAGIC, struct.pack("<HI", PACK_VERSION, len(entries))]
    for (slug, cp, _), payload in zip(entries, payloads, strict=True):
        s = slug.encode("ascii")
        parts.append(struct.pack("<B", len(s)) + s)
        parts.append(struct.pack("<III", cp, off, len(payload)))
        off += len(payload)
    parts.extend(payloads)
    path.write_bytes(b"".join(parts))


def load_index(path: Path | None = None) -> bool:
    """Parse header + index (payloads untouched). Returns False and logs
    once on missing/corrupt pack; subsequent calls are no-ops."""
    global _index, _path_loaded, _load_failed_logged
    if _index is not None:
        return bool(_index)
    p = path or _DEFAULT_PATH
    try:
        with p.open("rb") as f:
            head = f.read(10)
            if len(head) != 10 or head[:4] != PACK_MAGIC:
                raise ValueError("bad magic")
            version, count = struct.unpack("<HI", head[4:10])
            if version != PACK_VERSION:
                raise ValueError(f"unsupported pack version {version}")
            idx: dict[str, tuple[int, int]] = {}
            for _ in range(count):
                (slug_len,) = struct.unpack("<B", f.read(1))
                slug = f.read(slug_len).decode("ascii")
                cp, off, length = struct.unpack("<III", f.read(12))
                idx[slug] = (off, length)
                if cp:
                    _cp_to_slug.setdefault(cp, slug)
    except Exception:
        if not _load_failed_logged:
            logger.warning(
                "emoji pack unavailable at %s — standard-emoji rendering "
                "disabled (curated emoji unaffected)",
                p,
                exc_info=True,
            )
            _load_failed_logged = True
        _index = {}
        _cp_to_slug.clear()
        return False
    _index = idx
    _path_loaded = p
    return True


def pack_slugs() -> tuple[str, ...]:
    load_index()
    assert _index is not None
    return tuple(sorted(_index))


def has_slug(slug: str) -> bool:
    load_index()
    assert _index is not None
    return slug in _index


def slug_for_codepoint(cp: int) -> str | None:
    load_index()
    return _cp_to_slug.get(cp)


def get_sprite(slug: str) -> HiResEmoji | None:
    """HiResEmoji for a pack slug, decoding + caching on first use.
    Returns None for unknown slugs or on payload corruption (logged)."""
    if slug in _sprite_cache:
        return _sprite_cache[slug]
    load_index()
    assert _index is not None
    entry = _index.get(slug)
    if entry is None or _path_loaded is None:
        return None
    off, length = entry
    try:
        with _path_loaded.open("rb") as f:
            f.seek(off)
            raw = zlib.decompress(f.read(length))
        if len(raw) % 5:
            raise ValueError("payload not a multiple of 5 bytes")
        pixels: PixelData = [
            (raw[i], raw[i + 1], raw[i + 2], raw[i + 3], raw[i + 4])
            for i in range(0, len(raw), 5)
        ]
    except Exception:
        logger.warning("emoji pack payload for %r unreadable — skipping", slug)
        return None
    from led_ticker.pixel_emoji import HiResEmoji, _auto_trim_hires

    sprite = _auto_trim_hires(HiResEmoji(pixels=tuple(pixels), physical_size=32))
    _sprite_cache[slug] = sprite
    return sprite
