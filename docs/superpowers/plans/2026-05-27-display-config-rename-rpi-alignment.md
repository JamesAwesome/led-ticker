# DisplayConfig → RGBMatrixOptions Name Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename seven `DisplayConfig` (and matching `LedFrame`) fields to exactly match the corresponding `RGBMatrixOptions` attribute names from the rpi-rgb-led-matrix library. Hard rename — no backwards-compat shims.

**Architecture:** Seven field renames propagated through Python source → test files → TOML configs → live docs. All changes are mechanical search-and-replace with no logic changes. The docs-drift test auto-derives expected keys from `DisplayConfig`, so it will catch any missed docs update. `validate.py` has two `display.pixel_mapper` references that also need updating.

**Tech Stack:** Python/attrs, TOML, MDX (Astro Starlight).

---

## Rename map

| Old name (TOML / `DisplayConfig`) | New name | `LedFrame` old → new |
|---|---|---|
| `gpio_mapping` | `hardware_mapping` | `led_gpio_mapping` → `led_hardware_mapping` |
| `slowdown_gpio` | `gpio_slowdown` | `led_slowdown_gpio` → `led_gpio_slowdown` |
| `show_refresh` | `show_refresh_rate` | `led_show_refresh` → `led_show_refresh_rate` |
| `no_hardware_pulse` | `disable_hardware_pulsing` | `led_no_hardware_pulse` → `led_disable_hardware_pulsing` |
| `pixel_mapper` | `pixel_mapper_config` | `led_pixel_mapper` → `led_pixel_mapper_config` |
| `row_addr_type` | `row_address_type` | `led_row_addr_type` → `led_row_address_type` |
| `chain` | `chain_length` | `led_chain` → `led_chain_length` |

**Fields that already match the library and are NOT renamed:** `rows`, `cols`, `parallel`, `brightness`, `pwm_bits`, `pwm_lsb_nanoseconds`, `led_rgb_sequence`, `panel_type`, `multiplexing`, `scan_mode`, `pwm_dither_bits`, `rp1_rio`, `limit_refresh_rate_hz`, `default_scale`.

---

## File structure

- **Modify:** `src/led_ticker/config.py` — `DisplayConfig` field declarations, `_DISPLAY_INT_FIELDS`
- **Modify:** `src/led_ticker/frame.py` — `LedFrame` field declarations, `__attrs_post_init__`
- **Modify:** `src/led_ticker/app/factories.py` — `LedFrame(...)` kwargs, log string
- **Modify:** `src/led_ticker/validate.py` — two `display.pixel_mapper` references
- **Modify:** `tests/test_config.py` — inline TOML strings + assertions on `display.*`
- **Modify:** `tests/test_frame.py` — `frame.led_*` attribute assertions
- **Modify:** `tests/test_app.py` — `DisplayConfig(...)` kwargs + assertions
- **Modify:** `tests/test_validate.py` — inline TOML strings (90+ `chain =` instances; all 7 fields)
- **Modify:** `tests/conftest.py` — any `pixel_mapper=` in stub setup
- **Modify:** all 34 `config/*.toml` files + `tests/fixtures/broken-bigsign-config.toml`
- **Modify:** `docs/site/src/content/docs/reference/config-options.mdx`
- **Modify:** `docs/site/src/content/docs/hardware/panel-tuning.mdx`
- **Modify:** `docs/site/src/content/docs/concepts/display.mdx`
- **Modify:** `docs/site/src/content/docs/hardware/bigsign.mdx`
- **Modify:** `docs/site/src/content/docs/hardware/smallsign.mdx`
- **Modify:** `docs/site/src/content/docs/hardware/building-your-own.mdx`
- **Modify:** `docs/site/src/content/docs/showcase.mdx`
- **Modify:** `docs/site/src/content/docs/tutorial/01-setup.mdx`
- **Modify:** `docs/site/src/content/docs/tutorial/02-first-config.mdx`
- **Modify:** `docs/site/src/content/docs/tutorial/05-polish.mdx`
- **Modify:** `docs/site/src/content/docs/tools/gif-plan.mdx`
- **Modify:** `CLAUDE.md`
- **NOT modified:** `tests/stubs/rgbmatrix/__init__.py` — already uses library-side names (`chain_length`, `show_refresh_rate`, etc.)
- **NOT modified:** `docs/superpowers/plans/` or `docs/superpowers/specs/` — historical artefacts

---

### Task 1: Rename in Python source

**Files:**
- Modify: `src/led_ticker/config.py`
- Modify: `src/led_ticker/frame.py`
- Modify: `src/led_ticker/app/factories.py`
- Modify: `src/led_ticker/validate.py`

**Context:** The worktree for this plan is on a fresh branch off main. Run `git branch --show-current` before starting — abort if it says `main`.

- [ ] **Step 1: Rename in `config.py`**

Apply these exact renames (use replace_all where the old string only appears as this field name):

In `DisplayConfig`:
- `gpio_mapping: str = "adafruit-hat"` → `hardware_mapping: str = "adafruit-hat"`
- `chain: int = 1` → `chain_length: int = 1`
- `slowdown_gpio: int = 1` → `gpio_slowdown: int = 1`
- `pixel_mapper: str = ""` → `pixel_mapper_config: str = ""`
- `show_refresh: bool = False` → `show_refresh_rate: bool = False`
- `no_hardware_pulse: bool = False` → `disable_hardware_pulsing: bool = False`
- `row_addr_type: int = 0` → `row_address_type: int = 0`

In `_DISPLAY_INT_FIELDS` frozenset:
- `"chain",` → `"chain_length",`
- `"slowdown_gpio",` → `"gpio_slowdown",`
- `"row_addr_type",` → `"row_address_type",` (if present; add if missing)

In `_coerce_display`, the loop iterates `_DISPLAY_INT_FIELDS` by name and looks them up in `display_raw` — no other changes needed there since it uses the frozenset keys directly.

In `_coerce_section`, check for any reference to `display.chain` (now `display.chain_length`) or `display.pixel_mapper` (now `display.pixel_mapper_config`) — update if found.

- [ ] **Step 2: Rename in `frame.py`**

In `LedFrame` attrs class:
- `led_gpio_mapping: str = "adafruit-hat"` → `led_hardware_mapping: str = "adafruit-hat"`
- `led_chain: int = 1` → `led_chain_length: int = 1`
- `led_parallel: int = 1` → (unchanged)
- `led_slowdown_gpio: int = 1` → `led_gpio_slowdown: int = 1`
- `led_pixel_mapper: str = ""` → `led_pixel_mapper_config: str = ""`
- `led_show_refresh: bool = False` → `led_show_refresh_rate: bool = False`
- `led_no_hardware_pulse: bool = False` → `led_disable_hardware_pulsing: bool = False`
- `led_row_addr_type: int = 0` → `led_row_address_type: int = 0`

In `__attrs_post_init__`:
- `options.hardware_mapping = self.led_gpio_mapping` → `options.hardware_mapping = self.led_hardware_mapping`
- `options.chain_length = self.led_chain` → `options.chain_length = self.led_chain_length`
- `options.gpio_slowdown = self.led_slowdown_gpio` → `options.gpio_slowdown = self.led_gpio_slowdown`
- `options.pixel_mapper_config = self.led_pixel_mapper` → `options.pixel_mapper_config = self.led_pixel_mapper_config`
- `options.show_refresh_rate = 1` inside the `if self.led_show_refresh:` block: change condition to `if self.led_show_refresh_rate:`
- `options.disable_hardware_pulsing = True` inside `if self.led_no_hardware_pulse:`: change condition to `if self.led_disable_hardware_pulsing:`
- `options.row_address_type = self.led_row_addr_type` → `options.row_address_type = self.led_row_address_type`
- The `options.gpio_slowdown = self.led_slowdown_gpio` conditional: change both `if self.led_slowdown_gpio is not None:` and the assignment
- The `options.hardware_mapping = self.led_gpio_mapping` conditional: change `if self.led_gpio_mapping is not None:` and the assignment

- [ ] **Step 3: Rename in `factories.py`**

In `build_frame_from_config`'s `LedFrame(...)` call, rename the kwargs:
- `led_gpio_mapping=display.gpio_mapping,` → `led_hardware_mapping=display.hardware_mapping,`
- `led_chain=display.chain,` → `led_chain_length=display.chain_length,`
- `led_slowdown_gpio=display.slowdown_gpio,` → `led_gpio_slowdown=display.gpio_slowdown,`
- `led_pixel_mapper=display.pixel_mapper,` → `led_pixel_mapper_config=display.pixel_mapper_config,`
- `led_show_refresh=display.show_refresh,` → `led_show_refresh_rate=display.show_refresh_rate,`
- `led_no_hardware_pulse=display.no_hardware_pulse,` → `led_disable_hardware_pulsing=display.disable_hardware_pulsing,`
- `led_row_addr_type=display.row_addr_type,` → `led_row_address_type=display.row_address_type,`
- `led_scan_mode=display.scan_mode,` → (unchanged)

Also update the log format string to use the new names wherever old names appear.

- [ ] **Step 4: Rename in `validate.py`**

Two references to `display.pixel_mapper`:
- `display.pixel_mapper.startswith("Remap:")` → `display.pixel_mapper_config.startswith("Remap:")`
- `display.pixel_mapper[6:]` → `display.pixel_mapper_config[6:]`

(There are two such blocks — apply both.)

- [ ] **Step 5: Run tests to verify Python source changes are internally consistent**

```bash
python -m pytest tests/test_config.py tests/test_frame.py tests/test_app.py -q 2>&1 | tail -20
```

Expected: some tests will FAIL because they still use old field names in inline TOML or kwargs — that's fine and expected at this stage. The important thing is no *import* errors or *AttributeError* in Python source itself. If there are Python-level errors (not test assertion failures), fix them before continuing.

- [ ] **Step 6: Commit Python source changes**

```bash
git add src/led_ticker/config.py src/led_ticker/frame.py src/led_ticker/app/factories.py src/led_ticker/validate.py
git commit -m "refactor: rename DisplayConfig fields to match RGBMatrixOptions (source)"
```

---

### Task 2: Rename in test files

**Files:**
- Modify: `tests/test_config.py`
- Modify: `tests/test_frame.py`
- Modify: `tests/test_app.py`
- Modify: `tests/test_validate.py`
- Modify: `tests/conftest.py` (if it has `pixel_mapper=` references)
- Modify: any other test files with the old names

**Context:** These tests have inline TOML strings (which load through `load_config` and expect the new field names) and direct `DisplayConfig(...)` or `LedFrame(...)` constructor calls with keyword arguments.

- [ ] **Step 1: Rename in `tests/test_config.py`**

This file has:
- Inline TOML strings containing `gpio_mapping`, `slowdown_gpio`, `show_refresh`, `no_hardware_pulse`, `pixel_mapper`, `row_addr_type`, `chain` — rename all to new names
- Assertions like `assert config.display.gpio_mapping == ...` — rename to new field names
- `_DISPLAY_INT_FIELDS` reference at line ~244 — update to include new names

Use replace_all for each old name → new name. Be careful with `chain` — verify grep that every `chain` occurrence in this file is the display config field (not part of `chain_length`).

Specific patterns to replace:
- `gpio_mapping` → `hardware_mapping` (all occurrences)
- `slowdown_gpio` → `gpio_slowdown` (all occurrences)
- `show_refresh` → `show_refresh_rate` (all occurrences)
- `no_hardware_pulse` → `disable_hardware_pulsing` (all occurrences)
- `pixel_mapper` → `pixel_mapper_config` (all occurrences)
- `row_addr_type` → `row_address_type` (all occurrences)
- `chain = ` → `chain_length = ` (TOML key in strings; be careful of `chain_length` already present)
- `"chain"` → `"chain_length"` (in _DISPLAY_INT_FIELDS list)
- `.chain` → `.chain_length` (attribute access)

- [ ] **Step 2: Rename in `tests/test_frame.py`**

Assertions on `frame.led_*` attributes:
- `frame.led_gpio_mapping` → `frame.led_hardware_mapping`
- `frame.led_chain` → `frame.led_chain_length`
- `frame.led_slowdown_gpio` → `frame.led_gpio_slowdown`
- `frame.led_pixel_mapper` → `frame.led_pixel_mapper_config`
- `frame.led_show_refresh` → `frame.led_show_refresh_rate`
- `frame.led_no_hardware_pulse` → `frame.led_disable_hardware_pulsing`
- `frame.led_row_addr_type` → `frame.led_row_address_type`

Also any `LedFrame(led_gpio_mapping=...)` constructor calls in the test file.

- [ ] **Step 3: Rename in `tests/test_app.py`**

- `DisplayConfig(...)` kwargs: rename any old field names
- Assertions on `display.*` attributes
- Any inline TOML strings

Specific patterns matching the audit:
- `slowdown_gpio` → `gpio_slowdown` (lines ~27, 30, 1227, 1278)
- `pixel_mapper` → `pixel_mapper_config` (line ~153 test function and kwargs)
- `chain` → `chain_length` (lines ~24, 41)

- [ ] **Step 4: Rename in `tests/test_validate.py`**

This file has 90+ `chain =` occurrences in inline TOML strings. Use replace_all for each:

```python
# In all inline TOML strings (triple-quoted or multiline), replace:
# "chain = " → "chain_length = "
# "gpio_mapping" → "hardware_mapping"  
# "slowdown_gpio" → "gpio_slowdown"
# "show_refresh" → "show_refresh_rate"
# "no_hardware_pulse" → "disable_hardware_pulsing"
# "pixel_mapper" → "pixel_mapper_config"
# "row_addr_type" → "row_address_type"
```

Use replace_all=True for each pattern. For `chain`, search for `chain = ` (with trailing space) or `chain=` to avoid accidentally matching `chain_length` that might already appear. Verify with grep after.

- [ ] **Step 5: Rename in `tests/conftest.py` and other test files**

Check `tests/conftest.py` for `pixel_mapper=` or other old field names. Apply same renames.

Check any other test files flagged by running:
```bash
grep -rEl "gpio_mapping|slowdown_gpio|show_refresh[^_]|no_hardware_pulse|pixel_mapper[^_]|row_addr_type" tests/ --include="*.py"
```

Apply renames to any files found.

- [ ] **Step 6: Run test suite**

```bash
python -m pytest tests/ -q 2>&1 | tail -10
```

Expected: 2146 passed, 2 skipped (or similar). All TOML-loading tests that were failing in Task 1 should now pass since both the Python fields and the inline TOML strings are updated. If any failures remain, fix them.

- [ ] **Step 7: Commit test changes**

```bash
git add tests/
git commit -m "refactor: rename DisplayConfig fields in test files"
```

---

### Task 3: Rename in TOML config files

**Files:**
- Modify: all 34 files in `config/`
- Modify: `tests/fixtures/broken-bigsign-config.toml`

- [ ] **Step 1: Bulk-rename all TOML files**

Use `perl -pi -e` (works on macOS; supports word boundaries unlike BSD sed):

```bash
WROOT="$(git rev-parse --show-toplevel)"  # Set automatically from worktree root

find "$WROOT/config" "$WROOT/tests/fixtures" -name "*.toml" | xargs perl -pi -e '
  s/\bgpio_mapping\b/hardware_mapping/g;
  s/\bslowdown_gpio\b/gpio_slowdown/g;
  s/\bshow_refresh\b(?!_rate)/show_refresh_rate/g;
  s/\bno_hardware_pulse\b/disable_hardware_pulsing/g;
  s/\bpixel_mapper\b(?!_config)/pixel_mapper_config/g;
  s/\brow_addr_type\b/row_address_type/g;
  s/\bchain\b(?!_length)/chain_length/g;
'
```

The negative-lookahead `(?!_rate)`, `(?!_config)`, `(?!_length)` patterns prevent double-substitution if a file already contains a new name (e.g. a comment).

- [ ] **Step 2: Verify no old names remain in TOML files**

```bash
grep -rn "gpio_mapping\|slowdown_gpio\|show_refresh[^_]\|no_hardware_pulse\|pixel_mapper[^_]\|row_addr_type\|[^_]chain[^_]" config/ tests/fixtures/ 2>/dev/null
```

Expected: no output. If any lines appear, fix manually.

- [ ] **Step 3: Run test suite to confirm TOML loading works**

```bash
python -m pytest tests/ -q 2>&1 | tail -10
```

Expected: all pass.

- [ ] **Step 4: Commit TOML changes**

```bash
git add config/ tests/fixtures/
git commit -m "refactor: rename display config fields in TOML config files"
```

---

### Task 4: Rename in live docs

**Files:**
- Modify: `docs/site/src/content/docs/reference/config-options.mdx`
- Modify: `docs/site/src/content/docs/hardware/panel-tuning.mdx`
- Modify: `docs/site/src/content/docs/concepts/display.mdx`
- Modify: `docs/site/src/content/docs/hardware/bigsign.mdx`
- Modify: `docs/site/src/content/docs/hardware/smallsign.mdx`
- Modify: `docs/site/src/content/docs/hardware/building-your-own.mdx`
- Modify: `docs/site/src/content/docs/showcase.mdx`
- Modify: `docs/site/src/content/docs/tutorial/01-setup.mdx`
- Modify: `docs/site/src/content/docs/tutorial/02-first-config.mdx`
- Modify: `docs/site/src/content/docs/tutorial/05-polish.mdx`
- Modify: `docs/site/src/content/docs/tools/gif-plan.mdx`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Bulk-rename in MDX files**

```bash
WROOT="$(git rev-parse --show-toplevel)"

find "$WROOT/docs/site/src/content/docs" "$WROOT/CLAUDE.md" -name "*.mdx" -o -name "CLAUDE.md" | xargs perl -pi -e '
  s/\bgpio_mapping\b/hardware_mapping/g;
  s/\bslowdown_gpio\b/gpio_slowdown/g;
  s/\bshow_refresh\b(?!_rate)/show_refresh_rate/g;
  s/\bno_hardware_pulse\b/disable_hardware_pulsing/g;
  s/\bpixel_mapper\b(?!_config)/pixel_mapper_config/g;
  s/\brow_addr_type\b/row_address_type/g;
  s/\bchain\b(?!_length)/chain_length/g;
'
```

Perl's negative-lookahead prevents double-substitution on names already updated (e.g. `show_refresh_rate` → `show_refresh_raterate` is impossible with the `(?!_rate)` guard).

- [ ] **Step 2: Update `config-options.mdx` table rows**

The reference table has rows like `| \`gpio_mapping\` | ... |`. The sed above will rename the backtick-quoted field names. Verify the table looks correct:

```bash
grep -A2 "hardware_mapping\|gpio_slowdown\|show_refresh_rate\|disable_hardware_pulsing\|pixel_mapper_config\|row_address_type\|chain_length" docs/site/src/content/docs/reference/config-options.mdx | head -40
```

All table rows should show new names. Also update the coercion behavior list in that file — it has a sentence listing field names that accept numeric strings. Find the sentence containing `pwm_bits, pwm_lsb_nanoseconds` and update any old names in it (specifically `chain` → `chain_length`, `slowdown_gpio` → `gpio_slowdown`).

- [ ] **Step 3: Verify no old names remain in docs or CLAUDE.md**

```bash
WROOT="$(git rev-parse --show-toplevel)"
grep -rn "gpio_mapping\|slowdown_gpio\|show_refresh[^_r]\|no_hardware_pulse\|pixel_mapper[^_c]\|row_addr_type" \
  "$WROOT/docs/site/src/content/docs/" "$WROOT/CLAUDE.md" 2>/dev/null
# chain check separately to avoid false positives in chain_length
grep -rn "[^_a-z]chain[^_l]" \
  "$WROOT/docs/site/src/content/docs/" "$WROOT/CLAUDE.md" 2>/dev/null | grep -v "chain_length"
```

Expected: no output. Fix any stragglers manually.

- [ ] **Step 5: Run prettier on all changed MDX files**

```bash
cd docs/site && pnpm prettier --write "src/content/docs/**/*.mdx"
```

- [ ] **Step 6: Run full test suite**

```bash
python -m pytest tests/ -q 2>&1 | tail -10
```

Expected: all pass. The docs-drift test verifies that all `DisplayConfig` field names appear in `config-options.mdx` — this will confirm the docs table is complete.

- [ ] **Step 7: Commit docs changes**

```bash
git add docs/site/src/content/docs/ CLAUDE.md
git commit -m "refactor: rename display config fields in docs and CLAUDE.md"
```
