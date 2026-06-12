# `rp1_rio` → `rp1_pio` Config Rename Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename the `rp1_rio` display-config knob to `rp1_pio` to track the upstream rgbmatrix library rename (hzeller#1892, merged into `jamesawesome/rpi-rgb-led-matrix` `main` on 2026-06-12), including the semantics flip: the library's default Pi 5 backend is now RIO, and the knob now *forces PIO* instead of *forcing RIO*.

**Architecture:** Hard rename with no translation shim, matching the precedent set by `2026-05-27-display-config-rename-rpi-alignment.md` (seven-field hard rename). Two deliberate additions beyond pure rename: (1) a load-time obsolete-key warning through the existing `CoercionWarning` channel so deployed configs that still say `rp1_rio` get told what happened instead of being silently ignored; (2) a Dockerfile cache-bust bump so the next image build compiles the renamed library. The `frame.py` `hasattr` guard is kept, so led-ticker keeps working against both pre- and post-rename library builds.

**Tech Stack:** Python/attrs + dataclasses, TOML, pytest (via `make test` / `PYTHONPATH=tests/stubs uv run pytest`), MDX (Astro Starlight).

---

## Background — why the semantics flip matters

The library change (upstream #1892, now on fork `main`, which the Dockerfile clones unpinned):

| | Old library (pre-2026-06-12) | New library |
|---|---|---|
| Option name | `RGBMatrixOptions.rp1_rio` | `RGBMatrixOptions.rp1_pio` |
| CLI flag | `--led-rp1-rio` | `--led-rp1-pio` |
| Default backend | PIO (`0`) | **RIO** (`0`) |
| Setting `1` means | force RIO | **force PIO** |

Every production/example config in this repo that sets the knob sets `rp1_rio = 1` (wants RIO). RIO is the new default, so the correct migration for **every TOML in this repo is to delete the line** — not to write `rp1_pio = 0`. A config would only ever set `rp1_pio = 1`, and only to trade refresh speed for lower CPU on a Pi 5.

`_coerce_display` ignores unknown TOML keys, so a deployed config still containing `rp1_rio = 1` keeps loading after this change and gets RIO (the new default) — behavior preserved by coincidence. The obsolete-key warning in Task 1 makes that explicit instead of silent.

## Rename map

| Location | Old | New |
|---|---|---|
| `DisplayConfig` field / TOML key | `rp1_rio: int = 0` | `rp1_pio: int = 0` |
| `_DISPLAY_INT_FIELDS` entry | `"rp1_rio"` | `"rp1_pio"` |
| `LedFrame` field | `led_rp1_rio: int = 0` | `led_rp1_pio: int = 0` |
| `__attrs_post_init__` guard | `hasattr(options, "rp1_rio")` | `hasattr(options, "rp1_pio")` |
| Test stub attribute | `self.rp1_rio = 0` | `self.rp1_pio = 0` |

## File structure

- **Modify:** `src/led_ticker/config.py` — `DisplayConfig` field, `_DISPLAY_INT_FIELDS`, obsolete-key warning in `_coerce_display`
- **Modify:** `src/led_ticker/frame.py` — `LedFrame` field + apply block
- **Modify:** `src/led_ticker/app/factories.py` — log string + `LedFrame(...)` kwarg
- **Modify:** `tests/stubs/rgbmatrix/__init__.py` — stub options attribute
- **Modify:** `tests/test_config.py` — 4 existing references + 1 new warning test
- **Modify:** `scripts/panel_color_test.py` — docstring mention
- **Modify:** 24 `config/*.toml` files + `tests/fixtures/broken-bigsign-config.toml` — delete `rp1_rio = 1` lines, rewrite adjacent comments
- **Modify:** docs site: `reference/config-options.mdx`, `hardware/bigsign.mdx`, `hardware/longboi.mdx`, `concepts/display.mdx`, `tutorial/01-setup.mdx`, `tutorial/02-first-config.mdx`, `tutorial/05-polish.mdx`, `tools/panel-test.mdx`
- **Modify:** `README.md`, `CLAUDE.md`, `.claude/skills/creating-a-config/SKILL.md`, `.claude/skills/creating-a-config/references/hardware-guide.md`
- **Modify:** `Dockerfile` — `RGBMATRIX_CACHE_BUST` 3 → 4, header comment
- **NOT modified:** `docs/superpowers/plans/` — historical artefacts

The docs-drift tripwire (`tests/test_docs_config_options_drift.py` derives expected keys from `dataclasses.fields(DisplayConfig)`) will fail until `config-options.mdx` is updated — that is expected and is fixed in Task 4.

---

### Task 1: Config-layer rename + obsolete-key warning

**Files:**
- Modify: `src/led_ticker/config.py:30` (field), `:314` (`_DISPLAY_INT_FIELDS`), `:336-359` (`_coerce_display`)
- Test: `tests/test_config.py:140,155,164,206`

**Context:** Run `git branch --show-current` first — abort if it says `main`; create branch `rp1-pio-rename` off main.

- [ ] **Step 1: Update existing test references and add the failing warning test**

In `tests/test_config.py`, change the four existing references:
- Line 140: `assert cfg.display.rp1_rio == 0` → `assert cfg.display.rp1_pio == 0`
- Line 155 (inline TOML in `test_display_config_perf_tuning_keys`): `rp1_rio = 1` → `rp1_pio = 1`
- Line 164: `assert cfg.display.rp1_rio == 1` → `assert cfg.display.rp1_pio == 1`
- Line ~206 (`test_bigsign_example_config_loads`): `assert cfg.display.rp1_rio == 1` → `assert cfg.display.rp1_pio == 0  # RIO backend is the library default; example config no longer sets the knob`

Add this new test next to `test_display_config_perf_tuning_keys`:

```python
def test_obsolete_rp1_rio_key_warns_and_is_ignored(tmp_path):
    """The library renamed rp1_rio → rp1_pio (and flipped the default
    backend to RIO) in June 2026. The old key must not crash a deployed
    config, but it must surface a warning saying what to do."""
    p = tmp_path / "config.toml"
    p.write_text("""\
[display]
rows = 32
cols = 64
rp1_rio = 1

[[playlist.section]]
mode = "swap"
""")
    cfg = load_config(p)
    assert cfg.display.rp1_pio == 0  # old key is ignored, not translated
    warns = [w for w in cfg._coerce_warnings if w.field == "display.rp1_rio"]
    assert len(warns) == 1
    assert "rp1_pio" in warns[0].message
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd /Users/james/projects/github/jamesawesome/led-ticker && PYTHONPATH=tests/stubs uv run pytest tests/test_config.py -q`
Expected: FAIL — `AttributeError: 'DisplayConfig' object has no attribute 'rp1_pio'` (and the new test fails the same way).

- [ ] **Step 3: Rename in `config.py` and add the warning**

In `DisplayConfig` (line 30):

```python
    rp1_pio: int = 0  # Pi 5 only: 0 = RIO backend (library default, fast), 1 = force PIO (low CPU)
```

In `_DISPLAY_INT_FIELDS` (line ~314): `"rp1_rio",` → `"rp1_pio",`

In `_coerce_display`, insert immediately after the `kwargs: dict[str, Any] = {}` line:

```python
    if "rp1_rio" in display_raw:
        warnings.append(
            CoercionWarning(
                field="display.rp1_rio",
                original=display_raw["rp1_rio"],
                coerced=None,
                message=(
                    "display.rp1_rio is obsolete and ignored: the rgbmatrix "
                    "library renamed the knob to rp1_pio and made RIO the "
                    "default Pi 5 backend (June 2026). rp1_rio = 1 (RIO) is "
                    "now the default — delete this line. To force the "
                    "low-CPU PIO backend instead, set rp1_pio = 1."
                ),
            )
        )
```

`CoercionWarning` is already imported at the top of `config.py` (`from led_ticker._coerce import CoercionWarning`).

- [ ] **Step 4: Run the tests to verify they pass**

Run: `PYTHONPATH=tests/stubs uv run pytest tests/test_config.py -q`
Expected: only `test_bigsign_example_config_loads` still FAILS (the example TOML still contains `rp1_rio = 1`, which no longer maps to a field — the assertion `rp1_pio == 0` passes but the file edit happens in Task 3). If it fails for that reason, that's the expected intermediate state; everything else must pass. (If you prefer a green commit, fold the one-line edit of `config/config.bigsign.example.toml` from Task 3 into this commit.)

- [ ] **Step 5: Commit**

```bash
git add tests/test_config.py src/led_ticker/config.py
git commit -m "feat(config): rename rp1_rio to rp1_pio, warn on the obsolete key"
```

---

### Task 2: Frame, factories, and test stub

**Files:**
- Modify: `src/led_ticker/frame.py:37-39` (field), `:78-81` (apply block)
- Modify: `src/led_ticker/app/factories.py:921,934,965`
- Modify: `tests/stubs/rgbmatrix/__init__.py:55-57`

- [ ] **Step 1: Rename in `frame.py`**

Replace the field declaration (currently lines 37–39):

```python
    # Pi 5 only: 0 = RP1 RIO backend (library default — fast refresh,
    # more CPU), 1 = force the RP1 PIO backend (lower CPU, slower
    # refresh). Ignored on Pi 4.
    led_rp1_pio: int = 0
```

Replace the apply block (currently lines 78–81):

```python
        # rp1_pio is exposed by rgbmatrix builds from June 2026 onward
        # (upstream renamed rp1_rio and flipped the default backend to
        # RIO); tolerate older builds where the binding doesn't have it.
        if self.led_rp1_pio and hasattr(options, "rp1_pio"):
            options.rp1_pio = self.led_rp1_pio
```

- [ ] **Step 2: Rename in `factories.py`**

In `build_frame_from_config`:
- Log format string: `rp1_rio=%d` → `rp1_pio=%d`
- Log argument: `display.rp1_rio,` → `display.rp1_pio,`
- `LedFrame(...)` kwarg: `led_rp1_rio=display.rp1_rio,` → `led_rp1_pio=display.rp1_pio,`

- [ ] **Step 3: Rename in the stub**

In `tests/stubs/rgbmatrix/__init__.py`, replace:

```python
        # Pi 5 fork (kingdo9) only — present here so tests exercise the
        # rp1_rio code path. Real Pi 4 builds don't expose this attribute.
        self.rp1_rio = 0
```

with:

```python
        # Pi 5 knob (rgbmatrix builds from June 2026 onward) — present
        # here so tests exercise the rp1_pio code path.
        self.rp1_pio = 0
```

- [ ] **Step 4: Run the full suite**

Run: `make test`
Expected: PASS except `test_docs_config_options_drift.py` (docs row still says `rp1_rio` — fixed in Task 4) and possibly `test_bigsign_example_config_loads` (fixed in Task 3). No other failures.

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/frame.py src/led_ticker/app/factories.py tests/stubs/rgbmatrix/__init__.py
git commit -m "feat(frame): pass rp1_pio through LedFrame and factories"
```

---

### Task 3: Config TOMLs, fixture, and diagnostic script

**Files:**
- Modify: 24 files in `config/` (list below), `tests/fixtures/broken-bigsign-config.toml:42`, `scripts/panel_color_test.py:6`

- [ ] **Step 1: Delete the bare `rp1_rio = 1` lines**

These files contain a standalone `rp1_rio = 1` line with no adjacent prose to rewrite — delete the line entirely (RIO is now the library default):

`config/config.bands_border_test.example.toml`, `config.bg_color_test.example.toml`, `config.bigsign.moonbunny.example.toml` (also fix its comment, step 2), `config.busy_longboi.toml`, `config.gif_test.example.toml`, `config.gif_text.example.toml`, `config.hires_emoji_test.example.toml`, `config.hires_fonts_test.example.toml`, `config.hires_transitions_test.example.toml`, `config.image_test.example.toml`, `config.lightbulb_border_test.example.toml`, `config.mlb_promotions_test.toml`, `config.mlb_scoreboard_test.toml`, `config.moonbunny.example.toml`, `config.moonbunny.production.toml`, `config.pool_bigsign.toml`, `config.presentation_test.example.toml`, `config.rainbow_border_test.example.toml`, `config.random_transitions.toml`, `config.scale_smoketest.toml`, `config.shimmer_test.bigsign.example.toml`, `tests/fixtures/broken-bigsign-config.toml`

```bash
cd /Users/james/projects/github/jamesawesome/led-ticker
grep -rl 'rp1_rio = 1' config/ tests/fixtures/ | xargs sed -i '' '/^rp1_rio = 1$/d'
```

(macOS sed. Lines with trailing comments are NOT matched by this pattern and are handled one by one in step 2.)

- [ ] **Step 2: Rewrite the commented configs**

`config/config.bigsign.example.toml` (lines 42–54): replace the comment block + line:

```
# rp1_rio = 1 selects RIO (Registered IO) mode — faster refresh, more CPU
# than PIO mode (rp1_rio = 0). The Pi 5 has cores to spare and the bigger
# panel benefits from the extra Hz.
#
# gpio_slowdown = 3 pairs with rp1_rio = 1. The Pi 4 default of 2 is too
# aggressive with RIO mode; raise to 4–5 if you still see flicker after
# switching to RIO.
```
→
```
# The library's default Pi 5 backend is RIO (Registered IO) — faster
# refresh, more CPU than PIO. The Pi 5 has cores to spare and the bigger
# panel benefits from the extra Hz. Set rp1_pio = 1 only if you need to
# trade refresh speed for lower CPU.
#
# gpio_slowdown = 3 pairs with RIO mode. The Pi 4 default of 2 is too
# aggressive with RIO; raise to 4–5 if you still see flicker.
```
and delete the `rp1_rio = 1` line after `gpio_slowdown = 3`.

`config/config.bigsign.moonbunny.example.toml:14`: `(pixel_mapper_config, gpio_slowdown, rp1_rio, pwm_bits)` → `(pixel_mapper_config, gpio_slowdown, pwm_bits)`

`config/config.longboi.toml` (lines 28–32): replace

```
# Pi 5 RP1 RIO backend (faster refresh, slightly more CPU than PIO).
# rp1_rio = 1 requires row_address_type = 0 (default) — do not set row_address_type = 1.
# Raise gpio_slowdown to 4–5 if flicker persists.
gpio_slowdown = 5
rp1_rio = 1                   # RIO mode (faster refresh, more CPU than PIO)
```
→
```
# Pi 5 RP1 RIO backend (the library default; faster refresh, slightly
# more CPU than PIO). RIO requires row_address_type = 0 (default) — do
# not set row_address_type = 1. Raise gpio_slowdown if flicker persists.
gpio_slowdown = 5
```
(Match the file's actual current text when editing — line numbers above are from the pre-edit grep.)

`config/config.pool_longboi.toml` (lines 37–39): replace

```
# Pi 5 RP1 RIO backend (matches config.longboi.toml).
gpio_slowdown = 5
rp1_rio = 1
```
→
```
# Pi 5 RP1 RIO backend — the library default (matches config.longboi.toml).
gpio_slowdown = 5
```

`config/config.mlb_two_row_test.toml` (lines 34–36): replace

```
# Pi 5 RP1 GPIO tuning: RIO mode + gpio_slowdown=3 + 8-bit PWM.
gpio_slowdown = 3
rp1_rio = 1
```
→
```
# Pi 5 RP1 GPIO tuning: RIO backend (library default) + gpio_slowdown=3 + 8-bit PWM.
gpio_slowdown = 3
```

`config/config.showroom-bigsign.example.toml` (lines 41–43): replace

```
# Performance — RP1 RIO mode with 8-bit PWM for fast refresh.
gpio_slowdown = 3
rp1_rio = 1
```
→
```
# Performance — RP1 RIO backend (library default) with 8-bit PWM for fast refresh.
gpio_slowdown = 3
```

- [ ] **Step 3: Update the diagnostic script docstring**

`scripts/panel_color_test.py:6`: `gpio_slowdown, rp1_rio, etc.` → `gpio_slowdown, rp1_pio, etc.`

- [ ] **Step 4: Verify no `rp1_rio` remains in configs and the suite is green**

Run: `grep -rn 'rp1_rio' config/ tests/fixtures/ scripts/`
Expected: no output.

Run: `make test`
Expected: PASS except `test_docs_config_options_drift.py` (fixed in Task 4).

- [ ] **Step 5: Commit**

```bash
git add config/ tests/fixtures/broken-bigsign-config.toml scripts/panel_color_test.py
git commit -m "feat(config): drop rp1_rio from TOMLs — RIO is the library default"
```

---

### Task 4: Docs site, README, CLAUDE.md, skill references

**Files:**
- Modify: `docs/site/src/content/docs/reference/config-options.mdx:27,52,59`
- Modify: `docs/site/src/content/docs/hardware/bigsign.mdx:91,96,116-131,211-225`
- Modify: `docs/site/src/content/docs/hardware/longboi.mdx:86-98`
- Modify: `docs/site/src/content/docs/concepts/display.mdx:38,67`
- Modify: `docs/site/src/content/docs/tutorial/01-setup.mdx:88`, `tutorial/02-first-config.mdx:81`, `tutorial/05-polish.mdx:310`
- Modify: `docs/site/src/content/docs/tools/panel-test.mdx:10`
- Modify: `README.md:84`, `CLAUDE.md:291-292,299`
- Modify: `.claude/skills/creating-a-config/SKILL.md:133`, `.claude/skills/creating-a-config/references/hardware-guide.md:46-49`

- [ ] **Step 1: `reference/config-options.mdx`**

Line 27 (coercion note): `pwm_dither_bits`, `rp1_rio`, → `pwm_dither_bits`, `rp1_pio`,

Line 52 (`gpio_slowdown` row): `bigsign uses `3` (paired with `rp1_rio = 1`)` → `bigsign uses `3` (paired with the default RIO backend)`

Line 59, replace the whole row:

```
| `rp1_pio`                  | int    | `0`              | Pi 5 only. `0` = RIO backend (library default — faster refresh, more CPU). `1` = force the PIO backend (lower CPU, slower refresh). Ignored on Pi 4.                                                                                  |
```

- [ ] **Step 2: `hardware/bigsign.mdx`**

Line 91: `# bumped from 2 to pair with rp1_rio=1; raise to 4-5 if flicker` → `# bumped from 2 to pair with RIO mode (default); raise to 4-5 if flicker`

Line 96: delete the line `rp1_rio = 1            # RIO mode (faster, more CPU). 0 = PIO mode (lower CPU)` from the TOML example.

Section `### \`rp1_rio = 1\`` (lines ~116–124), replace heading and body:

```mdx
### RP1 backend (RIO vs PIO)

Pi-5 only. The RP1 SoC offers two GPIO drive modes:

- **RIO mode (`rp1_pio = 0`, the library default)** — faster refresh, higher CPU.
- **PIO mode (`rp1_pio = 1`)** — lower CPU, slower refresh.

The bigsign uses RIO — the default, so nothing to set. The Pi 5 has
cores to spare and the bigger panel wants every Hz it can get. Note
that RIO mode requires bumping `gpio_slowdown` (next section). Before
June 2026 the knob was called `rp1_rio` and PIO was the default; an
old `rp1_rio = 1` line in a config is now ignored (with a startup
warning) and RIO applies anyway.
```

`### \`gpio_slowdown = 3\`` body (line ~129): `must pair with \`rp1_rio = 1\`` → `must pair with RIO mode (the default)` and `when paired with RIO mode` stays.

Annotated TOML at lines ~211–225: replace

```
# Pi 5 RP1 GPIO tuning.
#
# rp1_rio = 1 selects RIO (Registered IO) mode — faster refresh, more CPU
# than PIO mode (rp1_rio = 0). The Pi 5 has cores to spare and the bigger
# panel benefits from the extra Hz.
#
# gpio_slowdown = 3 pairs with rp1_rio = 1. The Pi 4 default of 2 is too
# aggressive with RIO mode; raise to 4–5 if you still see flicker after
# switching to RIO.
```
→
```
# Pi 5 RP1 GPIO tuning.
#
# The library's default Pi 5 backend is RIO (Registered IO) — faster
# refresh, more CPU than PIO. Set rp1_pio = 1 only to trade refresh
# speed for lower CPU.
#
# gpio_slowdown = 3 pairs with RIO mode. The Pi 4 default of 2 is too
# aggressive with RIO; raise to 4–5 if you still see flicker.
```
and delete the `rp1_rio = 1` line from the code block below it.

- [ ] **Step 3: `hardware/longboi.mdx`**

Line 86: `# Pi 5 + rp1_rio=1; raise if flicker persists` → `# Pi 5 RIO backend (default); raise if flicker persists`
Line 87: delete `rp1_rio = 1                   # RIO mode (faster refresh, more CPU than PIO)` from the TOML example.

Tuning-knobs table (lines ~96–98):
- `gpio_slowdown` row: `Pi 5 with \`rp1_rio=1\` needs higher slowdown than Pi 4.` → `Pi 5 with the default RIO backend needs higher slowdown than Pi 4.`
- Delete the `rp1_rio` row entirely.
- `row_address_type` row: `Required when \`rp1_rio = 1\`. Do not set to \`1\` — it breaks display output with RIO mode.` → `Required with the default RIO backend. Do not set to \`1\` — it breaks display output with RIO mode.`

- [ ] **Step 4: `concepts/display.mdx`, tutorials, `tools/panel-test.mdx`**

- `concepts/display.mdx:38`: delete the `rp1_rio = 1` line from the TOML example (note it ends with a template-literal backtick — keep `pwm_bits = 8\`}` as the new last line).
- `concepts/display.mdx:67`: `\`rp1_rio\`, or the other Pi-tuning options` → `\`rp1_pio\`, or the other Pi-tuning options`
- `tutorial/01-setup.mdx:88`: `(\`pixel_mapper_config\`, \`gpio_slowdown\`, \`rp1_rio\`, \`pwm_bits\`)` → `(\`pixel_mapper_config\`, \`gpio_slowdown\`, \`pwm_bits\`)`
- `tutorial/02-first-config.mdx:81`: `\`pwm_bits\`, \`rp1_rio\`. These` → `\`pwm_bits\`, \`rp1_pio\`. These`
- `tutorial/05-polish.mdx:310`: `tuning for \`gpio_slowdown\`, \`rp1_rio\`, and \`pixel_mapper_config\`` → `tuning for \`gpio_slowdown\`, \`rp1_pio\`, and \`pixel_mapper_config\``
- `tools/panel-test.mdx:10`: `chain length, \`rp1_rio\`, slowdown` → `chain length, \`rp1_pio\`, slowdown`

- [ ] **Step 5: `README.md`, `CLAUDE.md`, skill files**

- `README.md:84`: `On the Pi 5 the runtime CLI accepts \`--led-rp1-rio=0|1\` for the RP1 backend mode;` → `On the Pi 5 the RP1 RIO backend is the default; the runtime CLI accepts \`--led-rp1-pio=1\` to force the low-CPU PIO backend.`
- `CLAUDE.md:292`: `the runtime CLI also accepts \`--led-rp1-rio=0|1\` (PIO vs Registered IO mode)` → `the RP1 RIO backend is the default; \`--led-rp1-pio=1\` forces the low-CPU PIO backend (renamed from \`--led-rp1-rio\`, June 2026)`
- `CLAUDE.md:299`: `\`gpio_slowdown = 3\` paired with \`rp1_rio = 1\`` → `\`gpio_slowdown = 3\` paired with the default RIO backend`
- `.claude/skills/creating-a-config/SKILL.md:133`: `Suggest \`pwm_bits = 8\`, \`rp1_rio = 1\`` → `Suggest \`pwm_bits = 8\` (RIO backend is the library default)`
- `.claude/skills/creating-a-config/references/hardware-guide.md:46-49`: replace the `rp1_rio` bullet with `- **RIO backend** — the library default on Pi 5: faster refresh, higher CPU. Set \`rp1_pio = 1\` to force the lower-CPU PIO backend.`; in the `gpio_slowdown` bullet `paired with \`rp1_rio=1\`` → `paired with the default RIO backend`; in the summary line drop `+ \`rp1_rio = 1\``.

- [ ] **Step 6: Verify the drift test passes and nothing is left**

Run: `make test`
Expected: full PASS, including `tests/test_docs_config_options_drift.py`.

Run: `grep -rn 'rp1_rio\|rp1-rio' --exclude-dir=node_modules --exclude-dir=.git --exclude-dir='docs/superpowers' . | grep -v 'docs/superpowers'`
Expected: hits only in `src/led_ticker/config.py` (the obsolete-key warning) and `tests/test_config.py` (the warning test).

- [ ] **Step 7: Commit**

```bash
git add docs/site README.md CLAUDE.md .claude/skills/creating-a-config
git commit -m "docs: rp1_pio rename — RIO is the default Pi 5 backend"
```

---

### Task 5: Dockerfile cache bust

**Files:**
- Modify: `Dockerfile:10,27`

- [ ] **Step 1: Bump the cache bust and update the header comment**

Line 27: `ARG RGBMATRIX_CACHE_BUST=3` → `ARG RGBMATRIX_CACHE_BUST=4`

Line 10 comment block: append to the fork description: `Library as of June 2026 defaults the Pi 5 backend to RP1 RIO and exposes rp1_pio (renamed from rp1_rio).`

The Dockerfile clones `--depth=1 --branch main` (unpinned), so the bump forces the next image build to compile the renamed library. The `hasattr` guard in `frame.py` means led-ticker code works against both library generations, so devices that rebuild before/after this PR in either order stay functional.

- [ ] **Step 2: Commit**

```bash
git add Dockerfile
git commit -m "build: bump RGBMATRIX_CACHE_BUST for the rp1_pio library rename"
```

---

### Task 6: Final verification and PR

- [ ] **Step 1: Full suite + lint**

Run: `make test && make lint`
Expected: PASS, no lint errors.

- [ ] **Step 2: Push and open the PR**

```bash
git push -u origin rp1-pio-rename
gh pr create --title "Rename rp1_rio config knob to rp1_pio (library backend default flip)" --body "$(cat <<'EOF'
The rgbmatrix library (jamesawesome/rpi-rgb-led-matrix, upstream hzeller#1892, merged 2026-06-12) renamed `RGBMatrixOptions.rp1_rio` to `rp1_pio` and flipped the default Pi 5 backend from PIO to RIO. This PR tracks that rename in led-ticker.

- `DisplayConfig.rp1_rio` → `rp1_pio` (hard rename, matching the 2026-05-27 seven-field rename precedent). New semantics: `0` = RIO (library default), `1` = force low-CPU PIO.
- All repo TOMLs that set `rp1_rio = 1` (wanting RIO) drop the line — RIO is now the default.
- Deployed configs still containing `rp1_rio` keep loading: the key is ignored (behavior unchanged, they get RIO) and a startup/validate warning explains the rename.
- `LedFrame` keeps the `hasattr` guard, so the code runs against both pre- and post-rename library builds.
- `RGBMATRIX_CACHE_BUST` bumped so the next image build compiles the renamed library.
- Docs site, README, CLAUDE.md, and the creating-a-config skill updated; the config-options drift test enforces the docs table.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Self-review notes

- **Spec coverage:** library rename tracked (Tasks 1–2), configs migrated (Task 3), docs/skills (Task 4), deployment path (Task 5), fleet-safety via obsolete-key warning (Task 1) — covers all risks identified in the 2026-06-12 upstream-sync analysis.
- **Deliberate non-goals:** no `rp1_rio` → `rp1_pio` translation shim (project precedent is hard rename; all known configs want RIO, which is now the default, so translation would only matter for a hypothetical explicit `rp1_rio = 0`, which no config has ever set); no library pinning change in the Dockerfile (out of scope).
- **Type consistency:** `rp1_pio: int = 0` in `DisplayConfig`, `led_rp1_pio: int = 0` in `LedFrame`, `led_rp1_pio=display.rp1_pio` in factories, stub exposes `rp1_pio` — all consistent.
- Line numbers are from 2026-06-12 HEAD of led-ticker `main`; re-grep before editing if the tree has moved.
