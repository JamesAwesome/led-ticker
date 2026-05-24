# Deep Review 2 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Execute a 5-domain parallel review of the led-ticker codebase and synthesize all findings into `~/Desktop/deep-review-2.md`.

**Architecture:** Five read-only Explore agents run in parallel (one per domain), each producing structured Critical / Significant / Minor findings tagged by domain. A synthesis step in the main session combines all five output streams into a single document matching the format of `~/Desktop/engine-review.md`.

**Tech Stack:** Agent tool (general-purpose subagent type), file reading, markdown synthesis.

---

## Task 1: Run all five review agents in parallel

Dispatch all five agents in a single message so they run concurrently. Do NOT run them sequentially — the whole point is parallel execution.

**Files read per agent:** Specified in each prompt below.

- [ ] **Step 1: Dispatch all five agents simultaneously**

Send one message containing five Agent tool calls with these prompts:

---

### Agent 1 prompt — Engine re-eval `[engine]`

```
You are performing an architectural code review of the led-ticker Python asyncio package. Led-ticker drives RGB LED matrix panels from a Raspberry Pi via a TOML config. You are doing a POST-REFACTOR assessment — several large refactors landed recently and you need to evaluate whether they achieved their goals and whether they introduced any new issues.

CONTEXT on recent large refactors:
- Large #1 (app.py split): app.py (~1256 lines, 5 mixed responsibilities) was split into src/led_ticker/app/ with cli.py, coercion.py, factories.py, run.py. A shared src/led_ticker/_coerce.py was extracted for pure coercion helpers. Goal: remove the "gravity well" pattern, let validate.py and factories.py share construction without a validate_only toggle.
- Large #2+4 (ticker methods): module-level free functions (_scroll_and_delay, _scroll_one_by_one, _scroll_side_by_side, _scroll_between, _run_swap, _show_one, _swap_and_scroll) were pulled onto the Ticker class as methods. Goal: eliminate boilerplate parameter-threading of canvas/frame/notif_queue/scroll_speed.
- Large #3 (ScaledCanvas encapsulation): 24+ isinstance(canvas, ScaledCanvas) sites were replaced with paint_hires(canvas, callback) helper. _y_offset renamed to y_offset_real. rebind_innermost(new_real) added. Goal: stop leaking the abstraction — callers should not need to pattern-match on the wrapper type.

READ ALL of these files thoroughly before making any findings:
- src/led_ticker/app/__init__.py
- src/led_ticker/app/cli.py
- src/led_ticker/app/coercion.py
- src/led_ticker/app/factories.py
- src/led_ticker/app/run.py
- src/led_ticker/_coerce.py
- src/led_ticker/ticker.py
- src/led_ticker/scaled_canvas.py
- src/led_ticker/widget.py
- src/led_ticker/validate.py
- src/led_ticker/config.py
- src/led_ticker/transitions/__init__.py

For each refactor, answer:
1. Did the split actually achieve single-responsibility? Are there residual cross-module tangles (e.g., does cli.py import from factories.py in ways that suggest the boundary is wrong)?
2. Are there leftover validate_only toggle patterns or other signs the split was incomplete?
3. For ticker methods: are there any remaining module-level free functions that should be methods? Any methods that re-thread fields as parameters unnecessarily?
4. For ScaledCanvas: are there any remaining isinstance(canvas, ScaledCanvas) sites outside of scaled_canvas.py itself? Are there any new paint_hires call sites that look wrong? Does unwrap_to_real still appear at scatter/dissolve sites correctly?

Also evaluate the engine against Python async best practices:
- Any asyncio.get_event_loop() calls (deprecated — should be asyncio.get_running_loop() or asyncio.run())
- Missing cancellation handling on long-running tasks
- Fixed-sleep tick loops that don't account for work time (i.e., sleep(N) instead of sleep(max(0, N - elapsed)))
- asyncio.gather vs sequential awaits for independent coroutines

Output format — for EACH finding, use this exact structure:
### [SEVERITY]: [Short title]
**File:** src/led_ticker/path/to/file.py:line_range
**Issue:** One paragraph. Be concrete about the impact.
**Fix direction:** Specific suggestion.

Severity: CRITICAL (correctness bug, broken contract, silent failure), SIGNIFICANT (maintainability tax, DX pain, systemic issue), MINOR (cleanup, polish, consistency).

Tag EVERY finding with [engine].

IMPORTANT: Only report what you actually observe. Do not invent findings. Cite exact file paths and line numbers. If a refactor landed cleanly with no issues, say so explicitly for that refactor.
```

---

### Agent 2 prompt — Test suite quality `[tests]`

```
You are performing a test suite quality review of the led-ticker Python asyncio package. Led-ticker drives RGB LED matrix panels. You are not reviewing the production source — you are reviewing the TEST CODE itself for quality, coverage, and maintainability.

READ ALL of these files thoroughly:
- tests/conftest.py
- tests/stubs/ (all files — these simulate rgbmatrix hardware)
- tests/fixtures/ (all files)
- tests/test_app.py
- tests/test_app_factories_module.py
- tests/test_app_coercion_module.py
- tests/test_app_cli_module.py
- tests/test_app_run_module.py
- tests/test_app_runtime_warnings.py
- tests/test_ticker.py
- tests/test_ticker_display.py
- tests/test_ticker_wraps_forever.py
- tests/test_engine_redraw_contract.py
- tests/test_docs_config_options_drift.py
- tests/test_widget_protocol.py
- tests/test_scaled_canvas.py
- tests/test_validate.py
- tests/test_coerce.py
- tests/test_widgets/test_message.py
- tests/test_widgets/test_two_row.py
- tests/test_widgets/test_gif.py
- tests/test_widgets/test_still.py
- tests/test_widgets/test_image_base.py
- tests/test_widgets/test_row_layout.py
- tests/test_widgets/test_rss_feed.py

IMPORTANT CONTEXT from CLAUDE.md about test fixtures:
- mock_frame: SwapOnVSync.return_value = canvas (same object). Fine for tests that don't care about capture-correctness.
- swapping_frame: rotates between two canvas mocks. Use this in regression tests for the double-buffering constraint (constraint #1: SwapOnVSync return value MUST be captured). A test that should catch dropped-capture bugs but uses mock_frame will silently pass when it should fail.

Evaluate these dimensions:

1. ORGANIZATION AND NAMING
   - Are test files named consistently with their source module?
   - Are test function names descriptive? Do they follow a consistent naming convention?
   - Are test classes used well, or are they just wrappers around a single test?

2. FIXTURE REUSE VS DUPLICATION
   - Are there copy-pasted setup blocks (canvas creation, widget construction, mock wiring) that recur across multiple test files and should be fixtures?
   - Are fixtures in conftest.py appropriately scoped (function/module/session)?
   - Are there test files with their own local fixtures that duplicate conftest.py fixtures?

3. COVERAGE GAPS
   - Based on what you read, which behaviors or code paths appear untested or under-tested?
   - Look specifically for: error paths in factories/coercion, edge cases in validate.py rules, widget fields that have no test, transition edge cases.
   - Note: you are inferring from test code, not running coverage tooling.

4. TEST BRITTLENESS
   - Are tests accessing private attributes (_frame_count, _effect_frames, _pixels, etc.) in ways that would break on valid refactors?
   - Are there magic numbers or unexplained constants in assertions?
   - Are tests asserting implementation details (exact method call counts, specific internal state) rather than observable behavior?

5. META-TRIPWIRES
   - test_engine_redraw_contract.py (AST-scans ticker.py): Is the AST scanner robust? What happens if the loop pattern changes? Is the ALLOW_LIST maintained correctly?
   - test_docs_config_options_drift.py: What does it actually check? Is it comprehensive? Could it silently miss a new field?

6. FIXTURE DISCIPLINE
   - Identify any test that uses mock_frame but exercises the double-buffering swap path — these should use swapping_frame. A test that drops the SwapOnVSync return value and uses mock_frame will always pass (same object returned), masking the constraint-#1 regression.

7. TEST SPEED
   - Any tests doing real file I/O, real HTTP calls, or real subprocess execution that should be mocked?
   - Any unnecessarily heavy setup (building large data structures, sleeping)?

Output format — for EACH finding:
### [SEVERITY]: [Short title]
**File:** tests/path/to/test_file.py:line_range
**Issue:** One paragraph. Be concrete.
**Fix direction:** Specific suggestion.

Severity: CRITICAL (masks real bugs, breaks reliability), SIGNIFICANT (coverage gap, pattern violation, maintainability), MINOR (cleanup, naming, polish).

Tag EVERY finding with [tests].

Only report what you actually observe. Cite exact file paths and line numbers.
```

---

### Agent 3 prompt — Python idioms / modern Python `[python]`

```
You are performing a Python idioms and modern Python review of the led-ticker source package. Led-ticker is an asyncio Python 3.11+ toolkit that drives RGB LED matrix panels. You are evaluating the production source for adherence to modern Python best practices — not looking for bugs, but for patterns that are outdated, inconsistent, or miss opportunities from Python 3.11+.

READ ALL of these files:
- src/led_ticker/__init__.py
- src/led_ticker/_compat.py
- src/led_ticker/_types.py
- src/led_ticker/_coerce.py
- src/led_ticker/app/__init__.py
- src/led_ticker/app/cli.py
- src/led_ticker/app/coercion.py
- src/led_ticker/app/factories.py
- src/led_ticker/app/run.py
- src/led_ticker/ticker.py
- src/led_ticker/frame.py
- src/led_ticker/scaled_canvas.py
- src/led_ticker/text_render.py
- src/led_ticker/validate.py
- src/led_ticker/widget.py
- src/led_ticker/drawing.py
- src/led_ticker/colors.py
- src/led_ticker/color_providers.py
- src/led_ticker/color_lut.py
- src/led_ticker/animations.py
- src/led_ticker/borders.py
- src/led_ticker/pixel_emoji.py
- src/led_ticker/config.py
- src/led_ticker/widgets/__init__.py
- src/led_ticker/widgets/message.py
- src/led_ticker/widgets/two_row.py
- src/led_ticker/widgets/gif.py
- src/led_ticker/widgets/still.py
- src/led_ticker/widgets/_image_base.py
- src/led_ticker/widgets/_frame_aware.py
- src/led_ticker/widgets/_row_layout.py
- src/led_ticker/widgets/_image_fit.py
- src/led_ticker/transitions/__init__.py
- src/led_ticker/transitions/push.py
- src/led_ticker/transitions/wipe.py
- src/led_ticker/transitions/effects.py

Evaluate these specific dimensions:

1. ASYNCIO PATTERNS
   - asyncio.get_event_loop() calls: deprecated in 3.10+. Should be asyncio.get_running_loop() (inside a running loop) or asyncio.run() (at entry point).
   - Sync calls blocking the event loop: CPU-heavy operations (parsing, image processing, large loops) called directly in async functions without asyncio.to_thread(). Note: feedparser was already identified as needing to_thread — look for others.
   - asyncio.gather vs sequential awaits: if multiple independent coroutines are awaited one after another (await a(); await b()), they should be gathered.
   - asyncio.TaskGroup (Python 3.11+): where multiple tasks are created and awaited, TaskGroup provides better cancellation semantics than gather.
   - Cancellation handling: are long-running loops (widget update loops, the main display loop) cancellable? Do they handle asyncio.CancelledError correctly?

2. ATTRS USAGE
   - Style consistency: @attrs.define vs @attr.s vs @attr.attrs — should be uniformly @attrs.define (modern).
   - Validators: manual isinstance checks or value checks in __attrs_post_init__ that should be attrs validators.
   - __init_subclass__ guards: are the existing ones (on ColorProvider, BorderEffect) robust? Do they catch all required abstract properties?
   - Mutable defaults: any list/dict defaults not using attrs.Factory?

3. TYPE ANNOTATIONS
   - Any bare: dict (not dict[str, X]), list (not list[X]), tuple (not tuple[X, ...]), type (not type[X]) — these are unparameterized and lose type information.
   - Missing return types on public methods/functions.
   - Optional[X] where X | None is cleaner (3.10+).
   - Union[X, Y] where X | Y is cleaner (3.10+).
   - typing.List, typing.Dict, typing.Tuple, typing.Set (all deprecated in 3.9+ in favour of builtins).
   - Any used as a type annotation where a more specific type is available (beyond the already-fixed Canvas=Any).
   - Callable[..., Any] where a more specific Callable type is possible.

4. PYTHON 3.11+ FEATURES AVAILABLE BUT UNUSED
   - Self type (typing.Self): methods that return self or cls instances.
   - LiteralString: functions that take SQL/shell/format strings where injection matters.
   - ExceptionGroup / except*: not likely needed here, but check.
   - match statement: chains of if/elif isinstance(...) or if x == "a" / elif x == "b" that could be match/case.
   - StrEnum / IntEnum: any string or int constants that are effectively enums.

5. DEPRECATED / OUTDATED PATTERNS
   - %-style string formatting: "hello %s" % name (use f-strings).
   - .format()-style string formatting: "hello {}".format(name) (use f-strings where not already).
   - os.path usage: os.path.join, os.path.exists, os.path.dirname (use pathlib.Path).
   - open() calls without explicit encoding=.
   - bare except: or except Exception: without re-raise (swallowed exceptions).

6. GENERAL BEST PRACTICES
   - Magic numbers: unexplained numeric literals in logic (not in constants).
   - Functions longer than ~50 lines doing more than one thing.
   - Module-level mutable state (global dicts/lists used as caches without thread-safety consideration in async context).
   - Inconsistent naming conventions (camelCase mixed with snake_case for Python identifiers).

Output format — for EACH finding:
### [SEVERITY]: [Short title]
**File:** src/led_ticker/path/to/file.py:line_range
**Issue:** One paragraph. Describe the pattern and its impact.
**Fix direction:** Specific suggestion. For type annotation findings, show the before/after.

Severity: CRITICAL (correctness risk from the pattern), SIGNIFICANT (material DX/maintainability issue), MINOR (cleanup, consistency, modernization).

Tag EVERY finding with [python].

Only report what you actually observe. Cite exact file paths and line numbers. Do NOT flag the Canvas=Any issue — it was already found and addressed. If a dimension has no findings, say so explicitly.
```

---

### Agent 4 prompt — Install, deploy & CI `[deploy]`

```
You are performing a DevOps and infrastructure review of the led-ticker project's install scripts, deploy configuration, Docker setup, and CI/CD pipeline.

CONTEXT:
- Led-ticker runs on a Raspberry Pi (Pi 4 or Pi 5) as a systemd service.
- It requires a custom rgbmatrix C library that must be built from source.
- The Docker image is the primary production deployment method.
- There is also a bare-metal install path via deploy/install.sh.
- Two Pi hardware targets: Pi 4 (RGBMATRIX_REF=main) and Pi 5 (RGBMATRIX_REF=pi5_support).
- The CI runs on a self-hosted runner, not GitHub-hosted runners.

READ ALL of these files thoroughly:
- deploy/install.sh
- deploy/led-ticker.service
- Dockerfile
- compose.yaml
- docker-compose.yml
- .github/workflows/ci.yml
- .github/workflows/docs-deploy.yml
- .github/dependabot.yml
- README.md

Evaluate these dimensions:

1. INSTALL.SH CORRECTNESS
   - The script checks `python3 -c "import rgbmatrix" 2>/dev/null` BEFORE activating the venv. This means it checks the system Python, not the venv Python. If rgbmatrix is installed in the venv but not system-wide, the check fails and it tries to rebuild unnecessarily. Is this a real bug?
   - After `source "${INSTALL_DIR}/venv/bin/activate"`, the script uses `pip install "${REPO_DIR}"`. Does this use the venv pip or the system pip? (Hint: source activates the venv, so pip should be the venv pip — but verify.)
   - Idempotency: what happens on a second run? Does `mkdir -p "${INSTALL_DIR}"` handle it? Does `python3 -m venv` handle re-runs on an existing venv?
   - Update path: if a user wants to upgrade led-ticker to a new version, what do they do? Is there a documented path?
   - Error handling: `set -euo pipefail` is present. What specific failures could still be silent (e.g., the rgbmatrix check, the pip install)?
   - The PI5=1 conditional sets the same RGBMATRIX_REPO for both branches. Is this intentional or a copy-paste oversight? (The comment says "Pi 4 (existing sign), pi5_support = kingdo9 PR #1886 + our build patch" — so the repo IS the same, only the ref differs. Verify.)

2. SYSTEMD UNIT (led-ticker.service)
   - Security hardening: is ProtectSystem used? NoNewPrivileges? PrivateTmp? CapabilityBoundingSet? ProtectHome?
   - Restart policy: what RestartSec is configured? Is there a StartLimitIntervalSec?
   - Environment loading: how does the service load API keys from .env? Is it EnvironmentFile=?
   - WorkingDirectory: is it set correctly for config file resolution?
   - User: does the service run as root? Is this necessary for LED matrix hardware access?

3. DOCKERFILE
   - USER directive: does the image run as root? If so, is this documented as intentional (rgbmatrix needs GPIO access)?
   - Multi-stage build: is it used?
   - Layer ordering: are dependency layers before source layers for cache efficiency?
   - .env handling: is the .env file baked into the image or mounted at runtime?
   - Base image: python:3.13-bullseye — bullseye is Debian 11. Is this still the right choice given the rgbmatrix build requirements? Is there a slimmer option (-slim)?
   - Are there any obvious security issues (exposed secrets, world-writable files, running pip as root in final stage)?

4. COMPOSE FILES
   - Are compose.yaml and docker-compose.yml consistent in their service definitions?
   - Which is canonical? Is docker-compose.yml a legacy v1-format file?
   - Does compose.yaml mount the config correctly (:ro)?
   - Is the .env file handled via env_file: or environment:?

5. CI PIPELINE
   - Self-hosted runner security: GitHub Actions workflows triggered by pull_request run on the self-hosted runner. Can a PR from a fork trigger the runner? This is a serious security risk if so.
   - Coverage threshold: --cov is run but is --cov-fail-under set anywhere? Without it, coverage can drop to 0% without failing CI.
   - Missing checks: no Docker build verification (make build-docker is never run in CI — a broken Dockerfile won't be caught until deploy time).
   - Action version pinning: actions/checkout@v6, astral-sh/setup-uv@v8.1.0, actions/setup-node@v6.4.0 — are these pinned to a commit SHA? Pinning by tag means a tag can be moved to a malicious commit.
   - The ci-passed rollup job: if the changes job is skipped (e.g., on a merge queue event), what happens? Does the rollup correctly handle this?
   - docs-deploy.yml: what triggers it? Does it deploy on every push to main, or only when docs change? Is there a review gate?

6. DEPENDABOT
   - Is Docker (the Dockerfile base image) covered? (Python, npm, github-actions are covered — check if Docker is too.)
   - Are the grouping strategies sensible? Is astro excluded from the group correctly?

Output format — for EACH finding:
### [SEVERITY]: [Short title]
**File:** path/to/file.ext:line_range
**Issue:** One paragraph. Be concrete about the impact.
**Fix direction:** Specific suggestion.

Severity: CRITICAL (security risk, correctness bug, broken deployment), SIGNIFICANT (operational risk, missing safeguard), MINOR (cleanup, modernization, optional hardening).

Tag EVERY finding with [deploy].

Only report what you actually observe. Cite exact file paths and line numbers.
```

---

### Agent 5 prompt — Tooling & dependency hygiene `[tooling]`

```
You are performing a tooling and dependency hygiene review of the led-ticker project's scripts, tools, and package configuration.

CONTEXT:
- render_demo: renders led-ticker configs to animated GIFs for the docs site. Uses recording.py to intercept SwapOnVSync and snapshot canvas state. placeholder.py synthesizes stand-in assets for brand images not in the repo.
- gif_plan: calculates recommended render durations for demo GIFs (how long to run the renderer for a config before cutting).
- render_emoji_previews.py: generates emoji preview assets for the docs.
- check-no-foreign-lockfiles.sh: a pre-commit script.
- crypto-ticker.py: a standalone script in scripts/.
- The package uses uv for dependency management (pyproject.toml + uv.lock).

READ ALL of these files thoroughly:
- tools/render_demo/render.py
- tools/render_demo/recording.py
- tools/render_demo/placeholder.py
- tools/render_demo/README.md
- tools/render_demo/test_render.py
- tools/render_demo/test_renderer_multiframe.py
- tools/render_demo/test_recording.py
- tools/render_demo/test_placeholder.py
- tools/gif_plan/plan.py
- tools/gif_plan/test_plan.py
- tools/gif_plan/conftest.py
- tools/render_emoji_previews.py
- scripts/check-no-foreign-lockfiles.sh
- scripts/crypto-ticker.py
- Makefile
- pyproject.toml

Evaluate these dimensions:

1. RENDER_DEMO ROBUSTNESS
   - recording.py: the SwapOnVSync intercept pattern — is it resilient? What happens if the canvas doesn't have a _pixels dict (e.g., real hardware canvas accidentally passed)?
   - placeholder.py: what types of missing assets does it handle? What does it NOT handle (e.g., missing font files vs missing image files)? Are there edge cases that could cause it to silently produce a wrong asset?
   - render.py: what happens with a bad TOML? A widget that raises during draw? A config that references a missing font?
   - Test coverage: test_render.py, test_renderer_multiframe.py, test_recording.py, test_placeholder.py — what do they cover? What's missing?

2. GIF_PLAN CORRECTNESS
   - plan.py: is the duration calculation correct for all mode types (swap, forever_scroll, infini_scroll)?
   - test_plan.py: what does it cover? Edge cases for empty playlists, single widgets, infinite-scroll configs?
   - Is the output format (recommended duration + cutoff guard) documented?

3. RENDER_EMOJI_PREVIEWS.PY
   - Is it documented? Is there a Makefile target for it?
   - Is it still needed and maintained, or is it a one-off script that has become stale?
   - Does it have error handling?

4. CHECK-NO-FOREIGN-LOCKFILES.SH
   - What does it check? Does it correctly identify the files it's looking for?
   - Is it invoked as a pre-commit hook? Is it in .pre-commit-config.yaml?
   - Edge cases: what if there are no lockfiles at all? What if a new lockfile type is added?

5. CRYPTO-TICKER.PY
   - What does it do? Is it documented in the README or Makefile?
   - Does it have dependencies beyond what's in pyproject.toml?
   - Is it tested?
   - Is it still actively used or is it an orphaned prototype?

6. MAKEFILE PATTERNS
   - Are all targets correctly declared .PHONY?
   - The render-long-demos target uses `set -a; . ./.env; set +a` to source env vars. This is bash syntax. The developer's shell is fish. Does `make` use bash or fish? (Make always uses /bin/sh by default, not the user's shell — but verify this works with POSIX sh.)
   - Is there a `make upgrade` or `make update` target for updating dependencies?
   - Any missing targets that would be useful (e.g., `make render-emoji-previews`)?
   - Are there Makefile variables that should be documented?

7. PYPROJECT.TOML DEP HYGIENE
   - tomli-w: listed as a runtime dependency. Search render_demo/render.py, all app/ files, and validate.py for `import tomli_w` or `tomli-w`. If it's not imported, it's an unused dep and should be moved to dev or removed.
   - tomli: listed as `tomli>=2.0; python_version<'3.11'`. But requires-python = ">=3.11". This conditional is dead — Python 3.11+ has tomllib in stdlib. This dep can be removed entirely.
   - imageio: what does led-ticker use imageio for? Search src/ for `import imageio`. Compare to Pillow usage — is there overlap where Pillow could replace imageio?
   - Version pins: are lower bounds reasonable for the current feature usage? Any packages missing upper bounds that could cause silent breakage on a major bump?
   - Dev deps: is everything in [project.optional-dependencies] dev actually used? (ruff, pyright, pytest, pytest-asyncio, pytest-cov, pytest-mock, pre-commit — these all seem used. Verify.)
   - hatchling as build backend: is this the right choice? Any issues with it vs setuptools?

Output format — for EACH finding:
### [SEVERITY]: [Short title]
**File:** path/to/file.ext:line_range
**Issue:** One paragraph. Be concrete.
**Fix direction:** Specific suggestion.

Severity: CRITICAL (broken behavior, security issue), SIGNIFICANT (correctness risk, missing safeguard, wasted dep), MINOR (cleanup, missing docs, optional improvement).

Tag EVERY finding with [tooling].

Only report what you actually observe. Cite exact file paths and line numbers.
```

---

- [ ] **Step 2: Verify each agent returned structured findings**

Before synthesizing, confirm each agent output:
- Contains at least one finding (a "no findings" result in any domain is a signal to re-dispatch with a more targeted prompt)
- Uses the `### [SEVERITY]: [title]` format consistently
- Tags every finding with its domain tag

If any agent returned unstructured prose without the finding format, re-dispatch that agent with a note to follow the output format exactly.

---

## Task 2: Synthesize findings into deep-review-2.md

Combine all five agent outputs into a single document. This task runs in the main session after all agents have returned.

**Output file:** `~/Desktop/deep-review-2.md`

- [ ] **Step 1: Collect and deduplicate findings**

Before writing the document, mentally cross-reference all findings for duplicates (same issue spotted by two agents from different angles). Where two findings overlap, merge them into one entry and note both perspectives.

- [ ] **Step 2: Assign final severity**

The agents may have different severity calibrations. Normalize:
- CRITICAL: must fix before shipping anything new — correctness bugs, security issues, silent failure modes
- SIGNIFICANT: meaningful tax on correctness, maintainability, or contributor DX — fix in the next round of batches
- MINOR: cleanup, polish, consistency — batch into a single "polish" PR

When in doubt, promote rather than demote. It's better to have a SIGNIFICANT that turns out minor than a MINOR that turns out significant.

- [ ] **Step 3: Identify cross-cutting observations**

After cataloguing all findings, look for themes that span multiple domains. Examples of cross-cutting patterns from the first review:
- "The extension boundary is typed as Any" (affected engine, widget, transition layers)
- "Silent failure is the default failure mode" (affected validation, registry, type coercion)

Write 2–5 cross-cutting observations (CC1, CC2...) that group findings by root cause rather than by domain.

- [ ] **Step 4: Write the prioritized action list**

Group findings into three tiers:
- **Quick Wins (< 1 PR each):** Single-file, low-risk changes. Anything that's a one- or two-liner fix, a dead code deletion, or a clear mechanical swap (e.g., `Optional[X]` → `X | None`).
- **Medium (1–2 PRs each):** Changes requiring a few files, a new module, or careful test updates.
- **Large (multi-PR):** Architectural changes, new subsystems, significant refactors.

Within each tier, order by: highest user/contributor impact first, then easiest-first as a tiebreaker.

- [ ] **Step 5: Write the document**

Write `~/Desktop/deep-review-2.md` with this exact structure:

```markdown
# Deep Review 2 — Findings
Date: 2026-05-24

## Executive Summary

[2-3 sentences. What is the dominant theme? What is the single most important finding? How does the codebase compare to the state before the large refactors?]

## Critical Findings

### C1. [domain tag] [title]
...

## Significant Findings

### S1. [domain tag] [title]
...

## Minor Findings

### M1. [domain tag] [title]
...

## Cross-Cutting Observations

### CC1. [title]
...

## Prioritized Action List

### Quick Wins (< 1 PR each)
1. **[Short title]** — [Finding ref]. [File]. [One sentence on what to change.]
...

### Medium (1–2 PRs each)
1. **[Short title]** — [Finding ref]. [1-2 sentences on scope.]
...

### Large (multi-PR)
1. **[Short title]** — [Finding refs]. [1-2 sentences on scope.]
...
```

- [ ] **Step 6: Verify the document**

After writing, check:
- Every finding from every agent appears somewhere in the document (Critical/Significant/Minor)
- Every item in the prioritized action list points back to a finding (no orphan action items)
- The executive summary accurately reflects the dominant themes — not a laundry list, a theme
- Domain tags (`[engine]`, `[tests]`, `[python]`, `[deploy]`, `[tooling]`) appear on every finding

- [ ] **Step 7: Save memory**

After the document is complete, save a project memory noting:
- The review is done
- The output file path
- The top 2-3 cross-cutting themes for context in future conversations

---

## Self-Review Notes (written after drafting)

**Spec coverage check:**
- ✓ Engine re-eval agent: covers post-refactor assessment + async best practices
- ✓ Test suite agent: covers all 7 quality dimensions from spec
- ✓ Python idioms agent: covers asyncio, attrs, typing, 3.11+, deprecated patterns
- ✓ Install/deploy/CI agent: covers all 6 dimensions from spec
- ✓ Tooling agent: covers render_demo, gif_plan, scripts, Makefile, dep hygiene
- ✓ Synthesis task: produces the exact document structure from spec
- ✓ Domain tags: specified in every agent prompt and in synthesis step

**Placeholder scan:** No TBDs or incomplete steps. Every agent prompt is self-contained.

**File path accuracy:** Verified against actual repo state (2026-05-24). app/ submodules confirmed present. color_lut.py confirmed. recording.py and placeholder.py in render_demo confirmed.
