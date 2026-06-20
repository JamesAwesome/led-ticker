# Display scheduling — on/off + dim windows (adoption item #5)

**Date:** 2026-06-20
**Status:** approved (design), pre-implementation
**Goal:** Let a user schedule panel brightness by time of day — bright daytime, dim
evening, dark overnight — from TOML, applied live (no restart), without touching
the render loop.

## Background / why

From the LEDMatrix steal list (#5): "Display scheduling (on/off hours + dim
schedule) — config + brightness call in swap path." A sign owner wants the panel
bright during the day, dimmed in the evening, and dark overnight, on a daily
schedule, set once in config.

The rgbmatrix `RGBMatrix` object exposes a **runtime-settable `brightness`**
property (the test stub has it too: `tests/stubs/rgbmatrix/__init__.py` sets
`self.brightness = 100`); assigning it takes effect on the next `SwapOnVSync`. No
re-init needed. There is no existing runtime brightness consumer and no global
timezone (the clock widget carries its own via `zoneinfo`).

## Decisions (from brainstorming)

1. **Unified brightness windows** — a list of `start`/`end`/`brightness` windows;
   `brightness = 0` means off/dark. Not separate on/off + dim knobs.
2. **Off = dark, keep rendering** — set `matrix.brightness = 0`; the engine loop is
   untouched (no pause/clear). Lowest-risk; brightness applies on the next swap.
3. **Windows + optional per-window `days`** — `days = ["mon", ...]`; absent = every
   day. State-shaped, no new dependency. (Cron was considered and declined — it's
   event-shaped and would add a dependency.)
4. **Override-ready seam (forward-looking; NOT built now)** — the brightness
   written to the panel resolves at a single point that accepts an optional
   override provider, so a future webhook/HTTP push can win over the schedule with
   no rework. See "Future work".

## Config schema (`config.py`)

`DisplayConfig` gains `schedule: ScheduleConfig` (default disabled).

```python
@dataclass
class ScheduleWindow:
    start: str            # "HH:MM" 24-hour, local wall-clock
    end: str              # "HH:MM"; start > end wraps past midnight
    brightness: int       # 0–100; 0 = off/dark
    days: list[str] = field(default_factory=list)  # mon..sun; empty = every day

@dataclass
class ScheduleConfig:
    enabled: bool = False
    timezone: str = ""    # IANA (zoneinfo); empty = system local time
    windows: list[ScheduleWindow] = field(default_factory=list)
```

TOML shape:

```toml
[display.schedule]
enabled = true
timezone = "America/New_York"

[[display.schedule.windows]]
start = "07:00"
end = "18:00"
brightness = 100

[[display.schedule.windows]]
start = "18:00"
end = "23:00"
brightness = 40

[[display.schedule.windows]]
start = "23:00"   # wraps past midnight
end = "07:00"
brightness = 0    # dark overnight
```

Outside every active window, the base `[display] brightness` applies. The loader
parses `[[display.schedule.windows]]` into `ScheduleWindow` objects (`brightness`
is a plain int; `days` entries are lowercased on load).

## Scheduler (`src/led_ticker/schedule.py`, pure + testable)

A small module with no hardware/asyncio dependency.

```python
_DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")  # Mon=0 (datetime.weekday)

@attrs.define(frozen=True)
class _Window:
    start_min: int        # minutes since midnight
    end_min: int
    brightness: int
    days: frozenset[int]  # weekday ints; empty = every day

@attrs.define(frozen=True)
class Scheduler:
    windows: tuple[_Window, ...]

    @classmethod
    def from_config(cls, cfg: ScheduleConfig) -> "Scheduler": ...

    def brightness_for(self, now: datetime, base: int) -> int:
        """The scheduled brightness at `now` (a tz-aware or naive local datetime),
        or `base` if no window is active. Last matching window wins."""
```

**Matching rules:**
- Time is `now.hour * 60 + now.minute`. Boundaries: `start` inclusive, `end`
  exclusive.
- Non-wrap window (`start_min < end_min`): active when `start_min <= t < end_min`.
- Wrap window (`start_min > end_min`, e.g. 23:00–07:00): active when
  `t >= start_min` OR `t < end_min`.
- **`days` + wrap ("owned by start day"):** a window's `days` filter is checked
  against the day its *start* falls on. For a wrap window active in its
  post-midnight tail (`t < end_min`), the owning day is *yesterday*
  (`(now.weekday() - 1) % 7`). For the pre-midnight part (and all non-wrap
  windows) the owning day is `now.weekday()`. Empty `days` = always matches.
  So `start="23:00" end="07:00" days=["fri"]` is active Fri 23:00 → Sat 07:00.
- **Overlap:** iterate windows in config order; the **last** matching window wins
  (a later, more-specific window overrides an earlier general one).
- `start_min == end_min` is rejected at validation (ambiguous: empty or all-day).

## Application (`app/run.py`)

A supervised ticker mirroring `_ttl_ticker`:

```python
_SCHEDULE_TICK_SECONDS = 30.0

async def _schedule_ticker(
    led_frame, scheduler, tz, base, *,
    override=None,                      # forward-looking: Callable[[], int | None] | None
    interval=_SCHEDULE_TICK_SECONDS,
):
    def apply():
        o = override() if override is not None else None
        led_frame.matrix.brightness = o if o is not None else scheduler.brightness_for(
            datetime.now(tz), base
        )
    apply()                            # correct on frame 1 (like busy.update())
    while True:
        await asyncio.sleep(interval)
        apply()
```

Wiring in `run()` (right after the busy-light / overlay block, inside the `try`):

```python
if config.display.schedule.enabled:
    from led_ticker.schedule import Scheduler
    sched = Scheduler.from_config(config.display.schedule)
    tz = ZoneInfo(config.display.schedule.timezone) if config.display.schedule.timezone else None
    spawn_tracked(
        _supervised_schedule(led_frame, sched, tz, config.display.brightness)
    )
```

`_supervised_schedule` wraps `_schedule_ticker` in try/except that logs and returns
(a scheduler crash must NEVER freeze the panel — same contract as
`_serve_busy_supervised`). `base` = the configured `[display] brightness`.

The 30 s cadence means a transition lands within 30 s of a window boundary; no
per-frame cost. Setting `matrix.brightness` from this coroutine is safe — it and
the render loop are cooperative coroutines on one event loop, never concurrent.

## Validation (`validate.py`)

When `display.schedule.enabled`, surfaced at `led-ticker validate`:
- `timezone`: empty OK; else `ZoneInfo(tz)` in try/except `(ZoneInfoNotFoundError,
  ValueError)` → error "not a valid IANA timezone name"; non-string → error
  (mirror `clock.py`'s pattern).
- each window: `start`/`end` match `^\d{2}:\d{2}$` with hour 0–23, minute 0–59;
  `start != end`; `brightness` int 0–100 (bool excluded — it's an int subclass);
  `days` ⊆ `{mon..sun}` (case-insensitive).
- `enabled` with empty `windows` → **warning** (schedule is a no-op; base
  brightness always applies).
- Overlap is allowed (last-wins is documented, not an error).

## Docs

- Extend `docs/site/src/content/docs/concepts/display.mdx` with a "Scheduling"
  section (the windows model, `brightness=0`=off, wrap-past-midnight, `days`,
  timezone, last-wins).
- Add the `[display.schedule]` fields to
  `docs/site/src/content/docs/reference/config-options.mdx`. **`tests/test_docs_config_options_drift.py`
  audits that page against the config dataclasses — update it in lockstep so the
  drift test passes.**
- Add a `[display.schedule]` example block to the example config(s).

## Known interactions / limitations

- **busy-light & plugin overlays** paint in `swap()`; `brightness` is a global
  hardware PWM scale, so the busy dot dims/darkens with the panel — consistent,
  documented.
- **Live preview** (`_preview_tee`) mirrors *canvas pixels*, not hardware PWM
  brightness, so the preview shows full-brightness content even when the panel is
  dimmed/off — documented limitation.
- **web-status** does not yet show "off/dimmed (scheduled)" — a dark panel reads as
  "running". Captured as a fast-follow (status-schema bump), out of scope here.

## Future work (designed-for, not built)

- **External brightness override (webhook/HTTP push).** The `_schedule_ticker`'s
  `override` parameter is the seam: a future supervised HTTP listener — mirroring
  `busy_http.serve_busy` (never freezes the panel on bind failure) + `BusyLight`'s
  `ttl_seconds` auto-clear — would hold a pushed brightness override and expose a
  `current() -> int | None` provider passed as `override=`. When set it wins over
  the schedule; on TTL expiry it clears and the schedule resumes. No ticker rework
  needed. (Tracked separately.)
- **web-status scheduled-state indicator** (above).

## Testing

- `schedule.py` unit tests (pure): in-window → its brightness; outside → base;
  non-wrap boundaries (start inclusive, end exclusive); midnight wrap (both
  halves); `days` filter; **wrap + days "owned by start day"** (Fri 23:00→Sat
  07:00 active, Sat 23:00 not when days=[fri]); overlap last-wins; `from_config`
  parsing; tz-aware `now` (a DST-transition day still resolves via `datetime.now(tz)`).
- `_schedule_ticker` test: sets `led_frame.matrix.brightness` from the schedule
  (stub matrix attribute), applies immediately at startup, and the `override`
  provider (when supplied) wins — proving the forward-looking seam works.
- `config.py` load test (`[[display.schedule.windows]]` → objects) +
  `validate.py` tests (bad tz, bad HH:MM, brightness out of range, bad day,
  enabled-empty warning, start==end).
- `test_docs_config_options_drift.py` stays green with the new fields documented.

## Non-goals

- Pausing/clearing the render loop during off windows (CPU saving) — brightness-0
  only.
- Cron expressions / arbitrary recurrence — windows + `days` only.
- Building the webhook override or the web-status indicator (future work above).
- Per-widget or per-section brightness — this is a whole-panel hardware setting.
