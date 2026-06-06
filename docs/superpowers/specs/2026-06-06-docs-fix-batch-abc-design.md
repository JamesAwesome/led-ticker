# Docs Fix Batch A+B+C — Design (Phase 3b)

**Date:** 2026-06-06
**Status:** Approved (brainstorm/audit), pending implementation plan

## Context

Phase 3b — the **first fix PR** from the Phase 3a audit. The findings report (`docs/superpowers/specs/2026-06-06-docs-audit-findings.md`) is the design input; this spec pins the one piece that needs real design (the etherscan code fix) and scopes the PR. Same branch family, off main.

**This PR = audit batches A + B + C** (user picked all four batches; D — the broad polish — is a separate later PR):
- **A — Correctness:** the wrong commands/flags/field-names/links that break or mislead.
- **B — Etherscan key:** wire `ETHERSCAN_API_KEY` from `.env` in the widget code (the user chose the code fix over docs-only), then make the docs/demo/fact-pack correct.
- **C — Consistency:** pitfalls CTA, unify the validate-command form, align the validation page name.

## A — Correctness fixes (exact edits from the findings report)

1. `widgets/gif.mdx` — replace `hold_seconds` → `hold_time` in both places (the caption ~L155 and the floor note ~L178).
2. `tools/render-demo.mdx` — remove the `--fps N` row from the CLI-flags table (the flag doesn't exist in `render.py`). If worth keeping the cadence note, state the fixed 20 fps / 50 ms engine tick in prose, not as a flag. (Nice-to-have, optional in this PR: add the required `config` positional row.)
3. `reference/cli.mdx` — add a `led-ticker plugins` subcommand section; add `--fix` to the `validate` flag table AND the Tips re-list. (Spot-check the `pyproject.toml` entry-point spelling while here.)
4. `tutorial/02-first-config.mdx` — fix the `--duration 20` advice: it isn't forwarded by `make render-demo`. Either drop it or show the direct `uv run python tools/render_demo/render.py config/config.toml -o preview.gif --duration 20` form.
5. `tutorial/03-multi-widget.mdx` — reword "hi-res path activates when `default_scale > 1`" to the accurate trigger: the effective/per-section scale (≥ 2) and a tall-enough band, not `default_scale`.
6. `tutorial/05-polish.mdx` — fix the dead link `/reference/config-pitfalls/` → `/pitfalls/`.
7. `concepts/borders.mdx` — change the Lightbulbs example (~L219–223) from `[[section]]`/`[[section.widget]]` to `[[playlist.section.widget]]` (consistent with every other block).
8. `hardware/longboi.mdx` — fix the contradictory `gpio_slowdown` "Why" (value is already 5): "raise to 4–5" → "raise to 6+ if flicker persists."

## B — Etherscan: wire `.env` in code (+ make the docs true)

**Code** (`src/led_ticker/widgets/crypto/etherscan.py`):
- Make the key optional: `api_key: str` → `api_key: str = ""` (attrs field).
- In `start(...)`, make the `api_key` param default `""` so a config without it is valid.
- Add `import os`.
- In `update()`, resolve the key before building params:
  ```python
  api_key = self.api_key or os.getenv("ETHERSCAN_API_KEY", "")
  if not api_key:
      raise ValueError(
          "ETHERSCAN_API_KEY not set. Add it to your .env file "
          "(or set api_key in the widget config)."
      )
  ```
  and use the resolved `api_key` (not `self.api_key`) in `params["apikey"]`.
- Rationale: keeps existing `api_key = "..."` TOML configs working (the field still wins), AND makes the documented `.env` path real — mirroring `weather.py`'s `os.getenv("WEATHERAPI_KEY")` + `ValueError` pattern. No `validate_config` exists for etherscan, so nothing to relax; the field is just no longer mandatory.

**Test** (`tests/test_widgets/test_etherscan.py`, new — mirror `tests/test_widgets/test_weather.py` session-mocking + `monkeypatch.setenv`):
- With `ETHERSCAN_API_KEY` set and no TOML `api_key`, `update()` uses the env key (assert the request `params["apikey"]` is the env value via a mocked `session.get`).
- With an explicit TOML `api_key`, it wins over the env var.
- With neither set, `update()` raises `ValueError` mentioning `ETHERSCAN_API_KEY`.
- Keep lines ≤ 88 cols (CI ruff over `src/ tests/`).

**Docs** (now that `.env` works):
- `widgets/etherscan.mdx` — present the `.env` path as the primary, working one (`ETHERSCAN_API_KEY` in `.env`, no `api_key` needed in TOML); note the TOML `api_key` field still works as an alternative. Remove the contradiction (it currently shows a placeholder TOML string while telling the reader to use `.env`).
- `docs/site/demos-long/widget-etherscan.toml` — keep it relying on `# requires-env: ETHERSCAN_API_KEY` (this now actually works); ensure it has no bogus `api_key`.
- The etherscan **fact-pack** (`docs/content-source/**` `api_key` entry) — update so it matches the `.env`-first story.

## C — Consistency

1. `pitfalls.mdx` — add a bottom `RelatedPages` CTA (e.g. `tools/validate`, `getting-started`, `transitions`). (Rubric #16 applies to reference pages.)
2. **Unify the validate-command form** across pages — pick ONE: bare `led-ticker validate config/config.toml` (used by getting-started, tutorial-02, tutorial-05) vs `make validate CONFIG=…` (used by pitfalls). **Decision: standardize on the bare `led-ticker validate …` form** (it's what the tutorial path teaches and what `tools/validate.mdx` documents first); update `pitfalls.mdx` to match. (Both work; one form site-wide.)
3. **Align the validation page's name** — the page at `/pitfalls/` is titled "Validation rules"; tutorial-05 calls it "Config pitfalls"; the sidebar/nav says "pitfalls". **Decision: keep the page title "Validation rules" and the `/pitfalls/` route; fix tutorial-05's link text to "Validation rules"** (it's already getting its dead-link fixed in A#6). Don't rename the route (avoids redirects).

## Applying the DOCS-STYLE rubric

These are corrections to existing pages; the tech-writer reviewer confirms each edited page still passes the §3 checklist and that no fix introduced a new issue. The etherscan page, after the fix, should read cleanly (working `.env` path, named secret, blameless copy).

## The review loop

After implementation: a tech-writer review over the edited pages + the etherscan change, and the standard verification (build/lint/ruff/test). No hobbyist-persona pass needed for mechanical corrections, but run it on the etherscan page (its key story was the worst reader-trap).

## Verification

- `make docs-build` + `make docs-lint` clean; every edited link resolves (`astro check`).
- `uv run --extra dev ruff check src/ tests/` clean.
- `tests/test_widgets/test_etherscan.py` passes (env path, TOML path, neither→ValueError); the existing suite stays green.
- Spot-check: `grep -rn "hold_seconds" docs/site` returns nothing; `grep -rn "config-pitfalls" docs/site` returns nothing; `grep -rn "\-\-fps" docs/site/src/content/docs/tools/render-demo.mdx` returns nothing.
- The etherscan demo TOML renders (or is correctly SKIP-guarded by `# requires-env`).

## Out of scope (this PR)

- Batch D (the broad polish: troubleshooting boxes, reader-naming, tutorial time-stamps, OptionsTable migration) — separate later PR.
- The `validate.py:70` animation-hint code bug (the docs are correct; that's a separate code fix, not part of the docs effort).
- Renaming the `/pitfalls/` route or adding redirects.
- Re-auditing; the findings report is the source of the edit list.
