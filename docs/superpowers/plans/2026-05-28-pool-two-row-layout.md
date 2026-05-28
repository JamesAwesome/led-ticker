# Pool Widget Two-Row Layout — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `layout = "two_row"` to the pool widget — produces stacked label-on-top / big-number-on-bottom rendering by reusing the existing `TwoRowMessage` primitive, with a new bigsign testing config that drives it.

**Architecture:** PoolMonitor gains a `layout` field (default `"ticker"`, new value `"two_row"`). When `"two_row"`, `update()` dispatches to `_build_two_row_screens()` which produces `TwoRowMessage` instances instead of `SegmentMessage`. Per-row fonts route through the existing `app/factories.py` dispatch layer (`top_font`/`top_font_size`/etc. — widened from `{"two_row"}` to `{"two_row", "pool"}`). Five screens cycle (title + today + 7d + season HI + season LO).

**Tech Stack:** Python `attrs`, asyncio, pytest, existing `TwoRowMessage` primitive in `widgets/two_row.py`.

**Spec:** `docs/superpowers/specs/2026-05-28-pool-two-row-layout-design.md`

---

## File map

| File | Role |
|---|---|
| `src/led_ticker/widgets/pool.py` | Add `layout` + per-row runtime fields; rename existing `_build_screens` → `_build_ticker_screens`; add `_build_two_row_screens`; dispatch in `update()`. |
| `src/led_ticker/app/factories.py` | Widen `_DISPATCH_APPLICABLE_TYPES` for `top_font`/`top_font_size`/`top_font_threshold`/`bottom_font`/`bottom_font_size`/`bottom_font_threshold` from `{"two_row"}` to `{"two_row", "pool"}`. Add field hints for `layout` and `top_row_height` (already documented for two_row). |
| `src/led_ticker/validate.py` | Pool-specific validation: layout enum check + dead-knob-under-ticker check. |
| `tests/test_widgets/test_pool.py` | New `TestTwoRowLayout` class — 13 behavioral tests + 1 type-widening tripwire. |
| `tests/test_validate.py` | 4 validation tests for the layout enum + dead-knob cases. |
| `config/config.pool_bigsign.toml` | **Create.** Bigsign testing config (256×64 vertical-serpentine, hi-res Inter, cyan label_color). |
| `CLAUDE.md` | One bullet under "Load-bearing invariants by subsystem" mirroring MLB's layout switch. |

---

### Task 1: Add `layout` field + dispatch skeleton

Set up the routing without changing rendered output yet. After this task, `layout = "ticker"` (the default) still produces the same `SegmentMessage`-based screens it always has; setting `layout = "two_row"` produces empty `feed_stories` (we'll fill that in next tasks).

**Files:**
- Modify: `src/led_ticker/widgets/pool.py:169` (class definition) and `:243` (`update()`)
- Test: `tests/test_widgets/test_pool.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_widgets/test_pool.py` (anywhere after the existing `_monitor` helper at line ~118):

```python
class TestTwoRowLayout:
    """Pool widget two_row layout: title + 4 stories using TwoRowMessage."""

    def test_layout_defaults_to_ticker(self):
        m = _monitor()
        assert m.layout == "ticker"

    def test_layout_two_row_field_accepts_value(self):
        m = _monitor(layout="two_row")
        assert m.layout == "two_row"

    def test_layout_two_row_dispatch_uses_build_two_row_screens(self):
        """When layout=two_row, update() routes to the two_row builder.
        At this skeleton stage the builder produces empty stories; the
        next task fills it in.
        """
        m = _monitor(layout="two_row")
        m._build_screens = lambda **_kw: None  # would-fail tripwire if called
        m._build_two_row_screens(
            current_c=27.78,
            current_age_s=10.0,
            past_c=27.2,
            today_min_c=25.6,
            today_max_c=28.9,
            d7_mean_c=26.7,
            d7_min_c=24.4,
            d7_max_c=28.9,
            season_min_c=21.7,
            season_max_c=31.1,
        )
        # No assertion on stories yet — the skeleton only proves the method exists.
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `make test ARGS="tests/test_widgets/test_pool.py::TestTwoRowLayout -v"`
Expected: `AttributeError: 'PoolMonitor' object has no attribute 'layout'` on the first test.

- [ ] **Step 3: Add the runtime field and skeleton method**

Edit `src/led_ticker/widgets/pool.py`. Find the attrs field block (around line 185 where `font: Font = attrs.field(...)` lives). Add `layout` immediately after `font`:

```python
    font: Font = attrs.field(default=FONT_DEFAULT, kw_only=True)
    layout: str = attrs.field(default="ticker", kw_only=True)
    label_color: Color = attrs.field(default=RGB_WHITE, kw_only=True)
```

Rename the existing `_build_screens(...)` method (line 288) to `_build_ticker_screens(...)`. Update its only caller in `update()` (line 268 — look for the `self._build_screens(` call inside `update()`'s success branch).

Add a new method directly above `_build_ticker_screens`:

```python
    def _build_two_row_screens(
        self,
        *,
        current_c: float,
        current_age_s: float,
        past_c: float | None,
        today_min_c: float | None,
        today_max_c: float | None,
        d7_mean_c: float | None,
        d7_min_c: float | None,
        d7_max_c: float | None,
        season_min_c: float | None,
        season_max_c: float | None,
    ) -> None:
        """Build feed_title + feed_stories in two_row layout. See spec
        docs/superpowers/specs/2026-05-28-pool-two-row-layout-design.md.
        """
        # Filled in by Task 3.
        return None
```

In `update()` (around line 268, where `self._build_ticker_screens(...)` is now called), wrap the call in a dispatch:

```python
        if self.layout == "two_row":
            self._build_two_row_screens(
                current_c=current_c,
                current_age_s=age,
                past_c=past_c,
                today_min_c=today_min_c,
                today_max_c=today_max_c,
                d7_mean_c=d7_mean_c,
                d7_min_c=d7_min_c,
                d7_max_c=d7_max_c,
                season_min_c=season_min_c,
                season_max_c=season_max_c,
            )
        else:
            self._build_ticker_screens(
                current_c=current_c,
                current_age_s=age,
                past_c=past_c,
                today_min_c=today_min_c,
                today_max_c=today_max_c,
                d7_mean_c=d7_mean_c,
                d7_min_c=d7_min_c,
                d7_max_c=d7_max_c,
                season_min_c=season_min_c,
                season_max_c=season_max_c,
            )
```

- [ ] **Step 4: Run tests to verify pass**

Run: `make test ARGS="tests/test_widgets/test_pool.py -v"`
Expected: All 30+ pool tests pass (existing + 3 new).

Run: `make test`
Expected: 2257+ total pass, no regressions.

- [ ] **Step 5: Lint**

Run: `make lint`
Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker/widgets/pool.py tests/test_widgets/test_pool.py
git commit -m "$(cat <<'EOF'
feat: pool layout field + two_row dispatch skeleton

Adds `layout: str = "ticker"` to PoolMonitor with `"two_row"` as a
recognized value. update() dispatches to _build_ticker_screens (the
renamed _build_screens) for ticker layout, and to a new empty
_build_two_row_screens for the new layout.

No rendering change yet — Task 3 fills in the two_row screen
builder. This task only establishes the routing so subsequent tests
can target it.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Add per-row runtime fields

Three optional fields on `PoolMonitor` that thread directly to `TwoRowMessage` (no renaming, no shadow fields). All `kw_only`.

**Files:**
- Modify: `src/led_ticker/widgets/pool.py` (class definition)
- Test: `tests/test_widgets/test_pool.py`

- [ ] **Step 1: Write failing tests**

Append to `TestTwoRowLayout` in `tests/test_widgets/test_pool.py`:

```python
    def test_top_font_field_default_is_none(self):
        m = _monitor()
        assert m.top_font is None

    def test_bottom_font_field_default_is_none(self):
        m = _monitor()
        assert m.bottom_font is None

    def test_top_row_height_field_default_is_none(self):
        m = _monitor()
        assert m.top_row_height is None

    def test_per_row_fields_accept_overrides(self):
        sentinel_font = object()
        m = _monitor(
            top_font=sentinel_font,
            bottom_font=sentinel_font,
            top_row_height=4,
        )
        assert m.top_font is sentinel_font
        assert m.bottom_font is sentinel_font
        assert m.top_row_height == 4
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `make test ARGS="tests/test_widgets/test_pool.py::TestTwoRowLayout -v -k field"`
Expected: `AttributeError: 'PoolMonitor' object has no attribute 'top_font'`.

- [ ] **Step 3: Add the runtime fields**

In `src/led_ticker/widgets/pool.py`, find the attrs field block (where `layout` was added in Task 1). Add the three new fields immediately after `label_color`:

```python
    label_color: Color = attrs.field(default=RGB_WHITE, kw_only=True)
    top_font: Font | None = attrs.field(default=None, kw_only=True)
    bottom_font: Font | None = attrs.field(default=None, kw_only=True)
    top_row_height: int | None = attrs.field(default=None, kw_only=True)
    feed_title: SegmentMessage | None = attrs.field(init=False, default=None)
```

- [ ] **Step 4: Run tests to verify pass**

Run: `make test ARGS="tests/test_widgets/test_pool.py -v"`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/widgets/pool.py tests/test_widgets/test_pool.py
git commit -m "$(cat <<'EOF'
feat: add per-row font/row-height runtime fields to PoolMonitor

top_font, bottom_font, top_row_height — all kw_only, all default
None. Thread directly to TwoRowMessage in the next task. No
rendering change.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Implement `_build_two_row_screens` (all five screens)

Produce `feed_title` + 4 `feed_stories` matching the spec's per-screen content map. Tests are written first, the method is filled in once to pass them all.

**Files:**
- Modify: `src/led_ticker/widgets/pool.py` (the `_build_two_row_screens` skeleton from Task 1)
- Test: `tests/test_widgets/test_pool.py`

- [ ] **Step 1: Write the failing tests**

Append to `TestTwoRowLayout`:

```python
    def _build(self, **overrides):
        """Run _build_two_row_screens with realistic defaults; allow per-test overrides."""
        m = _monitor(layout="two_row", **overrides.pop("monitor_kwargs", {}))
        args = dict(
            current_c=27.78,
            current_age_s=10.0,
            past_c=27.2,
            today_min_c=25.6,
            today_max_c=28.9,
            d7_mean_c=26.7,
            d7_min_c=24.4,
            d7_max_c=28.9,
            season_min_c=21.7,
            season_max_c=31.1,
        )
        args.update(overrides)
        m._build_two_row_screens(**args)
        return m

    def test_yields_title_plus_four_stories(self):
        m = self._build()
        assert m.feed_title is not None
        assert len(m.feed_stories) == 4

    def test_title_is_two_row_message(self):
        from led_ticker.widgets.two_row import TwoRowMessage
        m = self._build()
        assert isinstance(m.feed_title, TwoRowMessage)

    def test_all_stories_are_two_row_messages(self):
        from led_ticker.widgets.two_row import TwoRowMessage
        m = self._build()
        for s in m.feed_stories:
            assert isinstance(s, TwoRowMessage)

    def test_title_screen_text(self):
        m = self._build()
        assert m.feed_title.top_text == "POOL"
        assert m.feed_title.bottom_text == "TEMPS"

    def test_today_screen_text(self):
        m = self._build()
        today = m.feed_stories[0]
        assert today.top_text == "POOL 24H"
        assert today.bottom_text == "82F"  # 27.78C -> 82F

    def test_seven_day_screen_text(self):
        m = self._build()
        d7 = m.feed_stories[1]
        assert d7.top_text == "POOL 7D AVG"
        assert d7.bottom_text == "80"  # 26.7C -> 80F

    def test_season_hi_screen_text(self):
        m = self._build()
        season_hi = m.feed_stories[2]
        assert season_hi.top_text == "POOL SEASON HI"
        assert season_hi.bottom_text == "88"  # 31.1C -> 88F

    def test_season_lo_screen_text(self):
        m = self._build()
        season_lo = m.feed_stories[3]
        assert season_lo.top_text == "POOL SEASON LO"
        assert season_lo.bottom_text == "71"  # 21.7C -> 71F

    def test_today_bottom_color_is_zone_color(self):
        from led_ticker.widgets.pool import _zone_color
        m = self._build()
        today = m.feed_stories[0]
        # 27.78C = 82F → ORANGE zone (>=80, <90)
        assert today.bottom_color is _zone_color(82.0)

    def test_today_bottom_color_when_stale(self):
        from led_ticker.widgets.pool import DIM
        m = self._build(current_age_s=10_000.0)  # well past default stale_after=900
        today = m.feed_stories[0]
        assert today.bottom_color is DIM

    def test_seven_day_bottom_color_is_avg(self):
        from led_ticker.widgets.pool import AVG_COLOR
        m = self._build()
        assert m.feed_stories[1].bottom_color is AVG_COLOR

    def test_season_hi_bottom_color_is_hi(self):
        from led_ticker.widgets.pool import HI_COLOR
        m = self._build()
        assert m.feed_stories[2].bottom_color is HI_COLOR

    def test_season_lo_bottom_color_is_lo(self):
        from led_ticker.widgets.pool import LO_COLOR
        m = self._build()
        assert m.feed_stories[3].bottom_color is LO_COLOR

    def test_label_color_threads_to_every_top(self):
        sentinel = object()
        m = self._build(monitor_kwargs={"label_color": sentinel})
        assert m.feed_title.top_color is sentinel
        for s in m.feed_stories:
            assert s.top_color is sentinel

    def test_no_trend_arrow_in_today_screen(self):
        m = self._build()
        today = m.feed_stories[0]
        # The trend arrow glyphs from _trend_arrow are ^/v/-
        # None should appear anywhere in the today screen text.
        combined = today.top_text + today.bottom_text
        assert "^" not in combined
        assert "v" not in combined
        # `-` could appear in a future label; we only check it doesn't
        # show up next to the temperature value.
        assert today.bottom_text == "82F"  # exact match, no trailing arrow

    def test_per_row_fields_thread_to_two_row_message(self):
        sentinel_font_top = object()
        sentinel_font_bottom = object()
        m = self._build(monitor_kwargs={
            "top_font": sentinel_font_top,
            "bottom_font": sentinel_font_bottom,
            "top_row_height": 4,
        })
        today = m.feed_stories[0]
        assert today.top_font is sentinel_font_top
        assert today.bottom_font is sentinel_font_bottom
        assert today.top_row_height == 4
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `make test ARGS="tests/test_widgets/test_pool.py::TestTwoRowLayout -v"`
Expected: many failures (empty feed_stories list, feed_title is None).

- [ ] **Step 3: Implement `_build_two_row_screens`**

Replace the skeleton body in `src/led_ticker/widgets/pool.py`. Add the import to the existing `TwoRowMessage` import line at the top:

```python
from led_ticker.widgets.two_row import TwoRowMessage
```

Then replace the method body:

```python
    def _build_two_row_screens(
        self,
        *,
        current_c: float,
        current_age_s: float,
        past_c: float | None,
        today_min_c: float | None,
        today_max_c: float | None,
        d7_mean_c: float | None,
        d7_min_c: float | None,
        d7_max_c: float | None,
        season_min_c: float | None,
        season_max_c: float | None,
    ) -> None:
        """Build feed_title + feed_stories in two_row layout. See spec
        docs/superpowers/specs/2026-05-28-pool-two-row-layout-design.md.
        """
        now_display = _c_to_display(current_c, self.units)
        zone_f = _c_to_display(current_c, "imperial")
        stale = current_age_s > self.stale_after

        kw = {
            "font": self.font,
            "top_font": self.top_font,
            "bottom_font": self.bottom_font,
            "top_row_height": self.top_row_height,
            "top_color": self.label_color,
        }

        self.feed_title = TwoRowMessage(
            top_text="POOL",
            bottom_text="TEMPS",
            bottom_color=RGB_WHITE,
            **kw,
        )

        today_bottom_color = DIM if stale else _zone_color(zone_f)
        today = TwoRowMessage(
            top_text="POOL 24H",
            bottom_text=_fmt_temp(now_display, self.units),
            bottom_color=today_bottom_color,
            **kw,
        )
        d7 = TwoRowMessage(
            top_text="POOL 7D AVG",
            bottom_text=self._disp(d7_mean_c),
            bottom_color=AVG_COLOR,
            **kw,
        )
        season_hi = TwoRowMessage(
            top_text="POOL SEASON HI",
            bottom_text=self._disp(season_max_c),
            bottom_color=HI_COLOR,
            **kw,
        )
        season_lo = TwoRowMessage(
            top_text="POOL SEASON LO",
            bottom_text=self._disp(season_min_c),
            bottom_color=LO_COLOR,
            **kw,
        )
        self.feed_stories = [today, d7, season_hi, season_lo]
```

If `TwoRowMessage`'s constructor rejects any of the keyword names above (e.g. if it doesn't accept `top_color`/`bottom_color` as construction kwargs), check `src/led_ticker/widgets/two_row.py` for the actual field names and adjust. Do NOT add new attribute names to PoolMonitor that shadow TwoRowMessage's surface — that defeats the threading model.

- [ ] **Step 4: Run tests to verify pass**

Run: `make test ARGS="tests/test_widgets/test_pool.py -v"`
Expected: all `TestTwoRowLayout` tests pass.

- [ ] **Step 5: Update type annotations for feed_title and feed_stories**

The existing fields on `PoolMonitor` are annotated as `SegmentMessage | None` and `list[SegmentMessage]`. They now hold either type. Update at their declaration site (around line 187):

```python
    feed_title: SegmentMessage | TwoRowMessage | None = attrs.field(
        init=False, default=None
    )
    feed_stories: list[SegmentMessage | TwoRowMessage] = attrs.field(
        init=False, factory=list
    )
```

Add a tripwire test:

```python
    def test_feed_stories_type_accepts_both_message_types(self):
        """feed_stories must accept SegmentMessage (ticker) or
        TwoRowMessage (two_row) — Container Protocol conformance
        depends on the field's declared type."""
        from led_ticker.widgets.message import SegmentMessage
        from led_ticker.widgets.two_row import TwoRowMessage
        m = self._build()
        for s in m.feed_stories:
            assert isinstance(s, (SegmentMessage, TwoRowMessage))
```

- [ ] **Step 6: Run pyright on pool.py**

Run: `uv run pyright src/led_ticker/widgets/pool.py`
Expected: 0 errors.

- [ ] **Step 7: Full test suite**

Run: `make test`
Expected: 2270+ pass.

- [ ] **Step 8: Lint**

Run: `make lint`
Expected: clean.

- [ ] **Step 9: Commit**

```bash
git add src/led_ticker/widgets/pool.py tests/test_widgets/test_pool.py
git commit -m "$(cat <<'EOF'
feat: implement _build_two_row_screens (5 screens: title + 4 data)

Builds TwoRowMessage feed_title + 4 feed_stories when layout=two_row:
- Title:     POOL / TEMPS                  (white bottom)
- Today:     POOL 24H / 82F                (zone color OR DIM if stale)
- 7-day:     POOL 7D AVG / 78              (AVG_COLOR pink)
- Season HI: POOL SEASON HI / 95           (HI_COLOR orange)
- Season LO: POOL SEASON LO / 72           (LO_COLOR blue)

label_color drives every top_color. font / top_font / bottom_font /
top_row_height thread directly to TwoRowMessage (no shadow fields).
Trend arrow is intentionally dropped in two_row mode (bottom row is
the value only; spec calls this out as a known tradeoff).

Widens feed_title and feed_stories type annotations to
`SegmentMessage | TwoRowMessage` so Container Protocol conformance
covers both modes.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Two-row placeholder

Mirror the ticker mode's `_set_placeholder` so the initial-load and error states render correctly in two_row mode too.

**Files:**
- Modify: `src/led_ticker/widgets/pool.py:350` (`_set_placeholder`)
- Test: `tests/test_widgets/test_pool.py`

- [ ] **Step 1: Write failing test**

Append to `TestTwoRowLayout`:

```python
    def test_placeholder_in_two_row_mode_uses_two_row_message(self):
        from led_ticker.widgets.two_row import TwoRowMessage
        m = _monitor(layout="two_row")
        m._set_placeholder()
        assert isinstance(m.feed_title, TwoRowMessage)
        assert m.feed_title.top_text == "POOL"
        assert m.feed_title.bottom_text == "TEMPS"
        assert len(m.feed_stories) == 1
        assert isinstance(m.feed_stories[0], TwoRowMessage)
        assert m.feed_stories[0].top_text == "POOL TEMPS"
        assert m.feed_stories[0].bottom_text == "--"

    def test_placeholder_in_ticker_mode_unchanged(self):
        """Existing ticker-mode placeholder behavior must not regress."""
        from led_ticker.widgets.message import SegmentMessage
        m = _monitor()  # default layout=ticker
        m._set_placeholder()
        assert isinstance(m.feed_title, SegmentMessage)
        for s in m.feed_stories:
            assert isinstance(s, SegmentMessage)
```

- [ ] **Step 2: Run to verify failure**

Run: `make test ARGS="tests/test_widgets/test_pool.py -v -k placeholder"`
Expected: `test_placeholder_in_two_row_mode_uses_two_row_message` fails (placeholder still builds SegmentMessage).

- [ ] **Step 3: Implement dispatch in `_set_placeholder`**

In `src/led_ticker/widgets/pool.py`, replace the body of `_set_placeholder` (around line 350) with:

```python
    def _set_placeholder(self) -> None:
        if self.layout == "two_row":
            kw = {
                "font": self.font,
                "top_font": self.top_font,
                "bottom_font": self.bottom_font,
                "top_row_height": self.top_row_height,
                "top_color": self.label_color,
                "bottom_color": self.label_color,
            }
            self.feed_title = TwoRowMessage(
                top_text="POOL",
                bottom_text="TEMPS",
                **kw,
            )
            self.feed_stories = [
                TwoRowMessage(
                    top_text=self.title,
                    bottom_text="--",
                    **kw,
                )
            ]
            return
        self.feed_title = SegmentMessage(
            [(self.title, RGB_WHITE)], center=True, font=self.font
        )
        self.feed_stories = [
            SegmentMessage(
                [(f"{self.title} ", self.label_color), ("--", self.label_color)],
                center=True,
                font=self.font,
            )
        ]
```

- [ ] **Step 4: Run tests**

Run: `make test ARGS="tests/test_widgets/test_pool.py -v"`
Expected: all pool tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/widgets/pool.py tests/test_widgets/test_pool.py
git commit -m "$(cat <<'EOF'
feat: two_row placeholder for pool widget

_set_placeholder now produces TwoRowMessage instances when
layout=two_row. Title screen splits POOL/TEMPS; the single story
screen shows the configured title on top and "--" on bottom.
Mirrors the ticker mode's placeholder for the new layout.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Widen dispatch table to accept per-row fonts on `pool`

The factories layer already knows how to resolve `top_font` + `top_font_size` + `top_font_threshold` into a single `top_font: Font` — but only for the `two_row` widget type. Widen the type set to include `pool` so the same machinery applies.

**Files:**
- Modify: `src/led_ticker/app/factories.py:293-313` (`_DISPATCH_APPLICABLE_TYPES`)
- Test: `tests/test_widgets/test_pool.py`

- [ ] **Step 1: Write failing test**

Append to `TestTwoRowLayout`:

```python
    @pytest.mark.asyncio
    async def test_pool_config_accepts_top_font_via_factories(self):
        """End-to-end: a config with top_font/top_font_size on a pool
        widget must build cleanly. Before widening _DISPATCH_APPLICABLE_TYPES,
        this raised 'unknown field' validation errors."""
        from unittest.mock import AsyncMock, MagicMock
        from led_ticker.app.factories import _build_widget

        session = MagicMock()
        cfg = {
            "type": "pool",
            "layout": "two_row",
            "font": "Inter-Regular",
            "font_size": 32,
            "font_threshold": 80,
            "top_font_size": 16,
            "bottom_font_size": 32,
            "label_color": [130, 220, 255],
        }
        # Don't actually start the widget (would need INFLUXDB_TOKEN);
        # we only need validate_widget_cfg to accept the field set.
        from led_ticker.app.factories import validate_widget_cfg
        await validate_widget_cfg(cfg, session=session)
        # If we got here without raising, the fields were accepted.
```

- [ ] **Step 2: Run to verify failure**

Run: `make test ARGS="tests/test_widgets/test_pool.py -v -k accepts_top_font"`
Expected: `ValueError: widget type='pool' got unknown fields: 'bottom_font_size'...` or similar.

- [ ] **Step 3: Widen the dispatch sets**

Edit `src/led_ticker/app/factories.py`. Find `_DISPATCH_APPLICABLE_TYPES` (line 293). Update six entries:

```python
    "top_font": {"two_row", "pool"},
    "top_font_size": {"two_row", "pool"},
    "top_font_threshold": {"two_row", "pool"},
    "bottom_font": {"two_row", "pool"},
    "bottom_font_size": {"two_row", "pool"},
    "bottom_font_threshold": {"two_row", "pool"},
```

- [ ] **Step 4: Run tests**

Run: `make test ARGS="tests/test_widgets/test_pool.py -v"`
Expected: all pool tests pass including the new one.

- [ ] **Step 5: Full suite — make sure nothing else broke**

Run: `make test`
Expected: 2273+ pass.

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker/app/factories.py tests/test_widgets/test_pool.py
git commit -m "$(cat <<'EOF'
feat: factories accepts per-row fonts on pool widget

Widens six entries in _DISPATCH_APPLICABLE_TYPES from {"two_row"} to
{"two_row", "pool"}: top_font, top_font_size, top_font_threshold,
bottom_font, bottom_font_size, bottom_font_threshold. The existing
resolution code (loads font_family at the given size+threshold and
passes the resulting Font to the widget) is reused unchanged.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: Validation — layout enum

Reject unknown values for `layout` at config-load time with a did-you-mean.

**Files:**
- Modify: `src/led_ticker/validate.py` (or `src/led_ticker/app/factories.py` — see Step 3 for which file)
- Test: `tests/test_validate.py`

- [ ] **Step 1: Write failing test**

Find the existing pool validation test block in `tests/test_validate.py` (search for `"type": "pool"`). Append a new test class at the END of the file:

```python
class TestPoolLayoutValidation:
    """Pool widget `layout` field accepts only "ticker" or "two_row"."""

    @pytest.mark.asyncio
    async def test_unknown_layout_value_raises(self):
        from unittest.mock import MagicMock
        from led_ticker.app.factories import validate_widget_cfg

        cfg = {"type": "pool", "layout": "scoreboard"}
        with pytest.raises(ValueError, match="layout.*ticker.*two_row"):
            await validate_widget_cfg(cfg, session=MagicMock())

    @pytest.mark.asyncio
    async def test_ticker_layout_accepted(self):
        from unittest.mock import MagicMock
        from led_ticker.app.factories import validate_widget_cfg
        cfg = {"type": "pool", "layout": "ticker"}
        await validate_widget_cfg(cfg, session=MagicMock())  # should not raise

    @pytest.mark.asyncio
    async def test_two_row_layout_accepted(self):
        from unittest.mock import MagicMock
        from led_ticker.app.factories import validate_widget_cfg
        cfg = {"type": "pool", "layout": "two_row"}
        await validate_widget_cfg(cfg, session=MagicMock())  # should not raise
```

- [ ] **Step 2: Run to verify failure**

Run: `make test ARGS="tests/test_validate.py::TestPoolLayoutValidation -v"`
Expected: `test_unknown_layout_value_raises` fails (no validation yet — "scoreboard" is silently accepted as a string attrs field).

- [ ] **Step 3: Find the validation entry point**

Read `src/led_ticker/app/factories.py:validate_widget_cfg` (search for `async def validate_widget_cfg`). Identify where widget-specific validation happens — look for places where MLB's `layout = "scoreboard"` is validated for reference.

If MLB has no equivalent (the field just accepts any string today), add new validation **early in `validate_widget_cfg`** before the type pop and before construction. Add this stanza:

```python
    # Pool layout enum
    if widget_cfg.get("type") == "pool":
        layout_value = widget_cfg.get("layout")
        if layout_value is not None and layout_value not in {"ticker", "two_row"}:
            valid = ["ticker", "two_row"]
            suggestion = difflib.get_close_matches(
                str(layout_value), valid, n=1, cutoff=0.4
            )
            hint = f" (did you mean {suggestion[0]!r}?)" if suggestion else ""
            raise ValueError(
                f"pool widget layout must be one of {valid}; "
                f"got {layout_value!r}{hint}"
            )
```

Confirm `difflib` is already imported in this file; if not, add `import difflib` at the top.

- [ ] **Step 4: Run tests**

Run: `make test ARGS="tests/test_validate.py::TestPoolLayoutValidation -v"`
Expected: all 3 pass.

- [ ] **Step 5: Commit**

```bash
git add src/led_ticker/app/factories.py tests/test_validate.py
git commit -m "$(cat <<'EOF'
feat: validate pool widget layout enum

Rejects unknown layout values on pool widgets at config-load time
with a did-you-mean suggestion. Accepts only "ticker" or "two_row".
Catches typos like layout="scoreboard" (the MLB value) cleanly with
a helpful error.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: Validation — dead knobs under ticker layout

If a user sets `top_font` (or any per-row knob) under `layout = "ticker"`, raise a `MigrationError`-style message rather than silently ignoring.

**Files:**
- Modify: `src/led_ticker/app/factories.py` (in `validate_widget_cfg`)
- Test: `tests/test_validate.py`

- [ ] **Step 1: Write failing tests**

Append to `TestPoolLayoutValidation` in `tests/test_validate.py`:

```python
    @pytest.mark.asyncio
    async def test_top_font_with_ticker_layout_raises(self):
        from unittest.mock import MagicMock
        from led_ticker.app.factories import validate_widget_cfg

        cfg = {
            "type": "pool",
            "layout": "ticker",
            "top_font_size": 16,
        }
        with pytest.raises(ValueError, match="layout.*two_row"):
            await validate_widget_cfg(cfg, session=MagicMock())

    @pytest.mark.asyncio
    async def test_top_font_with_default_layout_raises(self):
        """Same check applies when layout is omitted (defaults to ticker)."""
        from unittest.mock import MagicMock
        from led_ticker.app.factories import validate_widget_cfg

        cfg = {
            "type": "pool",
            "top_row_height": 4,
        }
        with pytest.raises(ValueError, match="layout.*two_row"):
            await validate_widget_cfg(cfg, session=MagicMock())

    @pytest.mark.asyncio
    async def test_per_row_knobs_ok_under_two_row(self):
        from unittest.mock import MagicMock
        from led_ticker.app.factories import validate_widget_cfg

        cfg = {
            "type": "pool",
            "layout": "two_row",
            "top_font_size": 16,
            "bottom_font_size": 32,
            "top_row_height": 4,
        }
        await validate_widget_cfg(cfg, session=MagicMock())  # should not raise
```

- [ ] **Step 2: Run to verify failures**

Run: `make test ARGS="tests/test_validate.py::TestPoolLayoutValidation -v"`
Expected: two failures (dead-knob cases are still silently accepted).

- [ ] **Step 3: Add the dead-knob check**

In `validate_widget_cfg` in `src/led_ticker/app/factories.py`, immediately after the layout-enum check from Task 6, add:

```python
    if widget_cfg.get("type") == "pool":
        layout_value = widget_cfg.get("layout", "ticker")
        if layout_value == "ticker":
            two_row_only = {
                "top_font",
                "top_font_size",
                "top_font_threshold",
                "bottom_font",
                "bottom_font_size",
                "bottom_font_threshold",
                "top_row_height",
            }
            offenders = two_row_only & set(widget_cfg.keys())
            if offenders:
                offender = sorted(offenders)[0]
                raise ValueError(
                    f"pool widget {offender!r} only applies when "
                    f"layout='two_row'; remove the field or set "
                    f"layout='two_row'."
                )
```

- [ ] **Step 4: Run tests**

Run: `make test ARGS="tests/test_validate.py::TestPoolLayoutValidation -v"`
Expected: all 6 pass.

- [ ] **Step 5: Full suite**

Run: `make test`
Expected: 2279+ pass.

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker/app/factories.py tests/test_validate.py
git commit -m "$(cat <<'EOF'
feat: pool widget rejects dead per-row knobs under ticker layout

Setting top_font / bottom_font / top_font_size / bottom_font_size /
top_font_threshold / bottom_font_threshold / top_row_height while
layout="ticker" (or default) now raises with a helpful message
pointing users at layout="two_row". Catches the silent-dead-knob
class of config bug at load time.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 8: Field hints for `layout` and `top_row_height`

Wire the new fields into `FIELD_HINTS` so `led-ticker validate --list-fields pool` includes them.

**Files:**
- Modify: `src/led_ticker/app/factories.py:55` (`FIELD_HINTS` dict)

- [ ] **Step 1: Add layout hint**

Find `FIELD_HINTS` in `src/led_ticker/app/factories.py` (line 55). Find an existing pool-specific or shared entry near other layout-related hints. Look for `"team"` (the MLB-specific entry) for grouping inspiration. Add the new entries near `"team"` (or wherever pool fields live):

```python
    "layout": FieldHint(
        '"ticker" | "two_row"',
        'pool widget render mode: "ticker" cycles single-row segmented '
        "messages (with trend arrow); "
        '"two_row" stacks a label on top and the headline value on bottom '
        "(no trend arrow). Bigsign-recommended.",
        '"ticker"',
    ),
    "top_row_height": FieldHint(
        "int (logical rows)",
        "two_row layout only: top band height in logical rows. None = symmetric 8/8 split.",
        "none",
    ),
```

If a `"layout"` key already exists (added for MLB), edit its description to mention the pool valid values explicitly, rather than overwriting.

- [ ] **Step 2: Verify the validate command surfaces them**

Run: `uv run led-ticker validate --list-fields pool 2>&1 | grep -E "layout|top_row_height"`
Expected: both hints appear.

- [ ] **Step 3: Run lint + tests**

Run: `make lint && make test`
Expected: clean.

- [ ] **Step 4: Commit**

```bash
git add src/led_ticker/app/factories.py
git commit -m "$(cat <<'EOF'
docs: field hints for pool layout + top_row_height

Surfaces the new pool-widget knobs via `led-ticker validate
--list-fields pool` so users discover them without grepping the
spec.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 9: Create bigsign testing config

Concrete config for hardware verification on a 256×64 bigsign panel.

**Files:**
- Create: `config/config.pool_bigsign.toml`

- [ ] **Step 1: Write the config**

Create `config/config.pool_bigsign.toml`:

```toml
# Pool widget — bigsign (256×64) hardware testing config (two_row layout)
#
# 8× P3 32×64 panels in a 2×4 vertical-serpentine = 256×64 logical.
# Driven by a Raspberry Pi 5 through an Adafruit RGB Matrix HAT.
#
# Single section, single pool widget in two_row mode. Cycles 5
# screens: title → today → 7-day → season HI → season LO. Hi-res
# Inter font: 16 px for the label (top row), 32 px fills the data
# row (bottom). Cyan label_color matches the longboi/smallsign
# pool test configs.
#
# Usage:
#   cp config/config.pool_bigsign.toml config/config.toml
#   # Make sure .env defines INFLUXDB_TOKEN (and URL/ORG/BUCKET if not default):
#   #   INFLUXDB_URL=http://pool_monitor:8086
#   #   INFLUXDB_ORG=pool
#   #   INFLUXDB_BUCKET=pool_temps
#   #   INFLUXDB_TOKEN=...
#   docker compose up

[display]
rows = 32
cols = 64
chain_length = 8
parallel = 1

# Vertical-serpentine mapping. See https://docs.ledticker.dev/hardware/bigsign/
pixel_mapper_config = "Remap:256,64|192,32n|192,0n|128,32n|128,0n|64,32n|64,0n|0,32n|0,0n"

brightness = 60
default_scale = 4

hardware_mapping = "adafruit-hat"

# Pi 5 RP1 tuning (matches config.bigsign.example.toml).
gpio_slowdown = 3
rp1_rio = 1
pwm_bits = 8
show_refresh_rate = true

[[playlist.section]]
mode = "swap"
hold_time = 5
loop_count = 0  # infinite — soak test

[[playlist.section.widget]]
type = "pool"
title = "POOL TEMPS"
units = "imperial"
update_interval = 60   # fast: prove the background fetch fires every minute
# sensor_id = "12345"  # optional; omit to use cross-sensor global aggregate
stale_after = 900
layout = "two_row"
# Hi-res Inter at the bigsign-tuned sizes.
# font_size = 32 fills the 32-real bottom band; top_font_size = 16
# gives a smaller label (~50% of the 32-real top band).
font = "Inter-Regular"
font_size = 32
font_threshold = 80
top_font_size = 16
# bottom_font_size omitted — falls back to font_size = 32.
# label_color tints "POOL 24H" / "POOL 7D AVG" / "POOL SEASON" prefix labels.
label_color = [130, 220, 255]
```

- [ ] **Step 2: Validate**

Run: `make validate CONFIG=config/config.pool_bigsign.toml`
Expected: `No issues found.`

- [ ] **Step 3: Validate the other pool configs still pass**

Run: `make validate CONFIG=config/config.pool_longboi.toml && make validate CONFIG=config/config.pool_smallsign.toml`
Expected: both clean.

- [ ] **Step 4: Commit**

```bash
git add config/config.pool_bigsign.toml
git commit -m "$(cat <<'EOF'
feat: bigsign hardware testing config for pool widget two_row layout

256×64 vertical-serpentine panel + Pi 5 RP1 tuning. Single section,
single pool widget in layout = "two_row" with Inter-Regular hi-res:
top_font_size = 16 for the label row, font_size = 32 (inherited by
bottom) for the data row. Cyan label_color matches the longboi /
smallsign pool configs for visual consistency.

loop_count = 0 + update_interval = 60 for hardware soak testing.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 10: Render demo gifs (two-row + re-render ticker)

The pool widget demo gif (`docs/site/public/demos-long/widget-pool.gif`) was rendered before the recent label / `Pool ...` prefix / `AVG_COLOR` changes that landed in PR #125. Re-render it. Also add a new demo toml + gif specifically for the two_row layout so the docs can show both modes side-by-side.

**Files:**
- Create: `docs/site/demos-long/widget-pool-two-row.toml`
- Modify: `docs/site/public/demos-long/widget-pool.gif` (re-rendered)
- Create: `docs/site/public/demos-long/widget-pool-two-row.gif`

- [ ] **Step 1: Create the two-row demo TOML**

Create `docs/site/demos-long/widget-pool-two-row.toml`:

```toml
# Long demo: pool widget in two_row layout (bigsign-targeted).
# requires-env: INFLUXDB_TOKEN
#
# Skipped by `make render-long-demos` if INFLUXDB_TOKEN isn't set in
# the environment. Reads INFLUXDB_URL/ORG/BUCKET/TOKEN from .env.
# render-duration: 30

[display]
rows = 32
cols = 64
chain_length = 8
default_scale = 4
brightness = 60

[[playlist.section]]
mode = "swap"
loop_count = 1
hold_time = 5.0

[[playlist.section.widget]]
type = "pool"
title = "POOL TEMPS"
units = "imperial"
update_interval = 5
layout = "two_row"
font = "Inter-Regular"
font_size = 32
font_threshold = 80
top_font_size = 16
label_color = [130, 220, 255]
```

- [ ] **Step 2: Re-render the existing ticker demo**

Confirm `INFLUXDB_TOKEN` is set in `.env` (long-running demos that need it are skipped otherwise). Then:

Run: `make render-long-demo NAME=widget-pool`
Expected: writes a fresh `docs/site/public/demos-long/widget-pool.gif` reflecting the PR #125 changes (white labels, "Pool 24h"/"Pool 7D"/"Pool Season" prefixes, pink AVG_COLOR for the 7-day mean).

If `INFLUXDB_TOKEN` is not available in this environment, skip the re-render and document the skip in the commit message — the demo doesn't gate CI.

- [ ] **Step 3: Render the new two_row demo**

Run: `make render-long-demo NAME=widget-pool-two-row`
Expected: writes a fresh `docs/site/public/demos-long/widget-pool-two-row.gif` cycling all five screens.

Same `INFLUXDB_TOKEN` requirement applies; skip with a note if unavailable.

- [ ] **Step 4: Commit**

```bash
git add docs/site/demos-long/widget-pool-two-row.toml docs/site/public/demos-long/widget-pool-two-row.gif docs/site/public/demos-long/widget-pool.gif
git commit -m "$(cat <<'EOF'
docs: re-render pool demo + add two_row demo gif

- docs/site/demos-long/widget-pool-two-row.toml: bigsign-scale demo
  config exercising layout = "two_row" with Inter hi-res fonts +
  cyan label_color.
- Re-renders widget-pool.gif to reflect PR #125's white labels,
  "Pool 24h"/"Pool 7D"/"Pool Season" prefixes, and the pink
  AVG_COLOR for the 7-day mean — the previous gif was rendered
  before those changes shipped.
- Adds widget-pool-two-row.gif for the new layout.

If INFLUXDB_TOKEN was unavailable in this environment, one or both
gifs may not have been rendered locally — the docs PR/CI step
re-renders or the demo is skipped per make render-long-demos
convention.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 11: Update pool documentation pages

Update the user-facing docs page (`pool.mdx`) and the content-source mirror (`pool.md`) to describe the `layout` field, the per-row knobs, and embed the new two_row demo gif. Also bump `config/config.example.toml`'s pool block to mention `layout` as a toggle.

**Files:**
- Modify: `docs/site/src/content/docs/widgets/pool.mdx`
- Modify: `docs/content-source/widgets/pool.md`
- Modify: `config/config.example.toml` (the pool block updated in PR #126)

- [ ] **Step 1: Read the current pool.mdx structure**

Read `docs/site/src/content/docs/widgets/pool.mdx`. Identify where existing demos / options / examples land (the file has "Required environment variables", "Options", and "Tips" sections per the layout convention).

- [ ] **Step 2: Add a layout section to pool.mdx**

Add a new H2 section directly after "Options" (or wherever logically groups with rendering choices). Use this content verbatim — adapt headings to match the file's existing H-level convention:

```markdown
## Layouts

The pool widget renders in one of two modes, selected by `layout`:

### `layout = "ticker"` (default)

Single-row segmented screens. The today screen shows current temp + trend arrow (`↑` / `↓` / `–`) + today's HI/LO. The 7-day screen shows the mean alongside hi/lo. The season screen shows HI and LO together. Best for smaller panels (smallsign 160×16) where vertical space is limited.

![Pool widget ticker layout demo](/demos-long/widget-pool.gif)

### `layout = "two_row"`

Stacked label-on-top / big-number-on-bottom. Top row carries a descriptive label (`POOL 24H`, `POOL 7D AVG`, `POOL SEASON HI`, `POOL SEASON LO`). Bottom row carries the headline value in a semantic color (zone-color current temp, pink 7-day mean, orange season HI, blue season LO). The trend arrow is intentionally dropped — bottom is the value only. Season splits into HI and LO screens. Best for bigsign / longboi (256×64 / 512×64) where vertical headroom is available.

![Pool widget two_row layout demo](/demos-long/widget-pool-two-row.gif)

Per-row fonts/sizes/thresholds (`top_font`, `top_font_size`, `top_font_threshold`, `bottom_font`, `bottom_font_size`, `bottom_font_threshold`) and an explicit `top_row_height` (logical rows) apply ONLY in `layout = "two_row"`. Setting them under ticker layout raises a config-load error.
```

- [ ] **Step 3: Add layout knobs to the Options table in pool.mdx**

Find the Options table/list. Add these rows (use the file's existing table style):

| Option | Type | Description | Default |
|---|---|---|---|
| `layout` | `"ticker" \| "two_row"` | Rendering mode. See [Layouts](#layouts). | `"ticker"` |
| `top_font` | font name | two_row only: font for the top label row. | inherits `font` |
| `top_font_size` | int (px) | two_row only: top label row text height in real pixels. | inherits `font_size` |
| `top_font_threshold` | int 0-255 | two_row only: hi-res threshold for top row. | inherits `font_threshold` |
| `bottom_font` | font name | two_row only: font for the bottom value row. | inherits `font` |
| `bottom_font_size` | int (px) | two_row only: bottom value row text height in real pixels. | inherits `font_size` |
| `bottom_font_threshold` | int 0-255 | two_row only: hi-res threshold for bottom row. | inherits `font_threshold` |
| `top_row_height` | int (logical rows) | two_row only: top band height. `None` = symmetric 8/8 split. | `None` |

- [ ] **Step 4: Mirror updates into pool.md (content-source)**

Open `docs/content-source/widgets/pool.md`. Add an equivalent "Layouts" section + the new options. Use the same content but in pure markdown (no MDX components). Match the existing file's tone and structure.

- [ ] **Step 5: Update config.example.toml's pool block**

In `config/config.example.toml`, find the pool section (the block updated in PR #126). Add a commented `layout` hint near the existing `# label_color = ...` comment:

```toml
# layout = "two_row"   # optional: stacks "POOL 24H" / "POOL 7D AVG" / etc on top and the
#                      # headline value on bottom. Best for bigsign / longboi. See:
#                      # https://docs.ledticker.dev/widgets/pool/#layouts
```

- [ ] **Step 6: Validate the docs site builds**

Run: `cd docs/site && pnpm run build 2>&1 | tail -5`
Expected: build succeeds, no broken links.

If the build fails because of missing INFLUXDB_TOKEN or the new gif not having been rendered (Task 10 step 3 may have skipped it), the gif `<img>` references will broken-link. Acceptable: the gifs land in the same PR but may have placeholder during the PR review window. The docs PR review catches it.

- [ ] **Step 7: Commit**

```bash
git add docs/site/src/content/docs/widgets/pool.mdx docs/content-source/widgets/pool.md config/config.example.toml
git commit -m "$(cat <<'EOF'
docs: describe pool layout option + per-row knobs

Adds a "Layouts" section to pool.mdx (and the content-source
mirror pool.md) covering ticker vs two_row modes. Embeds both demo
gifs side-by-side. Extends the Options table with the eight new
TOML keys (layout + 7 per-row knobs) including their two_row-only
applicability.

Adds a commented layout hint to config/config.example.toml's pool
block pointing to the new docs section.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 12: CLAUDE.md invariant

Document the layout-switch invariant under the "Load-bearing invariants" section so future contributors don't accidentally regress it.

**Files:**
- Modify: `CLAUDE.md` (find "Load-bearing invariants by subsystem")

- [ ] **Step 1: Add a "Pool widget layouts" bullet**

In `CLAUDE.md`, find the "Load-bearing invariants by subsystem" section. Locate a similar widget-shape bullet (e.g. the MLB scoreboard one or the Container widgets one added in PR #122). Add this new bullet near the MLB scoreboard invariant since they share the layout-switch pattern:

```markdown
**Pool widget layouts** (`PoolMonitor.layout` in `widgets/pool.py`) — `layout = "ticker"` (default) cycles single-row `SegmentMessage` screens with a trend arrow on today. `layout = "two_row"` cycles five `TwoRowMessage` screens (title + today + 7-day + season HI + season LO) with a label-on-top / big-number-on-bottom split. The season screen INTENTIONALLY splits into HI and LO under two_row — they each get a dedicated row pair. Trend arrow is INTENTIONALLY dropped in two_row mode (the bottom row is the value only). `feed_title` and `feed_stories` are annotated `SegmentMessage | TwoRowMessage` to cover both layouts; Container Protocol conformance applies in both modes. Per-row fonts (`top_font` / `top_font_size` / etc.) thread through the dispatch layer (`app/factories.py:_DISPATCH_APPLICABLE_TYPES` widens these from `{"two_row"}` to `{"two_row", "pool"}`) — never invent shadow field names on PoolMonitor. Setting per-row knobs while `layout = "ticker"` raises at config-load time (validation rejects dead-knob configs). Tripwires: `tests/test_widgets/test_pool.py::TestTwoRowLayout` (~17 tests) + `tests/test_validate.py::TestPoolLayoutValidation` (6 tests).
```

- [ ] **Step 2: Verify the docs site builds**

Run: `cd docs/site && pnpm install --silent && pnpm run build 2>&1 | tail -5` (only if docs lint hook expects this; otherwise skip)
Expected: build succeeds.

Skip this step if the docs site is not being touched in this branch.

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "$(cat <<'EOF'
docs: document pool widget layout switch invariant

Locks in the layout="ticker" | "two_row" contract, the per-row
font dispatch flow, the season-screen split rule, and the
deliberate-trend-arrow-drop semantic — so future edits don't
silently regress the two_row layout into producing SegmentMessage
again or re-inventing shadow field names.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 13: Final verification + PR

End-to-end sanity check.

**Files:** None (verification only)

- [ ] **Step 1: Full test suite**

Run: `make test`
Expected: 2279+ pass, no skips beyond the existing 2.

- [ ] **Step 2: Lint + format**

Run: `make lint && make format`
Expected: clean. If format reformatted unrelated files, revert those with `git checkout -- <file>` (per the user's standing rule about not bundling format drift).

- [ ] **Step 3: Pyright on touched files**

Run: `uv run pyright src/led_ticker/widgets/pool.py src/led_ticker/app/factories.py`
Expected: 0 errors.

- [ ] **Step 4: Validate all pool configs**

Run:
```bash
make validate CONFIG=config/config.pool_bigsign.toml
make validate CONFIG=config/config.pool_longboi.toml
make validate CONFIG=config/config.pool_smallsign.toml
make validate CONFIG=config/config.example.toml
```
Expected: all "No issues found."

- [ ] **Step 5: Push the branch**

```bash
git push -u origin <current-branch-name>
```

- [ ] **Step 6: Open the PR (after user confirmation)**

```bash
gh pr create --title "feat: pool widget two_row layout + bigsign testing config" --body "$(cat <<'EOF'
## Summary

Adds `layout = "two_row"` to the pool widget. New rendering mode produces stacked label-on-top / big-number-on-bottom screens via the existing `TwoRowMessage` primitive. Mirrors MLB's `layout = "ticker" | "scoreboard"` pattern.

Five screens cycle in two_row mode: title → today → 7-day → season HI → season LO. Season splits into HI/LO so each headline value gets its own row pair. Trend arrow intentionally dropped (bottom row is the value only).

Spec: `docs/superpowers/specs/2026-05-28-pool-two-row-layout-design.md`
Plan: `docs/superpowers/plans/2026-05-28-pool-two-row-layout.md`

## Test Plan

- [x] 18+ behavioral / validation / tripwire tests pass.
- [x] `make lint` clean, `pyright` 0 errors.
- [x] All pool configs (`pool_bigsign`, `pool_longboi`, `pool_smallsign`, `example`) validate clean.
- [x] Full suite: 2279+ passed, 2 skipped.
- [ ] Hardware verification on bigsign: deploy `config.pool_bigsign.toml` and confirm the five-screen cycle renders with cyan labels and per-screen bottom colors.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Self-Review

**Spec coverage check:**

- ✅ Layout enum (`ticker` / `two_row`) — Task 1 (field), Task 6 (validation).
- ✅ Per-screen content map (5 screens) — Task 3.
- ✅ Color application per screen — Task 3.
- ✅ Stale today handling — Task 3.
- ✅ Trend arrow dropped — Task 3 (test `test_no_trend_arrow_in_today_screen`).
- ✅ Per-row runtime fields — Task 2.
- ✅ Dispatch table widening — Task 5.
- ✅ Dead-knob validation — Task 7.
- ✅ Placeholder two-row variant — Task 4.
- ✅ Type widening on feed_title/feed_stories — Task 3 Step 5.
- ✅ Field hints — Task 8.
- ✅ Bigsign testing config — Task 9.
- ✅ Re-render existing pool demo + add two_row demo gif — Task 10.
- ✅ User-facing docs (pool.mdx, pool.md, config.example.toml hint) — Task 11.
- ✅ CLAUDE.md invariant — Task 12.

**Placeholder scan:** None. Every step has actual code or an actual command.

**Type consistency:** All references to `_build_two_row_screens`, `_build_ticker_screens`, `layout`, `top_font`, `bottom_font`, `top_row_height`, `label_color` use the same names across Tasks 1, 2, 3, 4, 5, 6, 7. `TwoRowMessage` constructor kwargs (`top_text`, `bottom_text`, `top_color`, `bottom_color`, `top_font`, `bottom_font`, `top_row_height`) are spelled identically wherever referenced.

**Task ordering check:** Task 5 (dispatch widen) before Task 6 (layout-enum validation) and Task 7 (dead-knob validation) — correct because validation tests need the dispatch-time fields to be acceptable on pool widgets first. Task 4 (placeholder) after Task 3 (real screens) — correct because they share the TwoRowMessage construction pattern.
