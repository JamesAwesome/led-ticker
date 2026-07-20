# Standard-Emoji Hires Pack Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Any standard emoji (~1,400, single-codepoint, Noto-derived) renders as a 32×32 hires sprite when typed as unicode or `:cldr_slug:`, via one committed lazy-loaded pack asset.

**Architecture:** A generation-time pipeline (manifest builder → Noto fetcher/packer) produces a committed `emoji_pack.bin` (custom `LTEP` format: index + zlib payloads) plus a tiny generated BMP-allowlist module. A new runtime module `emoji_pack.py` does lazy index/sprite loading with per-sprite caching. `pixel_emoji.py` gains a `_hires_for()` resolver consulted on curated miss at every hires gate, a fold-to-first-base unicode fallback, and pack-aware `emoji_slugs()`/`is_emoji_slug()`. A validate rule warns on hires-only slugs at scale 1. Companion flair PR caps stickers random variety per firing.

**Tech Stack:** Python stdlib only at runtime (`struct`, `zlib`); Pillow + network only in `tools/`. Repo: core (`/Users/james/projects/github/jamesawesome/led-ticker`), branch `emoji-pack-spec`. Flair companion: led-ticker-plugins checkout `/Users/james/projects/github/jamesawesome/led-ticker-plugins-flight`.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-20-standard-emoji-hires-pack-design.md` (normative).
- NO runtime network access of any kind; the committed pack + manifest are what builds consume.
- Curated registries ALWAYS win; the packer refuses entries whose slug OR codepoint collides with curated (`_build_emoji_registry` slugs ∪ `HIRES_REGISTRY` slugs ∪ `_UNICODE_EMOJI_MAP` values/keys).
- Pack format: magic `LTEP`, u16 version = 1, u32 count; index entries `u8 slug_len + ascii slug + u32 codepoint + u32 offset + u32 length`; payloads = zlib of raw `(x, y, r, g, b)` u8 quints. Sprites 32×32, alpha threshold ≥ 110, Lanczos from Noto `png/512`.
- Fold rules: VS + skin-tone strip (existing `_emoji_key`); ZWJ → FIRST base codepoint; regional-indicator flags + keycaps → strip; unmapped → strip (today's behavior).
- Pack emoji are hires-only: no lowres sprites, unicode strips at scale 1, `:slug:` at scale 1 → validate WARNING.
- Slugs: CLDR short names sanitized to `[a-z_][a-z0-9_.]*`; in-pack dupes get `_2` suffix; must be visible in the committed manifest.
- Stickers cap (flair): `_RANDOM_VARIETY_CAP = 12` distinct slugs per firing, constant not knob; explicit `emoji=[...]` untouched.
- No `from __future__ import annotations`. Lint gates: `uv run --extra dev ruff check src/ tests/ tools/`, `ruff format --check`, `PYRIGHT_PYTHON_FORCE_VERSION=latest uv run --extra dev pyright src/` (CI scope is `src/` only).
- Work on branch `emoji-pack-spec` (core) / a new `stickers-variety-cap` branch (flair). PRs open at the end; NO merge without James's word. Hard visual gate before the core PR.
- This checkout's pre-commit/pre-push hooks are broken (`pre-commit not found`) — use `git commit/push --no-verify` after running the lint gates manually.

All commands run from the core repo root unless stated.

---

### Task 1: Pack format module + fixture round-trip (pure, no network)

The binary format reader/writer lives in ONE runtime module so the packer (tools) and runtime import the same code — no format drift.

**Files:**
- Create: `src/led_ticker/emoji_pack.py`
- Test: `tests/test_emoji_pack.py` (new)

**Interfaces:**
- Produces (consumed by Tasks 2–4):
  - `PACK_MAGIC = b"LTEP"`, `PACK_VERSION = 1`
  - `write_pack(entries: list[tuple[str, int, list[tuple[int, int, int, int, int]]]], path: Path) -> None` — entries are `(slug, codepoint, pixels)`.
  - `load_index(path: Path | None = None) -> bool` — parse header+index into module state; default path = the installed asset; returns False (and logs once) on missing/corrupt.
  - `pack_slugs() -> tuple[str, ...]`, `has_slug(slug: str) -> bool`, `slug_for_codepoint(cp: int) -> str | None`
  - `get_sprite(slug: str) -> "HiResEmoji | None"` — lazy per-slug decode + cache.
  - `_reset_for_tests() -> None` — clears index + cache state.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_emoji_pack.py`:

```python
"""Pack format + lazy loader. Uses a synthetic fixture pack — no network,
no dependency on the committed asset (that's test_emoji_pack_asset.py)."""

from pathlib import Path

import pytest

from led_ticker import emoji_pack


@pytest.fixture(autouse=True)
def _fresh_pack_state():
    emoji_pack._reset_for_tests()
    yield
    emoji_pack._reset_for_tests()


def _fixture_entries():
    # two tiny sprites: a 2x2 red square and a single green px
    sq = [(0, 0, 255, 0, 0), (1, 0, 255, 0, 0), (0, 1, 255, 0, 0), (1, 1, 255, 0, 0)]
    dot = [(5, 5, 0, 255, 0)]
    return [("red_square", 0x1F7E5, sq), ("green_dot", 0x1F7E9, dot)]


class TestRoundTrip:
    def test_write_then_read_pixel_identical(self, tmp_path: Path):
        p = tmp_path / "fixture.bin"
        emoji_pack.write_pack(_fixture_entries(), p)
        assert emoji_pack.load_index(p) is True
        assert emoji_pack.pack_slugs() == ("green_dot", "red_square")
        s = emoji_pack.get_sprite("red_square")
        assert s is not None
        assert s.physical_size == 32
        assert sorted(s.pixels) == sorted(
            tuple(px) for px in _fixture_entries()[0][2]
        )

    def test_codepoint_lookup(self, tmp_path: Path):
        p = tmp_path / "fixture.bin"
        emoji_pack.write_pack(_fixture_entries(), p)
        emoji_pack.load_index(p)
        assert emoji_pack.slug_for_codepoint(0x1F7E9) == "green_dot"
        assert emoji_pack.slug_for_codepoint(0x1F525) is None

    def test_has_slug(self, tmp_path: Path):
        p = tmp_path / "fixture.bin"
        emoji_pack.write_pack(_fixture_entries(), p)
        emoji_pack.load_index(p)
        assert emoji_pack.has_slug("red_square")
        assert not emoji_pack.has_slug("rocket")


class TestDegradation:
    def test_missing_file_is_pack_absent(self, tmp_path: Path):
        assert emoji_pack.load_index(tmp_path / "nope.bin") is False
        assert emoji_pack.pack_slugs() == ()
        assert emoji_pack.get_sprite("anything") is None

    def test_bad_magic_is_pack_absent(self, tmp_path: Path):
        p = tmp_path / "bad.bin"
        p.write_bytes(b"NOPE" + b"\x00" * 32)
        assert emoji_pack.load_index(p) is False
        assert emoji_pack.pack_slugs() == ()

    def test_wrong_version_is_pack_absent(self, tmp_path: Path):
        p = tmp_path / "v9.bin"
        emoji_pack.write_pack(_fixture_entries(), p)
        raw = bytearray(p.read_bytes())
        raw[4:6] = (99).to_bytes(2, "little")
        p.write_bytes(bytes(raw))
        assert emoji_pack.load_index(p) is False

    def test_truncated_payload_returns_none_not_raise(self, tmp_path: Path):
        p = tmp_path / "trunc.bin"
        emoji_pack.write_pack(_fixture_entries(), p)
        p.write_bytes(p.read_bytes()[:-3])
        emoji_pack.load_index(p)
        assert emoji_pack.get_sprite("red_square") is None  # logged, not raised


class TestLaziness:
    def test_sprite_decode_is_lazy_and_cached(self, tmp_path: Path, monkeypatch):
        p = tmp_path / "fixture.bin"
        emoji_pack.write_pack(_fixture_entries(), p)
        emoji_pack.load_index(p)
        calls = []
        real = emoji_pack.zlib.decompress
        monkeypatch.setattr(
            emoji_pack.zlib, "decompress", lambda b: calls.append(1) or real(b)
        )
        assert calls == []  # index load decoded nothing
        emoji_pack.get_sprite("green_dot")
        assert len(calls) == 1
        emoji_pack.get_sprite("green_dot")
        assert len(calls) == 1  # cached
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run --no-sync python -m pytest tests/test_emoji_pack.py -q`
Expected: collection ERROR — `ModuleNotFoundError: No module named 'led_ticker.emoji_pack'`

- [ ] **Step 3: Implement `src/led_ticker/emoji_pack.py`**

```python
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

from led_ticker._types import PixelData

logger = logging.getLogger(__name__)

PACK_MAGIC = b"LTEP"
PACK_VERSION = 1
_DEFAULT_PATH = Path(__file__).parent / "assets" / "emoji_pack.bin"

# Module state: None = not attempted; {} after a failed load (pack absent).
_index: dict[str, tuple[int, int]] | None = None  # slug -> (offset, length)
_cp_to_slug: dict[int, str] = {}
_path_loaded: Path | None = None
_sprite_cache: dict[str, "object"] = {}
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


def get_sprite(slug: str):
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

    sprite = _auto_trim_hires(
        HiResEmoji(pixels=tuple(tuple(p) for p in pixels), physical_size=32)
    )
    _sprite_cache[slug] = sprite
    return sprite
```

(Import of `HiResEmoji` is deferred inside `get_sprite` to avoid an import
cycle — `pixel_emoji` imports `emoji_pack` at module level in Task 4.)

- [ ] **Step 4: Run tests**

Run: `uv run --no-sync python -m pytest tests/test_emoji_pack.py -q`
Expected: all pass (note: pyright the new module too: `PYRIGHT_PYTHON_FORCE_VERSION=latest uv run --extra dev pyright src/led_ticker/emoji_pack.py` → clean).

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/emoji_pack.py tests/test_emoji_pack.py
git commit --no-verify -m "feat(emoji-pack): LTEP pack format module — writer/reader, lazy index + sprite cache"
```

---

### Task 2: Manifest builder + packer tools; generate + commit the assets

**Files:**
- Create: `tools/gen_emoji_manifest.py` (CLDR → manifest; network, run once)
- Create: `tools/gen_emoji_pack.py` (manifest → Noto fetch → pack + BMP module; network at tool time only)
- Create (generated, committed): `tools/assets/emoji_manifest.txt`, `src/led_ticker/assets/emoji_pack.bin`, `src/led_ticker/_emoji_pack_bmp.py`
- Modify: `pyproject.toml` (ensure `src/led_ticker/assets/*.bin` ships in the wheel — check existing package-data config; hatchling includes package files by default, verify with a wheel build)
- Modify: `THIRD_PARTY_NOTICES.md` (generalize the fire clause to the pack)
- Test: `tests/test_emoji_pack_asset.py` (new — asserts on the COMMITTED artifacts, no network)

**Interfaces:**
- Consumes: `emoji_pack.write_pack` (Task 1).
- Produces: the three committed artifacts. `_emoji_pack_bmp.py` exposes `PACK_BMP: str` — every BMP (< U+10000) codepoint in the pack, as a characters string for regex-class use (Task 4's scanner needs a static allowlist because `_UEMOJI_RE` builds at import).

- [ ] **Step 1: Write `tools/gen_emoji_manifest.py`**

```python
#!/usr/bin/env python3
"""Build tools/assets/emoji_manifest.txt: one `U+XXXX<TAB>slug` line per
single-codepoint standard emoji, slugs from CLDR short names.

Run ONCE on a dev machine (network); the committed manifest is the
reviewable source of truth for what's in the pack and what it's named.

    uv run python tools/gen_emoji_manifest.py > tools/assets/emoji_manifest.txt

Sources:
- CLDR annotations (short names):
  https://raw.githubusercontent.com/unicode-org/cldr-json/main/cldr-json/cldr-annotations-full/annotations/en/annotations.json
Inclusion: single-codepoint entries with a `tts` name. Exclusions:
regional indicators (U+1F1E6-1F1FF), skin-tone modifiers (U+1F3FB-1F3FF),
ZWJ/VS/keycap components, and any codepoint already covered by the curated
`_UNICODE_EMOJI_MAP` (curated wins at the SOURCE).
"""

import json
import re
import sys
import unicodedata
import urllib.request

_CLDR_URL = (
    "https://raw.githubusercontent.com/unicode-org/cldr-json/main/"
    "cldr-json/cldr-annotations-full/annotations/en/annotations.json"
)
_SLUG_RE = re.compile(r"^[a-z_][a-z0-9_.]*$")


def _slugify(name: str) -> str:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")
    if not s or not s[0].isalpha():
        s = f"e_{s}"
    return s


def main() -> None:
    from led_ticker.pixel_emoji import _UNICODE_EMOJI_MAP, _emoji_key

    curated_keys = set(_UNICODE_EMOJI_MAP)
    with urllib.request.urlopen(_CLDR_URL, timeout=60) as r:
        ann = json.load(r)["annotations"]["annotations"]
    seen: dict[str, int] = {}
    out: list[tuple[int, str]] = []
    for chars, data in ann.items():
        if len(chars) != 1:
            continue  # single-codepoint scope (spec decision 1)
        cp = ord(chars)
        if 0x1F1E6 <= cp <= 0x1F1FF or 0x1F3FB <= cp <= 0x1F3FF:
            continue
        if _emoji_key(chars) in curated_keys:
            continue  # curated wins at the source
        tts = data.get("tts")
        if not tts:
            continue
        slug = _slugify(tts[0])
        n = seen.get(slug, 0) + 1
        seen[slug] = n
        if n > 1:
            slug = f"{slug}_{n}"
        assert _SLUG_RE.match(slug), slug
        out.append((cp, slug))
    for cp, slug in sorted(out):
        sys.stdout.write(f"U+{cp:04X}\t{slug}\n")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Write `tools/gen_emoji_pack.py`**

```python
#!/usr/bin/env python3
"""Build the committed emoji-pack artifacts from the manifest:

    uv run python tools/gen_emoji_pack.py

Reads tools/assets/emoji_manifest.txt, fetches each Noto Emoji PNG
(png/512/emoji_uXXXX.png) into a gitignored cache (tools/assets/_noto_cache/),
applies the proven :fire: recipe (Lanczos 32×32, alpha >= 110), and writes:

- src/led_ticker/assets/emoji_pack.bin   (the pack)
- src/led_ticker/_emoji_pack_bmp.py      (generated BMP allowlist for the
                                          unicode-run scanner, which builds
                                          its regex at import time)

Noto Emoji is © Google, Apache License 2.0 — THIRD_PARTY_NOTICES.md.
Missing glyphs (404) are reported and SKIPPED (some CLDR entries have no
Noto file); the run summary lists them for manifest pruning.
"""

import sys
import urllib.error
import urllib.request
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from led_ticker.emoji_pack import write_pack  # noqa: E402

_ROOT = Path(__file__).parent
_MANIFEST = _ROOT / "assets" / "emoji_manifest.txt"
_CACHE = _ROOT / "assets" / "_noto_cache"
_PACK_OUT = _ROOT.parent / "src" / "led_ticker" / "assets" / "emoji_pack.bin"
_BMP_OUT = _ROOT.parent / "src" / "led_ticker" / "_emoji_pack_bmp.py"
_NOTO = "https://raw.githubusercontent.com/googlefonts/noto-emoji/main/png/512/emoji_u{cp:04x}.png"
_ALPHA = 110


def _fetch(cp: int) -> Path | None:
    _CACHE.mkdir(exist_ok=True)
    dst = _CACHE / f"emoji_u{cp:04x}.png"
    if dst.exists():
        return dst
    try:
        with urllib.request.urlopen(_NOTO.format(cp=cp), timeout=60) as r:
            dst.write_bytes(r.read())
        return dst
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def _bake(png: Path) -> list[tuple[int, int, int, int, int]]:
    img = Image.open(png).convert("RGBA").resize((32, 32), Image.Resampling.LANCZOS)
    px = img.load()
    assert px is not None
    return [
        (x, y, *px[x, y][:3])
        for y in range(32)
        for x in range(32)
        if px[x, y][3] >= _ALPHA
    ]


def main() -> None:
    entries = []
    skipped: list[str] = []
    for line in _MANIFEST.read_text().splitlines():
        cp_s, slug = line.split("\t")
        cp = int(cp_s[2:], 16)
        png = _fetch(cp)
        if png is None:
            skipped.append(f"{cp_s} {slug}")
            continue
        pixels = _bake(png)
        if not pixels:
            skipped.append(f"{cp_s} {slug} (empty after threshold)")
            continue
        entries.append((slug, cp, pixels))
    _PACK_OUT.parent.mkdir(exist_ok=True)
    write_pack(entries, _PACK_OUT)
    bmp = "".join(sorted(chr(cp) for _, cp, _ in entries if cp < 0x10000))
    _BMP_OUT.write_text(
        '"""GENERATED by tools/gen_emoji_pack.py — do not edit.\n\n'
        "BMP (< U+10000) codepoints present in the emoji pack. The unicode\n"
        "run scanner's regex builds at import time, so pack BMP emoji need\n"
        'this static allowlist (astral emoji match by range)."""\n\n'
        f"PACK_BMP: str = {bmp!r}\n"
    )
    print(f"packed {len(entries)} sprites -> {_PACK_OUT} "
          f"({_PACK_OUT.stat().st_size / 1e6:.2f} MB); "
          f"{len(bmp)} BMP chars -> {_BMP_OUT}")
    if skipped:
        print(f"skipped {len(skipped)} (no Noto glyph / empty):")
        for s in skipped:
            print("  ", s)


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Generate the artifacts (network, dev machine)**

```bash
mkdir -p tools/assets src/led_ticker/assets
echo "tools/assets/_noto_cache/" >> .gitignore
uv run --no-sync python tools/gen_emoji_manifest.py > tools/assets/emoji_manifest.txt
wc -l tools/assets/emoji_manifest.txt   # expect ~1,300-1,500
uv run --no-sync python tools/gen_emoji_pack.py   # fetches ~1,400 PNGs (cached), writes pack + BMP module
```

If the packer's skip-list is non-trivial, prune those manifest lines and re-run so manifest == pack content. Sanity: pack size 1.5–4 MB. Then verify the wheel ships it:

```bash
uv build --wheel 2>/dev/null && unzip -l dist/*.whl | grep -E "emoji_pack.bin|_emoji_pack_bmp" && rm -rf dist
```

If the `.bin` is missing from the wheel, add to `pyproject.toml` under `[tool.hatch.build.targets.wheel]`: `artifacts = ["src/led_ticker/assets/*.bin"]` (hatchling excludes gitignored files only — a committed .bin is normally included; verify empirically).

- [ ] **Step 4: Write the committed-asset tests**

Create `tests/test_emoji_pack_asset.py`:

```python
"""Assertions on the COMMITTED pack artifacts (no network, no generation)."""

import re
from pathlib import Path

from led_ticker import emoji_pack

_MANIFEST = Path(__file__).parent.parent / "tools" / "assets" / "emoji_manifest.txt"
_SLUG_RE = re.compile(r"^[a-z_][a-z0-9_.]*$")


class TestManifest:
    def test_slugs_valid_and_unique(self):
        slugs = [ln.split("\t")[1] for ln in _MANIFEST.read_text().splitlines()]
        assert len(slugs) > 1000  # size tripwire (spec)
        assert len(set(slugs)) == len(slugs)
        for s in slugs:
            assert _SLUG_RE.match(s), s

    def test_no_curated_collisions(self):
        from led_ticker.pixel_emoji import HIRES_REGISTRY, _get_registry

        curated = set(_get_registry()) | set(HIRES_REGISTRY)
        packed = {ln.split("\t")[1] for ln in _MANIFEST.read_text().splitlines()}
        assert not (curated & packed), curated & packed


class TestCommittedPack:
    def test_loads_and_matches_manifest(self):
        emoji_pack._reset_for_tests()
        assert emoji_pack.load_index() is True
        packed = set(emoji_pack.pack_slugs())
        manifest = {ln.split("\t")[1] for ln in _MANIFEST.read_text().splitlines()}
        assert packed == manifest
        assert len(packed) > 1000

    def test_spot_sprite_decodes(self):
        emoji_pack._reset_for_tests()
        emoji_pack.load_index()
        slug = emoji_pack.slug_for_codepoint(0x1F680)  # 🚀 rocket
        assert slug is not None
        s = emoji_pack.get_sprite(slug)
        assert s is not None and len(s.pixels) > 50

    def test_bmp_module_matches_pack(self):
        from led_ticker._emoji_pack_bmp import PACK_BMP

        emoji_pack._reset_for_tests()
        emoji_pack.load_index()
        pack_bmp = {
            c for c in PACK_BMP
        }
        for ch in pack_bmp:
            assert emoji_pack.slug_for_codepoint(ord(ch)) is not None
```

- [ ] **Step 5: Run + THIRD_PARTY_NOTICES + commit**

Run: `uv run --no-sync python -m pytest tests/test_emoji_pack.py tests/test_emoji_pack_asset.py -q` → all pass.

In `THIRD_PARTY_NOTICES.md`, replace the fire-specific heading/paragraph with a pack-general one (keep the fire sentence as an example):

```markdown
## Noto Emoji — the `:fire:` hi-res sprite and the standard-emoji pack

The hi-res `:fire:` sprite (`_FIRE_HIRES_PIXELS`) and the standard-emoji
pack (`src/led_ticker/assets/emoji_pack.bin`, ~1,400 sprites) are derived
from Noto Emoji glyphs: source PNGs downsampled to 32×32 and
alpha-thresholded (see `tools/gen_fire_hires.py` and
`tools/gen_emoji_pack.py`; the pack's contents are enumerated in
`tools/assets/emoji_manifest.txt`).

- **Source:** Noto Emoji — https://github.com/googlefonts/noto-emoji
- **Copyright:** © Google LLC
- **License:** Apache License, Version 2.0 —
  https://www.apache.org/licenses/LICENSE-2.0
```

```bash
git add tools/gen_emoji_manifest.py tools/gen_emoji_pack.py tools/assets/emoji_manifest.txt src/led_ticker/assets/emoji_pack.bin src/led_ticker/_emoji_pack_bmp.py tests/test_emoji_pack_asset.py THIRD_PARTY_NOTICES.md .gitignore pyproject.toml
git commit --no-verify -m "feat(emoji-pack): manifest + packer tools; commit the ~1,400-sprite Noto pack"
```

---

### Task 3: `pixel_emoji` wiring — resolver, unicode fold, slugs, scanner

**Files:**
- Modify: `src/led_ticker/pixel_emoji.py`
- Test: `tests/test_pixel_emoji_pack_wiring.py` (new)

**Interfaces:**
- Consumes: `emoji_pack.get_sprite/has_slug/slug_for_codepoint/pack_slugs` (Task 1), `_emoji_pack_bmp.PACK_BMP` (Task 2).
- Produces: pack emoji render via every existing draw/measure path with NO caller changes.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_pixel_emoji_pack_wiring.py`:

```python
"""Pack wiring through pixel_emoji: slug + unicode + folds + laziness.
Uses the COMMITTED pack (rocket U+1F680 as the canonical pack emoji)."""

import pytest

from led_ticker import emoji_pack, pixel_emoji
from led_ticker.pixel_emoji import (
    _map_uemoji_to_slug,
    emoji_slugs,
    has_renderable_emoji,
    is_emoji_slug,
)


@pytest.fixture(autouse=True)
def _fresh():
    emoji_pack._reset_for_tests()
    yield
    emoji_pack._reset_for_tests()


class TestSlugSurface:
    def test_pack_slug_is_emoji_slug(self):
        rocket = emoji_pack_slug_for_rocket()
        assert is_emoji_slug(rocket)

    def test_emoji_slugs_includes_pack(self):
        slugs = emoji_slugs()
        assert len(slugs) > 1000  # spec tripwire
        assert "taco" in slugs  # curated intact

    def test_unknown_still_unknown(self):
        assert not is_emoji_slug("dragon_that_does_not_exist_xyz")


def emoji_pack_slug_for_rocket() -> str:
    emoji_pack.load_index()
    slug = emoji_pack.slug_for_codepoint(0x1F680)
    assert slug
    return slug


class TestUnicodeFold:
    def test_rocket_unicode_maps(self):
        assert _map_uemoji_to_slug("🚀") == emoji_pack_slug_for_rocket()

    def test_curated_unicode_still_wins(self):
        assert _map_uemoji_to_slug("🔥") == "fire"

    def test_skin_tone_folds_to_base(self):
        base = _map_uemoji_to_slug("👍")
        assert base is not None
        assert _map_uemoji_to_slug("👍🏽") == base

    def test_zwj_folds_to_first_base(self):
        first = _map_uemoji_to_slug("👨")
        assert first is not None
        assert _map_uemoji_to_slug("👨‍👩‍👧") == first

    def test_letter_flags_strip(self):
        assert _map_uemoji_to_slug("🇺🇸") is None

    def test_run_scanner_detects_pack_astral(self):
        assert has_renderable_emoji("we are live 🚀 now")

    def test_run_scanner_detects_pack_bmp(self):
        # ☂ U+2602 is BMP; in the pack via the generated allowlist. If the
        # committed manifest lacks it, substitute any PACK_BMP char.
        from led_ticker._emoji_pack_bmp import PACK_BMP

        ch = "☂" if "☂" in PACK_BMP else PACK_BMP[0]
        assert has_renderable_emoji(f"rain {ch} ahead")


class TestDrawPaths:
    def _scaled(self):
        from led_ticker.scaled_canvas import ScaledCanvas
        from tests.test_pixel_emoji import _make_canvas  # reuse stub factory

        real = _make_canvas(256, 64)
        return real, ScaledCanvas(real, scale=4, content_height=16)

    def test_pack_slug_draws_hires(self):
        real, canvas = self._scaled()
        rocket = emoji_pack_slug_for_rocket()
        pixel_emoji.draw_emoji_at(canvas, rocket, 0, 0)
        assert real.lit_count() > 50  # painted at physical resolution

    def test_pack_unicode_draws_in_text(self):
        real, canvas = self._scaled()
        from led_ticker.fonts import resolve_font

        font = resolve_font("Inter-Bold", size=30)
        pixel_emoji.draw_with_emoji(
            canvas, "GO 🚀", 0, 12, font, (255, 255, 255)
        )
        assert real.lit_count() > 100

    def test_scale1_pack_slug_strips(self):
        from tests.test_pixel_emoji import _make_canvas

        real = _make_canvas(160, 16)
        rocket = emoji_pack_slug_for_rocket()
        before = real.lit_count()
        pixel_emoji.draw_emoji_at(real, rocket, 0, 0)
        assert real.lit_count() == before  # hires-only: nothing at scale 1


class TestLaziness:
    def test_curated_draw_never_opens_pack(self, monkeypatch):
        opened = []
        real_load = emoji_pack.load_index
        monkeypatch.setattr(
            emoji_pack, "load_index", lambda *a, **k: opened.append(1) or real_load(*a, **k)
        )
        from tests.test_pixel_emoji import _make_canvas

        canvas = _make_canvas(160, 16)
        pixel_emoji.draw_emoji_at(canvas, "taco", 0, 0)
        assert opened == []  # curated hit → pack untouched
```

NOTE to implementer: `tests/test_pixel_emoji.py` already has a stub-canvas
factory — if its name isn't `_make_canvas` or it lacks `lit_count()`, adapt
these tests to the actual fixture idioms in that file (count via
`len(canvas._pixels)` etc.). Keep the ASSERTIONS as written; only adjust
the stub plumbing. Same for `resolve_font` import path.

- [ ] **Step 2: Run to verify failures**

Run: `uv run --no-sync python -m pytest tests/test_pixel_emoji_pack_wiring.py -q`
Expected: failures/errors — pack slugs unknown to `is_emoji_slug`, `_map_uemoji_to_slug("🚀")` returns None, etc.

- [ ] **Step 3: Wire `pixel_emoji.py`**

Four precise edits:

**(a) Module import + hires resolver.** Near the other imports:

```python
from led_ticker import emoji_pack
from led_ticker._emoji_pack_bmp import PACK_BMP
```

Below `HIRES_REGISTRY`'s definition add:

```python
def _hires_for(slug: str) -> "HiResEmoji | None":
    """Hires sprite for `slug`: curated registry first, then the standard-
    emoji pack (lazy). The ONE lookup every hires gate routes through so
    curated-wins can't drift per-site."""
    hit = HIRES_REGISTRY.get(slug)
    if hit is not None:
        return hit
    return emoji_pack.get_sprite(slug)
```

Route every `use_hires and slug in HIRES_REGISTRY` gate through it. Find
them: `grep -n "in HIRES_REGISTRY" src/led_ticker/pixel_emoji.py` — expect
~6 sites (the `draw_with_emoji` value/slug branches, `_paint_emoji_slug`,
`draw_emoji_at`, `measure_emoji_at`, and the width helper). Each changes
from:

```python
if use_hires and slug in HIRES_REGISTRY:
    candidate = HIRES_REGISTRY[slug]
```

to:

```python
candidate = _hires_for(slug) if use_hires else None
if candidate is not None:
```

(preserving each site's subsequent height-cap/downsample logic untouched).

**(b) Membership + slugs.** `is_emoji_slug` (the `slug in _get_registry() or slug in HIRES_REGISTRY` line) gains `or emoji_pack.has_slug(slug)`. `has_renderable_emoji`'s slug loop likewise. `emoji_slugs()` returns the union plus `emoji_pack.pack_slugs()`.

**(c) Unicode fold fallback.** Replace `_map_uemoji_to_slug`:

```python
def _map_uemoji_to_slug(chars: str) -> str | None:
    """Unicode-emoji → sprite-slug. Curated map first; then the pack via
    fold-to-first-base (spec fold rules). None = strip."""
    key = _emoji_key(chars)
    hit = _UNICODE_EMOJI_MAP.get(key)
    if hit is not None:
        return hit
    if not key:
        return None
    first = key[0]
    if "\U0001f1e6" <= first <= "\U0001f1ff":
        return None  # letter flags excluded
    return emoji_pack.slug_for_codepoint(ord(first))
```

(`_emoji_key` already stripped VS + tone; taking `key[0]` implements
ZWJ→first-base because ZWJ never sorts first in a valid sequence — add a
defensive `if first == "‍": return None`.)

**(d) Scanner allowlist.** In the `_UEMOJI_RE` construction, extend the
BMP base class: `_MAPPED_BMP` becomes `_MAPPED_BMP + _pack_bmp_class()`
where the helper `re.escape`s `PACK_BMP` for character-class use:

```python
_PACK_BMP_CLASS = re.escape(PACK_BMP)
```

and splice `_PACK_BMP_CLASS` into the same character classes that use
`_MAPPED_BMP`. Verify `_EMOJI_ASTRAL` covers the pack's astral range —
run: `uv run --no-sync python -c "from led_ticker.pixel_emoji import _uemoji_runs; print(list(_uemoji_runs('🚀🦞🪤🫠')))"` — all four must appear
(extend `_EMOJI_ASTRAL`'s ranges to `\U0001F300-\U0001FAFF` if any is
missed).

**Scale-1 strip (test `test_scale1_pack_slug_strips`):** in the lowres
fallback path (`icon = _get_registry()[slug]` sites), a pack-only slug is
absent from `_get_registry()` — change the two `KeyError`-intentional
lookups that a pack slug can now reach to `.get(slug)` + return-0/no-op
with a comment ("pack emoji are hires-only — silently skip at scale 1;
validate warns"). Keep genuine unknown-slug behavior for non-pack slugs
(guard with `emoji_pack.has_slug(slug)`).

- [ ] **Step 4: Run the new tests + the full emoji suite**

Run: `uv run --no-sync python -m pytest tests/test_pixel_emoji_pack_wiring.py tests/test_emoji_pack.py tests/test_emoji_pack_asset.py -q` → pass.
Run: `uv run --no-sync python -m pytest tests/ -q -k "emoji or pixel or sticker or slug or unicode"` → ALL pass (existing strip-behavior tests are the regression net for the fold rules).
Run the three lint gates.

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/pixel_emoji.py tests/test_pixel_emoji_pack_wiring.py
git commit --no-verify -m "feat(emoji-pack): wire pack into pixel_emoji — resolver, unicode fold, scanner, slugs"
```

---

### Task 4: Validate rule — hires-only emoji on a scale-1 display

**Files:**
- Modify: `src/led_ticker/validate.py`
- Test: `tests/test_validate.py` (append)

**Interfaces:**
- Consumes: `emoji_pack.has_slug`, `is_emoji_slug`, existing `_check_*` rule conventions (each returns `list[ValidationIssue]`, registered in the validator's rule list — follow `_check_typeless_transition_table` as the model, including its rule-numbering comment style; use the next free rule number).

- [ ] **Step 1: Write the failing test** (append to `tests/test_validate.py`, following that file's existing config-building idiom — reuse its helpers for constructing an `AppConfig` from TOML text):

```python
class TestHiresOnlyEmojiScale1:
    def test_pack_slug_on_scale1_warns(self, tmp_path):
        cfg = _write_config(
            tmp_path,
            """
            [display]
            rows = 16
            cols = 32
            chain_length = 5
            default_scale = 1

            [[playlist.section]]
            mode = "slideshow"
            [[playlist.section.widget]]
            type = "message"
            text = "liftoff :rocket:"
            """,
        )
        issues = _run_validate(cfg)
        warns = [i for i in issues if "rocket" in i.message and "scale 1" in i.message]
        assert warns and warns[0].severity == "warning"

    def test_same_config_scale4_no_warning(self, tmp_path):
        cfg = _write_config(
            tmp_path,
            """
            [display]
            rows = 32
            cols = 64
            chain_length = 8
            default_scale = 4

            [[playlist.section]]
            mode = "slideshow"
            [[playlist.section.widget]]
            type = "message"
            text = "liftoff :rocket:"
            """,
        )
        issues = _run_validate(cfg)
        assert not [i for i in issues if "rocket" in i.message]

    def test_curated_lowres_slug_scale1_no_warning(self, tmp_path):
        cfg = _write_config(
            tmp_path,
            """
            [display]
            rows = 16
            cols = 32
            chain_length = 5
            default_scale = 1

            [[playlist.section]]
            mode = "slideshow"
            [[playlist.section.widget]]
            type = "message"
            text = ":taco: tuesday"
            """,
        )
        issues = _run_validate(cfg)
        assert not [i for i in issues if "taco" in i.message]
```

(`_write_config` / `_run_validate`: use the file's actual helper names —
adapt plumbing, keep assertions.)

- [ ] **Step 2: Run to verify failure** — the warning doesn't exist yet.

- [ ] **Step 3: Implement the rule** in `validate.py` (model:
`_check_typeless_transition_table`; register it where the other rules run):

```python
def _check_hires_only_emoji_scale1(config: AppConfig) -> list[ValidationIssue]:
    """Rule N: a hires-only emoji slug on a scale-1 display never renders.

    Pack emoji (and any HIRES_REGISTRY-only slug) have no 8×8 sprite; at
    default_scale = 1 the draw path silently skips them. Warn with the
    slug + widget location so the surprise happens at validate time, not
    on the panel."""
    if config.default_scale > 1:
        return []
    from led_ticker.pixel_emoji import EMOJI_PATTERN, _get_registry, is_emoji_slug

    issues: list[ValidationIssue] = []
    lowres = _get_registry()
    for s_idx, section in enumerate(config.sections):
        for w_idx, widget in enumerate(section.widgets):
            for field in ("text", "top_text", "bottom_text"):
                val = getattr(widget, field, None) or (
                    widget.extra.get(field) if hasattr(widget, "extra") else None
                )
                if not isinstance(val, str):
                    continue
                for m in EMOJI_PATTERN.finditer(val):
                    slug = m.group(0)[1:-1]
                    if is_emoji_slug(slug) and slug not in lowres:
                        issues.append(
                            ValidationIssue(
                                severity="warning",
                                message=(
                                    f"section {s_idx + 1} widget {w_idx + 1}: "
                                    f":{slug}: is a hires-only emoji and this "
                                    f"display is scale 1 — it will not render"
                                ),
                                fix="Use a curated lowres emoji, or run on a scaled display.",
                            )
                        )
    return issues
```

(Adapt `ValidationIssue` construction + widget-field access to the file's
actual dataclass shapes — follow neighboring rules; the widget text may
live in raw cfg dicts rather than attributes.)

- [ ] **Step 4: Run** `uv run --no-sync python -m pytest tests/test_validate.py -q` → pass; full suite `-k "validate"` green; lint gates.

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/validate.py tests/test_validate.py
git commit --no-verify -m "feat(validate): warn on hires-only emoji slugs at scale 1"
```

---

### Task 5: Perf gates + docs + visual gate (HARD STOP for James)

**Files:**
- Modify: `tools/render_emoji_previews.py` (add pack contact-sheets), `docs/site/src/content/docs/assets/emoji.mdx`
- Scratch: `$CLAUDE_JOB_DIR/tmp/` benchmark + gate configs

- [ ] **Step 1: Perf benchmark (numbers for the PR body)**

Write + run `$CLAUDE_JOB_DIR/tmp/pack_perf.py`:

```python
import time

from led_ticker import emoji_pack

emoji_pack._reset_for_tests()
t0 = time.perf_counter()
ok = emoji_pack.load_index()
print(f"index load: {(time.perf_counter() - t0) * 1000:.1f}ms ok={ok} "
      f"entries={len(emoji_pack.pack_slugs())}")
slug = emoji_pack.slug_for_codepoint(0x1F680)
t0 = time.perf_counter()
emoji_pack.get_sprite(slug)
print(f"first sprite decode: {(time.perf_counter() - t0) * 1000:.2f}ms")
t0 = time.perf_counter()
for _ in range(1000):
    emoji_pack.get_sprite(slug)
print(f"cached lookup x1000: {(time.perf_counter() - t0) * 1000:.2f}ms")
```

Gate (spec): index < 50 ms, decode ms-class, cached lookup trivially fast. Record.

- [ ] **Step 2: Contact sheets + docs page**

Extend `tools/render_emoji_previews.py` with a `--pack-sheets` mode: group pack slugs by codepoint block (Smileys U+1F600-64F, Animals/Nature, Food U+1F32D-37F, Objects, Symbols, …), render each sprite at 32×32 into a labeled grid PNG per group → `docs/site/public/emoji/pack-<group>.png` (6–10 sheets, NOT 1,400 files). In `emoji.mdx`, after the curated table add:

```markdown
## Standard emoji

Beyond the curated set above, **any standard emoji** renders on hires
(scaled) displays — typed as real unicode (🚀) in widget text, or as its
CLDR-short-name slug (`:rocket:`). ~1,400 emoji ship in a lazy-loaded
pack derived from [Noto Emoji](https://github.com/googlefonts/noto-emoji)
(Apache 2.0). Skin-tone variants render as their base emoji; multi-person
(ZWJ) sequences fold to their first member; letter flags are not included.

**Scale-1 displays (smallsign):** standard emoji are hires-only — unicode
is stripped from the text, and `led-ticker validate` warns if a config
uses a hires-only `:slug:` at scale 1. The curated 8×8 set above is the
smallsign emoji set.
```

plus the sheet images. Prettier + `pnpm run build` in `docs/site` (72+ pages, exit 0 — `pnpm install` first if `@astrojs/sitemap` is missing in this checkout).

- [ ] **Step 3: Visual gate GIF**

Bigsign gate config (`$CLAUDE_JOB_DIR/tmp/pack-gate.toml`, lightning-gate shape): two slideshow sections, messages `"🚀 😂 🦞 🍕 ⚽ 💀"` and `"DEALS :rocket: :pizza: :skull:"` (substitute actual manifest slugs), Inter-Bold 30, `cut` transitions. Render via `uv run --no-sync python tools/render_demo/render.py ... --duration 8`, extract a contact sheet, CHECK IT YOURSELF (sprites at baseline, no tofu, correct advance/spacing), then **send the GIF to James and STOP**. Iterate on his feedback. Do not proceed to Task 6 without approval.

- [ ] **Step 4 (post-gate): Commit docs + previews**

```bash
git add tools/render_emoji_previews.py docs/site/public/emoji/pack-*.png docs/site/src/content/docs/assets/emoji.mdx
git commit --no-verify -m "docs(emoji): standard-emoji section + pack contact sheets"
```

---

### Task 6 (post-gate): Core PR

- [ ] **Step 1:** Full suite (`uv run --no-sync python -m pytest tests/ -q`) + all three lint gates + `pnpm run build` green.
- [ ] **Step 2:** Push `emoji-pack-spec`; `gh pr create` — body: what/why, the brainstorm decisions (broad-no-modifiers, all-slugs, curated-wins, hires-only, stickers cap deferred to flair), pack size + perf numbers table, fold rules, laziness guarantees, the visual-gate GIF, THIRD_PARTY_NOTICES generalization, and a "Release shape" note (core minor; flair patch companion follows). Include the standard "no merge without James" footer expectation. Watch `gh pr checks --watch`.
- [ ] **Step 3:** STOP — James reviews/merges; release is his call (`cut_release.py minor`).

---

### Task 7: Flair companion — stickers variety cap (after core PR opens; merge order per James)

**Files (led-ticker-plugins checkout, new branch `stickers-variety-cap` off origin/main):**
- Modify: `plugins/flair/src/led_ticker_flair/flair/stickers.py` (the random-pool site: `pool = self.emoji if self.emoji else list(emoji_slugs())` and the per-sticker `rng.choice(slugs)` planner)
- Test: `plugins/flair/tests/test_flair_stickers_transition.py` (append)

- [ ] **Step 1: Failing tests**

```python
class TestRandomVarietyCap:
    def test_random_mode_caps_distinct_slugs_per_firing(self, monkeypatch):
        import led_ticker_flair.flair.stickers as m

        # Pretend the drawable set is huge (the emoji-pack world).
        fake = tuple(f"pack_slug_{i}" for i in range(1400)) + ("taco",)
        monkeypatch.setattr(m, "emoji_slugs", lambda: fake)
        s = m.Stickers(seed=3)
        canvas = _StubCanvas(width=160, height=16)
        o = _make_widget(draw_pixel=False)
        i = _make_widget(draw_pixel=False)
        s.frame_at(0.5, canvas, o, i)  # forces plan
        distinct = {st.slug for st in s._stickers}
        assert 1 <= len(distinct) <= m._RANDOM_VARIETY_CAP

    def test_explicit_list_uncapped(self):
        explicit = ["taco", "sun", "moon", "star_yellow", "heart_red", "pride"]
        s = Stickers(emoji=list(explicit), seed=3)
        canvas = _StubCanvas(width=160, height=16)
        o = _make_widget(draw_pixel=False)
        i = _make_widget(draw_pixel=False)
        s.frame_at(0.5, canvas, o, i)
        assert {st.slug for st in s._stickers} <= set(explicit)

    def test_refire_resamples_variety(self, monkeypatch):
        import led_ticker_flair.flair.stickers as m

        fake = tuple(f"pack_slug_{i}" for i in range(1400))
        monkeypatch.setattr(m, "emoji_slugs", lambda: fake)
        s = m.Stickers()  # seedless
        canvas = _StubCanvas(width=160, height=16)
        o = _make_widget(draw_pixel=False)
        i = _make_widget(draw_pixel=False)
        s.frame_at(0.5, canvas, o, i)
        first = {st.slug for st in s._stickers}
        s.frame_at(0.96, canvas, o, i)
        s.frame_at(0.05, canvas, o, i)  # refire → replan
        s.frame_at(0.5, canvas, o, i)
        second = {st.slug for st in s._stickers}
        assert first != second  # 1400-choose-12 twice: collision ~impossible
```

(Adapt `s._stickers`/`.slug` to the actual planned-sticker field names in
`stickers.py` — keep assertions.)

- [ ] **Step 2:** RED → **Step 3:** implement — at the random-pool site:

```python
_RANDOM_VARIETY_CAP = 12  # distinct slugs per firing in random mode —
# chaos across firings, coherence within one (emoji-pack spec; the
# drawable set is ~1,400 slugs once core ships the standard-emoji pack)
```

```python
pool = self.emoji if self.emoji else list(emoji_slugs())
if not self.emoji and len(pool) > _RANDOM_VARIETY_CAP:
    pool = self._rng.sample(pool, _RANDOM_VARIETY_CAP)
```

(placed where the plan/replan builds its per-firing pool, so a refire
resamples; explicit lists bypass.)

- [ ] **Step 4:** Full flair suite + lint + pyright green. Commit on `stickers-variety-cap`, push, `gh pr create` — body notes: behavior change only once a pack-carrying core release is deployed; safe to merge any time (cap is set-size-agnostic); "Test on the sign" section per convention. STOP for James's merge word.
