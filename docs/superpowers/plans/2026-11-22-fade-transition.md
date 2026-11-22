# `fade` transition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `transition = "fade"` crossfades outgoing into incoming by snapshotting both widgets into readable rasters and blending in Pillow; `transition_color = [r, g, b]` turns it into a dip through that colour; `fade` joins the default `random` / `auto` pool; every existing transition stays byte-identical.

**PR shape (roadmap process: DRY refactors ship in a precursor PR attached to the seam's first consumer):**
- **PR A, branch `fade-precursor` off `origin/main`:** Tasks 1-6. Behaviour-free for every existing config. Its own antagonist loop.
- **PR B, branch `fade-transition` STACKED on A:** Tasks 7-10. Draft PR with base = A's branch; rebase onto `origin/main` and retarget after A merges. The hardware check deploys THIS branch (pushed).
- Worktree: `../led-ticker-wt-fade`. Every subagent verifies `pwd` + `git branch --show-current` before any git op. The design doc, the design-loop ledger and this plan are UNTRACKED in the main checkout: copy all three into the worktree when it is created and edit only those copies from then on (Hardware findings included).

**Architecture:** `PixelBuffer` (`rotate.py`) gains the canvas surface widgets paint through (`Clear` / `Fill` / `SetImage`), so `Fade.frame_at` can draw each widget once into a wrapped buffer, convert to a Pillow RGB image, and `SetImage` one `Image.blend` per frame onto the real canvas. The runner forwards three kwargs it already holds; the meta wrapper forwards `end_firing` so pooled fades release their snapshots; two breaker helpers let the fade trip a widget whose bad pixel values only surface at conversion. Colour-shape validation moves to a leaf module so the transitions package can import it without a cycle.

**Tech Stack:** Python 3.14, Pillow 13 (`Image.frombytes`, `Image.blend`, `Image.new`, `tobytes`; NOT `getdata`), pytest (`canvas`, `mock_frame`, `make_widget`, `no_sleep`, `bigsign_canvas`, `caplog`, `monkeypatch`), `uv run`.

**Spec:** `docs/superpowers/specs/2026-11-21-fade-design.md` (APPROVED 2026-11-22 via the design antagonist loop; ledger `docs/superpowers/reviews/2026-11-22-fade-design-antagonist.md`; gate `docs/superpowers/specs/2026-11-20-fade-gate.md`, local-only).

## Global Constraints

- Every existing transition and every existing config render byte-identically after PR A; PR B changes only configs that name `fade` or run a default pool.
- The fade's OWN code never raises out of `frame_at`: every image it holds is mode `RGB` and size `(real.width, real.height)`; a malformed colour raises in the constructor (guarded builder cuts); widget-sourced bad pixels trip the widget inside `_snapshot`.
- No `GetPixel` on real canvases; no `create_canvas`; the snapshot target is an OWNED `PixelBuffer`. `rotate.py` imports no Pillow.
- `fade.py` imports `rgb_shape_error` from `led_ticker.colors`, never from `led_ticker.app.*` (circular import through the transitions auto-import loop).
- `API_VERSION` bump = the next unclaimed minor: `(1, 5)` while PR #561 (`fix/image-play-settle-seam`, claims `(1, 4)`) is open. Re-check `git branch -r` + open PRs before merging PR A. Plugins probe with `>=`; tests pin `>=`.
- `min_frames = 8`. Blend factor `k = min(1.0, max(0.0, t))`. Dip: `k < 0.5 -> blend(out, through, 2k)` else `blend(through, in, 2k - 1)`.
- Default pool grows 15 -> 16; `fade` sorts between `dissolve` and `push_down`. Registry count 23 -> 24.
- `[dev]` tooling: `uv run pytest`, `uv run ruff check`, `uv run ruff format`, `PYRIGHT_PYTHON_FORCE_VERSION=latest uv run pyright` before push. No `from __future__ import annotations`. TDD per step; commit BEFORE any mutation check.
- Docs follow `docs/DOCS-STYLE.md`; the `TomlExample` beside a `DemoGif` is copied character-for-character from the demo TOML (hard rule, line 107).
- `gh pr create` and every `gh pr merge` need James's fresh per-PR go. PRs open as drafts.

## Review Focus

Inputs the spec implies but no task's tests exercise directly; each gets the named test in the owning task:

1. A plugin widget (not core) whose `draw()` reads `canvas.real` or calls a method `PixelBuffer` lacks: the fade must trip and complete, never raise (Task 7: `test_snapshot_widget_missing_canvas_method_trips_and_completes`, a stub widget calling `canvas.NoSuchMethod()`).
2. A `random` pool whose current child is `fade` when the process is cancelled mid-firing: `end_firing` still releases the snapshots (Task 5 + Task 7: `test_cancel_mid_fade_releases_snapshots`).
3. `transition_fps = 60` with `duration = 0.1`: `min_frames` floors at 8 frames (0.13 s), not 0.4 s; the docs floor wording says "at 20 fps" (Task 7: `test_min_frames_floor_is_tick_relative`).
4. A `fade` entry into a section whose incoming widget is schedule-filtered to nothing (`incoming` is a guard around a widget that draws nothing): t = 1 frame equals the incoming bg, not stale pixels (Task 7: `test_incoming_that_draws_nothing_fades_to_bg`).
5. A 160x16 smallsign at scale 1 with a 16-row `content_height` (no wrapper at all): live geometry is `None` and the buffer is drawn into directly (Task 7: `test_unwrapped_canvas_snapshots_directly`).

---

### Task 1: `rgb_shape_error` moves to a leaf module; import tripwires

**Files:**
- Modify: `src/led_ticker/colors.py` (add the function, no new imports beyond `typing.Any`)
- Modify: `src/led_ticker/app/coercion.py:863-878` (delete the body, add `from led_ticker.colors import rgb_shape_error  # noqa: F401 - re-export for validate/factories`, keep the name in the module)
- Modify: `src/led_ticker/validate.py:1553` (docstring: "`coercion.rgb_shape_error`" -> "`colors.rgb_shape_error`, re-exported by `app.coercion`")
- Test: `tests/test_coercion_rgb_shape.py` (existing; add one import-path assertion), `tests/test_import_cycles.py` (new)

**Interfaces:**
- Produces: `led_ticker.colors.rgb_shape_error(value: Any) -> str | None` (identical semantics: `None` iff list/tuple of exactly three non-bool ints 0..255). `led_ticker.app.coercion.rgb_shape_error` is the same object.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_coercion_rgb_shape.py (append)
def test_rgb_shape_error_lives_in_colors_and_is_reexported():
    from led_ticker import colors
    from led_ticker.app import coercion
    assert coercion.rgb_shape_error is colors.rgb_shape_error

# tests/test_import_cycles.py (new)
import os, subprocess, sys
from pathlib import Path
import pytest
REPO = Path(__file__).resolve().parent.parent

@pytest.mark.parametrize("module", ["led_ticker.plugin", "led_ticker.transitions"])
def test_bare_first_import_has_no_cycle(module):
    """A transition module importing from led_ticker.app would break these
    (the transitions auto-import loop runs before the package's re-exports).
    Must be a fresh interpreter: any earlier led_ticker.app import masks it."""
    r = subprocess.run(
        [sys.executable, "-c", f"import {module}"],
        env={**os.environ, "PYTHONPATH": f"{REPO}/src:{REPO}/tests/stubs"},
        capture_output=True, text=True, cwd=REPO,
    )
    assert r.returncode == 0, r.stderr
```

- [ ] **Step 2: Run them**: `uv run pytest tests/test_coercion_rgb_shape.py tests/test_import_cycles.py -v`. Expected: the `is` test FAILS (`colors` has no `rgb_shape_error`); the cycle tests PASS (baseline, they guard Task 7).
- [ ] **Step 3: Move the function** to `colors.py` (docstring: "Home is `led_ticker.colors` so the transitions package can import it without a cycle; `app.coercion` re-exports it for validate rule 74, rule 73 and the transition factory"), re-export from `coercion.py`, fix the `validate.py:1553` docstring.
- [ ] **Step 4: Run** `uv run pytest tests/test_coercion_rgb_shape.py tests/test_import_cycles.py tests/test_validate.py -q`. Expected: all PASS.
- [ ] **Step 5: Commit** `refactor(colors): rgb_shape_error lives in the leaf colors module; bare-import cycle tripwires`.

### Task 2: `PixelBuffer` canvas surface + snapshot-every-widget tripwire

**Files:**
- Modify: `src/led_ticker/rotate.py:47-139` (`PixelBuffer`)
- Test: `tests/test_pixel_buffer_surface.py` (new)

**Interfaces:**
- Produces on `PixelBuffer`: `Clear() -> None` (alias of `clear()`); `Fill(r: int, g: int, b: int) -> None` (every slot `(r, g, b)`, extent `(0, 0, width, height)`); `SetImage(image: Any, offset_x: int = 0, offset_y: int = 0) -> None`. Fast path when `image.mode == "RGB" and image.size == (width, height) and offset_x == offset_y == 0`: `raw = image.tobytes()`; `self._pixels = [(raw[i], raw[i+1], raw[i+2]) for i in range(0, len(raw), 3)]`; extent full. Otherwise walk `image.load()` like `HeadlessCanvas.SetImage` (`backends/headless.py:45-58`: alpha 0 -> black, per-pixel `SetPixel`, bounds and extent via `SetPixel`).
- `clear()`, `get()`, `lit_extent`, `SetPixel`, `SubFill` unchanged.

- [ ] **Step 1: Write the failing unit tests** (`tests/test_pixel_buffer_surface.py`)

```python
def test_fill_sets_every_slot_and_full_extent():      # Fill(1,2,3) -> get(x,y)==(1,2,3) everywhere, lit_extent==(0,0,w,h)
def test_clear_is_clear():                             # Fill then Clear() -> every get() None, lit_extent None
def test_setimage_fast_path_matches_headless():        # 8x4 RGB image at (0,0): PixelBuffer vs HeadlessCanvas get_pixel equal on every pixel
def test_setimage_offset_matches_headless():           # 4x2 RGB at (2,1): equal on every pixel incl. untouched ones (None -> black)
def test_setimage_partial_clip_matches_headless():     # 6x3 image at (5,2) on 8x4: no IndexError; equal
def test_setimage_rgba_alpha_zero_is_black():          # RGBA pixel alpha 0 -> (0,0,0); alpha 255 -> colour
def test_setimage_fast_path_extent_is_full():          # lit_extent == (0,0,w,h) after a full-size blit
def test_setimage_slow_path_extent_tracks_pixels():    # 2x2 at (3,1) -> lit_extent == (3,1,5,3)
```

- [ ] **Step 2: Run**: `uv run pytest tests/test_pixel_buffer_surface.py -v`. Expected: FAIL `AttributeError: 'PixelBuffer' object has no attribute 'Fill'`.
- [ ] **Step 3: Implement** the three methods per Interfaces.
- [ ] **Step 4: Run** the file + `uv run pytest tests/test_rotate*.py tests/test_lens*.py -q` (existing consumers). Expected: PASS.
- [ ] **Step 5: Write the failing tripwire** (same file):

```python
WIDGETS = ["clock", "countdown", "countup", "gif", "image", "message", "two_row"]
GEOMETRIES = [(160, 16, 1, 16), (256, 64, 4, 16), (256, 64, 1, 16), (128, 64, 2, 16)]  # (w, h, scale, content_height)

@pytest.mark.parametrize("name", WIDGETS)
@pytest.mark.parametrize("geom", GEOMETRIES)
def test_every_core_widget_snapshots_into_pixelbuffer(name, geom, tmp_path, monkeypatch):
    """(a) the breaker never trips; (b) PixelBuffer == HeadlessCanvas pixel-for-pixel.
    Fixture freezes time (clock/countdown/countup read datetime.now at draw)."""
    # widget built via the registry with a hires font + ':star:' + border + bg_color where the type accepts them
    # (gif/image: a 2-frame RGBA gif / RGB png written to tmp_path, fit="contain", no text)
    # draw through guard_for_transition(widget, RenderBreaker()) into _maybe_wrap(PixelBuffer(w,h), s, ch)
    # and into _maybe_wrap(HeadlessCanvas(w,h), s, ch) at cursor_pos 0 AND -30; assert not breaker.is_disabled(widget)
    # and buf.get(x,y) or (0,0,0) == headless.get_pixel(x,y) for every (x,y)
```

- [ ] **Step 6: Run**: `uv run pytest tests/test_pixel_buffer_surface.py -k snapshots -v`. Expected: PASS (the surface is complete). If any cell FAILS, the method a widget needs is missing; add it, do not skip the cell.
- [ ] **Step 7: Mutation check** (no commit of this): temporarily change the fast path's slice stride to 4; the gif/image cells must FAIL. Revert.
- [ ] **Step 8: Commit** `feat(rotate): PixelBuffer gains Clear/Fill/SetImage; every core widget snapshots pixel-exact`.

### Task 3: Breaker helpers for snapshotting transitions

**Files:**
- Modify: `src/led_ticker/render_breaker.py` (two module functions after `guard_for_transition`)
- Test: `tests/test_render_breaker.py` (existing; append)

**Interfaces:**
- Produces: `transition_draw_tripped(obj: Any) -> bool` — `isinstance(obj, _TransitionDrawGuard)` first, else `False`; then `breaker.is_disabled(object.__getattribute__(obj, "_widget"))`. `trip_transition_draw(obj: Any, exc: BaseException) -> bool` — same gate (returns `False` for a non-guard, trips nothing); else `breaker.trip(inner_widget, exc)` and returns `True`.

- [ ] **Step 1: Write the failing tests**

```python
class _IdKeyed:            # NO text/top_text/path, so _key falls back to id()
    def draw(self, canvas, cursor_pos=0, **kw): return canvas, 0

def test_trip_transition_draw_disables_the_inner_widget():
    w = _IdKeyed(); br = RenderBreaker(); g = guard_for_transition(w, br)
    assert trip_transition_draw(g, RuntimeError("x")) is True
    assert br.is_disabled(w)                       # the WIDGET, not the guard
    assert transition_draw_tripped(g) is True
def test_status_board_entry_names_the_widget_class():     # status_board disabled_widgets[-1]["type"] == "_IdKeyed"
def test_helpers_read_false_on_a_raw_widget():
    assert transition_draw_tripped(_IdKeyed()) is False
    assert trip_transition_draw(_IdKeyed(), RuntimeError()) is False
def test_tripped_reads_false_before_any_trip():            # fresh guard -> False
```

- [ ] **Step 2: Run**: FAIL `ImportError`. **Step 3: Implement.** **Step 4: Run** `uv run pytest tests/test_render_breaker.py -q`: PASS.
- [ ] **Step 5: Commit** `feat(breaker): transition_draw_tripped / trip_transition_draw for snapshotting transitions`.

### Task 4: Runner kwargs, protocol docstring, API minor, docs literals

**Files:**
- Modify: `src/led_ticker/transitions/__init__.py:444-457` (the `frame_at` call) and `:51-78` (protocol docstring)
- Modify: `src/led_ticker/plugin.py:192-200` (comment block + `API_VERSION`)
- Modify: `docs/site/src/content/docs/plugins/api-reference.mdx:42` (prose: "currently `(1, 5)`" + a `(1, 5)` clause), `:85` (name the kwargs); `docs/site/src/content/docs/plugins/authoring/01-scaffold.mdx:92` (literal); `docs/plugin-system.md:233-237` (one bullet)
- Modify: `CLAUDE.md:172` (constraint #2), `:214` (Meta bullet), `:255` (`API_VERSION` sentence)
- Test: `tests/test_transitions.py` (append to the runner tests), `tests/test_plugin_api_version.py` or wherever `API_VERSION >= (1, 3)` is pinned today (grep `API_VERSION >=`)

**Interfaces:**
- Produces: `frame_at` receives `incoming_scale: int | None`, `incoming_content_height: int`, `outgoing_bg_color: tuple[int,int,int] | None` (post-`_normalize_bg`) beside the existing `outgoing_scroll_pos`, `duration_ms`, `incoming_bg_color`. `API_VERSION == (1, 5)` with comment "`(1, 5)` — `frame_at` receives `incoming_scale`, `incoming_content_height` and `outgoing_bg_color`".

- [ ] **Step 1: Write the failing tests**

```python
async def test_frame_at_receives_geometry_and_outgoing_bg(canvas, mock_frame, make_widget, no_sleep):
    seen = []
    class _T:
        def frame_at(self, t, c, o, i, **kw): seen.append(kw); return c
    await run_transition(canvas, mock_frame, make_widget(), make_widget(), transition=_T(),
                         duration=0.1, incoming_scale=2, incoming_content_height=12,
                         outgoing_bg_color=(1, 2, 3), incoming_bg_color=(4, 5, 6))
    assert seen[0]["incoming_scale"] == 2 and seen[0]["incoming_content_height"] == 12
    assert seen[0]["outgoing_bg_color"] == (1, 2, 3) and seen[0]["incoming_bg_color"] == (4, 5, 6)
async def test_frame_at_within_section_sees_incoming_scale_none(...):   # no incoming_scale kwarg -> None, content_height 16, bg None
def test_api_version_is_at_least_1_5(): assert plugin.API_VERSION >= (1, 5)
```

- [ ] **Step 2: Run**: FAIL (`KeyError: 'incoming_scale'`, version). **Step 3: Implement** the three kwargs, the docstring (three bullets in the existing style), the version + comment, the two page literals, the api-reference clause and kwargs sentence, the plugin-system bullet, the three CLAUDE.md edits (constraint #2: "…or the test stub canvas, or an OWNED readable raster (`rotate.PixelBuffer`, flair's `Raster`) a snapshotting transition draws into — see `test_every_core_widget_snapshots_into_pixelbuffer`").
- [ ] **Step 4: Run** `uv run pytest tests/test_transitions.py tests/test_docs_plugin_api_drift.py tests/test_plugin*.py -q`: PASS. Also `rg "\(1, 4\)" src docs CLAUDE.md` returns nothing but PR #561's text if it has landed.
- [ ] **Step 5: Commit** `feat(transitions): frame_at receives incoming geometry and outgoing bg (API 1.5)`.

### Task 5: Meta wrapper forwards `end_firing` to the child that ran

**Files:**
- Modify: `src/led_ticker/transitions/meta.py:132-136`
- Test: `tests/test_transitions_meta.py` (append)

**Interfaces:**
- Produces: `_PickAhead.end_firing()` = `child = self._children[self._current]; try: hook = getattr(child, "end_firing", None); if callable(hook): hook() finally: self._current = self._advance(); self._log_pick()`.

- [ ] **Step 1: Write the failing tests** (children are plain stubs; no breaker, no runner)

```python
def test_end_firing_forwards_to_the_child_that_ran_not_the_next_pick():   # counting child at index 0 under auto: after one end_firing its count == 1 and child[1].count == 0
def test_end_firing_runs_exactly_once_per_firing_through_the_runner():    # run_transition with a 2-member random(rng=Random(1)) pool; child.ends == 1
def test_raising_child_hook_still_advances_the_pick(caplog):              # child.end_firing raises; wrapper._current moved; runner logs "end_firing"
def test_child_without_hook_is_unchanged():                                # bare stub, no AttributeError, auto still cycles 0,1,0
```

- [ ] **Step 2: Run**: FAIL. **Step 3: Implement.** **Step 4: Run** `uv run pytest tests/test_transitions_meta.py tests/test_factories_meta_transition.py -q`: PASS.
- [ ] **Step 5: Commit** `feat(meta): random/auto forward end_firing to the child that ran`.

### Task 6: PR A verification and push

- [ ] **Step 1:** `uv run pytest -q` (whole suite), `uv run ruff check`, `uv run ruff format --check`, `PYRIGHT_PYTHON_FORCE_VERSION=latest uv run pyright`. Expected: all green; the registry count test still says 23.
- [ ] **Step 2:** Byte-identity spot check: `make render-demo CONFIG=docs/site/demos/transitions-dissolve.toml OUT=/private/tmp/claude-501/-Users-james-projects-github-jamesawesome-led-ticker/d5cf4012-76cf-4eba-9ac9-37982eddf32a/scratchpad/dissolve-after.gif` and compare frame hashes with the same render from `origin/main` (worktree `../led-ticker`): identical.
- [ ] **Step 3:** `git push -u origin fade-precursor`. Do NOT `gh pr create` (James's go needed; the body goes in a file for later).
- [ ] **Step 4:** Antagonist loop on the PR A diff (ledger `docs/superpowers/reviews/2026-11-22-fade-precursor-antagonist.md`, cap 5, exit LOW/DOCS). Fold, re-run Step 1, push.

### Task 7: `fade.py`

**Files:**
- Create: `src/led_ticker/transitions/fade.py`
- Test: `tests/test_transitions_fade.py` (new)

**Interfaces:**
- Consumes: Task 1 `colors.rgb_shape_error`; Task 2 `PixelBuffer.{Clear,Fill,SetImage}`; Task 3 `transition_draw_tripped`, `trip_transition_draw`; Task 4 kwargs; `ticker._maybe_wrap(canvas, scale, content_height)`; `scaled_canvas.{is_scaled,unwrap_to_real}`; `transitions.register_transition`.
- Produces:

```python
@register_transition("fade")
class Fade:
    min_frames = 8
    def __init__(self, color: ColorTuple | None = None, **kwargs: Any) -> None: ...   # falsy -> mix; bad shape -> ValueError
    def frame_at(self, t: float, canvas: Canvas, outgoing: Any, incoming: Any, **kwargs: Any) -> Canvas: ...
    def end_firing(self) -> None: ...
```

Private helpers in `fade.py`: `_geometry(canvas) -> tuple[int, int] | None` (`(canvas.scale, canvas.content_height)` when `is_scaled(canvas)` else `None`); `_wrap(buf, geometry)` (`_maybe_wrap(buf, *geometry)` or `buf`); `_buffer_to_image(buf: PixelBuffer) -> Image.Image` (`Image.frombytes("RGB", (buf.width, buf.height), b"".join(bytes(p) if p is not None else b"\0\0\0" for p in buf._pixels))`; `bytes((255.0, 0, 0))` raises `TypeError`, `bytes((256, 0, 0))` raises `ValueError`, which is the conversion-trip path); `_snapshot(widget, real, bg, geometry, cursor_pos) -> Image.Image` (new `PixelBuffer(real.width, real.height)`; `Fill(*bg)` if bg else `Clear()`; `try: widget.draw(_wrap(buf, geometry), cursor_pos=cursor_pos); if transition_draw_tripped(widget): reset to bg; return _buffer_to_image(buf) except Exception as exc: if trip_transition_draw(widget, exc): log, return bg-only image; raise`). Instance state: `_out_img`, `_in_img`, `_key: tuple[Any, Any] | None` (the `outgoing`/`incoming` objects, compared with `is`), `_through_cache: dict[tuple[int,int], Image.Image]`, `_frames: int`, `_t0: float`. DEBUG lines: `fade: snapshot %dx%d in %.1f ms` on snapshot, `fade: firing done, %d frames, %.1f ms` in `end_firing`.

- [ ] **Step 1: Write the failing tests.** Helpers at the top of the file: `_canvas(w, h, scale, ch)` returning `(real HeadlessCanvas, wrapped)`; `_msg(text, color)` = `TickerMessage(text=text, font_color=color)`; `_expected(widget, w, h, scale, ch, bg, cursor)` draws independently into a fresh `HeadlessCanvas` and returns it; `_px(canvas, x, y)`. Drive `frame_at` directly (no runner) unless the test says "through the runner".

```python
# constructor
@pytest.mark.parametrize("shape", ["red", ("r","e","d"), [255, 0], [255.0, 0, 0], [256, 0, 0], [True, 0, 0]])
def test_bad_colour_raises_valueerror(shape)
@pytest.mark.parametrize("c", [None, (), []])
def test_falsy_colour_is_mix(c)                                 # Fade(color=c).through is None
def test_bad_colour_on_a_section_cuts_through_guarded_builder()  # run._build_trans_obj_guarded(cfg with type="fade", color=("r","e","d")) is None
@pytest.mark.parametrize("shape", [...same table..., [], [0, 0, 0]])
def test_constructor_and_rule74_agree(shape)                     # Fade raises iff rule 74 reports an ERROR for that shape on a fade slot
# endpoints (parametrised over (message->message) and (gif->message); gif from tmp_path, no text/border/background)
def test_t0_equals_outgoing_at_scroll_pos(pair)                  # outgoing_scroll_pos=-30; expected drawn independently at -30
def test_t1_equals_incoming(pair)
def test_mid_frame_is_blend(pair)                                # t=0.5 == Image.blend(out, in, 0.5) pixel-wise
def test_mix_quarter_is_blend_025()                              # t=0.25
# dip
def test_dip_black_midpoint_is_black_everywhere()                # color=(0,0,0), both snapshots lit, t=0.5 all (0,0,0)
def test_dip_nonblack_midpoint_is_through_colour()               # color=(0,0,255)
def test_dip_quarter_is_half_out_half_through()                  # t=0.25 == blend(out, through, 0.5)
def test_dip_three_quarter_is_half_through_half_in()             # t=0.75 == blend(through, in, 0.5)
def test_mix_never_paints_a_solid_frame()                        # color=None: no frame in t∈{.1..9} is uniform
# clamp / bg
def test_t_above_one_and_below_zero_clamp_to_endpoints()
def test_distinct_bgs_show_under_snapshots()                     # unlit pixel: t=0 == outgoing bg (10,0,0), t=1 == incoming bg (0,0,10); None -> black
# geometry
def test_cross_scale_incoming_at_incoming_geometry()             # 256x64, live scale 4, incoming_scale=2, incoming_content_height=16: t=1 == _maybe_wrap(.., 2, 16) draw
def test_cross_scale_outgoing_at_live_geometry()                 # same call: t=0 == scale-4 draw
def test_same_scale_cross_content_height()                       # scale 1 on 64 rows, 16 -> 12
def test_incoming_scale_none_uses_live_wrapper()
def test_unwrapped_canvas_snapshots_directly()                   # 160x16 raw HeadlessCanvas: works, t=0/t=1 exact (Review Focus 5)
# lazy snapshot / release
def test_draw_runs_once_per_widget_per_firing()                  # counting widgets, 20 frames -> 1 draw each
def test_end_firing_releases_and_next_firing_resnapshots()       # change outgoing.text between firings; new text shows
async def test_aba_through_seeded_random_pool_resnapshots()      # pool [Fade, Cut] rng=Random(seed) so fade runs on firings 1 and 3; breaker=None; through the runner
async def test_cancel_mid_fade_releases_snapshots()              # Review Focus 2: cancel the runner task on frame 2; fade._out_img is None
# breaker
def test_paint_then_raise_trips_and_completes_to_bg()            # incoming paints 10 pixels then raises; t=1 == bg only; breaker.is_disabled(widget)
def test_bad_channel_value_trips_at_conversion()                 # widget SetPixel(0,0,255.0,0,0); through the guard: tripped, t=1 == bg
def test_bad_channel_value_without_breaker_raises()              # breaker=None: TypeError out of frame_at
def test_snapshot_widget_missing_canvas_method_trips_and_completes()   # Review Focus 1
def test_incoming_that_draws_nothing_fades_to_bg()               # Review Focus 4
# per-frame path (spy canvas, NOT HeadlessCanvas)
def test_one_setimage_rgb_full_size_no_setpixel_per_frame()      # spy records SetImage calls (image.mode=="RGB", image.size==(w,h), offsets 0) and asserts SetPixel never called
# runner integration
async def test_min_frames_floor_is_tick_relative()               # Review Focus 3: scroll_speed=1/60, duration=0.1 -> 9 frame_at calls
def test_debug_lines(caplog)                                     # "fade: snapshot" once per firing, "fade: firing done" once
```

- [ ] **Step 2: Run**: `uv run pytest tests/test_transitions_fade.py -v`. Expected: FAIL `ModuleNotFoundError`/registry miss.
- [ ] **Step 3: Implement `fade.py`** per Interfaces. Module docstring: design path, the "never raises" invariant, the four raise points and where each is closed.
- [ ] **Step 4: Run** the file, then `uv run pytest tests/test_import_cycles.py tests/test_transitions.py -q`. Expected: the fade file PASSES; `test_transitions.py` FAILS only on the registry count (fixed in Task 8).
- [ ] **Step 5: Mutation checks** (revert each): first-half dip `2*k` -> `k` (quarter test fails); drop the `.get` default on `outgoing_scroll_pos` (direct-call test without the kwarg fails); wrap both buffers at incoming geometry (outgoing-geometry test fails); `Image.new("RGBA", …)` for through (spy test fails).
- [ ] **Step 6: Update the pins in the SAME commit** so the suite is never red: `tests/test_transitions_meta.py:23-39, 94-95` (`FIFTEEN` -> `SIXTEEN`, `"fade"` after `"dissolve"`), `tests/test_factories_meta_transition.py:26, 80-81, 89, 95, 101` (`SIXTEEN`, `[None] * 16`, `range(16)`), `tests/test_transitions.py:106` (`== 24`, `"fade"` in `expected`), CLAUDE.md `(15 today)` -> `(16 today)`. Run the three files: PASS.
- [ ] **Step 7: Commit** `feat(transitions): fade — crossfade, dip through transition_color; sixteen-member pool`.

### Task 8: Pool pins, registry count, pool colour inheritance, fact-pack tripwire

**Files:**
- Modify: `src/led_ticker/validate.py:1664` (rule 74 empty-colour message: when `ttype == "fade"` say "empty, so fade crossfades instead of dipping" rather than "falls back to its default colour")
- Test: `tests/test_factories_meta_transition.py` (append), `tests/test_validate.py` (one rule 74 wording test for `fade`), `tests/test_docs_transition_fact_packs.py` (new)

- [ ] **Step 1: Rule 74 wording**: failing test `test_rule74_empty_colour_on_fade_says_crossfade`; implement; run `uv run pytest tests/test_validate.py -k rule74 -q`: PASS.
- [ ] **Step 2: Write the failing pool-colour tests**

```python
def test_random_slot_colour_makes_pooled_fade_dip():          # {type:"random", transition_color:[255,0,0]} -> the Fade child .through == (255,0,0)
def test_bare_pool_entry_inherits_slot_colour()               # pool ["fade", "wipe_left"] under a coloured slot -> Fade.through set
def test_pool_entry_own_colour_wins()                          # {type:"fade", transition_color:[0,0,255]} -> (0,0,255)
def test_plain_fade_slot_with_both_keys_is_a_mix()             # transition_color + transition_colors on a plain fade slot -> through None (colors wins, color dropped)
def test_pool_parent_with_both_keys_dips_pooled_fade()         # inherited list dropped for a core child; parent color reaches it
```

- [ ] **Step 3: Write the failing fact-pack tripwire** (`tests/test_docs_transition_fact_packs.py`): for every name in `list_transition_names()` with no `.` and not in `META_TYPES`, count lines matching `^\| `name` ` across `docs/content-source/transitions/*.md`; assert exactly 1. Expected now: FAIL only for `fade` (0).
- [ ] **Step 4: Run** Step 2's tests (PASS after no code change? they should pass already; if any FAIL, the factory precedence differs from the design: stop and report) and Step 3 (fails on `fade` until Task 9).
- [ ] **Step 5: Commit** `test(transitions): sixteen-member default pool, registry 24, pool colour inheritance, fact-pack tripwire`.

### Task 9: Docs, demo GIF, CLAUDE.md

**Files:**
- Create: `docs/site/demos/transitions-fade.toml` (header `# render-duration: <plan-gif + Σ entry durations + 1>`; three sections: mix pair, dip-through-black pair `transition_color = [0, 0, 0]`, a `bg_color` pair with distinct bgs; `[display]` block copied from `transitions-color_flash.toml`; `[transitions] default = "fade"`, `duration = 0.8`)
- Create: `docs/site/public/demos/transitions-fade.gif` (`make render-demo CONFIG=docs/site/demos/transitions-fade.toml OUT=docs/site/public/demos/transitions-fade.gif`; sample by playback time per the making-a-gif skill; view the GIF before committing)
- Modify: `docs/content-source/transitions/special.md` (Variants row after `dissolve`: "`fade` | Crossfade: both widgets snapshotted once, blended per frame; `transition_color` turns it into a dip through that colour | Soft swaps, broadcast feel"; Tuning: `transition_duration` bullet gains "`fade` has a 0.4 s floor at 20 fps (`min_frames = 8`); below it, raise `transition_fps`"; `transition_color` bullet gains "`fade` (dips through it; unset = crossfade)")
- Modify: `docs/site/src/content/docs/transitions/special.mdx` (frontmatter description + intro add `fade`; a `## Fade` section before Pools: one paragraph, `<DemoGif src="/demos/transitions-fade.gif" caption="fade — crossfade, then a dip through black, then across bg colours" />`, a `TomlExample` copied character-for-character from the demo TOML from `[transitions]` to EOF, the pool-colour inheritance sentence, the known limit "gif / image widgets' text overlay, border and background hard-cut at the endpoints in every transition, the fade included", a tuning note placeholder "bigsign: if the tail pops in at `pwm_bits = 8`, try 9 or 10 (refresh cost: measured on the hardware check)")
- Modify: `docs/site/src/content/docs/transitions/index.mdx:17` ("Cut, fade, dissolve, …"), `:26-27` (`fade` in Info-dense and Branded-pro "Between sections"), `:65` ("…, color_flash, and the colour `fade` dips through")
- Modify: `docs/site/src/content/docs/reference/config-options.mdx:139` (add `fade`), `docs/site/src/content/docs/tutorial/05-polish.mdx:139` (add `fade`), `.claude/skills/creating-a-config/references/transition-selection.md:17-18` (`fade` in Info-dense and Branded-pro)
- Modify: `CLAUDE.md:76` (file map `fade.py`), `:213` (Special list: "`fade` (snapshot-and-blend crossfade; `transition_color` = dip)"), `:214` ("(15 today)" -> "(16 today)"), `:294` (step 6 carve-out)
- Test: `tests/test_docs_fade_demo_drift.py` (new; the flair pattern scoped to `transitions-fade` against `special.mdx` and `docs/site/demos/`)

- [ ] **Step 1: Write the drift test**, run: FAIL (no snippet yet).
- [ ] **Step 2: Demo TOML**, `make plan-gif CONFIG=docs/site/demos/transitions-fade.toml`, set the header, render, Read the GIF, iterate colours for LED contrast (memory: white washes, black invisible).
- [ ] **Step 3: Write the docs** per Files. `make docs-lint` (nvm/pnpm on PATH per memory).
- [ ] **Step 4: Run** `uv run pytest tests/test_docs_*.py tests/test_docs_transition_fact_packs.py tests/test_docs_fade_demo_drift.py -q`: PASS (config-options drift, plugin API drift, fact pack, demo drift).
- [ ] **Step 5: Commit** `docs(transitions): fade — special page, fact pack, demo GIF, catalogue rows, CLAUDE.md`.

### Task 10: PR B verification, spec artefacts, push

- [ ] **Step 1:** `git add docs/superpowers/specs/2026-11-21-fade-design.md docs/superpowers/reviews/2026-11-22-fade-design-antagonist.md docs/superpowers/plans/2026-11-22-fade-transition.md`; commit `docs(superpowers): fade design, design-loop ledger, plan`.
- [ ] **Step 2:** `uv run pytest -q`, `uv run ruff check`, `uv run ruff format --check`, `PYRIGHT_PYTHON_FORCE_VERSION=latest uv run pyright`, `uv run led-ticker validate CONFIG=docs/site/demos/transitions-fade.toml`. All green.
- [ ] **Step 3:** `git push -u origin fade-transition`. No `gh pr create` without James's go.
- [ ] **Step 4:** Antagonist loop on the PR B diff (ledger `docs/superpowers/reviews/2026-11-22-fade-transition-antagonist.md`, cap 5, exit LOW/DOCS). Fold, re-run Step 2, push.
- [ ] **Step 5: Put the fade on the bigsign and leave it there.** Steps 1-5 of `project_bigsign_hardware_check_procedure.md` (back up the live config under a NEW name, compose.override DEBUG, deploy the pushed `fade-transition` branch, a CORE-ONLY demo config with an empty `[web]` block and the live `[display]` block, the design's pairs (a)-(d) each named in its message text), then confirm from the DEBUG lines and a short in-container capture that fades fire, snapshots time out under one tick, and nothing tripped. Check the branch's version against flair 0.25.0's core floor first; a config with no `flair.*` names keeps a mismatch harmless. STOP with the fade live and ping James (PushNotification if available, else the final message) with: what is on the sign, the restore command, the eyes-on list from the design's Hardware section, the `gh pr create` asks for both PRs, and the `(1, 5)` / PR #561 merge-order condition. The eyes-on findings, the docs tuning note, and the restore happen after he looks. If this step lands on a work day, re-ask the window first.
