# Rainbow Lightbulbs + Docs Uplift Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `lit_color = "rainbow"` coloring option (per-bulb hue fixed by perimeter position, with an optional `hue_wraps` density knob) to the existing `LightbulbBorder`, and bring the docs page to parity with the other border styles (4 demo gifs + a Common patterns section).

**Architecture:** Rainbow is a *coloring* option orthogonal to `mode`. When a bulb is lit and rainbow is enabled, its color is computed from `hue_color((idx / count) * 360 * hue_wraps)`; otherwise the existing fixed `lit_color` path runs. Unlit bulbs always use `unlit_color`. Opt-in is the string sentinel `"rainbow"` on the existing `lit_color` field. Validation gains rules 50 (range) and 51 (dead-knob warning). Docs get per-mode gifs, a Rainbow bulbs subsection, and a Common patterns block.

**Tech Stack:** Python 3.13, attrs-free plain class (`LightbulbBorder`), pytest, `uv` for tooling, Astro/MDX docs site, `make render-pinned-demos` for gifs.

**Worktree note:** This plan executes in the `rainbow-lightbulbs` worktree (branch `worktree-rainbow-lightbulbs`). Run `make dev` once if not already done. The pre-commit git hook needs the venv on PATH — prefix git commits with `PATH="$PWD/.venv/bin:$PATH"` if `pre-commit not found` appears.

---

## File Structure

- `src/led_ticker/borders.py` — `LightbulbBorder.__init__` + `paint` (modify). Single class touched; rainbow logic lives inside the existing `is_lit` branches.
- `src/led_ticker/app/coercion.py` — `_coerce_border` `"lightbulbs"` case (modify): allow `"rainbow"` sentinel, add `hue_wraps` to allowed keys.
- `src/led_ticker/validate.py` — `_check_lightbulb_border` (modify): rules 50 + 51.
- `tests/test_borders.py` — new rainbow test class (modify/append).
- `tests/test_validate.py` — rules 50/51 tests (modify/append).
- `docs/site/demos-pinned/border-lightbulbs-{chase,alternate,unison,rainbow}.toml` — new pinned demo configs (create).
- `docs/site/public/demos-pinned/border-lightbulbs-*.gif` — rendered gifs (generated, committed).
- `docs/site/src/content/docs/concepts/borders.mdx` — Lightbulbs section rewrite (modify).

---

## Task 1: Rainbow coloring in `LightbulbBorder`

**Files:**
- Modify: `src/led_ticker/borders.py` (`LightbulbBorder.__init__` ~399-428, `paint` ~438-464)
- Test: `tests/test_borders.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_borders.py` (the file already imports `LightbulbBorder` and defines `_FakeRealCanvas`; add the `hue_color` import at the top alongside the existing border imports):

```python
# add to the existing top-of-file imports
from led_ticker.color_lut import hue_color


class TestLightbulbBorderRainbow:
    def test_rainbow_flag_set_via_sentinel(self):
        """lit_color='rainbow' sets _rainbow_lit and a default hue_wraps."""
        b = LightbulbBorder(mode="chase", lit_color="rainbow")
        assert b._rainbow_lit is True
        assert b.hue_wraps == 1.0

    def test_non_rainbow_keeps_tuple(self):
        b = LightbulbBorder(mode="chase", lit_color=(1, 2, 3))
        assert b._rainbow_lit is False
        assert b.lit_color == (1, 2, 3)

    def test_lit_bulbs_get_per_index_hues(self):
        """With chase_density=1 (all lit), bulb 0 and a bulb a quarter
        of the way around get different, position-derived hues."""
        canvas = _FakeRealCanvas(256, 64)
        b = LightbulbBorder(
            mode="chase",
            chase_density=1,  # all bulbs lit
            lit_color="rainbow",
            unlit_color=(0, 0, 0),
            bulb_size=3,
            gap=3,
        )
        b.paint(canvas, frame_count=0)
        positions = _lightbulb_positions(256, 64, bulb_size=3, gap=3)
        n = len(positions)
        quarter = n // 4
        # Bulb 0 hue == hue_color(0); top-left pixel.
        c0 = hue_color((0 / n) * 360 * 1.0)
        assert canvas.pixels[(0, 0)] == (c0.red, c0.green, c0.blue)
        # Quarter-around bulb has a clearly different hue.
        qx, qy = positions[quarter]
        cq = hue_color((quarter / n) * 360 * 1.0)
        assert canvas.pixels[(qx, qy)] == (cq.red, cq.green, cq.blue)
        assert canvas.pixels[(qx, qy)] != canvas.pixels[(0, 0)]

    def test_hue_wraps_tiles_multiple_spectra(self):
        """hue_wraps=2 means the bulb halfway around repeats bulb 0's hue."""
        canvas = _FakeRealCanvas(256, 64)
        b = LightbulbBorder(
            mode="chase",
            chase_density=1,
            lit_color="rainbow",
            unlit_color=(0, 0, 0),
            bulb_size=3,
            gap=3,
            hue_wraps=2.0,
        )
        b.paint(canvas, frame_count=0)
        positions = _lightbulb_positions(256, 64, bulb_size=3, gap=3)
        n = len(positions)
        half = n // 2
        # (half/n)*360*2 = 360 ≡ 0 (mod 360): same hue as bulb 0.
        hx, hy = positions[half]
        expect = hue_color((half / n) * 360 * 2.0)
        assert canvas.pixels[(hx, hy)] == (expect.red, expect.green, expect.blue)
        c0 = hue_color(0)
        assert canvas.pixels[(hx, hy)] == (c0.red, c0.green, c0.blue)

    def test_unlit_bulbs_keep_unlit_color_in_rainbow(self):
        """Unlit bulbs ignore rainbow and use unlit_color."""
        canvas = _FakeRealCanvas(256, 64)
        b = LightbulbBorder(
            mode="chase",
            chase_density=3,  # bulb idx 1 is unlit at frame 0
            lit_color="rainbow",
            unlit_color=(7, 8, 9),
            bulb_size=3,
            gap=3,
        )
        b.paint(canvas, frame_count=0)
        # Second bulb on top edge (x=6) is unlit (1 % 3 != 0).
        assert canvas.pixels[(6, 0)] == (7, 8, 9)

    def test_rainbow_composes_with_unison(self):
        """In unison 'lit' phase all bulbs lit and rainbow-colored; in
        'off' phase all use unlit_color."""
        lit_canvas = _FakeRealCanvas(256, 64)
        off_canvas = _FakeRealCanvas(256, 64)
        b = LightbulbBorder(
            mode="unison",
            lit_color="rainbow",
            unlit_color=(2, 2, 2),
            bulb_size=3,
            gap=3,
            speed_frames=1,
        )
        b.paint(lit_canvas, frame_count=0)   # phase 0 → lit
        b.paint(off_canvas, frame_count=1)   # phase 1 → unlit
        c0 = hue_color(0)
        assert lit_canvas.pixels[(0, 0)] == (c0.red, c0.green, c0.blue)
        assert off_canvas.pixels[(0, 0)] == (2, 2, 2)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `make test PYTEST_ARGS="tests/test_borders.py::TestLightbulbBorderRainbow -v"`
(or `PYTHONPATH=tests/stubs uv run pytest tests/test_borders.py::TestLightbulbBorderRainbow -v`)
Expected: FAIL — `LightbulbBorder.__init__() got an unexpected keyword argument 'hue_wraps'` / `AttributeError: _rainbow_lit`.

- [ ] **Step 3: Implement in `borders.py`**

In `LightbulbBorder.__init__`, change the signature `lit_color` type and add `hue_wraps`, and set the flag. Replace the current signature/body head:

```python
    def __init__(
        self,
        *,
        mode: str = "chase",
        bulb_size: int | None = None,
        gap: int = 3,
        lit_color: tuple[int, int, int] | str = (255, 220, 140),
        unlit_color: tuple[int, int, int] = (40, 20, 0),
        speed_frames: int | None = None,
        chase_density: int = 3,
        direction: str = "cw",
        hue_wraps: float = 1.0,
    ) -> None:
        self.mode = mode
        self._bulb_size_override = bulb_size
        self.gap = gap
        # lit_color may be the string sentinel "rainbow" — in that case
        # each lit bulb's color is derived from its perimeter index.
        self._rainbow_lit = lit_color == "rainbow"
        self.lit_color = lit_color
        self.unlit_color = unlit_color
        self.hue_wraps = hue_wraps
        if speed_frames is None:
            speed_frames = {"chase": 2, "alternate": 5, "unison": 8}.get(mode, 2)
        self.speed_frames = speed_frames
        self.chase_density = chase_density
        self.direction = direction
```

Add a helper and route lit bulbs through it. Add this method to the class:

```python
    def _lit_rgb(self, idx: int, count: int) -> tuple[int, int, int]:
        """Color for a lit bulb. Rainbow: hue from perimeter index;
        otherwise the fixed lit_color tuple."""
        if not self._rainbow_lit:
            return self.lit_color  # type: ignore[return-value]
        hue = (idx / count) * 360.0 * self.hue_wraps
        c = hue_color(hue)
        return (c.red, c.green, c.blue)
```

Add the import near the top of `borders.py` (next to `from led_ticker.color_lut import hue_color` — it is **already imported**, confirm and reuse).

Update the three mode branches in `paint` to use `_lit_rgb` for the lit color. Replace the chase / alternate / unison branches:

```python
        count = len(positions)
        if self.mode == "chase":
            step = phase if self.direction == "cw" else -phase
            for idx, (x0, y0) in enumerate(positions):
                is_lit = ((idx - step) % self.chase_density) == 0
                rgb = self._lit_rgb(idx, count) if is_lit else self.unlit_color
                self._paint_bulb(real, x0, y0, bulb_size, rgb)
        elif self.mode == "alternate":
            flip = phase % 2
            for idx, (x0, y0) in enumerate(positions):
                is_lit = ((idx + flip) % 2) == 0
                rgb = self._lit_rgb(idx, count) if is_lit else self.unlit_color
                self._paint_bulb(real, x0, y0, bulb_size, rgb)
        elif self.mode == "unison":
            all_lit = (phase % 2) == 0
            for idx, (x0, y0) in enumerate(positions):
                rgb = self._lit_rgb(idx, count) if all_lit else self.unlit_color
                self._paint_bulb(real, x0, y0, bulb_size, rgb)
        else:
            raise ValueError(
                f"LightbulbBorder.mode must be 'chase', 'alternate', or "
                f"'unison'; got {self.mode!r}"
            )
```

Update the class docstring to document the rainbow option (one sentence: "`lit_color` may be the string `\"rainbow\"`; each lit bulb takes a hue from its perimeter position, tiled `hue_wraps` times around the ring; unlit bulbs keep `unlit_color`.").

- [ ] **Step 4: Run the tests to verify they pass**

Run: `make test PYTEST_ARGS="tests/test_borders.py::TestLightbulbBorderRainbow -v"`
Expected: PASS (6 tests).

- [ ] **Step 5: Run the full border suite to confirm no regression**

Run: `make test PYTEST_ARGS="tests/test_borders.py -v"`
Expected: PASS (all existing lightbulb tests still green — the non-rainbow path is unchanged).

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker/borders.py tests/test_borders.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "feat: rainbow lit_color option for lightbulb border

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Coercion — accept `lit_color = "rainbow"` and `hue_wraps`

**Files:**
- Modify: `src/led_ticker/app/coercion.py` (`_coerce_border` `"lightbulbs"` case ~448-479)
- Test: `tests/test_borders.py` (coercion tests live alongside border tests; if there is a dedicated `tests/test_coercion.py`, use it — verify with `ls tests | grep coercion`)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_borders.py` (import `_coerce_border` at top if not present: `from led_ticker.app.coercion import _coerce_border`):

```python
class TestLightbulbRainbowCoercion:
    def test_rainbow_sentinel_builds_border(self):
        b = _coerce_border(
            {"style": "lightbulbs", "mode": "chase", "lit_color": "rainbow"}
        )
        assert isinstance(b, LightbulbBorder)
        assert b._rainbow_lit is True

    def test_hue_wraps_accepted(self):
        b = _coerce_border(
            {"style": "lightbulbs", "lit_color": "rainbow", "hue_wraps": 3}
        )
        assert b.hue_wraps == 3

    def test_junk_lit_color_string_rejected(self):
        with pytest.raises(ValueError, match="lit_color"):
            _coerce_border(
                {"style": "lightbulbs", "lit_color": "banana"}
            )

    def test_rgb_lit_color_still_validated(self):
        b = _coerce_border(
            {"style": "lightbulbs", "lit_color": [10, 20, 30]}
        )
        assert b.lit_color == (10, 20, 30)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `make test PYTEST_ARGS="tests/test_borders.py::TestLightbulbRainbowCoercion -v"`
Expected: FAIL — `hue_wraps` is an unknown key; `"rainbow"` string fails `_validate_rgb`.

- [ ] **Step 3: Implement in `coercion.py`**

In the `case "lightbulbs":` block, add `"hue_wraps"` to the `allowed` set:

```python
            case "lightbulbs":
                allowed = {
                    "mode",
                    "bulb_size",
                    "gap",
                    "lit_color",
                    "unlit_color",
                    "speed_frames",
                    "chase_density",
                    "direction",
                    "hue_wraps",
                }
```

Change the `lit_color` coercion to pass the `"rainbow"` sentinel through untouched:

```python
                if "lit_color" in kwargs:
                    if kwargs["lit_color"] == "rainbow":
                        pass  # sentinel — handled by LightbulbBorder
                    else:
                        kwargs["lit_color"] = tuple(
                            _validate_rgb(
                                kwargs["lit_color"], "border lightbulbs lit_color"
                            )
                        )
```

(`unlit_color` block is unchanged.)

- [ ] **Step 4: Run the tests to verify they pass**

Run: `make test PYTEST_ARGS="tests/test_borders.py::TestLightbulbRainbowCoercion -v"`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/app/coercion.py tests/test_borders.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "feat: coerce lightbulbs lit_color=rainbow + hue_wraps

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Validation — rule 50 (hue_wraps range) + rule 51 (dead-knob warning)

**Files:**
- Modify: `src/led_ticker/validate.py` (`_check_lightbulb_border`, after rule 49 ~1491, before `return issues`)
- Test: `tests/test_validate.py` (class `TestPoolLayoutValidation` exists; add a sibling `TestLightbulbHueWrapsValidation`)

- [ ] **Step 1: Write the failing tests**

First check how existing lightbulb validation tests build a config and call the validator (`grep -n "lightbulb\|_check_lightbulb\|rule=4" tests/test_validate.py`) and mirror that fixture/helper. Append, matching the existing harness used by other lightbulb rule tests:

```python
class TestLightbulbHueWrapsValidation:
    def _border_cfg(self, border):
        # Mirror the minimal config helper the other lightbulb-rule
        # tests use in this file (display + one section + one message
        # widget carrying `border`). Reuse the existing helper if one
        # exists rather than duplicating.
        ...

    def test_rule50_zero_hue_wraps_rejected(self):
        issues = self._validate(
            {"style": "lightbulbs", "lit_color": "rainbow", "hue_wraps": 0}
        )
        assert any(i.rule == 50 and i.severity == "error" for i in issues)

    def test_rule50_negative_hue_wraps_rejected(self):
        issues = self._validate(
            {"style": "lightbulbs", "lit_color": "rainbow", "hue_wraps": -1}
        )
        assert any(i.rule == 50 and i.severity == "error" for i in issues)

    def test_rule50_non_numeric_hue_wraps_rejected(self):
        issues = self._validate(
            {"style": "lightbulbs", "lit_color": "rainbow", "hue_wraps": "x"}
        )
        assert any(i.rule == 50 and i.severity == "error" for i in issues)

    def test_rule50_valid_hue_wraps_ok(self):
        issues = self._validate(
            {"style": "lightbulbs", "lit_color": "rainbow", "hue_wraps": 2.5}
        )
        assert not any(i.rule == 50 for i in issues)

    def test_rule51_dead_knob_warns(self):
        issues = self._validate(
            {"style": "lightbulbs", "hue_wraps": 2}  # no lit_color="rainbow"
        )
        assert any(i.rule == 51 and i.severity == "warning" for i in issues)
```

Implement the `_validate`/`_border_cfg` helper by copying the exact pattern an existing rule-44 test uses in this file (build an `AppConfig` with one section + one `message` widget whose `border` is the dict, then call `_check_lightbulb_border(config)`).

- [ ] **Step 2: Run the tests to verify they fail**

Run: `make test PYTEST_ARGS="tests/test_validate.py::TestLightbulbHueWrapsValidation -v"`
Expected: FAIL — no rule 50/51 issues emitted yet.

- [ ] **Step 3: Implement in `validate.py`**

Inside `_check_lightbulb_border`, in the per-widget loop after the rule-49 block and before the loop continues, add:

```python
            # Rule 50: hue_wraps (when set) must be a positive number.
            hue_wraps = border_raw.get("hue_wraps")
            if hue_wraps is not None and (
                isinstance(hue_wraps, bool)
                or not isinstance(hue_wraps, (int, float))
                or hue_wraps <= 0
            ):
                issues.append(
                    ValidationIssue(
                        rule=50,
                        location=loc,
                        severity="error",
                        message=(
                            f"hue_wraps must be a positive number; got {hue_wraps!r}"
                        ),
                        fix="Set hue_wraps to a positive number (e.g. 1.0 or 2).",
                    )
                )

            # Rule 51: hue_wraps set without lit_color="rainbow" is ignored — warn.
            if hue_wraps is not None and border_raw.get("lit_color") != "rainbow":
                issues.append(
                    ValidationIssue(
                        rule=51,
                        location=loc,
                        severity="warning",
                        message=(
                            "hue_wraps only applies when lit_color = \"rainbow\"; "
                            "ignored otherwise"
                        ),
                        fix='Set lit_color = "rainbow", or remove hue_wraps.',
                    )
                )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `make test PYTEST_ARGS="tests/test_validate.py::TestLightbulbHueWrapsValidation -v"`
Expected: PASS (5 tests).

- [ ] **Step 5: Run validate + borders suites**

Run: `make test PYTEST_ARGS="tests/test_validate.py tests/test_borders.py -q"`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker/validate.py tests/test_validate.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "feat: validate lightbulbs hue_wraps (rules 50/51)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Full suite + lint gate

**Files:** none (verification only)

- [ ] **Step 1: Run the full test suite**

Run: `make test`
Expected: PASS, coverage unchanged or higher. No new failures.

- [ ] **Step 2: Lint + format**

Run: `make lint` then `make format`
Expected: clean. If `make format` changes files, re-stage and amend the last commit.

- [ ] **Step 3: Config preflight on a hand-written rainbow config**

Create `/tmp/rainbow-check.toml`:

```toml
[display]
rows = 16
cols = 32
chain = 5
default_scale = 1

[[playlist.section]]
mode = "swap"
hold_time = 3.0

[[playlist.section.widget]]
type = "message"
text = "RAINBOW"
border = { style = "lightbulbs", lit_color = "rainbow", hue_wraps = 2 }
```

Run: `make validate CONFIG=/tmp/rainbow-check.toml`
Expected: passes with no errors/warnings (rainbow + hue_wraps is a valid combination).

---

## Task 5: Pinned demo configs (4 TOMLs)

**Files:**
- Create: `docs/site/demos-pinned/border-lightbulbs-chase.toml`
- Create: `docs/site/demos-pinned/border-lightbulbs-alternate.toml`
- Create: `docs/site/demos-pinned/border-lightbulbs-unison.toml`
- Create: `docs/site/demos-pinned/border-lightbulbs-rainbow.toml`

- [ ] **Step 1: Plan render durations with the making-a-gif skill**

Invoke the `making-a-gif` skill (or run `make plan-gif CONFIG=<toml>`) to get a `--duration` that captures a full animation cycle for each demo. Use that value as the `# render-duration: N` comment header (the Makefile reads it — see `docs/site/demos-pinned/border-constant.toml` for the format). Lightbulb chase needs enough seconds for the lit window to travel a visible distance; unison needs ~2 blink cycles.

- [ ] **Step 2: Write the four demo TOMLs**

Render at **bigsign** scale so the 3×3 bulbs are visible. Use the exact
`[display]` block from existing bigsign pinned demos (e.g.
`docs/site/demos-pinned/two_row-hires-emoji.toml`):
`rows=64`, `cols=256`, `chain=1`, `default_scale=4`. `border-lightbulbs-chase.toml`:

```toml
# render-duration: 6
[display]
rows = 64
cols = 256
chain = 1
default_scale = 4
brightness = 60

[transitions]
default = "cut"

[[playlist.section]]
mode = "swap"
loop_count = 1
hold_time = 5.0

[[playlist.section.widget]]
type = "message"
text = "MARQUEE"
border = { style = "lightbulbs", mode = "chase" }
```

`border-lightbulbs-alternate.toml` — same display/section, swap the widget:

```toml
[[playlist.section.widget]]
type = "message"
text = "TWINKLE"
border = { style = "lightbulbs", mode = "alternate" }
```

`border-lightbulbs-unison.toml`:

```toml
[[playlist.section.widget]]
type = "message"
text = "BLINK"
border = { style = "lightbulbs", mode = "unison" }
```

`border-lightbulbs-rainbow.toml`:

```toml
[[playlist.section.widget]]
type = "message"
text = "PARTY"
border = { style = "lightbulbs", mode = "chase", lit_color = "rainbow" }
```

(The renderer does not need `pixel_mapper_config` / `parallel` for demos — the `two_row-hires-emoji.toml` block above is sufficient. Use the `plan-gif` target per config: `make plan-gif CONFIG=docs/site/demos-pinned/border-lightbulbs-chase.toml` to confirm each `# render-duration`.)

- [ ] **Step 3: Validate each demo config**

Run: `for t in docs/site/demos-pinned/border-lightbulbs-*.toml; do make validate CONFIG=$t; done`
Expected: each passes.

- [ ] **Step 4: Commit the configs**

```bash
git add docs/site/demos-pinned/border-lightbulbs-*.toml
PATH="$PWD/.venv/bin:$PATH" git commit -m "docs: pinned demo configs for lightbulb border modes

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Render the 4 gifs

**Files:**
- Generate: `docs/site/public/demos-pinned/border-lightbulbs-{chase,alternate,unison,rainbow}.gif`

- [ ] **Step 1: Render the pinned demos**

Run: `make render-pinned-demos` (confirm exact target name via `grep -n "render.*demo" Makefile` — the Makefile section near line 148 builds `docs/site/demos-pinned/*.toml` → `docs/site/public/demos-pinned/*.gif`). This regenerates ALL pinned gifs; only the 4 new ones should appear as new files.

Expected: 4 new `border-lightbulbs-*.gif` files under `docs/site/public/demos-pinned/`.

- [ ] **Step 2: Eyeball each gif**

Open each gif and confirm: bulbs are visible, the chase travels, alternate twinkles, unison blinks, rainbow shows distinct per-bulb colors. If a cycle is cut off, bump the `# render-duration` in that TOML and re-render.

- [ ] **Step 3: Commit the gifs**

```bash
git add docs/site/public/demos-pinned/border-lightbulbs-*.gif
PATH="$PWD/.venv/bin:$PATH" git commit -m "docs: render lightbulb border demo gifs

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: Docs — borders.mdx Lightbulbs section rewrite

**Files:**
- Modify: `docs/site/src/content/docs/concepts/borders.mdx` (Lightbulbs section ~212-254; style table row ~24; intro ~10)

- [ ] **Step 1: Add per-mode demo gifs in the Modes list**

Under the Modes list (the `chase` / `alternate` / `unison` bullets), add a `<DemoGif>` for each, mirroring the existing usage in the file:

```mdx
<DemoGif
  src="/demos-pinned/border-lightbulbs-chase.gif"
  caption="`chase` — warm-white marquee, lit window travels clockwise"
/>
<DemoGif
  src="/demos-pinned/border-lightbulbs-alternate.gif"
  caption="`alternate` — even/odd twinkle, no directional motion"
/>
<DemoGif
  src="/demos-pinned/border-lightbulbs-unison.gif"
  caption="`unison` — all bulbs blink together"
/>
```

- [ ] **Step 2: Add the Rainbow bulbs subsection**

After the "Full table form" block, before "When to use each style", add:

```mdx
### Rainbow bulbs

Set `lit_color = "rainbow"` to color each lit bulb by its position around the
perimeter — a full hue spectrum wrapped around the ring. The hues are **static
in space**: they do not rotate over time, so with `mode = "chase"` the lit
window travels across a fixed string of colored bulbs, exactly like a strand of
party or Christmas lights. Unlit bulbs keep their `unlit_color` glow.

<DemoGif
  src="/demos-pinned/border-lightbulbs-rainbow.gif"
  caption="`lit_color = \"rainbow\"` with `mode = \"chase\"` — a traveling lit window over a fixed rainbow string"
/>

<TomlExample
  code={`border = { style = "lightbulbs", mode = "chase", lit_color = "rainbow" }`}
/>

**`hue_wraps`** (default `1.0`): how many full spectra tile around the perimeter.
`1.0` wraps one rainbow once around the whole edge (adjacent bulbs differ
subtly). Raise it to `2` or `3` to tile multiple rainbows and widen the
per-bulb color contrast.

<TomlExample
  code={`# Two full spectra around the ring — punchier per-bulb color
border = { style = "lightbulbs", lit_color = "rainbow", hue_wraps = 2 }`}
/>
```

- [ ] **Step 3: Add the Common patterns subsection**

After "When to use each style", add (matching the structure of the rainbow / color_cycle "Common patterns" blocks):

```mdx
### Common patterns

**Vegas / theatrical marquee** — warm-white chase tuned for a fast traveling
lit window:

<TomlExample
  code={`border = { style = "lightbulbs", mode = "chase", speed_frames = 1, chase_density = 2 }
# Tight, fast-moving marquee — every other bulb lit, one step per engine tick`}
/>

**Rainbow party lights** — a calm static string of colored bulbs:

<TomlExample
  code={`border = { style = "lightbulbs", mode = "chase", lit_color = "rainbow", chase_density = 1 }
# All bulbs lit, each its own hue — a steady rainbow strand`}
/>

**Holiday / themed two-color** — pick a palette for lit + unlit and alternate
them:

<TomlExample
  code={`border = { style = "lightbulbs", mode = "alternate", lit_color = [200, 30, 30], unlit_color = [20, 120, 40] }
# Red / green holiday twinkle`}
/>
```

- [ ] **Step 4: Update the full-table example + intro**

In the existing "Full table form" `<TomlExample>`, add a `hue_wraps` line:

```
           hue_wraps = 1.0,               # only used when lit_color = "rainbow"
```

Update the page intro (line ~10) and the style table note so they account for the rainbow option (e.g. change the `lightbulbs` table row's "Per-pixel color?" cell note to mention the optional rainbow coloring). Keep the in-prose defaults list (`mode = "chase"`, `bulb_size`, `gap`, …) accurate.

- [ ] **Step 5: Lint the docs**

Run: `cd docs/site && uv run --project .. pre-commit run docs-lint --files src/content/docs/concepts/borders.mdx` (or the repo's docs-lint command — confirm via `grep -n docs-lint Makefile .pre-commit-config.yaml`). If the site has an `astro check` / prettier step, run it on the file.
Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add docs/site/src/content/docs/concepts/borders.mdx
PATH="$PWD/.venv/bin:$PATH" git commit -m "docs: lightbulb border gifs, rainbow option, common patterns

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: Final verification + PR

**Files:** none

- [ ] **Step 1: Full suite once more**

Run: `make test && make lint`
Expected: PASS / clean.

- [ ] **Step 2: Push and open a PR (only after user go-ahead)**

```bash
git push -u origin worktree-rainbow-lightbulbs
gh pr create --title "Rainbow lightbulbs border + docs uplift" --body "$(cat <<'EOF'
## Summary
- Add `lit_color = "rainbow"` to the lightbulb border — per-bulb hue fixed by perimeter position, with an optional `hue_wraps` density knob. Composes with all three modes (chase/alternate/unison).
- Validation rules 50 (hue_wraps range) + 51 (dead-knob warning).
- Docs: 4 demo gifs (chase/alternate/unison/rainbow), a Rainbow bulbs subsection, and a Common patterns block on `concepts/borders`.

## Test plan
- New `TestLightbulbBorderRainbow`, `TestLightbulbRainbowCoercion`, `TestLightbulbHueWrapsValidation`.
- `make test` + `make lint` green.
- `make validate` on a rainbow config passes clean.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Do NOT merge — wait for explicit user go-ahead.

---

## Self-Review notes

- **Spec coverage:** feature (Task 1), coercion sentinel + hue_wraps (Task 2), validation rules 50/51 (Task 3), 4 gifs (Tasks 5-6), docs rewrite incl. rainbow subsection + 3 common patterns + per-mode gifs + hue_wraps in table (Task 7). All spec sections mapped.
- **Type consistency:** `_rainbow_lit` (bool), `hue_wraps` (float), `_lit_rgb(idx, count) -> tuple` used identically across borders.py and tests. `lit_color` typed `tuple | str` everywhere.
- **Out-of-scope honored:** no time-rotating hues, no `mode = "rainbow"`, unlit bulbs keep `unlit_color`, no font_color pairing pattern.
- **Open confirmation during execution:** exact bigsign `[display]` block for pinned demos (Task 5 Step 2) and exact `make render-pinned-demos` target name (Task 6 Step 1) — both flagged inline to verify against the repo rather than assumed.
