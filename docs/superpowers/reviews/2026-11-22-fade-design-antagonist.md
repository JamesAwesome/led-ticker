# Antagonist loop — `fade` transition DESIGN

Target: `docs/superpowers/specs/2026-11-21-fade-design.md`.
Rules: fresh reviewer per cycle, cap 5 cycles, exit when only LOW/DOCS remain
(folded in, then the design is stamped approved). A cycle 5 that still
reports MEDIUM+ stops and asks James. Delegated by James 2026-11-22
("loop, then demo on moonbunny/bigsign").

Pre-loop reconciliation (2026-11-22, before cycle 1): `API_VERSION` on
`origin/main` (`9b3e5e84`) is already `(1, 3)` (#551, `api.font(threshold=)`,
shipped in core v4.35.0 and consumed by flair 0.25.0), so the design's bump is
`(1, 3)` -> `(1, 4)`; both docs-page literals read `(1, 3)` today. Fixed in the
design, gate section 12 / table, and roadmap row 4. Re-verified: factory kwargs
block `factories.py:461-464`, pool refusal `:580-591`, registry count 23
(`tests/test_transitions.py:106`), `FIFTEEN` / `range(15)` / `[None] * 15`
pins, drift test literal regex `tests/test_docs_plugin_api_drift.py:153`,
rule 74 wording `validate.py:1664`.

## Cycle 1

Reviewer: fresh subagent. VERDICT: 0 HIGH, 2 MEDIUM, 4 LOW, 3 DOCS.

- MEDIUM a non-RGB or off-size blend image raises out of the fork's `SetImage` / `Image.blend`; `frame_at` is unguarded, so the process exits; `HeadlessCanvas` / `PreviewTee` accept RGBA so no listed test noticed. Verified (`transitions/__init__.py:444`, `preview.py:128-140`). FOLDED: "fade's own code must never raise" invariant with the two raise points named; spy tripwire asserts mode `RGB` + real size per frame.
- MEDIUM outgoing side under-pinned (`cursor_pos=0` or both buffers at incoming geometry pass the listed tests; `kwargs["outgoing_scroll_pos"]` KeyErrors a kwargs-less caller). Verified (`ticker.py:871`, `effects.py:56`). FOLDED: `.get("outgoing_scroll_pos", 0)`; endpoint test draws outgoing independently at a non-zero scroll pos; geometry test pins t = 0 at live geometry.
- LOW half-painted snapshot after a mid-draw trip (guard returns `(canvas, 0)` without clearing, `render_breaker.py:84-88`). FOLDED: post-draw disabled check resets the buffer via a `_snapshot` helper; breaker fixture paints then raises.
- LOW lens 1 ruling "not a blocker" survives; evidence uncited. FOLDED: scoped tally + flair `Raster` precedent in the design; plugins-repo mirror test filed as an issue before the feature PR merges.
- LOW gif/image snapshot = 16,384 Python `SetPixel` calls in frame 1. FOLDED: `PixelBuffer.SetImage` full-size-RGB-at-origin fast path (`PreviewTee` shape); conversion via one `Image.frombytes`.
- LOW A-B-A pool test vacuous with an unpinned rng or 3+ members. FOLDED: two-member pool, seeded rng, text changed between firings.
- DOCS CLAUDE.md constraint #2 and "Adding a New Transition" step 6 forbid the snapshot. FOLDED: carve-out for an owned readable raster added to the CLAUDE.md edit list.
- DOCS "for gifs this is new" wrong (`GifPlayer.draw` never advances the frame). FOLDED: reworded; only inline animated image emoji newly freeze.
- DOCS `[None] * 15` pin missing; release note should say an inherited slot colour makes the new member a dip; core `color=` forwarding is unconditional. FOLDED.
- Lenses with no finding: no `frame_at` driver outside the runner lacks `end_firing` (variant wrappers hold their own family); guards are fresh per `run_transition` so stale replay needs `breaker=None`; `[]` -> `()` -> mix, rule 74 warns, inherited `()` on a pool parent is refused at build; both runner wrappers unwrap to the same live buffer.
- Pre-existing, out of scope: a section without its own `transition` writing `transition_color` mutates the shared default (rule 74 docstring); CLAUDE.md names the fork shim `graphics.py` (file is `graphics.pyx`).

## Cycle 2

Reviewer: fresh subagent. VERDICT: 0 HIGH, 2 MEDIUM, 3 LOW, 2 DOCS.

- MEDIUM widget-sourced bad channel values (`(255.0,0,0)`, `256`) are stored by `PixelBuffer` and fail at the bytes conversion OUTSIDE the breaker (today the real `SetPixel` trips the widget inside the guard). Verified by probe. FOLDED: `_snapshot` helper owns draw + conversion in one try/except, trips via a new breaker helper, returns a bg image; re-raises only with `breaker=None`; test added.
- MEDIUM `transition_color = "red"` parses to `('r','e','d')` (`config.py:581`) and would raise from `Image.new` in `frame_at`. Verified. FOLDED: constructor validates via `coercion.rgb_shape_error` and raises `ValueError`, which `run._build_trans_obj_guarded` (`run.py:411`) turns into a cut; raise point three recorded.
- LOW bg test blind to a both-buffers-incoming-bg implementation. FOLDED: distinct colours pinned at t = 0 and t = 1.
- LOW dip ramp unpinned (`k` vs `2k` in the first half passes every listed test). FOLDED: t = 0.25 / 0.75 pins for mix and dip.
- LOW step-6 reset read the guard's private slots. FOLDED: public `render_breaker.transition_draw_tripped` / `trip_transition_draw` helpers in the precursor PR, with tests.
- DOCS meta `end_firing` order ambiguous. FOLDED: code shape written out; "fires on the child that ran" pinned.
- DOCS snippet/GIF parity rule and drift tripwire missing. FOLDED: DOCS-STYLE hard rule and a scoped drift test on the flair pattern added to the docs list.
- Lenses with no finding: 53/53 `frame_at` and every kwargs re-forward land on `**kwargs` callees; 25/25 test doubles take `**kwargs`; no child defines `end_firing`; `unwrap_to_real(ScaledCanvas(PixelBuffer))` returns the buffer and every draw path reads only the surface the precursor provides; render_demo reads `HeadlessCanvas._pixels` after per-pixel `SetImage`; rule 74 is quiet on a coloured pool parent; `last_scale` / `last_content_height` are untouched by skipped or reloaded sections, so the live wrapper IS the outgoing geometry.
- Pre-existing, out of scope: `Makefile:247-249` says `public/demos/` is gitignored (it is committed); a hot-reload changing a section's scale leaves `last_scale` stale for the next entry (all transitions); `ColorFlash` with `transition_color = "red"` already raises in `frame_at`.

## Cycle 3

Reviewer: fresh subagent. VERDICT: 1 HIGH, 1 MEDIUM, 3 LOW, 2 DOCS.

- HIGH (introduced by the cycle 2 fold) `fade.py` importing `app.coercion.rgb_shape_error` at module level is a circular import: the transitions package auto-imports modules mid-init, `app.coercion` imports widgets -> `app` -> `factories`, which imports `HARD_EXCLUDED` etc. from the partially initialised `led_ticker.transitions`; `import led_ticker.plugin` / `import led_ticker.transitions` fail when first (every plugin test suite); the console entry survives. Verified by the reviewer on a copied tree, and by import graph here (`coercion.py:11-21`, `factories.py:63-73`, no `app` import in `transitions/` today). FOLDED: `rgb_shape_error` moves to the leaf `led_ticker.colors` in the precursor PR with an `app.coercion` re-export; `fade.py` imports from `colors`; two subprocess import tripwires.
- MEDIUM breaker helpers' target identity unspecified: tripping the GUARD keys `id(guard)` for content-less widgets (`clock`), guards are fresh per firing, so the widget is never seen disabled, the ERROR repeats every firing and the bg reset never fires. Verified (`render_breaker.py:19-31`). FOLDED: helpers unwrap `_widget` first; tests use an id-keyed fixture and assert `breaker.is_disabled(widget)` directly.
- LOW Process item 1 omitted the second `API_VERSION` docs literal and the CLAUDE.md constraint #2 edit (precursor CI would fail). FOLDED.
- LOW `make plan-gif` models no transition time; all six committed transitions demos hand-pad. FOLDED: render-duration = plan + sum of entry durations + 1 s.
- LOW validate/runtime colour parity rests on both calling `rgb_shape_error`, unpinned. FOLDED: parametrised shape-table parity test.
- DOCS two Special-family enumerations missing (`tutorial/05-polish.mdx:139`, creating-a-config skill `transition-selection.md:18`). FOLDED.
- DOCS `special.mdx:50` `exclude` example silently gains `fade`. FOLDED into the release note.
- Lenses with no finding: runner frame walk 4 -> 2 and 16 -> 12: `unwrap_to_real(active)` IS the swapped buffer at every frame, frame 0 sees the live wrapper, the runner returns the incoming wrapper; `scroll_speed` 0.05 -> 0.5 s = 11 calls, 1.0 s = 21, `min_frames = 8` = 9 calls; `default_pool_names()` is registry-derived, `fade` sorts between `dissolve` and `push_down`; `pool = ["fade"]` alone is refused; no committed config or demo uses a default pool; breaker is never `None` in production; `render_demo` drives `app.run` so the GIF render exercises the breaker path; `rgb_shape_error`'s accept set matches every shape `_parse_transition` can produce and `_child_transition_cfg` refuses the same.
- Pre-existing, out of scope: rule 53's "kwargs checked by constructor" comment is wrong for core non-meta slots (validate never builds them); `tools/gif_plan` models no transition time.

## Cycle 4

Reviewer: fresh subagent. VERDICT: 0 HIGH, 1 MEDIUM, 4 LOW, 5 DOCS.

- MEDIUM no pixel read-back on gif/image snapshots: the precursor tripwire asserts only "never trips" and the endpoint tests name no widget type, so a stride/mode bug in the `SetImage` fast path (hit only by gif/image) ships green. Reviewer probed the correct shape: zero diffs across every geometry with a `tobytes()` fast path. FOLDED: tripwire asserts `PixelBuffer` pixels == `HeadlessCanvas.get_pixel` per widget type and scale; endpoint tests parametrised over `message` and `gif -> message`.
- LOW literal `object.__getattribute__` unwrap raises on a raw widget. FOLDED: `isinstance(obj, _TransitionDrawGuard)` gate first.
- LOW `through_img` lifecycle contradicted itself. FOLDED: cached per instance keyed on size, not dropped by `end_firing`; removed from "Left to the builder".
- LOW `getdata()` is deprecated in the locked Pillow 13.0.0. FOLDED: `tobytes()` sliced into 3-byte tuples.
- LOW precursor-behaviour CLAUDE.md edits were scheduled for the feature PR. FOLDED: moved to Process item 1.
- DOCS fact pack `docs/content-source/transitions/special.md` missing (Variants table + Tuning). FOLDED, plus a tripwire that every non-meta core name appears in exactly one content-source table.
- DOCS `index.mdx` "Which to use" table not edited while its skill mirror is. FOLDED: both.
- DOCS "forwards `color=` unconditionally" wrong: `colors` wins and `color` is dropped (`factories.py:461-464`); pools drop the inherited list for core children. FOLDED: reworded; both-keys slot case added to the pool-colour test.
- DOCS image `draw()` omits border and background too, not just text; pair (c) must be border- and background-free. FOLDED.
- DOCS two stale `rgb_shape_error` docstrings; subprocess tripwire env unspecified. FOLDED: docstrings in the precursor; `sys.executable -c`, no prior import, `PYTHONPATH=src:tests/stubs`.
- Lenses with no finding: `colors.py` is a leaf; all `rgb_shape_error` importers go through `app.coercion` and survive the re-export; no `hasattr` on the new `PixelBuffer` methods anywhere; `clear()` consumers untouched; the engine's last frame equals t = 0 and its first post-transition frame equals t = 1 (no `y_offset` / `font_color` in engine draws, `reset_canvas` Fill == snapshot Fill, `_set_logical_scale` is `play()`-only); `ScaledCanvas` needs only what the precursor adds; `end_firing` sits in the runner's `finally` so cancellation releases the snapshots; reload is checked only at section seams.
- Pre-existing, out of scope: content-source says `transition_color` tints `dissolve` (it ignores `color`); CLAUDE.md cites Pillow "locked 12.1.1" (lock pins 13.0.0); DOCS-STYLE cites `scripts/build-demos.mjs` (lives at `docs/site/scripts/`).

## Cycle 5

Reviewer: fresh subagent. VERDICT: 0 HIGH, 0 MEDIUM, 5 LOW, 3 DOCS -> loop exits (cap reached with only LOW/DOCS).

- LOW `(1, 4)` already claimed by open PR #561 (`fix/image-play-settle-seam`, `frames_to_rest` on gif/image hosts). Verified (`git diff origin/main origin/fix/image-play-settle-seam -- src/led_ticker/plugin.py`). FOLDED: bump is the next unclaimed minor, `(1, 5)` while #561 is open; re-check at precursor-merge time. The pre-loop line "the bump is `(1, 4)`" is retracted.
- LOW content-source tripwire as worded fails on main (prose mentions). FOLDED: first-column cell of a pipe-table row, registry minus `META_TYPES`, all four files.
- LOW pixel-equality tripwire draws `clock` twice against wall-clock time. FOLDED: time frozen in the fixture.
- LOW `PixelBuffer.SetImage` slow path has no core caller; inline-emoji claim stale. FOLDED: direct unit test; emoji dropped from the premise.
- LOW hardware section overclaimed the 5 fps capture (frame count, one-tick flash). FOLDED: those move to the spy-canvas tripwire; second DEBUG line per firing.
- DOCS `docs/plugin-system.md` and the `plugin.py` comment block missing from the bump list. FOLDED.
- DOCS branch stacking unstated. FOLDED: feature branch stacked on the precursor, rebased after merge, the deployed branch.
- DOCS `min_frames` floor undocumented. FOLDED: `transition_duration` bullet in `special.md`.
- Pre-existing, out of scope: CLAUDE.md / `animations.py:90` / `pixel_gain.py:22` say inline animated emoji paint via `SetImage` (no core path does); `tests/test_transitions.py:100-105` comment names `led-ticker-arcade` for the sprite families (they are in flair); `api-reference.mdx:42` is prose, not a table.

## Exit

Design stamped APPROVED 2026-11-22. Severity trend: 0H/2M -> 0H/2M -> 1H/1M -> 0H/1M -> 0H/0M. The cycle 3 HIGH was introduced by a cycle 2 fold (circular import) and caught by the next cycle; the loop paid for itself there.
Next: plan (`docs/superpowers/plans/2026-11-22-fade-transition.md`), build in `../led-ticker-wt-fade` (precursor branch `fade-precursor`, feature branch `fade-transition` stacked), per-PR antagonist loops (separate ledgers), bigsign demo.
