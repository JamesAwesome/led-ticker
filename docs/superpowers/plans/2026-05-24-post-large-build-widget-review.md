# Post-Implementation Review — Large: `_build_widget` Decomposition

> **For agentic workers:** Dispatch the agent prompt below as a single `general-purpose` subagent. Read its output, then synthesize findings into a short findings doc at `~/Desktop/post-large-build-widget-review.md`.

---

## Agent prompt

```
You are performing a post-implementation code review of a completed refactor in the led-ticker Python asyncio codebase. Led-ticker drives RGB LED matrix panels from a Raspberry Pi via a TOML config.

CONTEXT — what changed:
`_build_widget` in `src/led_ticker/app/factories.py` was a 308-line monolith with a `validate_only: bool` toggle that served two structurally different callers. It was decomposed over 10 commits (now on main) into:

1. `_resolve_asset_paths(widget_cfg, widget_type, config_dir)` — resolves relative `path` values for gif/image widgets; mutates in-place.
2. `_resolve_fonts(widget_cfg, cls, panel_h_for_warning)` — resolves font name strings to font objects; handles hires guards and clip warnings; mutates in-place.
3. `_validate_cfg_fields(widget_cfg, cls, widget_type)` — unknown-field check with difflib did-you-mean hints; raises ValueError.
4. `validate_widget_cfg(widget_cfg, session, ...) -> None` — PUBLIC async function that runs all validation phases without constructing any widget. The former `_build_widget(validate_only=True)` path, now explicit.
5. `_build_widget(widget_cfg, session, ...) -> Any` — now a 38-line thin orchestrator: peek type → validate → get class → construct.

The `validate_only: bool` parameter was removed from `_build_widget`. `src/led_ticker/validate.py` now calls `validate_widget_cfg` directly.

READ ALL of these files thoroughly before making any findings:
- src/led_ticker/app/factories.py
- src/led_ticker/app/__init__.py
- src/led_ticker/validate.py  (focus on _run_build_checks and _validate_widget_fields)
- tests/test_app.py  (focus on TestResolveAssetPaths, TestResolveFonts, TestValidateCfgFields, TestValidateWidgetCfg, TestUnknownKwargAllowlist)
- tests/test_validate.py

Evaluate these dimensions:

1. DECOMPOSITION COMPLETENESS
   - Did the extraction actually achieve single-responsibility for each helper? Are there any lingering multi-concern blobs in `validate_widget_cfg`?
   - Is `_build_widget` genuinely a thin orchestrator, or does it still contain logic that belongs in a helper?
   - Is `validate_widget_cfg` a complete and accurate validation gate? Could a config that should fail validation slip through it and cause a confusing error at construction time?
   - Are the helper functions genuinely independent (testable in isolation, no hidden coupling)?

2. VALIDATE_WIDGET_CFG AS A PUBLIC API
   - The function is now public (exported from `app/__init__.py` and called by `validate.py`). Is its signature stable? Are there parameters that would need to change if validation requirements evolve?
   - The `session` parameter is accepted but unused (noted in the docstring). Is this a design smell that will attract future misuse, or is it the right call for API parity?
   - Does the docstring accurately describe the contract — especially the in-place mutation of `widget_cfg` (type is popped, values coerced)? Could a caller be surprised by this side effect?
   - Is it tested as a public API (e.g., called from `validate.py` paths), or only tested directly? Both matter.

3. RESIDUAL VALIDATE.PY COUPLING
   - `validate.py` now imports `validate_widget_cfg` from `factories.py`. Does this create a circular import risk? (Check if `factories.py` imports from `validate.py` — it does: `from led_ticker.validate import MigrationError` inside `validate_widget_cfg`'s body. Does this lazy import correctly prevent the cycle?)
   - Is `_run_build_checks` in `validate.py` clean after the update? Does it pass the right arguments to `validate_widget_cfg`?
   - Are there any other `_build_widget` call sites in `validate.py` that were NOT updated?

4. TEST QUALITY FOR THE NEW HELPERS
   - `TestResolveAssetPaths` (5 tests): do they adequately cover the in-place mutation contract? Is the `"image"` type path tested, or only `"gif"`?
   - `TestResolveFonts` (10 tests): is the `panel_h_for_warning` warning path now tested (a warning branch test was added)? Any remaining gaps?
   - `TestValidateCfgFields` (4 tests): the registry-name tripwire (`type='message'` not `type='TickerMessage'`) — is it meaningful and would it catch a regression?
   - `TestValidateWidgetCfg` (4 tests): the does-not-instantiate test spies on `TickerMessage.__init__`. Would this catch a regression in `validate_widget_cfg` calling `cls(**widget_cfg)` by mistake? Is the spy pattern robust?
   - Are there integration-style tests (e.g., roundtrip: config TOML → `validate_widget_cfg` → no error, then `_build_widget` → widget instance) or only unit tests on each helper in isolation?

5. EDGE CASES AND FAILURE MODES
   - What happens when `_build_widget` is called with a `widget_cfg` missing the `"type"` key? Previously `validate_only=True` and the construction path shared the same `widget_cfg.pop("type")` — now `_build_widget` does `widget_cfg["type"]` (peek) BEFORE calling `validate_widget_cfg`. If `"type"` is missing, it raises `KeyError` immediately, before `validate_widget_cfg` can raise a clearer error. Is this a UX regression?
   - `validate_widget_cfg` calls `_coerce_widget_cfg(widget_cfg, coercion_collector)` which mutates the dict. If `validate_widget_cfg` raises halfway through (e.g., MigrationError after coercion but before `_validate_cfg_fields`), the dict is in a partially-mutated state. The caller (`validate.py`) passes a `copy.deepcopy` so this doesn't matter there — but could `_build_widget` ever be called in a way that re-uses the same dict after a failure? Check the call site in `run.py`.
   - The `widget_type: str = widget_cfg["type"]` annotation at line 432 uses `str` but `widget_cfg` is `dict[str, Any]`, so `widget_cfg["type"]` is actually `Any`. Pyright accepts `Any` → `str`. Is the annotation misleading (it claims `str` but gets `Any` from the dict value)? Could a non-string `type` value (e.g., an int from a malformed TOML) slip past this and cause a confusing downstream error?

6. DOCS AND DISCOVERABILITY
   - Is `validate_widget_cfg` mentioned in `CLAUDE.md`? It's now a public API that external callers (validate.py) depend on — should it have an entry in the architecture section?
   - Are the per-helper docstrings accurate and consistent? Do they all document the in-place mutation contract?

Output format — for EACH finding:
### [SEVERITY]: [Short title]
**File:** src/led_ticker/path/to/file.py:line_range
**Issue:** One paragraph. Be concrete about the impact.
**Fix direction:** Specific suggestion.

Severity: CRITICAL (correctness bug, broken contract, silent failure), SIGNIFICANT (maintainability tax, API risk, gap that will cause problems), MINOR (cleanup, polish, missed opportunity).

Tag every finding with one of: [decomp], [api], [coupling], [tests], [edge], [docs].

Only report what you actually observe. Cite exact file paths and line numbers. If a dimension has no findings, say so explicitly.
```
