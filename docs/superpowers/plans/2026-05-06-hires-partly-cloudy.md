# Add hires `partly_cloudy` weather icon + tripwire

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans for this short focused fix.

**Goal:** Make the weather widget render a crisp 32×32 icon for *every* condition `_match_condition` can return, not just 6 of the 7. Today, "Partly cloudy" Brooklyn weather falls back to the blocky 8×8 lowres sprite even on bigsign.

**Background:** `_match_condition(condition)` returns one of `{thunder, snow, rain, fog, partly_cloudy, cloud, sun}`. Six are in `HIRES_REGISTRY`; `partly_cloudy` is in lowres only (`pixel_emoji.py:2436`). When `WeatherWidget.draw` calls `draw_emoji_at(canvas, slug, ...)`, the dispatch in `pixel_emoji.py:2745` checks `slug in HIRES_REGISTRY` — for `partly_cloudy` that's False, so the lowres sprite renders even on a `ScaledCanvas`. Visible on hardware as a blocky icon next to crisp hires text and crisp hires neighbors.

The recent PR (`ee54a44`) added `partly_cloudy` to lowres but didn't add a hires variant or a tripwire to require one — this plan closes both gaps.

**Branch:** Continue on `main`. Personal repo, direct-to-main authorized.

---

## Audit findings

```
slug               | lowres | hires | size
partly_cloudy      | YES    | NO    | -      ← only gap
sun, cloud, rain,  | YES    | YES   | 32x32
snow, thunder, fog | YES    | YES   | 32x32
```

Width parity verified: every weather slug's lowres footprint is 8 logical, and every existing hires variant is 8 logical at scale=4 (`physical_width` defaults to `physical_size = 32`). New hires `partly_cloudy` should match this so layout doesn't shift between conditions.

`measure_emoji_at` ↔ `draw_emoji_at` already kept in sync by `TestMeasureEmojiAtMatchesDrawEmojiAt` — the new sprite plugs into both for free, no widget code changes.

---

## Task 1: Add `PARTLY_CLOUDY_HIRES` sprite + register

**Files:**
- Modify: `src/led_ticker/pixel_emoji.py` — define `PARTLY_CLOUDY_HIRES` near the other weather hires sprites (search for `CLOUD_HIRES` / `SUN_HIRES` / `RAIN_HIRES`), add `"partly_cloudy": PARTLY_CLOUDY_HIRES` to `HIRES_REGISTRY` (around line 2476-2480 where the other weather entries live).

**Approach (programmatic composition, not hand-painted):** the lowres `PARTLY_CLOUDY` is a cloud with a sun peeking out the top-right. Compose hires by:
1. Take `SUN_HIRES`, scale-crop to a smaller variant in the top-right quadrant (sun anchored ~rows 0–18, cols ~14–31).
2. Take `CLOUD_HIRES`, anchor to bottom-front (rows ~10–28, full width).
3. Where they overlap, the cloud's pixels win (cloud is "in front of" the sun visually).
4. Wrap as `HiResEmoji(physical_size=32, physical_width=None, pixels=...)` matching the existing pattern.

If the procedural composition looks bad, fall back to hand-painting a 32×32 sprite — roughly the same effort as `_generate_moon_hires` (~20–40 lit pixels by inspection of the lowres design).

**Steps:**

- [ ] **Step 1: Read existing hires sprite patterns**

```bash
grep -n "_HIRES: HiResEmoji\|_HIRES = HiResEmoji" src/led_ticker/pixel_emoji.py | head -10
```

Pick `CLOUD_HIRES` as the closest reference (similar subject, clean cloud silhouette).

- [ ] **Step 2: Write the generator function**

In `pixel_emoji.py` (alongside `_generate_moon_hires` which exists per CLAUDE.md):

```python
def _generate_partly_cloudy_hires() -> list[tuple[int, int, int, int, int]]:
    """Compose hires partly_cloudy from SUN_HIRES (top-right) +
    CLOUD_HIRES (bottom-front). Cloud pixels mask the sun where they
    overlap so the cloud reads as in front of the sun, matching the
    lowres design (PARTLY_CLOUDY in weather_icons.py).
    """
    pixels: dict[tuple[int, int], tuple[int, int, int]] = {}

    # Sun: shrink to ~14x14 anchored top-right (cols 16-31, rows 0-15).
    # Sample SUN_HIRES at half-resolution into the top-right quadrant.
    for x, y, r, g, b in SUN_HIRES.pixels:
        sx, sy = x // 2 + 16, y // 2
        if 16 <= sx < 32 and 0 <= sy < 16:
            pixels[(sx, sy)] = (r, g, b)

    # Cloud: full-size, anchored bottom-front (rows 10-31).
    for x, y, r, g, b in CLOUD_HIRES.pixels:
        cy = y + 4  # shift down 4 rows so cloud sits on bottom edge
        if 0 <= cy < 32:
            pixels[(x, cy)] = (r, g, b)  # cloud overwrites sun on overlap

    return [(x, y, r, g, b) for (x, y), (r, g, b) in pixels.items()]


PARTLY_CLOUDY_HIRES: HiResEmoji = HiResEmoji(
    physical_size=32,
    physical_width=None,
    pixels=_generate_partly_cloudy_hires(),
)
```

- [ ] **Step 3: Register in `HIRES_REGISTRY`**

```python
HIRES_REGISTRY: dict[str, HiResEmoji] = {
    # ... existing entries ...
    # Weather
    "cloud": CLOUD_HIRES,
    "rain": RAIN_HIRES,
    "snow": SNOW_HIRES,
    "thunder": THUNDER_HIRES,
    "fog": FOG_HIRES,
    "partly_cloudy": PARTLY_CLOUDY_HIRES,  # NEW
    # ... rest ...
}
```

- [ ] **Step 4: Sanity-render to PNG**

Per the user's pixel-art iteration workflow (memory note): render the sprite to `/tmp/partly_cloudy_hires.png` at 4× zoom and `Read` it before committing. Adjust if the composition looks broken (sun too small / cloud crops weirdly / colors clash).

```python
# Quick render snippet for /tmp script:
from PIL import Image
img = Image.new("RGB", (32*4, 32*4), (0, 0, 0))
for x, y, r, g, b in PARTLY_CLOUDY_HIRES.pixels:
    for dy in range(4):
        for dx in range(4):
            img.putpixel((x*4+dx, y*4+dy), (r, g, b))
img.save("/tmp/partly_cloudy_hires.png")
```

- [ ] **Step 5: Commit (only if visual passes)**

```bash
git commit -m "pixel_emoji: add hires partly_cloudy weather sprite"
```

---

## Task 2: Add the meta-tripwire

A test that asserts every slug `_match_condition` can return is in BOTH lowres and hires registries. Catches the next time someone adds a weather slug to lowres without remembering to add hires.

**Files:**
- Test: `tests/test_widgets/test_weather.py` (extend existing test class) OR `tests/test_pixel_emoji.py` (new class). Prefer test_weather.py since the test is about the weather widget's rendering contract.

**Steps:**

- [ ] **Step 1: Write the test**

```python
class TestWeatherSlugCoverage:
    """Tripwire: every slug `_match_condition` can return must have
    BOTH a lowres entry (so the small sign / non-ScaledCanvas path
    works) AND a hires entry (so bigsign renders crisply). A new
    slug added to either registry without the other slips through —
    weather conditions branch silently between crisp and blocky on
    different hardware."""

    def test_every_match_condition_slug_has_lowres_and_hires(self):
        from led_ticker.pixel_emoji import HIRES_REGISTRY, _get_registry
        from led_ticker.widgets.weather_icons import _match_condition

        # Probe every branch in _match_condition.
        probe_inputs = [
            "Thunderstorm",
            "Snow", "Blizzard", "Sleet", "Ice pellets",
            "Rain", "Drizzle", "Showers",
            "Fog", "Mist",
            "Partly cloudy",
            "Cloudy", "Overcast",
            "Sunny", "Clear",  # default branch
            "Banana",  # falls through to default ("sun")
        ]
        slugs = sorted({_match_condition(c) for c in probe_inputs})

        lowres = _get_registry()
        missing_lowres = [s for s in slugs if s not in lowres]
        missing_hires = [s for s in slugs if s not in HIRES_REGISTRY]

        assert not missing_lowres, (
            f"Slugs from _match_condition missing from lowres "
            f"_get_registry(): {missing_lowres}. The widget would "
            f"raise KeyError on these conditions."
        )
        assert not missing_hires, (
            f"Slugs from _match_condition missing from HIRES_REGISTRY: "
            f"{missing_hires}. The widget would render the lowres 8x8 "
            f"sprite on bigsign for these conditions — blocky and "
            f"inconsistent with neighboring hires elements."
        )
```

- [ ] **Step 2: Run the test — must pass after Task 1's sprite is added**

```bash
PYTHONPATH=tests/stubs uv run pytest \
  tests/test_widgets/test_weather.py::TestWeatherSlugCoverage -v
```

If it fails with `partly_cloudy` missing, Task 1 wasn't completed correctly. Otherwise green.

- [ ] **Step 3: Commit**

```bash
git commit -m "tests: tripwire — every _match_condition slug must have lowres + hires"
```

---

## Order of operations

1. Task 1 (sprite + render-to-PNG sanity check)
2. Task 2 (tripwire — depends on Task 1's sprite being in place)

Both can land in a single commit if the visual passes on first try.

---

## What's deferred

- **Hand-painting `partly_cloudy` from scratch** — only if the procedural composition looks broken. Hand-painted would have more control over the exact "sun peeking out" framing but ~3× more effort.
- **Auditing other widgets that use `draw_emoji_at`** — currently only `WeatherWidget`. CLAUDE.md mentions a "future MLB rework" might use it; not relevant today.
- **Substring-order bug in `_match_condition`** — `"Partly sunny"` returns `partly_cloudy` because the "partly" check is broader than the "cloud"/"sunny" checks. Logic bug, not hires-related; out of scope.
- **`_match_condition` default fall-through to `"sun"`** — unknown weather conditions render as sun (e.g., "Hazy"). Could be more granular but not a hires bug.
