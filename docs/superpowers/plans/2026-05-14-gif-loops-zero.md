# `gif_loops = 0` Implementation Plan

> Every subagent MUST run `git branch --show-current` first. Expected: `worktree-gif-loops-zero`.

**Goal:** Repurpose `gif_loops = 0` to mean "play through section's `hold_time`". Engine threads `hold_time` to `widget.play()`; GifPlayer computes effective loop count when `gif_loops = 0` and `hold_time` is provided.

**Spec:** `docs/superpowers/specs/2026-05-14-gif-loops-zero-design.md`

**Working directory:** `/Users/james/projects/github/jamesawesome/led-ticker/.claude/worktrees/gif-loops-zero/`

---

### Task 1: Allow `gif_loops = 0` in `__attrs_post_init__`

**File:** `src/led_ticker/widgets/gif.py`

Find:
```python
if self.gif_loops < 1:
    raise ValueError(f"gif_loops must be >= 1, got {self.gif_loops!r}")
```

Replace:
```python
if self.gif_loops < 0:
    raise ValueError(f"gif_loops must be >= 0, got {self.gif_loops!r}")
```

**Test (in `tests/test_widgets/test_gif.py`):**

```python
def test_gif_loops_zero_is_valid_post_init():
    """gif_loops=0 is now valid — means 'play through hold_time'."""
    widget = GifPlayer(path="x.gif", gif_loops=0)
    assert widget.gif_loops == 0


def test_gif_loops_negative_still_raises():
    """Boundary preserved: < 0 is still rejected."""
    with pytest.raises(ValueError, match="gif_loops must be >= 0"):
        GifPlayer(path="x.gif", gif_loops=-1)
```

Commit: `gif: allow gif_loops = 0 (post-init only, semantics in next commit)`

---

### Task 2: Add `hold_time` kwarg to `GifPlayer.play()` + branch on loop_count=0

**File:** `src/led_ticker/widgets/gif.py`

Modify `play()` signature:
```python
async def play(
    self,
    real_canvas: Canvas,
    frame: Any,
    loop_count: int = 1,
    *,
    hold_time: float | None = None,
) -> Canvas:
```

At the top of `play()` (after `self._load(...)` and the empty-frames early return, before `if not self._has_text_content()`), add:

```python
# gif_loops = 0 means "play loops that fit in section hold_time".
# When hold_time is provided, compute the effective loop count; when
# it isn't (e.g. forever_scroll context, or no section caller), fall
# back to 1 loop. Minimum 1 either way.
if loop_count == 0:
    if hold_time is not None and self._loop_ms > 0:
        loop_count = max(1, int(hold_time * 1000 / self._loop_ms))
    else:
        loop_count = 1
```

Note: `self._loop_ms` is set in `_load()`; do this AFTER `_load` runs but BEFORE the existing `loops = max(1, loop_count)` lines (so they remain correct).

**Tests:**

```python
async def test_gif_loops_zero_with_hold_time_computes_loops():
    """8s / 1000ms-per-loop = 8 loops."""
    widget = GifPlayer(path="x.gif", gif_loops=0)
    widget._frames = [(mock.Mock(), 250), (mock.Mock(), 250), (mock.Mock(), 250), (mock.Mock(), 250)]
    widget._loop_ms = 1000  # 4 frames × 250ms
    widget._has_text_content = lambda: False  # take the no-text path

    # Patch _play_no_text to capture loop_count it receives, return
    canvas = mock.Mock()
    frame = mock.Mock()
    captured = {}
    async def fake(rc, f, lc):
        captured["loops"] = lc
        return canvas

    with mock.patch.object(widget, "_play_no_text", fake):
        with mock.patch.object(widget, "_load"):
            await widget.play(canvas, frame, loop_count=0, hold_time=8.0)

    assert captured["loops"] == 8


async def test_gif_loops_zero_short_hold_time_minimum_one():
    """0.5s / 1000ms-per-loop floor of 0.5 → max(1, 0) = 1."""
    widget = GifPlayer(path="x.gif", gif_loops=0)
    widget._frames = [(mock.Mock(), 1000)]
    widget._loop_ms = 1000
    widget._has_text_content = lambda: False

    captured = {}
    async def fake(rc, f, lc):
        captured["loops"] = lc
        return rc

    with mock.patch.object(widget, "_play_no_text", fake):
        with mock.patch.object(widget, "_load"):
            await widget.play(mock.Mock(), mock.Mock(), loop_count=0, hold_time=0.5)

    assert captured["loops"] == 1


async def test_gif_loops_zero_no_hold_time_defaults_one():
    """No hold_time provided → minimum 1 loop."""
    widget = GifPlayer(path="x.gif", gif_loops=0)
    widget._frames = [(mock.Mock(), 1000)]
    widget._loop_ms = 1000
    widget._has_text_content = lambda: False

    captured = {}
    async def fake(rc, f, lc):
        captured["loops"] = lc
        return rc

    with mock.patch.object(widget, "_play_no_text", fake):
        with mock.patch.object(widget, "_load"):
            await widget.play(mock.Mock(), mock.Mock(), loop_count=0)

    assert captured["loops"] == 1


async def test_gif_loops_positive_unchanged_with_hold_time():
    """gif_loops = 5 + hold_time = 8.0 → 5 loops (no truncation)."""
    widget = GifPlayer(path="x.gif", gif_loops=5)
    widget._frames = [(mock.Mock(), 1000)]
    widget._loop_ms = 1000
    widget._has_text_content = lambda: False

    captured = {}
    async def fake(rc, f, lc):
        captured["loops"] = lc
        return rc

    with mock.patch.object(widget, "_play_no_text", fake):
        with mock.patch.object(widget, "_load"):
            await widget.play(mock.Mock(), mock.Mock(), loop_count=5, hold_time=8.0)

    assert captured["loops"] == 5
```

Commit: `gif: gif_loops=0 + hold_time → play through section duration`

---

### Task 3: Add `hold_time` kwarg to `StillImage.play()` (ignored)

**File:** `src/led_ticker/widgets/still.py`

Modify `play()` signature to accept `hold_time` kwarg. Don't use it — StillImage's `hold_seconds` is its own duration knob. Just preserves protocol compatibility so `_play_widget` can pass `hold_time` uniformly.

Find the current signature, add `hold_time: float | None = None` as a kw-only parameter (and a comment explaining why it's accepted but unused).

**Test:** none needed — protocol passthrough only.

Commit: `still: accept hold_time kwarg on play() for protocol uniformity`

---

### Task 4: Thread `hold_time` through `_play_widget` and `_show_one`

**File:** `src/led_ticker/ticker.py`

Find `_play_widget` (around line 791). Current signature:
```python
async def _play_widget(canvas: Any, frame: Any, widget: Any) -> Any:
```

Change to:
```python
async def _play_widget(canvas: Any, frame: Any, widget: Any, *, section_hold_time: float = 3.0) -> Any:
```

In the function body where it calls `widget.play(...)`, add `hold_time=section_hold_time` to the kwargs:

```python
new_real = await widget.play(innermost.real, frame, loop_count=loops, hold_time=section_hold_time)
```

(There are two `widget.play` calls — one inside `isinstance(canvas, ScaledCanvas)` branch, one outside. Update both.)

Find `_show_one` and its call to `_play_widget`. `_show_one` already has access to `hold_time` (it's an existing parameter). Pass it through:

```python
canvas = await _play_widget(canvas, frame, widget, section_hold_time=hold_time)
```

**Test:**

```python
async def test_play_widget_passes_hold_time_to_gif():
    """_play_widget threads section_hold_time → widget.play(hold_time=...)."""
    widget = mock.AsyncMock()
    widget.play = mock.AsyncMock(return_value=mock.Mock())
    # Avoid ScaledCanvas branch by passing a non-ScaledCanvas
    plain_canvas = mock.Mock(spec=[])  # no .real or .scale attrs

    await _play_widget(plain_canvas, mock.Mock(), widget, section_hold_time=8.0)

    # Pull the call's kwargs
    call_kwargs = widget.play.call_args.kwargs
    assert call_kwargs.get("hold_time") == 8.0
```

Commit: `ticker: thread section.hold_time through _play_widget → widget.play()`

---

### Task 5: Docs

**File:** `docs/site/content-source/widgets/gif.md`

Find the `gif_loops` row in the OptionsTable source. Update description to mention both modes:

> | `gif_loops` | int | `1` | Number of times the gif plays per visit. Set to `0` to play through the section's `hold_time` (the recommended idiom for "show this gif for the section's duration"). Negative values are rejected. |

**File:** `docs/site/src/content/docs/widgets/gif.mdx`

Find the section that discusses timing. Add a new heading:

```markdown
### Playing through `hold_time`: `gif_loops = 0`

When you want a gif to fill its section's duration (rather than playing
a fixed number of times), set `gif_loops = 0`. The engine computes how
many complete loops fit in `hold_time` and plays at least one even if
the time budget is shorter than the gif's own duration. Replaces the
older `gif_loops = 999` magic-number idiom.

`gif_loops` ≥ 1 still works exactly as before — it plays the exact
count regardless of `hold_time`.
```

Place near the existing `gif_loops` discussion.

**File:** `docs/site/src/content/docs/concepts/sections-and-modes.mdx`

If the page has timing prose, add a note near the gif/still discussion: "For gifs, `gif_loops = 0` plays through `hold_time`."

Commit: `docs: gif_loops = 0 plays through hold_time`

---

### Task 6: Migrate example configs

Sweep `config/` and `docs/site/demos-*/` for `gif_loops = 999` (and variants like 100+). For each occurrence:
- If it's clearly the "play through hold_time" idiom, replace with `gif_loops = 0`
- If it's genuinely "I want exactly N loops" (rare), leave alone
- Note moonbunny config has 2 instances; both are the magic-number idiom

```bash
grep -rln "gif_loops = 999" config/ docs/site/demos-*/
```

For each file, make the edit + add a brief comment removal if there was a "this number is big because" comment.

Validate each modified file with `make validate CONFIG=path/to.toml` (or `uv run led-ticker validate ...`) — should still pass.

Commit: `examples: migrate gif_loops = 999 magic number to gif_loops = 0`

---

### Task 7: Final verification + PR

```bash
make test
make lint
uv run pyright src/
make docs-lint
```

All must pass. Test count delta: +6 tests minimum (4 GifPlayer.play branches, 1 engine thread-through, 1 post-init=0 valid).

Push + `gh pr create`:
- Title: `gif: gif_loops = 0 plays through section hold_time`
- Body: reference config-surface review (PM #4 finding), explain the magic-number anti-pattern this replaces, summarize the engine plumbing, note StillImage is unchanged.
