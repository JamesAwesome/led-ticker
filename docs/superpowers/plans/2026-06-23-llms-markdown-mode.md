# Markdown Mode (llms.txt) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose the docs site as agent-consumable Markdown — `/llms.txt` (index), `/llms-full.txt` (whole docs), `/llms-small.txt` — generated at build time by the `starlight-llms-txt` plugin.

**Architecture:** Add the `starlight-llms-txt` Starlight plugin to `docs/site/astro.config.mjs`; it emits the `llms*.txt` files into `dist/` on `astro build`, served at the public site root by the existing Cloudflare deploy. Verify the high-value content (`OptionsTable` field tables, `TomlExample` blocks) survives into the Markdown, guard it with a build-time check, and make the files discoverable.

**Tech Stack:** Astro 6.4, Starlight 0.40, pnpm, Node 24, the `starlight-llms-txt` plugin.

## Global Constraints

- All work is in `docs/site/` (the docs site) and the engine repo's `Makefile` / `.github/workflows/ci.yml`. No engine Python code.
- The docs site uses **pnpm** (`corepack enable` first). Build: `cd docs/site && pnpm install --frozen-lockfile && pnpm run build` (== `make docs-build`). Lint: `pnpm run lint` (prettier --check + astro check, == `make docs-lint`).
- Cloudflare Access is removed — the endpoints are public; no auth/bypass work.
- Include **all** docs pages in the export (completeness over curation). Per-page `<url>.md` routes are OUT (follow-up).
- The export MUST preserve the per-widget `OptionsTable` field tables and `TomlExample` config blocks — that is the agent value; a fidelity sentinel guards it.
- Pin a known-good `starlight-llms-txt` version compatible with Starlight 0.40 / Astro 6.4; the first task verifies the build before anything builds on it.
- Keep `make docs-build` + `make docs-lint` green; the human-facing site is unchanged.

---

### Task 1: Install + wire the plugin; verify the three outputs generate

**Files:**
- Modify: `docs/site/package.json`, `docs/site/pnpm-lock.yaml` (add the dep)
- Modify: `docs/site/astro.config.mjs` (register the plugin)

**Interfaces:**
- Produces: a docs build that writes `docs/site/dist/llms.txt`, `dist/llms-full.txt`, and `dist/llms-small.txt`.

- [ ] **Step 1: Add the plugin dependency**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker/docs/site
corepack enable
pnpm add starlight-llms-txt
```
Record the installed version (`pnpm ls starlight-llms-txt`). If `pnpm add` resolves a version that errors against Starlight 0.40 in Step 3, pin a compatible older version (check the plugin's README/CHANGELOG for its Starlight peer range) and re-run.

- [ ] **Step 2: Register the plugin in astro.config.mjs**

In `docs/site/astro.config.mjs`, add the import at the top (next to the other imports):
```js
import starlightLlmsTxt from "starlight-llms-txt";
```
Then add a `plugins` array inside the `starlight({ ... })` config object (a sibling of `title`/`description`/`components`/`head`/`social`/`sidebar`):
```js
      plugins: [
        starlightLlmsTxt({
          projectName: "led-ticker",
          description:
            "An asyncio Python toolkit for displaying scrolling feeds on RGB LED matrix panels.",
        }),
      ],
```
Use the plugin's actual documented option names — open `node_modules/starlight-llms-txt/README.md` (or its types) and match the option keys exactly (e.g. `projectName`/`description` may be named differently; do NOT guess — read the installed package). Keep the config minimal (project name + description); do not exclude any pages.

- [ ] **Step 3: Build and confirm the three files generate**

Run:
```bash
cd /Users/james/projects/github/jamesawesome/led-ticker/docs/site
pnpm run build
ls -l dist/llms.txt dist/llms-full.txt dist/llms-small.txt
wc -l dist/llms.txt dist/llms-full.txt dist/llms-small.txt
```
Expected: the build succeeds and all three files exist and are non-trivial (`llms-full.txt` should be hundreds+ of lines — it's the whole docs). If `llms-small.txt` is not emitted by this plugin version, note it; the spec treats it as nice-to-have, but `llms.txt` + `llms-full.txt` are required.

- [ ] **Step 4: Lint passes**

Run: `cd docs/site && pnpm run lint`
Expected: prettier + astro check clean (the new plugin config is prettier-formatted; run `pnpm run format` if prettier flags `astro.config.mjs`).

- [ ] **Step 5: Commit**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker
git add docs/site/package.json docs/site/pnpm-lock.yaml docs/site/astro.config.mjs
git commit --no-verify -m "feat(docs): generate llms.txt via starlight-llms-txt"
```

---

### Task 2: Component-fidelity guard (the crux)

**Files:**
- Create: `docs/site/scripts/check-llms.mjs` (the build-output guard)
- Modify: `docs/site/package.json` (a `check:llms` script)
- Possibly modify: `docs/site/astro.config.mjs` (only if Step 2 finds a fidelity gap)

**Interfaces:**
- Consumes: the `dist/llms*.txt` files from Task 1.
- Produces: `pnpm run check:llms` — asserts the three files exist, are non-empty, and that `llms-full.txt` contains the OptionsTable field reference + a TOML fence. Exits non-zero on failure.

- [ ] **Step 1: Pick a fidelity sentinel from the BUILT output**

Widget pages render `<OptionsTable source="widgets/<name>" />` (fields come from `docs/content-source/widgets/<name>.md`) and `<TomlExample>` TOML blocks. A good OptionsTable sentinel is a fact-pack table description that does NOT appear in page prose. The confirmed choice: **`Rasterization threshold for hires fonts`** — the `font_threshold` row description, which lives only in the OptionsTable fact-packs (verified: it's in `docs/content-source/widgets/countdown.md`, not in `countdown.mdx` prose). Inspect the built `llms-full.txt`:
```bash
cd /Users/james/projects/github/jamesawesome/led-ticker/docs/site
# OptionsTable sentinel — a fact-pack-table-only phrase:
grep -c 'Rasterization threshold for hires fonts' dist/llms-full.txt   # >=1 means OptionsTables rendered
# TOML-fence sentinel — a fenced toml block survived from a TomlExample:
grep -c '```toml' dist/llms-full.txt
```
If `grep -c 'Rasterization threshold for hires fonts' dist/llms-full.txt` returns 0, the OptionsTable content did NOT survive → go to Step 3 (fix) before finalizing the check. (If you prefer a per-widget-specific sentinel, the `countdown_date` row text `Target date in TOML date syntax` is countdown-only and also table-sourced — either works.)

- [ ] **Step 2: Write the guard script**

Create `docs/site/scripts/check-llms.mjs`:
```js
// Guards the agent-facing Markdown export. Run AFTER `pnpm run build`.
// Fails if the llms.txt files are missing/empty or if the high-value
// OptionsTable field tables / TomlExample blocks did not survive into
// llms-full.txt (a future Astro/Starlight/plugin bump could silently gut them).
import { readFileSync, existsSync } from "node:fs";

const dist = new URL("../dist/", import.meta.url);
const required = ["llms.txt", "llms-full.txt"]; // llms-small.txt is nice-to-have
const errors = [];

for (const f of required) {
  const p = new URL(f, dist);
  if (!existsSync(p)) { errors.push(`missing dist/${f}`); continue; }
  const body = readFileSync(p, "utf8");
  if (body.trim().length < 200) errors.push(`dist/${f} is suspiciously small`);
}

const full = existsSync(new URL("llms-full.txt", dist))
  ? readFileSync(new URL("llms-full.txt", dist), "utf8")
  : "";

// Fidelity sentinels — confirmed present in the fact-pack tables, absent from prose.
const OPTIONS_TABLE_SENTINEL = "Rasterization threshold for hires fonts"; // font_threshold row, OptionsTable fact-packs
const TOML_FENCE_SENTINEL = "```toml";                                    // a TomlExample survived

if (!full.includes(OPTIONS_TABLE_SENTINEL))
  errors.push(`llms-full.txt is missing the OptionsTable field reference (sentinel: "${OPTIONS_TABLE_SENTINEL}") — widget option tables did not survive the export`);
if (!full.includes(TOML_FENCE_SENTINEL))
  errors.push(`llms-full.txt is missing a TOML code fence (sentinel: "${TOML_FENCE_SENTINEL}") — TomlExample blocks did not survive the export`);

if (errors.length) {
  console.error("check-llms FAILED:\n  - " + errors.join("\n  - "));
  process.exit(1);
}
console.log("check-llms OK: llms.txt + llms-full.txt present, OptionsTable + TOML content preserved");
```
If Step 1 led you to a different confirmed phrase, update `OPTIONS_TABLE_SENTINEL` to match. Add the script to `docs/site/package.json` `scripts`:
```json
    "check:llms": "node scripts/check-llms.mjs"
```

- [ ] **Step 3: Run the guard — fix component handling IF it fails**

Run:
```bash
cd /Users/james/projects/github/jamesawesome/led-ticker/docs/site
pnpm run build && pnpm run check:llms
```
Expected: PASS. **If it FAILS on the OptionsTable or TOML sentinel** (the plugin reads raw MDX and drops the components rather than rendered HTML), fix it before the guard can pass:
- First try the plugin's content option: many Starlight llms plugins expose a setting to base the export on the page's **rendered** content/HTML rather than raw source — set it (check the plugin README option names). Rebuild + re-run.
- If the plugin has no such option, add a per-page transform the plugin supports (a `content`/`transform` hook in its options) that, for a page containing `<OptionsTable source="X" />`, inlines `docs/content-source/X.md` (raw Markdown table), and converts `<TomlExample code={...}>` to a fenced ```toml block.
- Re-run `pnpm run build && pnpm run check:llms` until it passes. Do not weaken the sentinels to make it pass.

- [ ] **Step 4: Commit**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker
git add docs/site/scripts/check-llms.mjs docs/site/package.json docs/site/astro.config.mjs
git commit --no-verify -m "test(docs): guard llms.txt generation + OptionsTable/TomlExample fidelity"
```

---

### Task 3: Discoverability

**Files:**
- Modify: `docs/site/astro.config.mjs` (`head` array — `<link rel="alternate">`)
- Create: `docs/site/public/robots.txt`
- Modify: a docs page footer/pointer — `docs/site/src/content/docs/index.mdx` (a one-line "for agents/LLMs" pointer)

**Interfaces:**
- Consumes: the public `/llms.txt` from Tasks 1–2.

- [ ] **Step 1: Add the `<link rel="alternate">` head tag**

In `docs/site/astro.config.mjs`, add to the existing `head: [ ... ]` array (alongside the sidebar-state script) a tag pointing agents at the Markdown index:
```js
        {
          tag: "link",
          attrs: {
            rel: "alternate",
            type: "text/markdown",
            href: "/llms.txt",
            title: "led-ticker docs as Markdown (for LLMs/agents)",
          },
        },
```

- [ ] **Step 2: Add robots.txt advertising the index**

Create `docs/site/public/robots.txt`:
```
User-agent: *
Allow: /

# Agent-/LLM-friendly Markdown of these docs:
#   /llms.txt        index of all pages
#   /llms-full.txt   the entire docs as one Markdown document
Sitemap: https://docs.ledticker.dev/sitemap-index.xml
```
(Confirm Starlight emits `sitemap-index.xml`; if the sitemap path differs in `dist/`, use the real filename or drop the `Sitemap:` line.)

- [ ] **Step 3: Add a human-visible pointer on the home page**

In `docs/site/src/content/docs/index.mdx`, add a short line (in the page's existing voice, following `docs/DOCS-STYLE.md`) near the bottom — e.g. under the existing intro/links — noting the Markdown export for agents:
```mdx
Using an AI coding agent? These docs are available as plain Markdown at [`/llms.txt`](/llms.txt) (index) and [`/llms-full.txt`](/llms-full.txt) (everything in one file).
```
Place it where it reads naturally (e.g. after the "Full documentation" / getting-started links). Keep it one sentence; no padded opener.

- [ ] **Step 4: Build + lint + commit**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker/docs/site
pnpm run build && pnpm run check:llms && pnpm run lint
ls dist/robots.txt   # public/ files copy to dist root
cd /Users/james/projects/github/jamesawesome/led-ticker
git add docs/site/astro.config.mjs docs/site/public/robots.txt docs/site/src/content/docs/index.mdx
git commit --no-verify -m "feat(docs): advertise the llms.txt Markdown export (head link, robots, pointer)"
```

---

### Task 4: CI guard + contributor note

**Files:**
- Modify: `.github/workflows/ci.yml` (the `docs-lint` job — add a build + `check:llms` step)
- Modify: `Makefile` (a `docs-check-llms` target)
- Modify: `docs/DOCS-STYLE.md` or a docs README — a one-line note that the export exists + is guarded

**Interfaces:**
- Consumes: `pnpm run check:llms` from Task 2.

- [ ] **Step 1: Add a Makefile target**

In `Makefile`, add `docs-check-llms` to the `.PHONY` list and a target (near `docs-build`):
```make
docs-check-llms:  ## Build the docs + verify the llms.txt Markdown export
	cd docs/site && (corepack enable 2>/dev/null || true) && pnpm install --frozen-lockfile && pnpm run build && pnpm run check:llms
```

- [ ] **Step 2: Add the build + check step to the docs CI job**

The PR `docs-lint` job currently only runs `pnpm run lint` (no build), so a broken export wouldn't be caught in PR CI. In `.github/workflows/ci.yml`, in the `docs-lint` job, after the existing "Lint" step add:
```yaml
      - name: Build + verify llms.txt export
        working-directory: docs/site
        run: pnpm run build && pnpm run check:llms
```
(Keep it in the same job so it stays gated by the `docs` path filter and reuses the installed deps.)

- [ ] **Step 3: One-line contributor note**

In `docs/DOCS-STYLE.md` (or the docs README if one is the better home — check which exists), add a short note: the site ships an agent-facing Markdown export at `/llms.txt` + `/llms-full.txt`, generated by `starlight-llms-txt` and guarded by `make docs-check-llms` (so adding/renaming a component that breaks the OptionsTable/TomlExample export fails CI). Follow `docs/DOCS-STYLE.md` voice.

- [ ] **Step 4: Verify the full guard locally + commit**

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker
make docs-check-llms
```
Expected: build succeeds, `check-llms OK`.
```bash
git add Makefile .github/workflows/ci.yml docs/DOCS-STYLE.md
git commit --no-verify -m "ci(docs): build + guard the llms.txt export in CI"
```

---

## Final verification (before the PR)

- [ ] **Full docs build + guard + lint:**
```bash
cd /Users/james/projects/github/jamesawesome/led-ticker
make docs-build && make docs-check-llms && make docs-lint
```
Expected: all green; `dist/llms.txt`, `dist/llms-full.txt` present with OptionsTable + TOML content; site unchanged for humans.

- [ ] **Spot-check the export quality:** open `docs/site/dist/llms-full.txt` and confirm a widget section (e.g. `countdown`) reads as clean Markdown with its options table and TOML example intact — this is the deliverable an agent consumes.

- [ ] **Open the PR** (branch off main; do NOT merge without explicit user go-ahead). Summarize: `starlight-llms-txt` emits `/llms.txt` + `/llms-full.txt` (+ small), component fidelity verified + guarded, discoverability (head link / robots / pointer), CI builds + checks the export. Note per-page `.md` routes are a deferred follow-up.

## Self-Review notes (spec coverage)

- Spec §A (plugin + 3 outputs, build-time, existing deploy) → Task 1.
- Spec §B (component fidelity — OptionsTable/TomlExample survive; rendered-vs-MDX resolved by inspection; DemoGif caption-only) → Task 2 (Step 1 inspection determines the path; Step 3 fixes a gap if found; the sentinels guard it).
- Spec §C (discoverability — root /llms.txt, `<link rel>`, footer pointer, robots.txt) → Task 3.
- Spec Testing (generation guard + fidelity sentinel + no-regression) → Task 2 (`check:llms`) + Task 4 (CI wiring) + Final verification.
- Spec Risks (plugin compat → Task 1 Step 1/3 verify; content loss → Task 2 sentinels; size → `llms-small`/index covered in Task 1).
- Spec non-goals (per-page `.md` deferred; no curation) → enforced by omission + Global Constraints.
