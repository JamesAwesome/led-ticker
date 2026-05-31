# Transition FPS Design

## Goal

Add a `transition_fps` config field that lets users control how many animation
frames per second a transition renders. Currently hard-coded to 20 fps
(`scroll_speed = 0.05 s` in `run_transition`). On the longboi display, animated
transitions like `baseball_alternating` look choppy because the ball jumps
~14 physical pixels per frame at the default rate. Raising fps to 30–40
halves the per-frame jump and produces visibly smoother motion.

---

## Config Interface

`transition_fps` is a float field accepted wherever a transition is configured.
`None` (absent) means inherit the existing default (20 fps). Example:

```toml
# Global default — raises fps for every transition in the playlist
[transitions]
default = "push_left"
duration = 0.5
easing = "ease_out"
transition_fps = 40

# Between-section transition override
between_sections = {type = "nyancat_alternating", duration = 4.0, transition_fps = 30}

# Section-level — applies to both entry and widget-swap transitions for this section
[[playlist.section]]
transition = "baseball_alternating"
transition_duration = 2.0
transition_fps = 40          # NEW: overrides global default for this section

# Fine-grained: entry transition only
[playlist.section.entry_transition]
type = "baseball_alternating"
duration = 2.0
transition_fps = 40

# Fine-grained: widget-swap transition only
[playlist.section.widget_transition]
type = "baseball_alternating"
duration = 2.0
transition_fps = 40
```

Precedence mirrors the existing `duration`/`easing` precedence:

```
entry_transition.transition_fps
  > section.transition.transition_fps (when transition_specified)
    > between_sections.transition_fps
      > global default (20 fps)
```

Widget-swap transitions follow the same chain via `widget_transition` /
`section.transition` / global default.

---

## Data Model

### `TransitionConfig` (config.py)

Add one field:

```python
@dataclass
class TransitionConfig:
    type: str = "cut"
    duration: float = 0.5
    easing: str = "linear"
    color: tuple[int, int, int] | None = None
    colors: list[tuple[int, int, int]] | None = None
    show_pikachu: bool = True
    show_pokeball: bool = True
    transition_fps: float | None = None   # NEW — None inherits run_transition default
```

`None` is the only safe default — it means "use whatever `run_transition`
defaults to", which preserves backward compatibility for all existing configs.

### `_parse_transition` (config.py)

Add one extraction line in the `return TransitionConfig(...)` block:

```python
transition_fps=raw.get("transition_fps", default.transition_fps),
```

Also handle the inline dict form used by `between_sections`:

```toml
between_sections = {type = "baseball_alternating", duration = 2.0, transition_fps = 40}
```

This already works because `_parse_transition` receives the dict; no special case needed.

---

## `run_transition` — No Signature Change Needed

`run_transition` already accepts `scroll_speed: float = 0.05`. The callers
simply need to pass it when `transition_fps` is set:

```python
scroll_speed = (1.0 / cfg.transition_fps) if cfg.transition_fps is not None else 0.05
```

---

## Call Sites

### 1. Inter-section transitions — `app/run.py`

In the entry-transition selection block (currently lines 128–139), extract
`entry_fps` alongside `entry_duration`/`entry_easing`:

```python
if section.entry_transition is not None:
    entry_fps = section.entry_transition.transition_fps
elif section.transition_specified:
    entry_fps = section.transition.transition_fps
else:
    entry_fps = config.between_sections.transition_fps
```

Pass it to `run_transition`:

```python
canvas = await run_transition(
    ...,
    scroll_speed=(1.0 / entry_fps) if entry_fps is not None else 0.05,
)
```

### 2. Widget-swap transitions — `ticker.py`

`Ticker` stores `self.transition_config: TransitionConfig | None`. At the
`run_transition` call site (currently line 690):

```python
cfg = self.transition_config
canvas = await run_transition(
    ...,
    scroll_speed=(1.0 / cfg.transition_fps) if cfg.transition_fps is not None else 0.05,
)
```

---

## Validation

Add a validator rule (or inline check in `_parse_transition`):

- `transition_fps` must be a positive float: `transition_fps > 0`
- Clamp to a reasonable range: warn (not error) if `transition_fps < 5` or
  `transition_fps > 120`
  - Below 5 fps: likely unintentional; transitions will look like slideshows
  - Above 120 fps: exceeds what the Pi can push to the matrix; frames will
    pile up and the sleep budget goes negative

Add this as a new validate rule (rule 41 or next available). The rule fires on
`transition_fps` wherever it appears: `[transitions]`, `between_sections`,
section `transition`, `entry_transition`, `widget_transition`.

---

## `min_frames` Interaction

`run_transition` enforces `frame_count = max(int(duration / scroll_speed), transition.min_frames)`.
For `Baseball` and `BaseballReverse`, `min_frames = 40`.

With `transition_fps = 40` and `duration = 2.0`:
- `int(2.0 / 0.025) = 80 frames`
- `max(80, 40) = 80 frames` ✓

With `transition_fps = 10` and `duration = 2.0`:
- `int(2.0 / 0.1) = 20 frames`
- `max(20, 40) = 40 frames` — `min_frames` wins, effective fps becomes 20

This is correct behaviour: `min_frames` is a quality floor, not a ceiling.
The validator warning at `< 5 fps` covers the extreme case where the user
might be surprised by `min_frames` overriding their intent.

---

## longboi Config Change

Update the two MLB baseball sections in `config/config.longboi.toml`:

```toml
[[playlist.section]]
transition = "baseball_alternating"
transition_duration = 2.0
transition_fps = 40          # was: implicit 20 fps
```

40 fps → `scroll_speed = 0.025 s` → ball moves ~7 physical px/frame instead
of ~14. Should visibly reduce the choppiness.

---

## Files to Change

| File | Change |
|---|---|
| `src/led_ticker/config.py` | Add `transition_fps` to `TransitionConfig`; update `_parse_transition` |
| `src/led_ticker/app/run.py` | Extract `entry_fps`; pass `scroll_speed` to `run_transition` |
| `src/led_ticker/ticker.py` | Pass `scroll_speed` to `run_transition` in swap-mode branch |
| `src/led_ticker/validate.py` | Add rule for `transition_fps` range (warn < 5, warn > 120) |
| `config/config.longboi.toml` | Add `transition_fps = 40` to baseball sections |

---

## Testing

New tests in `tests/test_config.py` (or `test_transition_fps.py`):

1. `test_transition_fps_parsed_from_toml` — `transition_fps = 40` in a section
   produces `TransitionConfig(transition_fps=40.0)`.
2. `test_transition_fps_absent_defaults_none` — omitting the field gives `None`.
3. `test_transition_fps_inline_between_sections` — inline dict form
   `{type = "x", transition_fps = 30}` parses correctly.
4. `test_transition_fps_passed_to_run_transition` — mock `run_transition`;
   assert `scroll_speed=0.025` when `transition_fps=40`.
5. `test_transition_fps_none_uses_default` — `transition_fps=None` → caller
   passes `scroll_speed=0.05` (the existing default).

Validation rule test in `tests/test_validate.py`:

6. `test_transition_fps_below_5_warns` — `transition_fps = 2` triggers a warning.
7. `test_transition_fps_above_120_warns` — `transition_fps = 200` triggers a warning.
8. `test_transition_fps_valid_no_warning` — `transition_fps = 40` no warning.

---

## Out of Scope

- Per-transition-*type* fps defaults (e.g. baseball always uses 40 fps) — all
  transitions share the same `scroll_speed` in `run_transition`.
- Changing the baseball `min_frames` constant — it's a quality floor, not fps.
- Scroll-loop fps (section `scroll_step_ms`) — separate concept; controls
  cursor advance speed, not transition animation rate.
