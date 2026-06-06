# Batch D1 — Omit Release-History Framing (+ content-source fix + DOCS-STYLE principle) — Design

**Date:** 2026-06-06
**Status:** Approved (brainstorm), pending implementation plan

## Context

Phase 3b **Batch D1** — the first of two final docs-polish PRs (D2 = the cheap rubric polish). Phases 0–2, 3a (audit), and 3b A+B+C are shipped (PR #162). This PR makes concrete corrections; D2 follows with the broader polish. New branch `feat/docs-d1` off main.

**Trigger:** led-ticker is **unreleased**, so "legacy" / "backward compatibility" / "deprecated" / "no longer accepted" / "still works as before" framing is meaningless noise — there is no prior version to preserve. Document the current way only.

## Decisions (from brainstorm)

- **Scope D1 to concrete corrections:** (1) strip release-history framing from the docs site; (2) fix `hold_seconds`→`hold_time` in the skill's content-source; (3) add a DOCS-STYLE principle so the reviewer enforces it.
- **`mode = "gif"` stays documented** as a simpler/narrower alternative — keep the validator rule and the "prefer `mode = "swap"`" recommendation; only remove the legacy/removal framing.
- Two PRs (D1 corrections, D2 polish); this is D1.

## Deliverable

### 1. Strip release-history framing (docs site)

Reword each occurrence to describe the current way and omit the history. Exact targets (from a grep of `docs/site/src/content/docs/`):

- **`pitfalls.mdx` Rule 33** (`mode = "gif"`): keep the rule (the validator warns on `mode = "gif"`), but rewrite the body to drop "was the original way" / "preserved for backward compatibility" / "undocumented and may be removed in a future release." Neutral version: prefer `mode = "swap"` with a `gif` widget (full section feature set: transitions, `hold_time`, `bg_color`, multi-widget); `mode = "gif"` is a narrower direct-play form; to switch, change `mode = "gif"` → `mode = "swap"`.
- **`pitfalls.mdx` Rule 35** (the `play_count = 0` + `mode = "gif"` interaction): drop "legacy" adjective; describe the behavior plainly (`play_count = 0` needs the `swap` path; under `mode = "gif"` it falls back to one loop).
- **`concepts/sections-and-modes.mdx`** (`## Legacy: mode = "gif"` + "Preserved for backward compatibility" + "Existing configs continue to work"): retitle the heading (e.g. `## The `mode = "gif"` shorthand` or fold into the modes discussion); present it as a simpler alternative to `mode = "swap"` + gif widget; remove the compat sentences.
- **`tools/validate.mdx`** (two "legacy mode" mentions, ~L181 table row + ~L210 prose): reword to neutral (`mode = "gif"` → prefer `mode = "swap"`), no "legacy."
- **`widgets/weather.mdx`** (~L33, "`message =` … is no longer accepted"): replace with a plain "Set the content with `text =`." (drop the history).
- **`widgets/message.mdx`** + **`widgets/countdown.mdx`** (~L26/L30, "existing configs with `message =` … continue to work"): reduce to the current way — document `text =`; keep a brief "`message =` is also accepted" only if it's a current fact worth stating, but drop "existing configs … continue to work."
- **`widgets/gif.mdx`** (~L261, "play_count ≥ 1 still works exactly as before"): → "`play_count ≥ 1` plays the exact count regardless of `hold_time`."

The implementer rewords sensibly per the intent (document current behavior, omit history); the exact phrasing is theirs as long as no release-history framing remains and the facts stay correct (verify `mode = "gif"`/`play_count`/`text =` claims against the validator/widget code where in doubt).

### 2. Content-source `hold_seconds` → `hold_time`

In the `creating-a-config` skill's knowledge base (read by the skill to generate configs), replace the non-existent `hold_seconds` with `hold_time`:
- `docs/content-source/decision-rules-legacy.md` (Rule 8 heading + DETECT/FIX lines).
- `docs/content-source/asset-handling-legacy.md` (the still-image duration bullets).
- `docs/content-source/widgets-legacy.md` (the image-widget knob descriptions).

(Leave the `*-legacy.md` filenames — internal, not user-facing. Only fix the `hold_seconds` content.) Same rationale as the site fix: `hold_seconds` is not a real field; the skill would otherwise emit configs that fail validation.

### 3. Add a DOCS-STYLE principle

In `docs/DOCS-STYLE.md` §2, add a principle (next number after the existing 16):

> **No release-history framing.** led-ticker is unreleased — don't describe anything as "legacy", "deprecated", "backward-compatible", "no longer accepted", or "still works as before." There's no prior version to preserve, so document the current way only.

And append a short clause to the §3 checklist's tone item (currently "Tone consistent + matter-of-fact (no upsell, no breathless marketing)") → add "… and no release-history framing (legacy/deprecated/backward-compat)."

## Applying the DOCS-STYLE rubric

This is corrections to existing pages; the tech-writer reviewer confirms each reworded section still passes the §3 checklist and that the new no-history principle holds across the edited pages.

## The review loop

A tech-writer review over the edited pages confirms the rewordings read cleanly and no history framing remains. (No hobbyist pass needed — these are wording corrections.)

## Verification

- `grep -riE "\blegacy\b|backward[- ]?compat|deprecat|no longer (accepted|valid|supported)|preserved for|continue[s]? to work|still works.*as before|kept for compat" docs/site/src/content/docs/` returns nothing (the `mode = "gif"` content remains but without legacy framing).
- `grep -rn hold_seconds docs/content-source/` returns nothing.
- `docs/DOCS-STYLE.md` has the new principle + the checklist clause.
- `make docs-build` + `make docs-lint` clean; all edited pages still render and their links resolve.
- Facts unchanged: `mode = "gif"`, `play_count`, and `text =`/`message =` claims still match the code (spot-check where reworded).

## Out of scope (D1)

- The D2 polish (reader-naming, tutorial stamps + what-you'll-need boxes, glosses, tiny per-page fixes, troubleshooting boxes, OptionsTable migration).
- Removing `mode = "gif"` support or the validator rule (it stays; only the framing changes).
- Renaming the `*-legacy.md` content-source files.
