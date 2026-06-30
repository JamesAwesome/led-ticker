Task 1: complete (ef692516..a0f3099e, review clean; MINOR: dead monkeypatch param in test_refresh_writes_current_before_version — final-pass cleanup)
Task 2: complete (a0f3099e..1be2400a, review clean; reload version-collision gap fixed in TokenizedField via registry-identity tracking)
Task 3: complete (1be2400a..985ebaf7, review clean; full suite 3108 green)
Task 4: complete (985ebaf7..bb0331c5, review clean; full suite 3115; MINOR: stale 'Task 4' scaffolding comment in factories.py ~L1261 — final-pass cleanup)
Task 5: complete (bb0331c5..c935c3a3, opus review clean; freeze model C1/C2/I3 + held + no-leak all PASS; full suite 3126). MINOR (carry to final): pre-scroll-hold width grow -> stop_pos from initial cursor_pos, narrow once-per-visit tail-clip; freeze contract honored. Engine helpers _resolve_now_if_supported/_lock_resolution_if_supported + FrameAwareBase _resolution_locked are the reusable foundation for T6/T7.
Task 6: complete (c935c3a3..13f4cf12, review clean; per-row _top_width/_bottom_width invalidation correct; 9/9 tripwires; full suite 3135). MINOR (carry to final): wraps_forever/forces_offscreen_scroll read raw bottom_text -> a token resolving to '' reads as 'has text' while rendering blank (next-visit flip; sharp edge only if empty-resolving tokens become a use case).
Task 7: complete (13f4cf12..9bf4dd24, review clean after fix; CRITICAL typewriter-freeze-bypassed-in-play-loop FIXED + Important empty-value fallback FIXED + Minor comment; play-loop integration test fails-before/passes-after; full suite 3154)
Task 8: complete (9bf4dd24..0ed5c356, review clean after fix; CRITICAL reload-crash-on-bad-source-type FIXED via atomic-or-nothing guard keeping old registry+ticker; happy-path atomic swap+respawn intact; full suite 3159)
Task 9: complete (0ed5c356..8a94f827, review clean; Rule 56 _check_sources 6 error rules + no undeclared-token warning; 11 tests; full suite 3170)
Task 10: complete (8a94f827..e4dc2abe, review clean after doc-accuracy fixes; concept page + reference + example + cross-links; docs-build/lint clean). ALL 10 TASKS DONE.

Final review fix-wave (9e5586a8):
F1 — FIXED: Held image static fast-path now gated on `not self._has_overlay_tokens()` (both single-row _play_with_text and two-row _play_with_two_row_text). Two-row also gets per-tick top-row re-resolution in the held-held loop (no-bottom-scroll path only; scrolling path stays frozen per existing design). New helper: `_BaseImageWidget._has_overlay_tokens()` checks _token_text / _token_top / _token_bottom.has_tokens.
  Tripwires (2):
    - test_held_still_with_token_re_resolves_across_ticks (TestHeldImageTokenFastPath, test_image_base.py): FAILS before (fast-path fires, value frozen "A"); PASSES after (per-tick loop, value updates to "B")
    - test_held_still_two_row_with_token_re_resolves_across_ticks (TestHeldImageTokenFastPath, test_image_base.py): FAILS before (two-row fast-path fires + per-tick loop uses stale local, value frozen "0"); PASSES after (fast-path bypassed + per-tick re-resolve, value updates to "7")
F2 — FIXED: Both forces_offscreen_scroll and wraps_forever branches in ticker.py now call _resolve_now_if_supported before entry (to measure current value for stop/cycle_width) and wrap the loop in _lock_resolution_if_supported try/finally (mirrors the generic overflow branch at L704/L719). Prevents _bottom_width remeasure from changing cycle_width mid-scroll (position jitter / de-sync).
  Tripwires (2):
    - test_forces_offscreen_scroll_locks_resolution (TestTwoRowScrollBranchesFreeze, test_ticker_display.py): FAILS before (_resolution_locked never set); PASSES after (lock confirmed during loop, released in finally)
    - test_wraps_forever_locks_resolution (TestTwoRowScrollBranchesFreeze, test_ticker_display.py): FAILS before (same); PASSES after
T1 — FIXED: Dead `monkeypatch` param dropped from test_refresh_writes_current_before_version in test_sources.py.
T4 — FIXED: Stale "will merge in here in Task 4" comment in factories.py ~L1261 replaced with accurate description of current state (plugin types in _PLUGIN_SOURCE_TYPES, dispatched by get_source_class).
Full suite: 3174 passed, 2 skipped. Ruff: clean. Pyright: 0 errors.
ALL 10 TASKS + final review + F1/F2 fix wave complete.

Antagonistic-review fix wave (2026-06-30):
CRITICAL — F2c FIXED: Removed redundant second `_resolve_now_if_supported(ticker_obj)` call in the `forces_offscreen_scroll` branch (~L650). The bug: the top-of-function resolve at L635 + initial `_safe_draw` at L637 already leave `_bottom_width` correct. The second call (added by the F2 fix wave) unconditionally sets `_bottom_width = -1` again, and reading it directly with no intervening draw produced `cycle_width = canvas.width + (-1) = 159` (not 450) → `stop = -159` (not -450) → scroll stranded 291 px short of the bottom-row tail. Lock (`_lock_resolution_if_supported`) retained. wraps_forever branch audited and confirmed safe (reads cycle_width from per-tick `_safe_draw` return, not `_bottom_width` directly).
  New geometry tripwire: test_forces_offscreen_scroll_correct_geometry (TestTwoRowScrollBranchesFreeze, test_ticker_display.py). FAILS before fix (final_pos=-159 vs expected=-450); PASSES after (final_pos=-450). Existing lock-flag tripwires (F2a/F2b) retained.
MINOR — is_emoji_slug now checks both EMOJI_REGISTRY and HIRES_REGISTRY so hires-only slugs (registered via api.hires_emoji without a matching api.emoji) are correctly blocked from source-id collision.
  New test: test_is_emoji_slug_true_for_hires_only (test_pixel_emoji.py). FAILS before fix (returns False for hires-only slug); PASSES after.
Full suite: 3176 passed, 2 skipped. Ruff: clean. Pyright: 0 errors.
