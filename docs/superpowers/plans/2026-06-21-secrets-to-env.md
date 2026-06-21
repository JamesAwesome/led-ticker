# Secrets-to-env (Spec A) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make first-party `config.toml` secret-free — resolve the core `[web].token` / `[busy_light].token` env-first (config field kept as a logged fallback), make the crypto plugin read its CoinGecko key from env only, and document the "secrets live in `.env`" convention — so the web config editor (Spec B) can serve/save the file verbatim.

**Architecture:** A single `resolve_secret_token(env_var, config_value, *, label)` helper reads env-first and logs a deprecation warning when it falls back to a non-empty config field. It's applied at the two token consume sites (the webui sidecar process; the busy-HTTP listener in the display process). The crypto change is in the `led-ticker-plugins` monorepo (its own PR + `crypto-v0.2.0` tag); the engine catalog bumps to that tag.

**Tech Stack:** Python 3.14, stdlib `os`/`logging`, pytest, aiohttp (consume sites), uv workspace (crypto).

## Global Constraints

- Python 3.14; no `from __future__ import annotations`.
- Run `uv run --extra dev ruff check src/ tests/` before every push (CI lint).
- **The led-ticker checkout has a broken git pre-commit/pre-push hook** (stale worktree path) — commit AND push with `--no-verify`; run `uv run pytest` + ruff manually.
- Never commit on `main`; every task on a branch. No "gun"/"footgun" metaphors; follow `docs/DOCS-STYLE.md` for docs.
- No merge or tag without explicit user consent.
- Spec: env-first with config fallback (no upgrade lockout); redaction stays as the net (Spec B). `calendar.ics_url` is out of scope.

---

### Task 1: `resolve_secret_token` helper + wire both token consume sites (engine)

**Files:**
- Modify: `src/led_ticker/config.py` (add the helper)
- Modify: `src/led_ticker/webui/__init__.py:283-296` (`run_webui` — web token)
- Modify: `src/led_ticker/app/run.py:223` (busy `serve_busy` call — busy token)
- Test: `tests/test_secret_token.py` (new)

**Interfaces:**
- Produces: `led_ticker.config.resolve_secret_token(env_var: str, config_value: str, *, label: str) -> str` — returns env value if set, else config_value; logs one `logging.warning` when config_value is non-empty and env is unset.

- [ ] **Step 1: Branch + failing test**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker
git checkout main && git pull --ff-only origin main
git checkout -b feat/secrets-to-env
git branch --show-current   # MUST be feat/secrets-to-env — if main, STOP
```
Create `tests/test_secret_token.py`:
```python
import logging

from led_ticker.config import resolve_secret_token


def test_env_wins_over_config(monkeypatch):
    monkeypatch.setenv("LED_TICKER_TEST_TOK", "from-env")
    assert resolve_secret_token("LED_TICKER_TEST_TOK", "from-config", label="x") == "from-env"


def test_config_fallback_when_env_unset(monkeypatch, caplog):
    monkeypatch.delenv("LED_TICKER_TEST_TOK", raising=False)
    with caplog.at_level(logging.WARNING):
        out = resolve_secret_token("LED_TICKER_TEST_TOK", "from-config", label="web.token")
    assert out == "from-config"
    assert any("web.token" in r.message and "LED_TICKER_TEST_TOK" in r.message for r in caplog.records)


def test_empty_when_neither_set(monkeypatch, caplog):
    monkeypatch.delenv("LED_TICKER_TEST_TOK", raising=False)
    with caplog.at_level(logging.WARNING):
        out = resolve_secret_token("LED_TICKER_TEST_TOK", "", label="web.token")
    assert out == ""
    assert caplog.records == []  # no warning when there's nothing to migrate
```

- [ ] **Step 2: Run — fails (no `resolve_secret_token`)**

```bash
uv run pytest tests/test_secret_token.py -v
```
Expected: FAIL (`ImportError: cannot import name 'resolve_secret_token'`).

- [ ] **Step 3: Add the helper to `config.py`**

Ensure `import os` and `import logging` are present at the top of `src/led_ticker/config.py` (add whichever is missing). Add near the `WebConfig`/`BusyLightConfig` dataclasses:
```python
def resolve_secret_token(env_var: str, config_value: str, *, label: str) -> str:
    """Resolve an auth token env-first, with the config field as a fallback.

    Returns the env var's value when set; otherwise the config field. When the
    config field is used because the env var is unset, logs a one-line warning
    recommending the env var — secrets do not belong in config.toml. Empty when
    neither is set (open / no auth)."""
    env_value = os.getenv(env_var, "")
    if env_value:
        return env_value
    if config_value:
        logging.warning(
            "%s is set in config.toml; move it to the %s environment variable "
            "(secrets do not belong in config.toml).",
            label,
            env_var,
        )
    return config_value
```

- [ ] **Step 4: Run — passes**

```bash
uv run pytest tests/test_secret_token.py -v
```
Expected: PASS (3 tests).

- [ ] **Step 5: Wire the web token (webui process)**

In `src/led_ticker/webui/__init__.py`, `run_webui`, replace `token=web_cfg.token,` with a resolved value. Add `from led_ticker.config import resolve_secret_token` (top of file, with the other imports) and change the call:
```python
    runner = await serve_webui(
        config_path=config_path,
        status_path=Path(web_cfg.status_path).expanduser(),
        host=web_cfg.http_host,
        port=web_cfg.http_port,
        token=resolve_secret_token(
            "LED_TICKER_WEB_TOKEN", web_cfg.token, label="web.token"
        ),
    )
```

- [ ] **Step 6: Wire the busy token (display process)**

In `src/led_ticker/app/run.py` around line 223 (the `serve_busy(...)` call inside `_serve_busy_supervised`), resolve the busy token. Add `from led_ticker.config import resolve_secret_token` if not already imported, and change `token=cfg.token` to:
```python
            token=resolve_secret_token(
                "LED_TICKER_BUSY_TOKEN", cfg.token, label="busy_light.token"
            ),
```
(`cfg` here is the `BusyLightConfig`; confirm by reading `_serve_busy_supervised` — it takes `cfg` and calls `serve_busy(busy, host=cfg.http_host, port=cfg.http_port, token=cfg.token)`.)

- [ ] **Step 7: Full suite + lint, then commit**

```bash
uv run pytest -q 2>&1 | tail -5
uv run --extra dev ruff check src/ tests/ 2>&1 | tail -2
git add src/led_ticker/config.py src/led_ticker/webui/__init__.py src/led_ticker/app/run.py tests/test_secret_token.py
git commit --no-verify -m "feat(config): resolve web/busy tokens env-first (LED_TICKER_WEB_TOKEN/BUSY_TOKEN)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```
Expected: full suite green; ruff clean.

---

### Task 2: Docs + examples — the secrets-in-env convention (engine)

**Files:**
- Modify: `.env.example`
- Modify: `config/config.example.toml` (the `# token = ""` lines under `[web]` ~260 and `[busy_light]` ~238)
- Modify: `docs/site/src/content/docs/concepts/web-status-ui.mdx`
- Modify: `docs/site/src/content/docs/reference/config-options.mdx` (the `[web]`/`[busy_light]` `token` rows)
- Modify: `CLAUDE.md` (add the convention to the relevant invariant)

- [ ] **Step 1: Branch check**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker
git branch --show-current   # MUST be feat/secrets-to-env — if main, STOP
```

- [ ] **Step 2: `.env.example` — add the two token vars**

Append (grouped with the existing keys, with a short comment):
```
# Web UI / busy-light auth tokens (preferred over the config.toml `token` fields;
# required to enable the web config editor — see the web-status-ui docs).
LED_TICKER_WEB_TOKEN=
LED_TICKER_BUSY_TOKEN=
```

- [ ] **Step 3: `config/config.example.toml` — annotate the token fields as fallback**

Under `[web]`, change the `# token = ""` line's comment to point at the env var:
```
# token = ""        # fallback only — prefer LED_TICKER_WEB_TOKEN in .env (secrets don't belong in config.toml)
```
Under `[busy_light]`, add/annotate the equivalent line:
```
# token = ""        # fallback only — prefer LED_TICKER_BUSY_TOKEN in .env
```

- [ ] **Step 4: Docs pages**

In `docs/site/src/content/docs/concepts/web-status-ui.mdx` and the `token` rows of `docs/site/src/content/docs/reference/config-options.mdx`: state that the token is read from `LED_TICKER_WEB_TOKEN` (web) / `LED_TICKER_BUSY_TOKEN` (busy_light), with the config `token =` field as a migration fallback that logs a warning. Keep it matter-of-fact per `docs/DOCS-STYLE.md` (no release-history framing — describe the current recommended way: env var; the field is "a fallback", not "deprecated/legacy").

- [ ] **Step 5: `CLAUDE.md` convention**

Add one line to the Plugin/config invariants: **secrets belong in `.env`, never `config.toml`; first-party plugins read keys from env (`WEATHERAPI_KEY`, `COINGECKO_API_KEY`, `INFLUXDB_*`), and core's `[web]`/`[busy_light]` tokens resolve env-first via `resolve_secret_token`. The webui's value-blind redaction is the net for third-party plugins that ignore this.**

- [ ] **Step 6: Lint docs + commit**

```bash
make docs-lint 2>&1 | tail -5
git add .env.example config/config.example.toml docs/ CLAUDE.md
git commit --no-verify -m "docs: secrets-in-env convention; web/busy token env vars

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```
Expected: docs-lint passes.

---

### Task 3: crypto plugin → env-only (monorepo `led-ticker-plugins`)

**Files (in `/Users/james/projects/github/jamesawesome/led-ticker-plugins`):**
- Modify: `plugins/crypto/src/led_ticker_crypto/coingecko.py:244` (drop inline `api_key`)
- Modify: `plugins/crypto/pyproject.toml` (version `0.1.0` → `0.2.0`)
- Modify: `plugins/crypto/tests/` (the api_key test)
- Modify: `plugins/crypto/README.md` (drop inline `api_key`)

- [ ] **Step 1: Branch (monorepo)**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker-plugins
git checkout main && git pull --ff-only origin main
git checkout -b feat/crypto-env-only-key
git branch --show-current   # MUST be feat/crypto-env-only-key — if main, STOP
```

- [ ] **Step 2: Failing test — inline api_key must be ignored, env used**

Read `plugins/crypto/tests/` for the existing api_key test (likely in `test_coingecko.py` or `test_autolookup.py`). Add/adjust a test asserting env-only resolution:
```python
def test_api_key_from_env_only(monkeypatch):
    monkeypatch.setenv("COINGECKO_API_KEY", "env-key")
    # an inline api_key kwarg is ignored — env is the only source
    headers = _headers_for(api_key_kwarg="inline-key")  # see helper note below
    assert headers.get("x-cg-demo-api-key") == "env-key"
```
If the key resolution isn't independently callable, test through the widget's `create`/`from_config` path: construct with `api_key="inline-key"` in the cfg + `COINGECKO_API_KEY=env-key` set, and assert the outgoing request header uses `env-key` (mirror the existing api_key test's style — read it first and match its harness). Run it; expect FAIL (inline currently wins).

- [ ] **Step 3: Make resolution env-only**

In `coingecko.py:244`, change:
```python
        api_key = kwargs.get("api_key") or os.getenv("COINGECKO_API_KEY", "")
```
to:
```python
        api_key = os.getenv("COINGECKO_API_KEY", "")
```
(`**kwargs` still absorbs a stray inline `api_key` in a user's TOML without error — it's simply unused.)

- [ ] **Step 4: Run the test + full crypto suite**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker-plugins
uv run pytest plugins/crypto -v 2>&1 | tail -10
uv run ruff check plugins/crypto
```
Expected: the new test passes; any prior test that asserted inline-key precedence is updated (not weakened) to the env-only contract; suite green.

- [ ] **Step 5: README + version bump**

In `plugins/crypto/README.md`, remove the inline `api_key = "..."` option from the docs, leaving `COINGECKO_API_KEY` (env) as the only way to raise the rate limit. In `plugins/crypto/pyproject.toml`, bump `version = "0.1.0"` → `version = "0.2.0"`.

- [ ] **Step 6: Commit (monorepo)**

```bash
git add plugins/crypto/
git commit -m "feat(crypto)!: read COINGECKO_API_KEY from env only (drop inline api_key)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

> **Tag (CONSENT-GATED):** after this merges, cut `crypto-v0.2.0` and push it (`git tag crypto-v0.2.0 && git push origin crypto-v0.2.0`). Task 4's catalog bump references this tag, so the tag must exist before Task 4 merges. Do NOT tag without explicit user consent.

---

### Task 4: Engine catalog → `crypto-v0.2.0` (engine)

**Files (engine):**
- Modify: `src/led_ticker/plugins_catalog.json` (crypto `ref`)
- Modify: `tests/test_plugins/test_catalog.py` (the crypto ref/version assertion, if any)

- [ ] **Step 1: Branch check / new branch**

If continuing on `feat/secrets-to-env`, stay; else `git checkout feat/secrets-to-env`. Confirm not `main`. (This task can ride the same engine branch/PR as Tasks 1–2, or its own — keep with 1–2 since it's the same repo + theme.)

- [ ] **Step 2: Bump the crypto ref**

In `src/led_ticker/plugins_catalog.json`, the crypto entry's git source `"ref": "crypto-v0.1.0"` → `"ref": "crypto-v0.2.0"`. Leave `subdirectory`/`url`/`provides` unchanged.

- [ ] **Step 3: Update the catalog test if it pins the version**

`tests/test_plugins/test_catalog.py` asserts each bundled entry's ref starts with `<name>-v` (`test_bundled_entries_install_from_the_monorepo`) — that still passes. If any test pins the exact `crypto-v0.1.0`, update it to `crypto-v0.2.0`. Run:
```bash
cd /Users/james/projects/github/jamesawesome/led-ticker
uv run python -c "import json; json.load(open('src/led_ticker/plugins_catalog.json')); print('json ok')"
uv run pytest tests/test_plugins/test_catalog.py -q 2>&1 | tail -5
```
Expected: json valid; catalog tests green.

- [ ] **Step 4: Commit**

```bash
git add src/led_ticker/plugins_catalog.json tests/test_plugins/test_catalog.py
git commit --no-verify -m "chore(catalog): bump crypto to crypto-v0.2.0 (env-only api key)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Verify + open PRs

- [ ] **Step 1: Engine — full suite, lint, push, PR**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker
uv run --extra dev ruff check src/ tests/ && uv run pytest -q 2>&1 | tail -5
git push --no-verify -u origin feat/secrets-to-env
gh pr create --repo JamesAwesome/led-ticker --base main --head feat/secrets-to-env \
  --title "feat: secrets-to-env (web/busy tokens + crypto catalog) — Spec A" \
  --body "Prerequisite for the web config editor (Spec B). Resolves [web].token / [busy_light].token env-first (LED_TICKER_WEB_TOKEN / LED_TICKER_BUSY_TOKEN) with the config field as a logged fallback; documents the secrets-in-env convention; bumps the crypto catalog entry to crypto-v0.2.0 (env-only key, see led-ticker-plugins PR). config.toml is now secret-free for first-party setups. Do NOT merge without consent."
```

- [ ] **Step 2: Monorepo — push, PR (crypto)**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker-plugins
git push -u origin feat/crypto-env-only-key
gh pr create --repo JamesAwesome/led-ticker-plugins --base main --head feat/crypto-env-only-key \
  --title "feat(crypto)!: env-only COINGECKO_API_KEY (drop inline api_key)" \
  --body "Part of led-ticker secrets-to-env (Spec A). crypto now reads its key from COINGECKO_API_KEY env only; the inline api_key config option is dropped so config.toml stays secret-free. Breaking for anyone using inline api_key (move it to .env). Version bumped to 0.2.0; cut crypto-v0.2.0 after merge. Do NOT merge without consent."
```

- [ ] **Step 3: Confirm CI green on both** (`gh pr checks <PR#>`).

> **Merge order (consent-gated):** crypto PR (monorepo) first → cut `crypto-v0.2.0` → confirm the engine catalog ref resolves → merge the engine PR. The engine PR's catalog points at `crypto-v0.2.0`, so that tag should exist by the time the engine PR merges (CI doesn't fetch the tag, so engine CI is green regardless, but a deploy would need the tag).

---

## Self-review

**Spec coverage (Spec A):**
- core `[web].token` + `[busy_light].token` env-first + warning → Task 1. ✓
- crypto env-only + tag + catalog bump → Tasks 3 (plugin + tag) + 4 (catalog). ✓
- secrets-in-env convention in docs + CLAUDE.md → Task 2 + the CLAUDE.md line in Task 2. ✓
- `calendar.ics_url` out of scope → not touched. ✓
- Tests: env-wins / config-fallback+warning / neither (Task 1); crypto env-only (Task 3); catalog json+ref (Task 4). ✓

**Placeholder scan:** No TBD/TODO. Task 3 Step 2's test harness says "mirror the existing api_key test — read it first" because the exact helper name lives in the plugin's current tests; the implementer reads it and matches. The assertion (env wins over inline) is concrete.

**Type/name consistency:** `resolve_secret_token(env_var, config_value, *, label)` signature is defined in Task 1 and used identically in Steps 5–6; env var names `LED_TICKER_WEB_TOKEN`/`LED_TICKER_BUSY_TOKEN` and tag `crypto-v0.2.0` are consistent across Tasks 1–4 and the PRs.

**Pitfalls flagged:** broken local hook → `--no-verify`; never main; cross-repo ordering (crypto tag before engine catalog deploy); env-first/fallback keeps a path for a config token (intentional, redaction-net covers it); no tag/merge without consent.
