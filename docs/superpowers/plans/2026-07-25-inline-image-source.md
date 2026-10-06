# Inline Image Source (Phase 1, static) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `[[source]] type = "image"` declares a local PNG/GIF as a custom emoji slug — embed `:<id>:` inline anywhere emoji render; static only (GIF = frame 0), never darks the panel, atomic with reload.

**Architecture:** A declaration-only `ImageSource` (core source type) decodes the file at build time into the EXISTING sprite types (8×8 `PixelData` lowres + 32-px `HiResEmoji` hires) and STAGES them; a two-phase commit in `pixel_emoji` (stage/commit/abort) lands them in the emoji registries at the same point `set_data_registry` commits, so boot and reload are never torn. Zero new sprite polymorphism, zero fast-path/parity changes — the render path is untouched.

**Tech Stack:** Python, Pillow, attrs, pytest. Repo: core (`/Users/james/projects/github/jamesawesome/led-ticker`), branch `image-source-spec`.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-25-inline-image-source-design.md` (rev 2). Phase 1 is STATIC ONLY — a GIF contributes frame 0; no `AnimatedSprite`, no fast-path gate changes, no measure/draw changes (spec §4, §9).
- **Never dark the panel:** a bad image source LOGS + SKIPS at boot (inheriting `build_source_registry`'s per-source try/except) and reload keeps the old sources AND old emoji set atomically (spec §3). `led-ticker validate` is the loud surface.
- **Two-phase registration:** `stage_image_emoji` / `commit_image_emoji` / `abort_image_emoji` in `pixel_emoji`; commit happens at the SAME point `set_data_registry` commits (boot: `run.py` after `build_source_registry`; reload: `reload.py:224`). Commit refuses (skip+log) slugs already present from a non-image origin (curated-always-wins).
- **Widget-cache flush:** reload flushes the ENTIRE widget cache when the committed image slug set or any image source's resolved (path, mtime) changed (spec §2).
- Sprite forms: hires 32 px tall, width proportional capped at 128 px, RGBA alpha ≥ 110 keeps a pixel; lowres 8×8 resize. Existing types only: lowres `PixelData` (`list[tuple[int,int,int,int,int]]` of `(x, y, r, g, b)`), hires `HiResEmoji(pixels=..., physical_size=32)` (auto-trim computes `physical_width` at registry assembly for curated sprites — for image sprites pass `physical_width` explicitly from the lit bbox).
- Dotted ids encouraged; bare ids legal. Collision with ANY existing emoji slug (curated/pack/plugin) = validate ERROR + build-time skip-with-log.
- Path resolves against the config dir via the same convention as widget assets (`factories._resolve_asset_paths`, line ~593); `build_source` gains a `config_dir` param threaded from its two call sites (`run.py:432` area, `reload.py:215`).
- No `from __future__ import annotations`. Lint gates from repo root: `uv run --extra dev ruff check src/ tests/`, `uv run --extra dev ruff format --check src/ tests/`, `PYRIGHT_PYTHON_FORCE_VERSION=latest uv run --extra dev pyright src/` (2 pre-existing errors known-acceptable). Docs: `pnpm exec prettier --check` + `pnpm run build` in docs/site for any .mdx change.
- Tests: `uv run --no-sync python -m pytest`. Git hooks broken — `git commit/push --no-verify` after manual gates. Known local-only failure `test_no_legacy_mode_names_in_live_tree` — ignore.
- Task 5 ends at a HARD STOP: James reviews the bigsign AND smallsign visual gate before the PR (Task 6). No merge without his word.

---

### Task 1: Staged emoji registration surface (`pixel_emoji`)

**Files:**
- Modify: `src/led_ticker/pixel_emoji.py` (module-level, near `_get_registry` ~line 3056)
- Test: `tests/test_image_emoji_registration.py` (new)

**Interfaces:**
- Produces: `stage_image_emoji(slug: str, lowres: PixelData, hires: HiResEmoji) -> None`, `commit_image_emoji() -> None`, `abort_image_emoji() -> None`, module sets `_PENDING_IMAGE_EMOJI: dict[str, tuple[PixelData, HiResEmoji]]` and `_CONFIG_IMAGE_SLUGS: set[str]`. Task 2/3 call stage from `ImageSource` build and commit/abort from the boot/reload paths.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_image_emoji_registration.py`:

```python
"""Two-phase config-image emoji registration (stage/commit/abort)."""

import pytest

from led_ticker import pixel_emoji
from led_ticker.pixel_emoji import (
    HiResEmoji,
    abort_image_emoji,
    commit_image_emoji,
    stage_image_emoji,
)

_LOWRES = [(0, 0, 255, 0, 0), (1, 1, 0, 255, 0)]
_HIRES = HiResEmoji(
    pixels=tuple((x, y, 200, 200, 200) for x in range(4) for y in range(4)),
    physical_size=32,
    physical_width=4,
)


@pytest.fixture(autouse=True)
def _clean_registration():
    """Never leak staged/committed image slugs between tests."""
    abort_image_emoji()
    _wipe_committed()
    yield
    abort_image_emoji()
    _wipe_committed()


def _wipe_committed():
    for slug in list(pixel_emoji._CONFIG_IMAGE_SLUGS):
        pixel_emoji.EMOJI_REGISTRY.pop(slug, None)
        pixel_emoji.HIRES_REGISTRY.pop(slug, None)
    pixel_emoji._CONFIG_IMAGE_SLUGS.clear()


class TestStageCommit:
    def test_stage_alone_does_not_touch_registries(self):
        stage_image_emoji("cart.logo", _LOWRES, _HIRES)
        assert "cart.logo" not in pixel_emoji._get_registry()
        assert "cart.logo" not in pixel_emoji.HIRES_REGISTRY

    def test_commit_lands_both_forms_and_parse_gate_accepts(self):
        stage_image_emoji("cart.logo", _LOWRES, _HIRES)
        commit_image_emoji()
        assert pixel_emoji._get_registry()["cart.logo"] == _LOWRES
        assert pixel_emoji.HIRES_REGISTRY["cart.logo"] is _HIRES
        # lowres form present -> the 3-place parse gate accepts unchanged
        assert pixel_emoji.has_renderable_emoji("hi :cart.logo: there")

    def test_recommit_replaces_previous_set(self):
        stage_image_emoji("a", _LOWRES, _HIRES)
        commit_image_emoji()
        stage_image_emoji("b", _LOWRES, _HIRES)
        commit_image_emoji()
        reg = pixel_emoji._get_registry()
        assert "b" in reg and "a" not in reg  # old set swapped out

    def test_abort_drops_pending_keeps_committed(self):
        stage_image_emoji("keep", _LOWRES, _HIRES)
        commit_image_emoji()
        stage_image_emoji("drop", _LOWRES, _HIRES)
        abort_image_emoji()
        reg = pixel_emoji._get_registry()
        assert "keep" in reg and "drop" not in reg  # atomic reload semantics

    def test_commit_refuses_non_image_collision(self, caplog):
        # 'taco' is a curated slug — commit must skip it, log, and keep curated.
        curated = pixel_emoji._get_registry()["taco"]
        stage_image_emoji("taco", _LOWRES, _HIRES)
        commit_image_emoji()
        assert pixel_emoji._get_registry()["taco"] is curated
        assert "taco" not in pixel_emoji._CONFIG_IMAGE_SLUGS
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run --no-sync python -m pytest tests/test_image_emoji_registration.py -q`
Expected: FAIL — `ImportError: cannot import name 'stage_image_emoji'`.

- [ ] **Step 3: Implement** (in `pixel_emoji.py`, after `_get_registry`)

```python
# Config-declared image emoji ([[source]] type = "image") — two-phase so the
# registries commit atomically with set_data_registry: build STAGES, the
# boot/reload path COMMITS on overall success or ABORTS on failure. A failed
# reload therefore keeps BOTH the old sources and the old image slugs (never
# a torn half-set). See docs/superpowers/specs/2026-07-25-inline-image-source-design.md §2.
_PENDING_IMAGE_EMOJI: dict[str, tuple[PixelData, HiResEmoji]] = {}
_CONFIG_IMAGE_SLUGS: set[str] = set()


def stage_image_emoji(slug: str, lowres: PixelData, hires: HiResEmoji) -> None:
    """Buffer a config-image slug; no global mutation until commit."""
    _PENDING_IMAGE_EMOJI[slug] = (lowres, hires)


def abort_image_emoji() -> None:
    """Drop the pending set untouched (failed boot/reload build)."""
    _PENDING_IMAGE_EMOJI.clear()


def commit_image_emoji() -> None:
    """Swap the pending image slugs in: remove the previously committed set,
    insert the pending one. Refuses (skip + log) a slug already present from
    a non-image origin — curated/pack/plugin always win."""
    reg = _get_registry()  # materialize built-ins BEFORE collision checks
    for slug in _CONFIG_IMAGE_SLUGS:
        reg.pop(slug, None)
        HIRES_REGISTRY.pop(slug, None)
    _CONFIG_IMAGE_SLUGS.clear()
    for slug, (lowres, hires) in _PENDING_IMAGE_EMOJI.items():
        if slug in reg or slug in HIRES_REGISTRY or emoji_pack.has_slug(slug):
            logging.getLogger(__name__).error(
                "image source id %r collides with an existing emoji slug — "
                "skipped (use a dotted id like 'cart.%s')",
                slug,
                slug,
            )
            continue
        reg[slug] = lowres
        HIRES_REGISTRY[slug] = hires
        _CONFIG_IMAGE_SLUGS.add(slug)
    _PENDING_IMAGE_EMOJI.clear()
```

Check module imports: `emoji_pack` is already imported lazily/module-level in this file (grep `import emoji_pack` — reuse whatever form exists; the pack lookup degrades to False on a corrupt pack per its own contract). `logging` is imported.

- [ ] **Step 4: Run to verify pass** — the Step-1 tests + `uv run --no-sync python -m pytest tests/test_pixel_emoji.py -q` (no regression in the emoji suite).

- [ ] **Step 5: Gates + commit**

```bash
git add src/led_ticker/pixel_emoji.py tests/test_image_emoji_registration.py
git commit --no-verify -m "feat(emoji): staged config-image registration (stage/commit/abort)"
```

---

### Task 2: `ImageSource` + decode + boot wiring

**Files:**
- Modify: `src/led_ticker/sources.py` (new `ImageSource` after `StaticSource`)
- Modify: `src/led_ticker/app/factories.py` (`_SOURCE_TYPES` ~1462, `build_source` ~1484 gains `config_dir`)
- Modify: `src/led_ticker/app/run.py` (`build_source_registry` ~432: thread `config_dir`, commit after the loop)
- Test: `tests/test_image_source.py` (new)

**Interfaces:**
- Consumes: Task 1's `stage_image_emoji` / `commit_image_emoji`.
- Produces: `ImageSource(id=..., path=...)` (attrs, `type = "image"` in `_SOURCE_TYPES`); `sources.load_image_sprites(path: Path) -> tuple[PixelData, HiResEmoji]` (pure decode helper — Task 4's validate rule reuses it); `build_source(cfg, session=None, config_dir=None)`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_image_source.py`. Generate fixtures with Pillow in the tests (no binary fixtures in git):

```python
"""ImageSource: decode -> stage -> commit; boot never darks."""

from pathlib import Path

import pytest
from PIL import Image

from led_ticker import pixel_emoji
from led_ticker.pixel_emoji import abort_image_emoji
from led_ticker.sources import ImageSource, load_image_sprites


@pytest.fixture(autouse=True)
def _clean():
    abort_image_emoji()
    for slug in list(pixel_emoji._CONFIG_IMAGE_SLUGS):
        pixel_emoji.EMOJI_REGISTRY.pop(slug, None)
        pixel_emoji.HIRES_REGISTRY.pop(slug, None)
    pixel_emoji._CONFIG_IMAGE_SLUGS.clear()
    yield


def _png(tmp_path: Path, name="logo.png", size=(64, 64)) -> Path:
    img = Image.new("RGBA", size, (255, 0, 0, 255))
    p = tmp_path / name
    img.save(p)
    return p


def _gif(tmp_path: Path, name="anim.gif") -> Path:
    frames = [Image.new("RGB", (40, 40), c) for c in ((255, 0, 0), (0, 255, 0))]
    p = tmp_path / name
    frames[0].save(p, save_all=True, append_images=frames[1:], duration=100)
    return p


class TestLoadImageSprites:
    def test_png_builds_both_forms(self, tmp_path):
        lowres, hires = load_image_sprites(_png(tmp_path))
        assert lowres and all(len(px) == 5 for px in lowres)
        assert max(p[0] for p in lowres) <= 7 and max(p[1] for p in lowres) <= 7
        assert hires.physical_size == 32
        assert hires.pixels  # opaque red square -> fully lit
        assert hires.physical_width and hires.physical_width <= 128

    def test_gif_uses_frame_zero(self, tmp_path):
        lowres, hires = load_image_sprites(_gif(tmp_path))
        # frame 0 is red; every lit pixel red-dominant
        assert all(px[2] > px[3] for px in hires.pixels)  # r > g

    def test_wide_image_caps_at_128(self, tmp_path):
        _, hires = load_image_sprites(_png(tmp_path, size=(1000, 40)))
        assert max(p[0] for p in hires.pixels) <= 127

    def test_transparent_pixels_dropped(self, tmp_path):
        img = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
        img.putpixel((0, 0), (255, 255, 255, 255))
        p = tmp_path / "dot.png"
        img.save(p)
        lowres, hires = load_image_sprites(p)
        assert len(hires.pixels) < 32 * 32  # alpha<110 dropped

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(Exception, match="no-such"):
            load_image_sprites(tmp_path / "no-such.png")


class TestImageSourceStaging:
    def test_build_stages_but_does_not_commit(self, tmp_path):
        src = ImageSource(id="cart.logo", path=str(_png(tmp_path)))
        src.prepare()  # decode + stage
        assert "cart.logo" in pixel_emoji._PENDING_IMAGE_EMOJI
        assert "cart.logo" not in pixel_emoji._get_registry()

    def test_compute_returns_literal_token(self, tmp_path):
        # Defensive value if token resolution ever sees it (it should not:
        # is_emoji_slug excludes registered slugs from _candidate_ids).
        src = ImageSource(id="cart.logo", path=str(_png(tmp_path)))
        assert src.compute() == ":cart.logo:"
```

Plus boot-path tests appended to the same file (read `run.py`'s `build_source_registry` at ~432 first and mirror its call idiom):

```python
class TestBootWiring:
    def test_bad_image_source_skips_not_raises(self, tmp_path):
        # build_source_registry's per-source try/except must swallow a
        # decode failure: the registry builds, the panel boots.
        from led_ticker.app.run import build_source_registry
        from led_ticker.config import SourceConfig  # match actual ctor shape

        good = SourceConfig(type="static", id="ok", options={"value": "x"})
        bad = SourceConfig(
            type="image", id="broken", options={"path": str(tmp_path / "nope.png")}
        )
        reg = build_source_registry([good, bad], session=None)
        assert reg.get("ok") is not None
        assert reg.get("broken") is None  # skipped, not fatal
```

(Adapt `SourceConfig` construction to its real shape — read `src/led_ticker/config.py`'s SourceConfig and match how existing tests build it; grep `SourceConfig(` in `tests/`.)

- [ ] **Step 2: Run to verify failure** — `ImportError: ImageSource`.

- [ ] **Step 3: Implement**

In `sources.py` (after `StaticSource`; Pillow import must be function-local — sources.py currently has no PIL dependency at module import and the render path shouldn't gain one):

```python
def load_image_sprites(path):
    """Decode an image file into the two inline-sprite forms.

    Returns ``(lowres, hires)``: an 8x8 ``PixelData`` and a 32-px-tall
    ``HiResEmoji`` (width proportional, capped at 128 px; RGBA alpha >= 110
    keeps a pixel — the Noto bake recipe). A GIF contributes frame 0 only
    (Phase 1 is static; inline animation is the planned follow-up).
    Raises on a missing/undecodable file — the CALLER decides posture
    (build_source_registry skips + logs; validate errors loudly).
    """
    from PIL import Image  # noqa: PLC0415

    from led_ticker.pixel_emoji import HiResEmoji  # noqa: PLC0415

    img = Image.open(path)  # frame 0 of a multi-frame file by default
    img = img.convert("RGBA")

    def _bake(im, target_h, cap_w):
        w = max(1, round(im.width * target_h / im.height))
        if w > cap_w:
            im2 = im.resize((cap_w, target_h), Image.Resampling.LANCZOS)
        else:
            im2 = im.resize((w, target_h), Image.Resampling.LANCZOS)
        px = im2.load()
        return [
            (x, y, *px[x, y][:3])
            for y in range(im2.height)
            for x in range(im2.width)
            if px[x, y][3] >= 110
        ]

    hires_pixels = _bake(img, 32, 128)
    lowres = _bake(img, 8, 8)
    lit_w = (max(p[0] for p in hires_pixels) + 1) if hires_pixels else 1
    hires = HiResEmoji(
        pixels=tuple(hires_pixels), physical_size=32, physical_width=lit_w
    )
    return lowres, hires


@attrs.define(eq=False)
class ImageSource(DataSource):
    """Declaration-only source: registers a config-declared image as an
    inline emoji slug (`:id:`). No polling, no monitor entry. `prepare()`
    decodes + STAGES (pixel_emoji.stage_image_emoji); the boot/reload path
    commits atomically alongside set_data_registry. `compute()` returns the
    literal token as a defensive value — once the slug is committed,
    `is_emoji_slug` excludes it from TokenizedField._candidate_ids and the
    emoji parser owns the token outright."""

    path: str = ""

    def prepare(self) -> None:
        from led_ticker.pixel_emoji import stage_image_emoji  # noqa: PLC0415

        lowres, hires = load_image_sprites(self.path)
        stage_image_emoji(self.id, lowres, hires)

    def compute(self) -> str:
        return f":{self.id}:"
```

(Match `DataSource`'s actual attrs field set — read `sources.py:28-60` for how `id` is declared; mirror `StaticSource`'s pattern exactly.)

In `app/factories.py`: add `"image": ImageSource` to `_SOURCE_TYPES` (~1462); extend `build_source(cfg, session=None, config_dir=None)`: after instantiating, if the source is an `ImageSource`, resolve a relative `path` against `config_dir` (same semantics as `_resolve_asset_paths`, line ~593 — reuse or mirror its logic) and call `source.prepare()`. A raise from `prepare()` propagates — the CALLER's per-source try/except gives the skip posture.

In `app/run.py`: thread `config_dir` into `build_source_registry` → `build_source` (the boot call site already has the config dir in scope — grep `config_dir` around run.py:192/374 for the variable to pass), and after the build loop call `commit_image_emoji()` (import from `led_ticker.pixel_emoji`). Boot order note: `build_source_registry` runs before widget construction (run.py ~980), preserving the spec §1 ordering invariant — assert nothing, but say so in a comment.

- [ ] **Step 4: Run to verify pass** — Task 2 tests + `tests/test_image_emoji_registration.py` + the sources/token suites: `uv run --no-sync python -m pytest tests/test_image_source.py tests/test_image_emoji_registration.py -q -k ""` and `-k "source or token"` broad pass.

- [ ] **Step 5: Gates + commit**

```bash
git add src/led_ticker/sources.py src/led_ticker/app/factories.py src/led_ticker/app/run.py tests/test_image_source.py
git commit --no-verify -m "feat(sources): image source — config-declared inline emoji (static, boot wiring)"
```

---

### Task 3: Reload atomicity + widget-cache flush

**Files:**
- Modify: `src/led_ticker/reload.py` (the source-rebuild block ~206-224 + the widget-cache eviction ~188)
- Test: `tests/test_image_source_reload.py` (new)

**Interfaces:**
- Consumes: Task 1's commit/abort; Task 2's `ImageSource`/`build_source(config_dir=)`.
- Produces: reload semantics — stage-during-temp-build, `commit_image_emoji()` immediately before `set_data_registry(new_reg)` (reload.py:224), `abort_image_emoji()` in the existing atomic-failure branch (~219); a full `widget_cache.clear()` when the new config's image-source set (ids + resolved paths + mtimes) differs from the old.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_image_source_reload.py`. Read `tests/` for the existing reload-test idiom first (grep `_apply_reload\|reload` in tests — e.g. `tests/test_hot_reload*.py`) and mirror how they build old/new configs and invoke the reload function. The three behaviors to pin:

```python
class TestReloadAtomicity:
    def test_failed_reload_keeps_old_image_slugs(self, ...):
        # old config: image source A (committed). new config: A' (valid) + B (missing file).
        # reload fails atomically -> registry keeps old sources AND slug A
        # still renders; nothing from A'/B applied.
        ...

    def test_successful_reload_swaps_slug_set(self, ...):
        # old: A. new: B. after reload: B renders, A is gone (recommit swap).
        ...

class TestWidgetCacheFlush:
    def test_image_source_change_flushes_widget_cache(self, ...):
        # widget text references :b: but widget config unchanged between
        # old/new; adding image source B must clear widget_cache so the
        # reconstructed widget sees _has_emoji=True.
        ...
```

Write these as REAL tests against the actual reload entry point (the `...` above is for THIS plan's brevity only because the reload harness idiom must be copied from the existing reload tests — the implementer fills bodies by mirroring `tests/test_hot_reload*.py` setup verbatim; the three assertions above are the contract). If the existing harness can't express one of them, say so in the report rather than watering the assertion down.

- [ ] **Step 2: Run to verify failure.**

- [ ] **Step 3: Implement** (in `reload.py`)

In the rebuild loop block (~206-224): `build_source` calls now pass `config_dir` (the reload path has it in scope — grep). In the exception branch that returns keeping old sources (~219): add `abort_image_emoji()`. Immediately before `set_data_registry(new_reg)` (~224): add `commit_image_emoji()`. Import both from `led_ticker.pixel_emoji` in the function-local import block (~178).

Widget-cache flush: before/after the source rebuild, compute `old_image_set` and `new_image_set` as `{(id, resolved_path, mtime)}` from each config's `[[source]]` entries with `type == "image"` (mtime via `Path.stat().st_mtime_ns`, 0 when missing). If they differ, `widget_cache.clear()` (the dict passed at reload.py:154) with one INFO log ("image sources changed — widget cache flushed"). Place it so the flush happens ONLY on a successful reload (same success path as the commit).

- [ ] **Step 4: Run to verify pass** — new tests + the full reload suite: `uv run --no-sync python -m pytest tests/ -q -k "reload or image"`.

- [ ] **Step 5: Gates + commit**

```bash
git add src/led_ticker/reload.py tests/test_image_source_reload.py
git commit --no-verify -m "feat(reload): image emoji commit atomic with set_data_registry + widget-cache flush"
```

---

### Task 4: Validate rules

**Files:**
- Modify: `src/led_ticker/validate.py` (extend rule 56 ~202/223; new rule 70)
- Test: `tests/test_validate.py` (append)

**Interfaces:**
- Consumes: Task 2's `load_image_sprites` (same decode path = preflight sees what boot renders); rule numbering — 69 is the current max, image rules take **70**.
- Produces: extended rule-56 messaging + rule 70 (`_check_image_sources`).

- [ ] **Step 1: Write the failing tests** (append to `tests/test_validate.py`, using the `conf` fixture + async `validate_config` idiom used by `TestGlyphCoverage`; build tiny real image files with Pillow into `tmp_path` and point `path` at them — the `conf` fixture writes the config into `tmp_path` so relative `assets/...` paths can anchor there, mirroring how existing asset-path tests do it, grep `_resolve_asset_paths` usage in tests):

```python
class TestImageSourceValidate:
    async def test_missing_file_errors(self, conf): ...          # rule 70 ERROR names the path
    async def test_collision_names_origin_and_suggests_dotted(self, conf): ...
        # id="taco" -> ERROR contains "pack" or "curated" origin wording AND "cart.taco"-style dotted suggestion (rule 56 extension)
    async def test_same_config_source_id_collision(self, conf): ...
        # type="clock" id="x" + type="image" id="x" -> ERROR (rule 56 extension)
    async def test_animated_gif_warns_frame_zero(self, conf): ...  # rule 70 WARNING "first frame"
    async def test_scale1_section_warns_approximate(self, conf): ...  # rule 70 WARNING on 8x8 approximation
    async def test_dangling_image_source_warns(self, conf): ...  # declared, no widget text references :id: -> WARNING
    async def test_oversized_source_warns(self, conf): ...       # frame area > 512x512 -> WARNING
    async def test_valid_image_config_is_clean_and_token_not_unknown(self, conf): ...
        # registers via the same decode path BEFORE token checks: a config whose
        # only emoji is an image slug validates with 0 errors (ordering invariant)
```

Write full bodies following the file's established `_HIRES_CFG`-style templates (each test = one small TOML string + `validate_config` + an assertion on `result.errors` / `result.warnings` filtered by `rule`). Every assertion must be non-vacuous: positive tests assert the rule number IS present, negative tests assert it is NOT, on configs that genuinely reach the phase (rows=64 geometry — the rule-1-suppression trap from the glyph-ladder work).

- [ ] **Step 2: Run to verify failure.**

- [ ] **Step 3: Implement**

`_check_image_sources(config, config_dir) -> tuple[errors, warnings]` (rule 70): for each `[[source]]` with `type == "image"` — missing/undecodable file → ERROR (decode via `load_image_sprites`, catching its raise); Pillow `n_frames > 1` → WARNING ("renders as its first frame; inline animation is a planned follow-up"); source frame area > 512×512 → WARNING; no widget text containing `:id:` → WARNING (scan the same `text`/`top_text`/`bottom_text` fields rule 68 walks); any section with scale 1 whose text references the id → WARNING (8×8 approximation). On successful decode, STAGE + COMMIT the slugs before validate's token/widget checks run (mirror boot ordering; validate is a one-shot process so committed slugs are fine — but run `_check_image_sources` BEFORE the token-unknown checks in the runner ordering). Extend rule 56's existing `is_emoji_slug(src.id)` branch (~202/223): when the source is an image source, the message becomes the tailored one ("id 'X' collides with an existing emoji slug (<origin: curated/pack/plugin>) — use a dotted id like 'cart.X'"); add the same-config cross-type id collision check (two `[[source]]` entries sharing an id where at least one is an image).

- [ ] **Step 4: Run** — `uv run --no-sync python -m pytest tests/test_validate.py -q` (full file green, no regression).

- [ ] **Step 5: Gates + commit**

```bash
git add src/led_ticker/validate.py tests/test_validate.py
git commit --no-verify -m "feat(validate): rule 70 image sources + rule 56 image-tailored collisions"
```

---

### Task 5: Docs + visual gate (HARD STOP for James)

**Files:**
- Modify: `docs/site/src/content/docs/assets/emoji.mdx` ("Your own images as emoji" section)
- Modify: `docs/site/src/content/docs/concepts/value-tokens.mdx` (pointer)
- Modify: `config/config.halal-cart.example.toml` (commented-out image-source block)
- Modify: `.claude/skills/creating-a-config` fact-packs IF a sources/emoji fact-pack exists (`docs/content-source/` — check; skip with a note if not)
- Scratch: `$CLAUDE_JOB_DIR/tmp/image-source-gate*.{toml,gif,png}`

- [ ] **Step 1: Full suite + lint gates.** `uv run --no-sync python -m pytest tests/ -q` (only the known local failure) + the three lint gates. Record counts.

- [ ] **Step 2: Docs.** emoji.mdx section: the 4-line TOML example (dotted id), where files go (`config/assets/` + the honest file-placement walkthrough: scp/SMB/USB; the web UI has no asset upload today — future work), sizing (32 px hires / 8×8 lowres approximation on smallsign), GIF = first frame (animation planned), collision note (dotted ids). value-tokens.mdx: one paragraph + link ("declaring an image? see the emoji page"). halal example: commented block near the other `[[source]]`s. Prettier + `pnpm run build` (expect all pages, exit 0).

- [ ] **Step 3: The gate renders.** Two configs: bigsign flat (rows=64/cols=256/chain=1/scale=4) and smallsign (rows=16/cols=160/chain=1/scale=1); each declares a generated logo PNG (`Pillow`-drawn multicolor mark, saved under the render config's dir in `assets/`) + one animated GIF source, embeds both in (a) a scrolling message and (b) a held message. Render both with `tools/render_demo/render.py`; build contact sheets. CHECK YOURSELF: bigsign shows the 32-px sprite inline both modes; GIF shows frame 0; smallsign shows the 8×8 approximation (present, legibly-approximate); no `?`, no literal `:token:` text.

- [ ] **Step 4: HARD STOP.** Send James both sheets + the suite counts. Do NOT commit docs or open the PR until approved.

- [ ] **Step 5 (post-gate): Commit docs + example.**

```bash
git add docs/site/src/content/docs/assets/emoji.mdx docs/site/src/content/docs/concepts/value-tokens.mdx config/config.halal-cart.example.toml
git commit --no-verify -m "docs(emoji): your own images as inline emoji — image source docs + example"
```

---

### Task 6 (post-gate): PR

- [ ] **Step 1:** Push `image-source-spec`; `gh pr create`. Body: the ask (custom emoji from config); the `[[source]] type="image"` surface + dotted-id convention; static-first phasing (animation = recorded Phase 2 with its findings); the two-phase registration atomic with reload + widget-cache flush; never-darks posture; rule 70 + rule-56 extension; the hostile-review provenance (ENG+PM findings shaped rev 2); both visual gates. Release = core minor.
- [ ] **Step 2:** `gh pr checks --watch`. STOP — James merges + releases.

---

## Self-review (done at write time)

- **Spec coverage:** §1 ImageSource/ordering → T2; §2 stage/commit/abort + cache flush → T1/T3; §3 posture → T2 (boot skip) + T3 (atomic reload); §4 static-only → global constraint (no render-path task exists, by design); §5 collisions → T1 (commit refusal) + T4 (rule 56); §6 validate → T4; §7 docs → T5; §8 tests → T1–T5; §9 Phase 2 → explicitly none. Non-goals respected.
- **Placeholder scan:** T3 Step 1 and T4 Step 1 use contract-sketches with explicit instructions to mirror named existing test harnesses (reload tests / TestGlyphCoverage) rather than full verbatim bodies — deliberate: those harness idioms must be copied from the live files, and a fabricated harness here would be wrong. Each sketch pins the exact assertions required. All implementation code is complete.
- **Type consistency:** `stage_image_emoji(slug, lowres: PixelData, hires: HiResEmoji)` consistent across T1 def / T2 caller; `load_image_sprites(path) -> (PixelData, HiResEmoji)` consistent T2 def / T4 consumer; `build_source(cfg, session=None, config_dir=None)` consistent T2/T3; rule numbers 56/70 consistent.
