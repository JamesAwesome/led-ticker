# Antagonist loop — PR #551 `feat/plugin-font-thresholds` (core, API 1.3)

Roadmap item 3 (text styling, font route). Core half: plugin fonts declare a
default `font_threshold` via `api.font(name, path, threshold=None)`; plugin
fonts now count as hi-res in `list_available_hires_fonts`. Rules: fresh
reviewer per cycle, full diff each cycle, cap 5, exit when only LOW/DOCS
remain (folded, then ship). Design:
`docs/superpowers/specs/2026-11-20-flair-display-fonts-design.md`; plan:
`docs/superpowers/plans/2026-11-20-plugin-font-thresholds.md`.

Pre-loop: one executing-plans final review (fresh opus) found minors only;
two CLAUDE.md fixes folded (`4c8b76d3`). Deferred from it: stale threshold
entry on re-registration; `resolve_font` docstring; rules 63/64 plugin-font
tests.

## Cycle 1

Reviewer: fresh fable subagent (lenses: every `list_available_hires_fonts` /
`_is_hires_font_name` consumer; `_commit` collision/ordering with the uncounted
surface; literal-128 bypass sweep; live mutations of the three load-bearing
tests; docs drift). VERDICT: 0 HIGH, 0 MEDIUM, 3 LOW, 1 DOCS.

- LOW `--list-fields` printed `font_threshold` default as "128 (80 for Inter-Regular)", wrong for a plugin font with a declared value; an operator copying it as "the default" overrides the plugin's 45. FOLDED: per-font wording; the four `tests/golden/list_fields/*.txt` regenerated (one row each).
- LOW `default_threshold(name)` returns 128 for a plugin's own font when called at import or inside `register()` (plugin values land at commit); the docs told plugins to call it with no timing caveat. FOLDED: caveat in the docstring, api-reference row and CLAUDE.md paragraph.
- LOW `test_rule2_warns_when_one_plugin_font_widget_overrides` used 100 vs unset, which warns under the mutated code too (100 vs 128); the one survivor of mutation 1. FOLDED: 128 vs unset, so the test now also pins "spelling out the loader default is NOT on-default for a plugin font".
- DOCS api-reference `default_threshold` exports row (and the tutorial's parenthetical) still read "80 for Inter-Regular, 128 otherwise". FOLDED.
- Deferred items from the pre-loop review FOLDED on the reviewer's finding that `api.font` double-registration is the only reachable route for the stale threshold: `api.font` pops the stale entry when `threshold is None` (RED→GREEN `test_font_reregistration_without_threshold_drops_stale_entry`); `resolve_font` docstring; rules 63/64 pins for a plugin font (`plugin_font_brand` fixture moved to `tests/conftest.py`; the rotation-rule stub fixtures now `pop` so a plugin-font teardown's `reset_plugins()` doesn't break them).
- Mutations confirmed by the reviewer (worktree untouched): `default_threshold` ignoring plugin values → 5/6 targeted tests fail (6/6 after the fold); listing dropping plugin names → 3/3; `api.font` validation removed → 5/5.
- Out of scope, pre-existing (not counted): webui `inventory.py` font picker never lists plugin fonts; CLAUDE.md "Hi-res fonts" scan order omits plugin fonts being consulted first; rule 2 only inspects `font`, not `top_font`/`bottom_font`; `_find_font_path` does not fall through to the user dir for a registered-but-missing plugin path.

Full suite after the fold: 5287 passed, 5 skipped.
