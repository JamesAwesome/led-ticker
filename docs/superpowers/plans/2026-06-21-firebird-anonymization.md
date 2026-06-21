# Moon Bunny → Firebird Anonymization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the real "Moon Bunny Aerial" studio identity from the repo (leaked production configs + every reference in shipped/example/docs surface) and replace it with the fictional Firebird Yoga brand (DOCS-STYLE.md §6).

**Architecture:** Mechanical-but-careful rename across ~55 files, driven by §6 as the single source of truth. Aerial-arts disciplines are re-authored to yoga (not find-replaced). Ends with a completeness-guard test proving zero real-brand strings remain outside the archival `docs/superpowers/`.

**Tech Stack:** TOML configs, Astro/Starlight docs, pytest, the `render-demo` GIF toolchain.

## Global Constraints

- Worktree `/Users/james/projects/github/jamesawesome/led-ticker-worktrees/firebird-brand`, branch `feat/firebird-anonymization` (carries the approved §6 brand commit `8ce18f4`; base `origin/main` @ b839616). **Run `git branch --show-current` first; abort if it prints `main`.**
- Run `make dev` once before the first commit. Tests: `PYTHONPATH=tests/stubs uv run pytest`.
- Lint/format (test/py files): `uv run --extra dev ruff check src/ tests/` + `ruff format`.
- Docs: `make docs-build` + `make docs-lint` clean. **Never pipe `docs-lint` to `tail`** (masks the exit code, DOCS-STYLE §4) — run `make docs-format`, then `make docs-lint`.
- **§6 of `docs/DOCS-STYLE.md` is the source of truth** for all new copy/handles/colors. Re-author aerial disciplines to yoga; never find-replace them.
- **Group C is OFF-LIMITS:** do NOT edit anything under `docs/superpowers/` (plans/specs/walkthroughs — historical record).
- **The "pole" trap:** `barber-pole`/`candy-cane` are BORDER styles. Never replace `"pole"`. Some demo files carry BOTH brand copy AND a barber-pole border — rewrite the copy, leave the border config.
- No release-history framing in rewritten copy (DOCS-STYLE principle 17 — no "legacy/deprecated/backward-compatible").
- Commit trailer on every commit:
  `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`
  `Claude-Session: https://claude.ai/code/session_01P7r9q2YjKvWBsTSfdPotAh`
- **Asset binaries + asset paths are OUT OF SCOPE for this PR.** The non-shippable sample
  assets (`pika_wave*.gif`, `moon_bunny_transparent.gif`, `moon-transparent.png`, `bunny-*.png`,
  `kpop-dance.webp`) are replaced by a SEPARATE shippable-asset-sweep PR. In this PR, **leave
  every asset `path = "assets/…"` line unchanged** even when the brand COPY around it changes —
  do not repoint, rename, or remove asset files, and do not rewrite "Pikachu"/asset prose. A
  config can legitimately end this PR with Firebird copy + a still-old logo asset; that's
  expected and the asset sweep fixes it. (This is why the completeness guard's needles are
  `moonbunny`/`moon bunny`/`moonbunnyaerial`/`aerial` only — NOT the asset names.)

### Canonical substitution map (apply everywhere; §6 is the authority)

Identity / handles / contact — straight substitutions:

| Moon Bunny (old) | Firebird (new) |
|------------------|----------------|
| `Moon Bunny Aerial` / `MOON BUNNY AERIAL` | `Firebird Yoga` / `FIREBIRD YOGA` |
| `Moon Bunny` / `MOON BUNNY` | `Firebird Yoga` (or split lockup `Fire`/`Bird` where the layout splits two words) |
| `moonbunny` (codename/slug/filename) | `firebird` |
| `@moonbunnyaerial` | `@firebirdyoga.demo` |
| `@MoonBunny` (short) | `@firebird` |
| `moonbunnyaerial.com` / `www.moonbunnyaerial.com` | `firebirdyoga.demo` |
| `info@moonbunnyaerial.com` | `hello@firebirdyoga.demo` |
| `@MoonBunnyBakery` (stray variant in hardware-guide) | `@firebird` |

Slogans / disciplines — **re-authored** (do NOT keep the Moon Bunny phrasing):

| Old (aerial) | New (yoga, §6) |
|--------------|----------------|
| `Aerial for Everybody` / `Aerial For Everybody` | tagline `Breathe. Move. Rise.` |
| `Find Your Strength … Find Your Community … Aerial for Everybody` | storefront scroll `Breathe Deep :heart: Flow Strong :heart_green: Rise Together` |
| `Aerial Circus` (the split-lockup 2nd line) | `Yoga Studio` |
| `Beginner Friendly - Kid Friendly - Everybody Friendly` | `Beginner Friendly - Drop-Ins Welcome - Every Body Welcome` |
| `Now booking spring classes — all levels welcome!` | `Now booking spring sessions — your first class is free.` |
| disciplines `Aerial Silks, Lyra, Flow Props, Ballet, Dance, All Levels` | classes `Vinyasa Flow, Yin, Hot Power, Restorative, Slow Flow, All Levels` |
| `Aerial Silks · lyra · flow props · ballet · dance` (ribbon) | `Vinyasa · yin · hot power · restorative · slow flow · all levels` |
| `KIDS SUMMER CAMPS … NOW ENROLLING … ALL AGES WELCOME` | `BEGINNER SERIES :star: NOW ENROLLING :star: ALL LEVELS WELCOME` |
| `K-POP DANCE CLASS … NOW OPEN … ALL LEVELS` | `CANDLELIGHT FLOW :star: NOW OPEN :star: ALL LEVELS` |

Never introduce the term **"bikram"** (use "Hot Power" / "heated flow"). Keep emoji slugs as-is (`:heart:`, `:heart_green:`, `:star:`, `:instagram:`, `:email:`). When a string's exact yoga wording isn't in this table, follow §6's voice (warm, two-beat imperative; no "Find Your ___" / "___ for Everybody" shape).

---

### Task 1: Leak cleanup

**Files:**
- Delete (tracked): `config/config.moonbunny.production.toml`, `config/config.pool_bigsign.toml`
- Modify: `.gitignore`

- [ ] **Step 1: Confirm both are tracked**

Run: `git ls-files config/config.moonbunny.production.toml config/config.pool_bigsign.toml`
Expected: both paths printed.

- [ ] **Step 2: Remove them from the tree**

```bash
git rm config/config.moonbunny.production.toml config/config.pool_bigsign.toml
```

- [ ] **Step 3: Add ignore rules**

In `.gitignore`, next to the existing `config/config.toml` block (~line 148), add:

```
config/config.*.production.toml
config/config.pool_bigsign.toml
```

- [ ] **Step 4: Verify the ignore actually blocks re-add**

```bash
printf '# x\n' > config/config.moonbunny.production.toml
git check-ignore config/config.moonbunny.production.toml   # expect: prints the path (ignored)
rm config/config.moonbunny.production.toml
git status --porcelain config/   # expect: no untracked production toml
```

- [ ] **Step 5: Commit**

```bash
git add .gitignore && git commit -m "chore(config): remove leaked production configs + gitignore them

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01P7r9q2YjKvWBsTSfdPotAh"
```

---

### Task 2: Group B — filename/asset renames + referrers

**Files:**
- Rename: `config/config.moonbunny.example.toml` → `config/config.firebird.example.toml`
- Rename: `config/config.bigsign.moonbunny.example.toml` → `config/config.bigsign.firebird.example.toml`
- Rename: `docs/site/public/showcase/moonbunny/` → `docs/site/public/showcase/firebird/`
- Modify: `.dockerignore`, `docs/site/src/content/docs/showcase.mdx`, `tests/test_app.py`

> This task only RENAMES files + updates references to the names. Content rewrites of the config bodies happen in Task 3; the showcase prose rewrite happens in Task 6. Keep this task to renames + path/name updates so the suite stays green.

- [ ] **Step 1: git mv the configs + asset dir**

```bash
git mv config/config.moonbunny.example.toml config/config.firebird.example.toml
git mv config/config.bigsign.moonbunny.example.toml config/config.bigsign.firebird.example.toml
git mv docs/site/public/showcase/moonbunny docs/site/public/showcase/firebird
```

- [ ] **Step 2: Update `.dockerignore`**

`.dockerignore:12` reads `config/config.moonbunny.example.toml` → change to `config/config.firebird.example.toml`.

- [ ] **Step 3: Update the showcase image src (prose rewrite is Task 6)**

In `docs/site/src/content/docs/showcase.mdx`, update only the asset path now: `src="/showcase/moonbunny/placeholder.svg"` → `src="/showcase/firebird/placeholder.svg"` (the `## moonbunny` heading, alt text, and body prose are rewritten in Task 6).

- [ ] **Step 4: Rename the config-loader test**

In `tests/test_app.py` (~line 344): rename the method `test_moonbunny_bigsign_config_widgets_build` → `test_firebird_bigsign_config_widgets_build`; update the loaded path `config/config.moonbunny.example.toml` → `config/config.firebird.example.toml`; update the docstring's "config.moonbunny.example.toml" mention and the "The moonbunny config references…" comment to "The Firebird config…". Keep the licensed-font skip behavior (the `beloved-sans-bold.otf` check) exactly as-is.

- [ ] **Step 5: Run the renamed test + suite**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_app.py -q`
Expected: PASS (the test loads the renamed config + builds widgets, or skips if the licensed font is absent).

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "refactor(config): rename moonbunny example configs + showcase asset dir to firebird

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01P7r9q2YjKvWBsTSfdPotAh"
```

---

### Task 3: Group A — example config bodies → Firebird

**Files:**
- Modify: `config/config.firebird.example.toml`, `config/config.bigsign.firebird.example.toml`, `config/config.gif_test.example.toml`, `config/config.hires_fonts_test.example.toml`

- [ ] **Step 1: Read §6 + the substitution map, then rewrite each config's brand copy**

For each of the four configs, apply the canonical substitution map (Global Constraints) to every Moon Bunny string: studio name/headline, handles (`@moonbunnyaerial`→`@firebirdyoga.demo`, `@MoonBunny`→`@firebird`), URL/email, taglines/slogans (re-authored), disciplines→yoga classes, the comment headers (e.g. `# Moon Bunny Aerial — store-window display config` → `# Firebird Yoga — store-window display config`). Keep all non-brand config (widget types, layout, colors that aren't brand-specific, emoji slugs, the `pixel_mapper_config`) unchanged. Where a config sets a brand color, you MAY map to the §6 palette, but do not over-polish `config.firebird.example.toml` (step 3 of the project supersedes it) — just make it correct + Moon-Bunny-free.

- [ ] **Step 2: Verify the configs still load + validate**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_app.py::TestConfigWidgetBuild -q` (or the class containing `test_firebird_bigsign_config_widgets_build`).
Expected: PASS / skip (font). Also smoke-load each:
```bash
PYTHONPATH=tests/stubs uv run python -c "import tomllib; [tomllib.load(open(f,'rb')) for f in ['config/config.firebird.example.toml','config/config.bigsign.firebird.example.toml','config/config.gif_test.example.toml','config/config.hires_fonts_test.example.toml']]; print('parse ok')"
```

- [ ] **Step 3: Grep these four files for residue**

Run: `git grep -in "moonbunny\|moon bunny\|aerial" -- config/` → expect NO matches.

- [ ] **Step 4: Commit**

```bash
git add config/ && git commit -m "docs(config): rewrite example-config brand copy to Firebird Yoga

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01P7r9q2YjKvWBsTSfdPotAh"
```

---

### Task 4: Group A — repo surface (skill, README, issue template, CLAUDE.md)

**Files:**
- Modify: `.claude/skills/creating-a-config/SKILL.md` + `.claude/skills/creating-a-config/references/{snippets,decision-rules,hardware-guide,asset-handling}.md`
- Modify: `README.md`, `.github/ISSUE_TEMPLATE/submit-sign.yml`, `CLAUDE.md`

- [ ] **Step 1: Apply the substitution map to each file**

Rewrite all Moon Bunny copy → Firebird per the map. Specifics:
- `references/hardware-guide.md` has a stray `@MoonBunnyBakery` → `@firebird`.
- `README.md` references the example config name (now `config.firebird.example.toml`) and may carry `@moonbunnyaerial` / a tagline — update name + copy.
- `.github/ISSUE_TEMPLATE/submit-sign.yml` placeholder `e.g. "moonbunny aerial storefront, NYC"` → `e.g. "firebird yoga storefront, NYC"`.
- `CLAUDE.md`'s moonbunny mention (the config-name reference) → `config.firebird.example.toml` / Firebird.

- [ ] **Step 2: Grep these files for residue**

Run: `git grep -in "moonbunny\|moon bunny\|aerial" -- .claude/skills/creating-a-config README.md .github CLAUDE.md` → NO matches.

- [ ] **Step 3: Commit**

```bash
git add -A && git commit -m "docs: rewrite config-skill + README + issue-template + CLAUDE.md to Firebird

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01P7r9q2YjKvWBsTSfdPotAh"
```

---

### Task 5: Group A — docs-site demo TOMLs → Firebird

**Files:**
- Modify the ~22 demo TOMLs that contain Moon Bunny copy:
  - `docs/site/demos-pinned/{border-color_cycle-range, gif-two_row, image-two_row-scroll_through, image-two_row, image-typewriter-border, image-typewriter, message-brand-color, message-gradient, two_row-asymmetric, two_row-brand-handle, two_row-font-hierarchy, two_row-hires-emoji}.toml`
  - `docs/site/demos-long/{tutorial-01-setup, tutorial-02-first-config, tutorial-03a-sections, tutorial-03b-multi-widget, tutorial-03c-two_row-basic, tutorial-03d-two_row-hires, tutorial-04a-font, tutorial-04c-image-with-text, tutorial-05a-transitions, tutorial-05b-final, widget-pool-two-row}.toml`
  - (Re-confirm the exact set: `git grep -il "moonbunny\|aerial\|moon bunny" -- docs/site/demos-pinned docs/site/demos-long`.)

- [ ] **Step 1: Rewrite the brand copy in each demo TOML**

Apply the substitution map to the `text`/`top_text`/`bottom_text`/`text_separator` brand strings. **Do NOT touch `"pole"` in any border config** (`{style = "bands", … "barber-pole"/"candy-cane" …}`) — these demos pair brand copy with a barber-pole border; only the brand text changes. Keep font sizes, colors, layout, transitions unchanged unless the color is a brand color you're mapping to §6 (keep visual parity — same palette intent).

- [ ] **Step 2: Grep the demo TOMLs for residue + confirm "pole" untouched**

Run: `git grep -in "moonbunny\|moon bunny\|aerial" -- docs/site/demos-pinned docs/site/demos-long` → NO matches.
Run: `git diff -- docs/site/demos-pinned docs/site/demos-long | grep -i "pole"` → expect NO changes to `pole` lines (only brand-copy lines changed).

- [ ] **Step 3: Note which demos need a GIF re-render (handed to Task 6)**

List every modified demo whose CHANGED text is VISIBLE in its rendered output (e.g. `two_row-brand-handle`, `message-brand-color`, `message-gradient`, `two_row-hires-emoji`, `two_row-asymmetric`, the tutorial demos that show the handle/tagline). Record this list in the task report — Task 6 re-renders their paired GIFs.

- [ ] **Step 4: Commit**

```bash
git add docs/site/demos-pinned docs/site/demos-long && git commit -m "docs(demos): rewrite demo-config brand copy to Firebird (pole/borders untouched)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01P7r9q2YjKvWBsTSfdPotAh"
```

---

### Task 6: Group A — docs-site .mdx pages + snippet/GIF parity

**Files:**
- Modify the ~13 .mdx with Moon Bunny copy: `docs/site/src/content/docs/{concepts/display.mdx, concepts/fonts.mdx, widgets/gif.mdx, widgets/image.mdx, widgets/message.mdx, widgets/two_row.mdx, tutorial/01-setup.mdx, tutorial/02-first-config.mdx, tutorial/03-multi-widget.mdx, tutorial/04-custom-branding.mdx, tutorial/05-polish.mdx, showcase.mdx}` (re-confirm with `git grep -il`).
- Re-render any GIF whose visible copy changed (Task 5's list).

- [ ] **Step 1: Rewrite the prose + inline snippets to Firebird**

Apply the substitution map to prose AND to any `TomlExample`/code snippet. **Snippet/GIF parity (DOCS-STYLE §4, hard rule):** where a snippet quotes a demo TOML from Task 5, the snippet must match that TOML **character-for-character** on the lines it shows — copy the lines out of the (now-rewritten) demo TOML, don't retype. `showcase.mdx`: rewrite the `## moonbunny` heading → `## Firebird Yoga`, the alt text, and the "moonbunny is an aerial-arts studio…" body into a Firebird yoga-studio description (per §6 voice; the storefront leverages two_row/gif/hires-emoji/transitions).

- [ ] **Step 2: Re-render the GIFs whose visible copy changed**

For each demo on Task 5's list, find its embedded `.gif` (`grep -rn "<demo-name>.gif" docs/site/src/content/docs/`), then re-render:
```bash
make render-demo CONFIG=docs/site/demos-pinned/<name>.toml OUT=docs/site/public/demos-pinned/<name>.gif
```
**If a re-render is blocked** (missing licensed font / asset — e.g. the Beloved Sans the test_app skip references), do NOT let snippet and GIF silently diverge: FLAG it in the task report (which GIFs are now stale-vs-snippet) and add a one-line note so a maintainer re-renders at deploy. The snippet must still match the new TOML (the GIF is the stale artifact, surfaced honestly per DOCS-STYLE principle 9). Record exactly which GIFs were re-rendered vs flagged.

- [ ] **Step 3: Docs build + lint + technical-writer review**

```bash
make docs-format && make docs-build && make docs-lint
```
Expected: clean. Each touched page is reviewed against the DOCS-STYLE §3 rubric (the technical-writer review loop, §5) during the task review.

- [ ] **Step 4: Grep the .mdx for residue**

Run: `git grep -in "moonbunny\|moon bunny\|aerial" -- docs/site/src/content/docs` → NO matches.

- [ ] **Step 5: Commit**

```bash
git add docs/site && git commit -m "docs: rewrite docs-site pages + showcase to Firebird; re-render affected GIFs

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01P7r9q2YjKvWBsTSfdPotAh"
```

---

### Task 7: Group A — test fixtures

**Files:**
- Modify: `tests/test_app.py`, `tests/test_gif_path_resolution.py`, `tests/test_pixel_emoji.py`, `tests/test_widgets/test_gif.py`, `tests/test_widgets/test_two_row.py`

- [ ] **Step 1: Rewrite the brand fixture strings**

Apply the map: `@MoonBunny` → `@firebird`; `:instagram: @moonbunnyaerial` → `:instagram: @firebirdyoga.demo`; `:email: info@moonbunnyaerial.com` → `:email: hello@firebirdyoga.demo`. These are arbitrary fixture strings (the tests assert layout/measurement behavior, not the literal brand) — update the literal AND any assertion that compares against it (e.g. `assert widget.top_text == "@MoonBunny"` → `"@firebird"`).

- [ ] **Step 2: Run the affected tests**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_gif_path_resolution.py tests/test_pixel_emoji.py tests/test_widgets/test_gif.py tests/test_widgets/test_two_row.py tests/test_app.py -q`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/ && git commit -m "test: rewrite brand fixtures to Firebird handles

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01P7r9q2YjKvWBsTSfdPotAh"
```

---

### Task 8: Completeness guard + final verification

**Files:**
- Create: `tests/test_no_real_brand.py`

- [ ] **Step 1: Write the guard**

```python
"""Completeness guard for the Moon Bunny -> Firebird anonymization.

Asserts the real studio identity appears NOWHERE in the tracked tree except the
archival design docs under docs/superpowers/ (which record history as written).
Prevents both an incomplete rename and a future reintroduction."""

import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
# Real-brand needles (case-insensitive). "aerial" is included because the real
# studio is an aerial-arts studio; it must not survive in shipped/docs copy.
NEEDLES = ["moonbunny", "moon bunny", "moonbunnyaerial", "aerial"]
# Archival design docs record the old brand as written at the time — allowed.
ALLOW_PREFIXES = ("docs/superpowers/",)


def _tracked_files():
    out = subprocess.run(
        ["git", "ls-files"], cwd=REPO, capture_output=True, text=True, check=True
    )
    return [p for p in out.stdout.splitlines() if p]


def test_no_real_brand_strings_outside_archival():
    offenders = []
    for needle in NEEDLES:
        res = subprocess.run(
            ["git", "grep", "-il", needle, "--"] + [":!docs/superpowers"],
            cwd=REPO, capture_output=True, text=True,
        )
        for path in res.stdout.splitlines():
            if path and not path.startswith(ALLOW_PREFIXES):
                offenders.append(f"{needle}: {path}")
    assert not offenders, (
        "real-brand strings still present (anonymization incomplete):\n"
        + "\n".join(sorted(set(offenders)))
    )
```

> Note: this guard test file itself must not contain a bare real-brand string that
> `git grep` would flag — the needles above are fine (they're the search terms, and
> `git grep -il moonbunny` would match THIS file). To avoid self-matching, the test
> file lives at `tests/test_no_real_brand.py`; add `tests/test_no_real_brand.py` to the
> grep exclusion (`:!docs/superpowers` AND `:!tests/test_no_real_brand.py`) so the
> guard doesn't flag its own needles. Update the `git grep` exclusions accordingly:
> `["git", "grep", "-il", needle, "--", ":!docs/superpowers", ":!tests/test_no_real_brand.py"]`.

- [ ] **Step 2: Run the guard — expect GREEN (tasks 1-7 did the renames)**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_no_real_brand.py -q`
Expected: PASS. **If it FAILS**, it prints the files still containing the brand — go back and fix those (a missed Group A/B file), then re-run.

- [ ] **Step 3: Manual final grep (belt + suspenders)**

Run: `git grep -in "moonbunny\|moon bunny\|aerial" -- . ':!docs/superpowers' ':!tests/test_no_real_brand.py'`
Expected: NO output.

- [ ] **Step 4: Full suite + docs + lint**

```bash
PYTHONPATH=tests/stubs uv run pytest -q
uv run --extra dev ruff check src/ tests/ && uv run --extra dev ruff format --check src/ tests/
make docs-format && make docs-build && make docs-lint
```
Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add tests/test_no_real_brand.py && git commit -m "test: completeness guard — no real-brand strings outside archival

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01P7r9q2YjKvWBsTSfdPotAh"
```

---

## Final verification (after all tasks)

- [ ] `tests/test_no_real_brand.py` passes (the completeness anchor).
- [ ] `PYTHONPATH=tests/stubs uv run pytest -q` — full suite green (esp. the renamed `test_firebird_bigsign_config_widgets_build` + the rewritten fixtures).
- [ ] `make docs-build` + `make docs-lint` clean; touched pages pass the DOCS-STYLE §3 rubric.
- [ ] `git grep -in "moonbunny\|aerial" -- . ':!docs/superpowers' ':!tests/test_no_real_brand.py'` → empty.
- [ ] Any re-rendered GIF committed; any blocked re-render explicitly flagged (snippet still matches the TOML).
- [ ] `git status` — no untracked (`??`) files; the two production configs are gone + gitignored.
- [ ] Push, open a PR against `main`, wait for CI green before requesting merge.

## Notes / gotchas

- **The "pole" trap is the #1 risk** — `barber-pole`/`candy-cane` borders share files with brand copy. Diff every demo/border edit for accidental `pole` changes.
- **GIF re-render may be blocked** by the gitignored licensed Beloved Sans font (the `test_app` skip references it). When blocked, flag the stale GIF honestly rather than committing a snippet/GIF mismatch.
- **Group C (`docs/superpowers/`) stays untouched** — the completeness guard excludes it by design.
- **History scrub is NOT in this PR** (deferred to open-source prep) — only HEAD is cleaned.
- After merge (controller action): track the deferred git-history scrub as a gate-1 open-source-prep follow-up; step 3 = the richer Firebird showcase example (built from the captured production-config content).
