# Design: Secrets out of config.toml, into env (prerequisite)

**Date:** 2026-06-21
**Status:** Approved for planning
**Relationship:** Prerequisite for the [web config editor](2026-06-21-web-config-editor-design.md). Independently valuable as config hygiene.

## Motivation

The web config editor will serve and save `config.toml` **verbatim**. That is only safe if the file holds no secrets. A secret-audit of core + all 10 first-party plugins (2026-06-21) found `config.toml` is almost secret-free already — this spec closes the last gaps so "first-party `config.toml` contains no secrets" is a guarantee, not a hope. Redaction stays as a defense-in-depth net for third-party plugins that ignore the convention.

## Audit result (what this spec acts on)

| surface | secret | today | action |
|---|---|---|---|
| core `[web].token` | web-UI auth token | inline in config | → env `LED_TICKER_WEB_TOKEN` (config field kept as fallback) |
| core `[busy_light].token` | busy-HTTP push token | inline in config | → env `LED_TICKER_BUSY_TOKEN` (config field kept as fallback) |
| crypto plugin `api_key` | CoinGecko demo key | env **or** inline (`kwargs.get("api_key") or os.getenv(...)`) | env-only (drop inline) |
| pool plugin | InfluxDB url/org/bucket/token | env-only ✅ | none |
| weather plugin | WeatherAPI key | env-only ✅ | none |
| calendar plugin `ics_url` | private calendar URL | inline in config | **out of scope** — feed *content*, not an API key; not name-matched by redaction; env is the wrong home for a URL |
| baseball, rss, nyancat, pokeball, pacman, sailor_moon | — | no secrets | none |

## Design

### Core token migration (env-first, config fallback)

Both `[web].token` and `[busy_light].token` resolve **env-first, config-field fallback**, so existing signs keep working on upgrade (no lockout) while new setups move the secret out of the file:

- Resolution: `os.getenv("LED_TICKER_WEB_TOKEN") or web_cfg.token` (and the busy equivalent). Env wins when set.
- If the config field is non-empty AND the env var is unset, log a one-line startup warning recommending the env var (same channel as the existing rule-37 coercion warnings). No hard break.
- Docs + `config.example.toml` / `.env.example`: present the env var as the canonical way; mark the inline `token =` field as a fallback for migration only.
- **Interaction with the editor (Spec B):** the recommended end state (token in env) makes `config.toml` truly secret-free → editor serves verbatim. A lingering inline `token` is still caught by redaction-as-net (Spec B), so the fallback is safe, just not ideal.

Resolution lives where the token is consumed today (`webui` build / `busy_http.serve_busy` call sites in `app/run.py` and `webui/run_webui`), reading env at consume time. No new config schema field.

### crypto plugin → env-only (cross-repo)

In `led-ticker-plugins/plugins/crypto`: change `api_key = kwargs.get("api_key") or os.getenv("COINGECKO_API_KEY", "")` to read env only (`os.getenv("COINGECKO_API_KEY", "")`); drop the inline `api_key` config option + its mention in the plugin README / available-plugins docs. Ships as its own crypto PR + `crypto-v0.2.0` tag, and the engine catalog entry (`plugins_catalog.json`) bumps `crypto` to `crypto-v0.2.0`.

This is a behavior change for anyone using inline `api_key` (a low-stakes demo rate-limit key) — they move it to `.env`. Documented in the crypto README; no silent fallback (keeps the plugin's config genuinely secret-free).

### Convention + docs

Add to the docs (plugins page + a short note on the config + web-status pages) and `CLAUDE.md`: **secrets belong in `.env`, never `config.toml`.** First-party plugins follow this; redaction protects against third-party plugins that don't.

## Scope

- IN: core `[web].token` + `[busy_light].token` env-first resolution + warning + docs; crypto env-only + tag + catalog bump; the secrets-in-env convention in docs/CLAUDE.md.
- OUT: `calendar.ics_url` (not a key); removing the config token fields entirely (kept as fallback); the editor itself (Spec B); forcing third-party plugins (can't — convention + redaction only).

## Testing

- Core: env var present → used; env unset + config field set → fallback used + warning logged; both unset → open/no-auth as today. (Web + busy each.)
- crypto: `COINGECKO_API_KEY` env used; an inline `api_key` left in a TOML table is silently inert (the value is no longer read — it lands in `**kwargs` and is unused, no error); README/available-docs drop the inline `api_key` mention.
- Docs drift: catalog `crypto` ref == `crypto-v0.2.0`.

## Risks

- The env-first/config-fallback keeps a path where a token can still sit in `config.toml`; that's intentional (no upgrade lockout) and covered by redaction-as-net in Spec B. The "secret-free" guarantee is for the *recommended* setup, enforced by docs + first-party compliance, not by hard removal.
