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
    last = None
    def apply():
        nonlocal last
        try:
            o = override() if override is not None else None
            level = o if o is not None else scheduler.brightness_for(
                datetime.now(tz), base
            )
        except Exception:
            logging.exception("schedule: brightness compute failed; holding")
            return                      # transient: keep last value, keep ticking
        led_frame.matrix.brightness = level
        if level != last:              # log only on CHANGE, not every 30s tick
            logging.info("schedule: brightness -> %d", level)
            last = level
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

`_supervised_schedule` wraps `_schedule_ticker` in try/except that logs and
returns (a scheduler crash must NEVER freeze the panel — same contract as
`_serve_busy_supervised`). **Crash-safety (perf review):** brightness is *sticky*
hardware state — if the ticker died mid-dark-window the panel would stay dark until
restart (indistinguishable from a freeze to the owner). So on a fatal exit the
supervised wrapper resets `led_frame.matrix.brightness = base` and logs at WARNING
before returning, degrading a dead scheduler to "always base brightness" (matching
the documented outside-all-windows fallback). The per-tick `apply()` also catches
its own transient exceptions and keeps ticking (above), so one bad sample can't end
the ticker. `base` = the configured `[display] brightness` — and MUST be the same
value passed to `LedFrame(led_brightness=...)`, so "no window matches" snaps to the
startup brightness, not the frame default; a test asserts this.

The 30 s cadence means a transition lands within 30 s of a window boundary (fine
for a day/night schedule); no per-frame cost — `datetime.now(tz)` + the linear
`brightness_for` scan run 2×/min, nowhere near the swap path. Setting
`matrix.brightness` from this coroutine is safe: the assignment is a single atomic
attribute write with no intervening `await`, and the C `SwapOnVSync` reads
brightness on the next vsync — there is no other thread and no multi-field tear.
The brightness change is a single vsync-aligned **step** (no ramp) — intentional;
a slow fade on a sign nobody's watching at 23:00 is needless per-frame complexity.

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
- Overlap is allowed (last-wins). A window that is **fully shadowed** (can never be
  the effective window because a later same-days window completely covers it) → a
  **warning** (it's dead config), surfaced for free since the summary below already
  resolves effective brightness.

**Resolved-schedule summary (product review — highest-leverage):** `led-ticker
validate` prints a human-readable resolution of the schedule so every silent rule
(wrap-past-midnight, last-wins, base fallback, `days`) becomes eyeball-able on a
sign with no console. Example:

```
display schedule (America/New_York), base 60%:
  every day   07:00–18:00 → 100%
  every day   18:00–23:00 →  40%
  every day   23:00–07:00 (overnight) →   0%  (dark)
  otherwise → 60% (base)
```

It annotates wrapped windows as "(overnight)", shows the base fallback explicitly,
and lists `days` per window. This single output answers "what brightness at a time
no window covers?" and "did my window wrap?" — the two most likely confusions.

## Docs

- Extend `docs/site/src/content/docs/concepts/display.mdx` with a "Scheduling"
  section. It must state plainly (product review):
  - **"Off" = the LEDs go dark; the Pi keeps running and rendering — this is NOT a
    sleep/power-save mode.** But the LEDs are the power hogs, so `brightness=0` does
    save the bulk of *panel* wattage; the Pi's own CPU/refresh load is unchanged.
  - **Timezone default is the Pi's system time** — fresh headless Pis are often on
    UTC, so set `timezone` explicitly or windows will be hours off (same foot-gun
    the clock widget documents).
  - Boundaries can land up to ~30 s late (the poll cadence); brightness changes are
    a single step, not a fade.
  - the windows model, `brightness=0`=off, wrap-past-midnight, `days`, last-wins.
  - **A schedule takes effect only at startup** — there is no live config reload
    yet (adoption #7), so flipping `enabled` or editing windows needs a restart.
- Add the `[display.schedule]` fields to
  `docs/site/src/content/docs/reference/config-options.mdx`. **`tests/test_docs_config_options_drift.py`
  audits that page against the config dataclasses — update it in lockstep so the
  drift test passes.**
- Add a **commented-out** full three-window day/evening/night `[display.schedule]`
  example to BOTH shipped example configs (smallsign + bigsign) — copy-paste from
  the shipped config is the primary discoverability path. Annotate `brightness = 0
  # dark — panel off overnight` so the `0` doesn't read as a placeholder.

## Known interactions / limitations

- **busy-light & plugin overlays** paint in `swap()`; `brightness` is a global
  hardware PWM scale, so the busy dot dims/darkens with the panel — consistent,
  documented.
- **Live preview** (`_preview_tee`) mirrors *canvas pixels*, not hardware PWM
  brightness, so the preview shows full-brightness content even when the panel is
  dimmed/off — documented limitation.
- **web-status** does not yet show "off/dimmed (scheduled)" — a dark panel reads as
  "running" (worse than the busy-dot case: the *whole* panel is dark). Full
  indicator is a fast-follow (status-schema bump). MITIGATION shipped here: the
  ticker logs `schedule: brightness -> N` on every change, so the diagnostic trail
  exists, and the docs pre-empt the "is my sign broken?" question. The web-status
  field is the fast-follow.
- **Overnight render cost:** `brightness=0` darkens the LEDs (≈0 panel current) but
  the Pi keeps rendering at full 20 fps cadence — CPU/refresh load is unchanged all
  night. Accepted for v1; a render-loop pause for power saving is deferred (Future
  work).

## Future work (designed-for, not built)

- **External brightness override (webhook/HTTP push).** The `_schedule_ticker`'s
  `override` parameter is the seam: a future supervised HTTP listener — mirroring
  `busy_http.serve_busy` (never freezes the panel on bind failure) + `BusyLight`'s
  `ttl_seconds` auto-clear — would hold a pushed brightness override and expose a
  `current() -> int | None` provider passed as `override=`. When set it wins over
  the schedule; on TTL expiry it clears and the schedule resumes. No ticker rework
  needed. (Tracked separately.)
- **web-status scheduled-state indicator** (above) — a `scheduled` brightness
  field in the status JSON (schema bump) so the UI can show "off/dimmed
  (scheduled)" instead of a bare "running".
- **Render-loop pause during off windows** (perf review) — pause/clear the engine
  during a `brightness=0` window to cut overnight CPU/refresh, with clean resume.
  More invasive (touches the engine loop, constraints #1/#12); deferred until the
  power saving is wanted.

## Testing

- `schedule.py` unit tests (pure): in-window → its brightness; outside → base;
  non-wrap boundaries (start inclusive, end exclusive); midnight wrap (both
  halves); `days` filter; **wrap + days "owned by start day"** (Fri 23:00→Sat
  07:00 active, Sat 23:00 not when days=[fri]); overlap last-wins; `from_config`
  parsing; tz-aware `now` (a DST-transition day still resolves via `datetime.now(tz)`).
- `_schedule_ticker` test: sets `led_frame.matrix.brightness` from the schedule
  (stub matrix attribute), applies immediately at startup, the `override` provider
  (when supplied) wins — proving the forward-looking seam — and logs only on a
  brightness CHANGE (not every tick). Crash-safety: a `brightness_for` that raises
  is caught and the ticker keeps the last value + keeps ticking; the supervised
  wrapper, on a fatal exit, resets `matrix.brightness = base`.
- **`base` consistency test** (perf review): the value passed to the scheduler as
  `base` is the same `config.display.brightness` fed to `LedFrame(led_brightness=)`,
  so "no window matches" resolves to the startup brightness, not the frame default.
- `config.py` load test (`[[display.schedule.windows]]` → objects) +
  `validate.py` tests (bad tz, bad HH:MM, brightness out of range, bad day,
  enabled-empty warning, start==end, fully-shadowed-window warning) + the
  resolved-schedule summary output (wrap annotated, base shown, days listed).
- `test_docs_config_options_drift.py` stays green with the new fields documented.

## Non-goals

- Pausing/clearing the render loop during off windows (CPU saving) — brightness-0
  only.
- Cron expressions / arbitrary recurrence — windows + `days` only.
- Building the webhook override or the web-status indicator (future work above).
- Per-widget or per-section brightness — this is a whole-panel hardware setting.
