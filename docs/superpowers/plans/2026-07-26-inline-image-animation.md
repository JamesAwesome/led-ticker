# Inline Image Animation (Phase 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Animated GIFs declared via `[[source]] type = "image"` animate inline at native GIF timing on scaled displays (hires-only; smallsign stays static frame 0), via registry frame-swapping at the `LedFrame.swap()` chokepoint.

**Architecture:** Registries keep holding ONLY static sprite types. Per-frame `HiResEmoji` sprites (layout-normalized to a union-extent `physical_width`) live in a private `_IMAGE_ANIMATIONS` table riding the existing stage/commit/abort/suspend lifecycle. `tick_image_animations()` — one guarded call at the top of `LedFrame.swap()` — bisects the cumulative-duration array per slug against a shared wall-clock epoch and swaps the current frame's sprite into `HIRES_REGISTRY` only when the index changed. `has_animated_emoji(text)` excludes the two image-overlay paint-once fast paths.

**Tech Stack:** Python, Pillow, pytest. Repo: core (`/Users/james/projects/github/jamesawesome/led-ticker`), branch `image-animation-spec`.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-25-inline-image-animation-design.md` (rev 2). HIRES-ONLY animation — `EMOJI_REGISTRY` keeps frame 0's lowres permanently; smallsign is static (validate note, no jitter).
- **Union-extent normalization (exact formula):** `physical_width = max over frames of (max_x_f + 1)`; pixels NOT origin-shifted; tripwire asserts no frame's rightmost lit pixel exceeds the applied width.
- **Tick semantics:** `now_ms = monotonic() * 1000` hoisted once per tick; per slug `elapsed = (now_ms - _ANIM_EPOCH_MS) % total_ms` → `bisect.bisect_right(cumulative, elapsed)`; O(slugs · log frames); dict write ONLY on index change; empty table = one truthiness check; the whole tick wrapped try/except-log-once (nothing in swap may raise).
- **Commit REBUILDS the animation table exactly** (clear all `_CONFIG_IMAGE_SLUGS` entries, insert only pending records) — the animated→static reload purge tripwire.
- **Caps, enforced at BOTH points:** frames > 24 → validate WARNING; frames > 60 → validate ERROR **and** `load_image_sprites` refusal (raise → caller's skip-with-log posture; never darks). Durations: `frame.info.get("duration", 100)`, min-clamped 20 ms.
- Fast-path exclusion: `pixel_emoji.has_animated_emoji(text) -> bool`; added as `and not has_animated_emoji(...)` to BOTH image-overlay gates (`_image_base.py` ~1725 single-row, ~2040 two-row). TickerMessage/two_row need no changes (engine redraws per tick).
- `LedFrame.swap()` gains the tick call — a documented non-paint responsibility; CLAUDE.md's overlay/idle invariant block gets one sentence.
- No `from __future__ import annotations`. Lint gates: `uv run --extra dev ruff check src/ tests/`, `ruff format --check`, `PYRIGHT_PYTHON_FORCE_VERSION=latest uv run --extra dev pyright src/` (2 pre-existing errors known-acceptable). Docs .mdx changes need `pnpm exec prettier --check` + `pnpm run build`. Tests: `uv run --no-sync python -m pytest`; known local failure `test_no_legacy_mode_names_in_live_tree` — ignore. Git hooks broken — `--no-verify`.
- Reviewers must NOT mutate tracked files (git show / throwaway copies). Task 5 = HARD STOP (James reviews bigsign-animated + smallsign-static gates). No merge without James.

---

### Task 1: Animation table + tick + lifecycle (pixel_emoji)

**Files:**
- Modify: `src/led_ticker/pixel_emoji.py` (beside the Phase-1 image-emoji block, ~line 3080)
- Test: `tests/test_image_animation.py` (new)

**Interfaces:**
- Produces: `@dataclass(frozen=True) class _ImageAnimation:` fields `hires_frames: tuple[HiResEmoji, ...]`, `cumulative_ms: tuple[int, ...]` (strictly increasing, last = total), `total_ms: int`; module state `_IMAGE_ANIMATIONS: dict[str, _ImageAnimation]`, `_ANIM_LAST_INDEX: dict[str, int]`, `_ANIM_EPOCH_MS: float` (module-load `monotonic()*1000`), `_PENDING_IMAGE_ANIMATIONS: dict[str, _ImageAnimation]`. Functions: `stage_image_emoji(slug, lowres, hires, animation: _ImageAnimation | None = None)` (backward-compatible), `tick_image_animations() -> None`, `has_animated_emoji(text: str) -> bool`, `frame_index_for(anim: _ImageAnimation, elapsed_ms: float) -> int` (pure, bisect). `commit_image_emoji` rebuilds `_IMAGE_ANIMATIONS`; `abort` clears pending animations; `suspend_image_emoji` pops the table into its snapshot (return type grows: `dict[slug, (lowres, hires, _ImageAnimation | None)]`) and the restore path re-stages with `animation=`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_image_animation.py`:

```python
"""Phase 2: the animation table, tick, and lifecycle."""

import pytest

from led_ticker import pixel_emoji
from led_ticker.pixel_emoji import (
    HiResEmoji,
    _ImageAnimation,
    abort_image_emoji,
    commit_image_emoji,
    frame_index_for,
    has_animated_emoji,
    stage_image_emoji,
    suspend_image_emoji,
    tick_image_animations,
)


def _hires(w=4):
    return HiResEmoji(
        pixels=tuple((x, y, 200, 0, 0) for x in range(w) for y in range(4)),
        physical_size=32,
        physical_width=w,
    )


_LOW = [(0, 0, 255, 0, 0)]


def _anim(n=3, dur=100):
    frames = tuple(_hires() for _ in range(n))
    cum = tuple(dur * (i + 1) for i in range(n))
    return _ImageAnimation(hires_frames=frames, cumulative_ms=cum, total_ms=cum[-1])


@pytest.fixture(autouse=True)
def _clean():
    abort_image_emoji()
    for slug in list(pixel_emoji._CONFIG_IMAGE_SLUGS):
        pixel_emoji.EMOJI_REGISTRY.pop(slug, None)
        pixel_emoji.HIRES_REGISTRY.pop(slug, None)
    pixel_emoji._CONFIG_IMAGE_SLUGS.clear()
    pixel_emoji._IMAGE_ANIMATIONS.clear()
    pixel_emoji._ANIM_LAST_INDEX.clear()
    yield


class TestFrameIndexFor:
    def test_table_driven(self):
        anim = _anim(3, 100)  # cum (100, 200, 300)
        for elapsed, expect in ((0, 0), (99, 0), (100, 1), (199, 1), (250, 2), (299, 2)):
            assert frame_index_for(anim, elapsed) == expect, elapsed

    def test_wraps_at_total(self):
        anim = _anim(3, 100)
        assert frame_index_for(anim, 300 % anim.total_ms) == 0


class TestLifecycle:
    def test_commit_lands_table_and_frame0(self):
        anim = _anim()
        stage_image_emoji("me.p", _LOW, anim.hires_frames[0], animation=anim)
        commit_image_emoji()
        assert pixel_emoji._IMAGE_ANIMATIONS["me.p"] is anim
        assert pixel_emoji.HIRES_REGISTRY["me.p"] is anim.hires_frames[0]

    def test_commit_purges_dead_entry_on_animated_to_static(self):
        anim = _anim()
        stage_image_emoji("me.p", _LOW, anim.hires_frames[0], animation=anim)
        commit_image_emoji()
        # reload: same slug, now STATIC (no animation record)
        static = _hires()
        stage_image_emoji("me.p", _LOW, static)
        commit_image_emoji()
        assert "me.p" not in pixel_emoji._IMAGE_ANIMATIONS  # table purged
        assert pixel_emoji.HIRES_REGISTRY["me.p"] is static

    def test_abort_drops_pending_animation(self):
        stage_image_emoji("me.p", _LOW, _hires(), animation=_anim())
        abort_image_emoji()
        commit_image_emoji()
        assert "me.p" not in pixel_emoji._IMAGE_ANIMATIONS

    def test_suspend_restore_round_trips_table(self):
        anim = _anim()
        stage_image_emoji("me.p", _LOW, anim.hires_frames[0], animation=anim)
        commit_image_emoji()
        snap = suspend_image_emoji()
        assert "me.p" not in pixel_emoji._IMAGE_ANIMATIONS  # suspended
        abort_image_emoji()
        for slug, (lowres, hires, animation) in snap.items():
            stage_image_emoji(slug, lowres, hires, animation=animation)
        commit_image_emoji()
        assert pixel_emoji._IMAGE_ANIMATIONS["me.p"] is anim


class TestTick:
    def test_tick_swaps_on_index_change_only(self, monkeypatch):
        anim = _anim(2, 100)  # frames at [0,100) and [100,200)
        stage_image_emoji("me.p", _LOW, anim.hires_frames[0], animation=anim)
        commit_image_emoji()
        t = {"now": pixel_emoji._ANIM_EPOCH_MS + 50}  # inside frame 0
        monkeypatch.setattr(pixel_emoji, "_now_ms", lambda: t["now"])
        tick_image_animations()
        before = pixel_emoji.HIRES_REGISTRY["me.p"]
        tick_image_animations()  # same frame -> no write
        assert pixel_emoji.HIRES_REGISTRY["me.p"] is before
        t["now"] += 100  # into frame 1
        tick_image_animations()
        assert pixel_emoji.HIRES_REGISTRY["me.p"] is anim.hires_frames[1]

    def test_lowres_never_swapped(self, monkeypatch):
        anim = _anim(2, 100)
        stage_image_emoji("me.p", _LOW, anim.hires_frames[0], animation=anim)
        commit_image_emoji()
        low_before = pixel_emoji._get_registry()["me.p"]
        t = {"now": pixel_emoji._ANIM_EPOCH_MS + 150}
        monkeypatch.setattr(pixel_emoji, "_now_ms", lambda: t["now"])
        tick_image_animations()
        assert pixel_emoji._get_registry()["me.p"] is low_before  # hires-only

    def test_empty_table_is_cheap_noop(self):
        tick_image_animations()  # must not raise, nothing registered


class TestHasAnimatedEmoji:
    def test_true_only_for_animated_slugs(self):
        anim = _anim()
        stage_image_emoji("me.p", _LOW, anim.hires_frames[0], animation=anim)
        stage_image_emoji("me.s", _LOW, _hires())  # static
        commit_image_emoji()
        assert has_animated_emoji("x :me.p: y")
        assert not has_animated_emoji("x :me.s: y")
        assert not has_animated_emoji("no tokens here")
```

- [ ] **Step 2: Run to verify failure** — `uv run --no-sync python -m pytest tests/test_image_animation.py -q` → ImportError.

- [ ] **Step 3: Implement** (in `pixel_emoji.py`, extending the Phase-1 block)

```python
import bisect  # add to the module imports (top of file) if absent


@dataclass(frozen=True)
class _ImageAnimation:
    """Per-slug animation record: layout-normalized hires frames + timing.

    `cumulative_ms` is strictly increasing; its last element == `total_ms`.
    Frames all share one `physical_width` (union extent — spec rev 2), so
    any frame measures identically: the F6 parity requirement holds by
    construction on the hires path. Lowres is NOT animated (smallsign shows
    frame 0; its advance is intrinsic to the pixels and would wobble)."""

    hires_frames: tuple[HiResEmoji, ...]
    cumulative_ms: tuple[int, ...]
    total_ms: int


_IMAGE_ANIMATIONS: dict[str, _ImageAnimation] = {}
_PENDING_IMAGE_ANIMATIONS: dict[str, _ImageAnimation] = {}
_ANIM_LAST_INDEX: dict[str, int] = {}
_ANIM_EPOCH_MS: float = time.monotonic() * 1000  # shared phase for all slugs
_ANIM_TICK_ERROR_LOGGED = False


def _now_ms() -> float:
    """Monkeypatch seam for the tick tests."""
    return time.monotonic() * 1000


def frame_index_for(anim: _ImageAnimation, elapsed_ms: float) -> int:
    """Pure: current frame index for an elapsed position in [0, total_ms)."""
    return min(
        bisect.bisect_right(anim.cumulative_ms, elapsed_ms),
        len(anim.hires_frames) - 1,
    )


def has_animated_emoji(text: str) -> bool:
    """True when any `:slug:` token in `text` is an ANIMATED image slug.

    Feeds the image-overlay fast-path gates: a paint-once path would freeze
    the sprite (the gif static-text freeze class), so animated slugs force
    the per-tick slow path. Static image slugs and everything else are
    unaffected."""
    if not _IMAGE_ANIMATIONS:
        return False
    return any(
        m.group(0)[1:-1] in _IMAGE_ANIMATIONS for m in EMOJI_PATTERN.finditer(text)
    )


def tick_image_animations() -> None:
    """Advance animated image slugs to their wall-clock frame.

    Called at the top of `LedFrame.swap()` — the single centralized swap
    point — so frames advance on every path that reaches the panel (engine
    ticks, play-widgets, transitions, idle keepalive). O(slugs · log frames)
    per call; writes `HIRES_REGISTRY` ONLY when a slug's index changed
    (hires-only: `EMOJI_REGISTRY` keeps frame 0's lowres — smallsign is
    static by design, spec rev 2). MUST NOT raise into swap: any error is
    swallowed and logged once."""
    global _ANIM_TICK_ERROR_LOGGED  # noqa: PLW0603
    if not _IMAGE_ANIMATIONS:
        return
    try:
        now = _now_ms()
        for slug, anim in _IMAGE_ANIMATIONS.items():
            elapsed = (now - _ANIM_EPOCH_MS) % anim.total_ms
            idx = frame_index_for(anim, elapsed)
            if _ANIM_LAST_INDEX.get(slug) != idx:
                HIRES_REGISTRY[slug] = anim.hires_frames[idx]
                _ANIM_LAST_INDEX[slug] = idx
    except Exception:
        if not _ANIM_TICK_ERROR_LOGGED:
            _ANIM_TICK_ERROR_LOGGED = True
            logging.getLogger(__name__).exception(
                "tick_image_animations failed — inline animation frozen"
            )
```

Extend the Phase-1 lifecycle functions:
- `stage_image_emoji(slug, lowres, hires, animation=None)`: also `if animation is not None: _PENDING_IMAGE_ANIMATIONS[slug] = animation`.
- `commit_image_emoji()`: after the existing removal loop add `for slug in list(_IMAGE_ANIMATIONS): _IMAGE_ANIMATIONS.pop(slug, None); _ANIM_LAST_INDEX.pop(slug, None)` — NOTE: only pop slugs that were in `_CONFIG_IMAGE_SLUGS`' old set... simplest correct form: since the table only ever holds config-image slugs, clear the WHOLE table + `_ANIM_LAST_INDEX` in the same place the old committed slugs are removed, then in the insert loop `if slug in _PENDING_IMAGE_ANIMATIONS and <slug inserted successfully>: _IMAGE_ANIMATIONS[slug] = _PENDING_IMAGE_ANIMATIONS[slug]`. Clear `_PENDING_IMAGE_ANIMATIONS` alongside `_PENDING_IMAGE_EMOJI` at the end.
- `abort_image_emoji()`: also clear `_PENDING_IMAGE_ANIMATIONS`.
- `suspend_image_emoji()`: snapshot entries become `(lowres, hires, _IMAGE_ANIMATIONS.get(slug))`; pop table entries + `_ANIM_LAST_INDEX` for suspended slugs. UPDATE THE CALLER: `validate.py`'s finally-restore loop unpacks the 3-tuple and passes `animation=`. (Grep `suspend_image_emoji()` — one call site in validate.py.)

- [ ] **Step 4: Run** — Task-1 tests + `tests/test_image_emoji_registration.py` + `tests/test_validate.py -q -k "Leak or ImageSource"` (the suspend-shape change must not break Phase-1 tests; update any that unpack the 2-tuple snapshot).

- [ ] **Step 5: Gates + commit**

```bash
git add src/led_ticker/pixel_emoji.py src/led_ticker/validate.py tests/test_image_animation.py tests/test_validate.py
git commit --no-verify -m "feat(emoji): animation table + wall-clock tick + lifecycle (Phase 2 core)"
```

---

### Task 2: Decode — layout-normalized frames + caps (sources)

**Files:**
- Modify: `src/led_ticker/sources.py` (`load_image_sprites` ~68, `ImageSource.prepare`)
- Test: `tests/test_image_source.py` (append)

**Interfaces:**
- Consumes: Task 1's `_ImageAnimation`, `stage_image_emoji(..., animation=)`.
- Produces: `load_image_sprites(path) -> tuple[PixelData, HiResEmoji, _ImageAnimation | None]` (THIRD element; None for static/single-frame). Frame caps: raises `ValueError("...exceeds 60 frames...")` for > 60 frames (caller's skip posture). `ImageSource.prepare()` passes `animation=` through.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_image_source.py`; reuse its `_png`/`_gif` helpers, add a multi-frame builder with controlled lit widths and durations)

```python
def _gif_frames(tmp_path, name, frames_spec):
    """frames_spec: list of (lit_width, duration_ms). 64x64 canvas,
    frame i lights columns [0, lit_width) rows [0, 8)."""
    from PIL import Image

    imgs = []
    for w, _d in frames_spec:
        im = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        for x in range(w):
            for y in range(8):
                im.putpixel((x, y), (255, 0, 0, 255))
        imgs.append(im.convert("P"))
    p = tmp_path / name
    imgs[0].save(
        p, save_all=True, append_images=imgs[1:],
        duration=[d for _w, d in frames_spec], disposal=2,
    )
    return p


class TestAnimatedDecode:
    def test_union_extent_applied_to_all_frames(self, tmp_path):
        from led_ticker.sources import load_image_sprites

        p = _gif_frames(tmp_path, "a.gif", [(16, 100), (64, 100), (32, 100)])
        _low, hires0, anim = load_image_sprites(p)
        assert anim is not None and len(anim.hires_frames) == 3
        widths = {f.physical_width for f in anim.hires_frames}
        assert len(widths) == 1  # every frame identical layout width
        # union EXTENT: no frame's rightmost lit pixel exceeds the width
        w = widths.pop()
        for f in anim.hires_frames:
            assert max((px[0] for px in f.pixels), default=0) < w

    def test_frame0_is_registry_sprite(self, tmp_path):
        from led_ticker.sources import load_image_sprites

        p = _gif_frames(tmp_path, "b.gif", [(16, 100), (64, 100)])
        _low, hires0, anim = load_image_sprites(p)
        assert hires0 is anim.hires_frames[0]

    def test_durations_cumulative_and_clamped(self, tmp_path):
        from led_ticker.sources import load_image_sprites

        p = _gif_frames(tmp_path, "c.gif", [(8, 5), (8, 250)])  # 5ms clamps to 20
        _low, _h, anim = load_image_sprites(p)
        assert anim.cumulative_ms == (20, 270) and anim.total_ms == 270

    def test_over_cap_refused(self, tmp_path):
        import pytest

        from led_ticker.sources import load_image_sprites

        p = _gif_frames(tmp_path, "d.gif", [(4, 30)] * 61)
        with pytest.raises(ValueError, match="60"):
            load_image_sprites(p)

    def test_static_png_returns_none_animation(self, tmp_path):
        from led_ticker.sources import load_image_sprites

        _low, _h, anim = load_image_sprites(_png(tmp_path))
        assert anim is None

    def test_prepare_stages_animation(self, tmp_path):
        from led_ticker import pixel_emoji
        from led_ticker.sources import ImageSource

        p = _gif_frames(tmp_path, "e.gif", [(8, 100), (16, 100)])
        ImageSource(id="me.anim", path=str(p)).prepare()
        assert "me.anim" in pixel_emoji._PENDING_IMAGE_ANIMATIONS
```

NOTE: Phase-1 callers of `load_image_sprites` unpack 2 values — update ALL call sites (grep: `ImageSource.prepare`, `validate.py`'s `_check_image_sources`) and any Phase-1 tests that unpack 2 (`tests/test_image_source.py` existing tests: change to `lowres, hires, _anim = ...`).

- [ ] **Step 2: Run to verify failure.**

- [ ] **Step 3: Implement** — rework `load_image_sprites`:

```python
_MAX_ANIM_FRAMES = 60
_MIN_FRAME_MS = 20


def load_image_sprites(path):
    """... (keep the Phase-1 docstring, extend:) For a multi-frame file,
    frames are decoded up to a hard cap of 60 (ValueError above it — the
    caller's skip posture applies) and every frame's HiResEmoji shares one
    physical_width = max over frames of (max_x + 1) (union EXTENT; pixels
    are NOT origin-shifted), so any frame measures identically. Returns
    (lowres, hires_frame0, animation-or-None). Memory note: frames are
    Python pixel tuples (~88 B each); the 60-frame cap bounds one slug at
    roughly 23 MB worst-case.  # Phase-2: bounded decode still a candidate
    """
    from PIL import Image  # noqa: PLC0415

    from led_ticker.pixel_emoji import HiResEmoji, _ImageAnimation  # noqa: PLC0415

    img = Image.open(path)
    n_frames = getattr(img, "n_frames", 1)
    if n_frames > _MAX_ANIM_FRAMES:
        raise ValueError(
            f"{path}: {n_frames} frames exceeds the {_MAX_ANIM_FRAMES}-frame "
            f"cap for inline animation"
        )

    frames_px: list[list[tuple[int, int, int, int, int]]] = []
    durations: list[int] = []
    for i in range(n_frames):
        img.seek(i)
        rgba = img.convert("RGBA")
        frames_px.append(_bake(rgba, 32, 128))  # the Phase-1 hires bake helper
        durations.append(max(int(img.info.get("duration", 100)), _MIN_FRAME_MS))
    img.seek(0)
    lowres = _bake(img.convert("RGBA"), 8, 8)

    # Union EXTENT across frames (spec rev 2): max (max_x + 1); no shifting.
    union_w = max(
        (max((p[0] for p in fpx), default=0) + 1 for fpx in frames_px), default=1
    )
    hires_frames = tuple(
        HiResEmoji(pixels=tuple(fpx), physical_size=32, physical_width=union_w)
        for fpx in frames_px
    )
    if n_frames == 1:
        return lowres, hires_frames[0], None
    cum: list[int] = []
    run = 0
    for d in durations:
        run += d
        cum.append(run)
    anim = _ImageAnimation(
        hires_frames=hires_frames, cumulative_ms=tuple(cum), total_ms=run
    )
    return lowres, hires_frames[0], anim
```

(Refactor the Phase-1 body so `_bake` is a module-level helper both paths share — it currently lives inline; keep behavior byte-identical for the static path.) `ImageSource.prepare()`: `lowres, hires, anim = load_image_sprites(self.path)` → `stage_image_emoji(self.id, lowres, hires, animation=anim)`.

- [ ] **Step 4: Run** — Task-2 + all Phase-1 image tests + `tests/test_validate.py -q -k ImageSource` (call-site updates).

- [ ] **Step 5: Gates + commit** — `git commit --no-verify -m "feat(sources): decode layout-normalized animation frames with caps (Phase 2)"`

---

### Task 3: Swap tick wiring + fast-path exclusion

**Files:**
- Modify: `src/led_ticker/frame.py` (`swap`, ~line 91)
- Modify: `src/led_ticker/widgets/_image_base.py` (both gates, ~1725 and ~2040)
- Modify: `CLAUDE.md` (one sentence in the Overlay hooks / Idle keepalive invariant area)
- Test: `tests/test_image_animation.py` (append), `tests/test_widgets/test_image_base.py` (append tripwire)

**Interfaces:**
- Consumes: Task 1's `tick_image_animations`, `has_animated_emoji`.
- Produces: every `LedFrame.swap()` advances animations; both image-overlay fast paths excluded for animated slugs.

- [ ] **Step 1: Failing tests**

Append to `tests/test_image_animation.py` (mirror `tests/test_frame.py`'s LedFrame construction idiom — read it first):

```python
class TestSwapTick:
    def test_swap_advances_a_due_animation(self, monkeypatch):
        # construct an LedFrame per tests/test_frame.py's idiom, commit an
        # animated slug, monkeypatch pixel_emoji._now_ms forward past frame 0,
        # call frame.swap(canvas), assert HIRES_REGISTRY[slug] is frame 1.
        ...

    def test_raising_tick_never_blocks_swap(self, monkeypatch):
        # monkeypatch pixel_emoji.tick_image_animations to raise via its
        # internals (patch _now_ms to raise); frame.swap() must still return
        # the swapped canvas (backend.swap called) — the guard swallows.
        ...
```

Write REAL bodies by copying the LedFrame/backend-stub setup from `tests/test_frame.py` (`TestGetCleanCanvasRecycling` shows the idiom). Append the freeze tripwire to `tests/test_widgets/test_image_base.py`, mirroring `test_gif_static_text_does_not_freeze_animation`'s structure:

```python
def test_still_image_with_animated_slug_not_frozen(...):
    # a StillImage widget whose text contains an animated image slug must
    # NOT take the paint-once fast path: has_animated_emoji(text) True ->
    # slow path -> pixels differ across two ticks with the clock advanced.
    ...
```

(Real body per that file's existing fast-path tests — they build the widget, drive `_play_with_text` ticks, compare canvases.)

- [ ] **Step 2: Verify failure.**

- [ ] **Step 3: Implement.** `frame.py` `swap()` — first line after `self._require_ready()`:

```python
        pixel_emoji.tick_image_animations()  # advance inline-image frames
        # (guarded internally — never raises into the swap; see the
        # CLAUDE.md swap-responsibilities invariant)
```

with a module-level `from led_ticker import pixel_emoji` (check frame.py's import style; a function-local import is fine if module-level creates a cycle — pixel_emoji does not import frame, so module-level should be safe; verify). Both `_image_base.py` gates: add `and not has_animated_emoji(<the text the gate governs>)` — single-row gate uses the widget's resolved overlay text (`text` in `_play_with_text`'s scope), two-row uses top+bottom (`has_animated_emoji(top_text) or has_animated_emoji(bottom_text)` — check the gate's in-scope variable names and use exactly those). Import from `led_ticker.pixel_emoji` alongside the file's existing pixel_emoji imports. CLAUDE.md: in the **Overlay hooks** invariant paragraph add: "`swap()` also carries two bookkeeping duties ahead of the hooks: `status_board.record_swap()` liveness and `pixel_emoji.tick_image_animations()` (inline-image frame advance, internally guarded — never raises)."

- [ ] **Step 4: Run** — new tests + `tests/test_frame.py` + `tests/test_widgets/test_image_base.py -q` (no fast-path regression) + full `-k "image or frame"`.

- [ ] **Step 5: Gates + commit** — `git commit --no-verify -m "feat(frame): swap-tick animation advance + image-overlay fast-path exclusion (Phase 2)"`

---

### Task 4: Validate — caps + rescoped warnings

**Files:**
- Modify: `src/led_ticker/validate.py` (`_check_image_sources`)
- Test: `tests/test_validate.py` (append/adjust)

**Interfaces:** Consumes Task 2's 3-tuple `load_image_sprites` + caps. Rule numbering unchanged (all under rule 70).

- [ ] **Step 1: Failing tests** (append; adjust the existing first-frame test):
  - frames > 24 → rule 70 WARNING (memory note).
  - frames > 60 → rule 70 ERROR (message names the cap).
  - The OLD unconditional "first frame" warning: now emitted ONLY for scale-1 sections referencing the slug ("animates on scaled displays; smallsign shows the first frame") — adjust the existing `test_animated_gif_warns_frame_zero` to pin the new scoping (scaled section → NO first-frame warning; scale-1 section → warning).
  - Aggregate: summed decoded-frame estimate across animated sources > ~64 MB → WARNING (build a config with three 61-frame... no — three ≤60-frame maximal GIFs is slow to generate; instead unit-test the helper `_animated_memory_estimate(sources) -> int` directly with synthetic `_ImageAnimation`-shaped counts, and one config-level smoke with a small threshold monkeypatched).
  - A valid animated config at scale 4 validates with 0 errors and NO first-frame warning.

Write real bodies per the file's `TestImageSourceValidate` idioms (Pillow-built fixtures in tmp).

- [ ] **Step 2: Verify failure.**
- [ ] **Step 3: Implement** in `_check_image_sources`: use the 3-tuple return; frame-count checks from the decode's `n_frames` probe (already present); the >60 ERROR comes from catching `load_image_sprites`' ValueError distinctly (match "frame") vs other decode errors; scale-1-scoped first-frame warning mirrors the existing scale-1 approximation warning's section-scale logic; `_animated_memory_estimate` = `sum(len(frames) × 4096 × 88)` (per-frame worst-case bytes) with the WARN threshold `64 * 1024 * 1024` as a module constant so tests can monkeypatch.
- [ ] **Step 4: Run** — full `tests/test_validate.py` green.
- [ ] **Step 5: Gates + commit** — `git commit --no-verify -m "feat(validate): animation frame caps + rescoped first-frame warning (Phase 2)"`

---

### Task 5: Docs + visual gate (HARD STOP for James)

**Files:**
- Modify: `docs/site/src/content/docs/assets/emoji.mdx` (the "first frame" sentence → animation semantics + caps + smallsign-static note)
- Modify: `docs/site/src/content/docs/concepts/value-tokens.mdx` (the image subsection's first-frame mention, if any)
- Scratch: `$CLAUDE_JOB_DIR/tmp/anim-gate/`

- [ ] **Step 1: Full suite + lint gates** (only the known local failure allowed); record counts.
- [ ] **Step 2: Docs.** emoji.mdx: replace "**Animated GIFs render as their first frame** for now — inline animation is a planned follow-up." with: "**Animated GIFs animate** on scaled displays — frames advance at the GIF's own timing, in phase everywhere the slug appears, even mid-scroll. Keep GIFs ≤ 24 frames for comfort (validate warns above that; > 60 frames is refused). On a scale-1 sign the sprite shows its first frame, static." Prettier + build.
- [ ] **Step 3: Gate renders.** Reuse the Phase-1 gate assets recipe (multicolor logo PNG + 2-frame arrow GIF with 300 ms frames, ABSOLUTE paths). Bigsign flat config: animated slug in (a) held and (b) scrolling text. Render ~4 s; build a contact sheet with TWO TIME-SEPARATED rows proving DIFFERENT frames (green up-arrow vs red down-arrow visible in different rows). Smallsign config: same sources; contact sheet proving the 8×8 stays frame 0 across time AND the text after the sprite does not shift horizontally between frames (crop-compare the columns right of the sprite). CHECK YOURSELF first.
- [ ] **Step 4: HARD STOP.** Send James both sheets + counts. No docs commit, no PR, until approved.
- [ ] **Step 5 (post-gate):** commit docs — `git commit --no-verify -m "docs(emoji): inline images animate on scaled displays (Phase 2)"`

---

### Task 6 (post-gate): PR

- [ ] **Step 1:** Push; `gh pr create`. Body: Phase-2 delivery of the original ask; the registry frame-swapping architecture (why zero consumption-site changes); hires-only + the lowres wobble finding that drove it; union-extent normalization + parity; the swap-tick invariant addition; caps + memory honesty; the antagonistic-review provenance (rev 2); both gates. Release = core minor.
- [ ] **Step 2:** `gh pr checks --watch`. STOP — James merges + releases.

---

## Self-review (done at write time)

- **Spec coverage:** §1 decode/union-extent/tripwire → T2; §2 table+purge → T1; §3 tick+swap+invariant-doc → T1/T3; §4 gates+tripwire → T3; §5 lifecycle (suspend 3-tuple, validate rescope) → T1/T4; §6 caps both points + aggregate + cache-leak note (documented in spec; no code) → T2/T4; Testing incl. parity (union-extent test in T2), animated→static purge (T1), swap integration (T3), visual gates (T5). Non-goals respected (no lowres animation, no plugin API).
- **Placeholder scan:** T3 Step 1 and parts of T4 Step 1 are contract-sketches pointing at named existing harnesses (`tests/test_frame.py`, the image-base fast-path tests, `TestImageSourceValidate`) — deliberate, as in prior plans; assertions are pinned, harness idioms must be copied from the live files.
- **Type consistency:** `_ImageAnimation(hires_frames, cumulative_ms, total_ms)` consistent T1/T2; `load_image_sprites -> (lowres, hires, anim|None)` consistent T2/T4 + call-site updates named; `stage_image_emoji(..., animation=None)` consistent T1/T2; `has_animated_emoji`/`tick_image_animations` consistent T1/T3.
