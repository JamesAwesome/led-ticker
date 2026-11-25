# Antagonist review ledger: `bg_color` shape (validate rule 76 + coercion guard)

Branch `validate/bg-color-shape` (follow-up from #565's list). Reviewer: fresh
subagent per cycle; mutations on a scratch copy of `src/`; full suite each cycle.
Exit rule: fold LOW/DOCS and stop once no HIGH/MEDIUM remain.

## Cycle 1 (2026-11-24) — VERDICT 1 HIGH, 1 MEDIUM, 3 LOW, 0 DOCS; suite 5545 passed

- HIGH: rule number 75 already taken (BDF `font_size` below cell height, #562,
  `_classify_error` + `tests/test_validate_font_followups.py`). FOLDED: renumbered
  to 76 everywhere (rule, dedupe set, comments, tests, CLAUDE.md).
- MEDIUM: a malformed SECTION-level `bg_color` that no widget inherits (every
  widget sets its own) never meets `_coerce_widget_colors`; `load_config` only
  `tuple()`s it and it reaches `run_transition`'s `Fill(*bg)` raw. Hot-reload and
  the webui gate on `validate_config` (rule 76 now catches it); boot did not.
  FOLDED: `app.run._refuse_malformed_section_bg` raises after `load_config` at
  boot, before the frame; tests `test_refuse_malformed_section_bg_*`. Loader left
  lenient on purpose so validate can still report it under rule 76 with the fix
  text (same choice rule 74 made for `transition_color`).
- LOW: titles not walked (a title `bg_color = "red"` fell through as a rule-less
  build error). FOLDED: rule 76 walks `section.title`; dedupe covers
  `section[i].title`; test `test_rule76_title_bg_color_is_error_exactly_once`.
- LOW: tupled-string hint unpinned (mutation survived). FOLDED:
  `test_rule76_section_level_string_names_the_tupled_string`.
- LOW: dedupe could hide a plugin's own `bg_color ...` message at the same
  widget. FOLDED: fold requires `"; got "` in the message (the `_validate_rgb`
  shape); test `test_rule76_dedupe_keeps_a_non_shape_bg_message`.
- Checked, no finding: no shipped example / plugin README / docs config is newly
  refused; plugin widgets receiving a core-coerced `graphics.Color` pass; no docs
  page enumerates rules beyond 71-73; `reference/config-options.mdx` already says
  `[r, g, b]`.

Mutations re-run after folding: title walk removed → 1 fails; `"; got "`
removed → 1 fails. Suite after folding: 5553 passed, 5 skipped.

Loop exits after cycle 1 (0 HIGH / 0 MEDIUM remain).
