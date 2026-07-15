# Colored value tokens (source-declared) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** A `:id:` value token renders in its own color (declared on the `[[source]]` via `color = <provider>`) while surrounding literal text keeps the widget's `font_color`. Phase 1 = `TickerMessage`.

**Architecture:** `DataSource.color` holds a `ColorProvider`; `TokenizedField.resolve_segments` returns typed spans; the message builds a per-visible-text-char color override and threads it through the existing per-char / whole-string / emoji draw paths. Geometry (width/scroll) is untouched.

**Tech Stack:** Python 3.14, attrs, pytest (headless).

## Global Constraints

- Never work on `main`; worktree `led-ticker--colored-tokens`, branch `feat/colored-value-tokens`. Verify `git branch --show-current` before editing.
- **Byte-identical default:** a source without `color`, and every existing `draw_with_emoji` caller, must render exactly as today. The new `draw_with_emoji` param defaults `None`.
- **Geometry unchanged:** width/scroll come from the flat `resolve()` string; colors never change layout. `resolve()` is UNTOUCHED.
- **Index space:** the per-char override is keyed by VISIBLE TEXT-CHAR index (emoji slugs excluded), matching `draw_with_emoji`'s `char_index` and `draw_text_per_char`'s `idx`.
- No `# type: ignore`, no `from __future__ import annotations`. Lint/format/pyright clean: `uv run --extra dev ruff check src/ tests/`, `... ruff format --check src/ tests/`, `... pyright src/led_ticker/sources.py src/led_ticker/widgets/message.py src/led_ticker/pixel_emoji.py src/led_ticker/app/factories.py`.
- Tests: `uv run --extra dev pytest` (no PYTHONPATH prefix).

---

### Task 1: Core infra — source color, typed segments, emoji override param

**Files:**
- Modify: `src/led_ticker/sources.py` (`DataSource.color`; `TokenizedField.resolve_segments`)
- Modify: `src/led_ticker/app/factories.py` (`build_source`: reserve + coerce `color`)
- Modify: `src/led_ticker/pixel_emoji.py` (`draw_with_emoji` gains `color_override`)
- Modify: `src/led_ticker/validate.py` (dry-run the source `color` coercion)
- Test: `tests/test_sources.py`, `tests/test_pixel_emoji.py` (or nearest existing emoji test module), `tests/test_validate.py`

**Interfaces produced (Task 2 consumes):**
- `DataSource.color: ColorProvider | None` (default None)
- `TokenizedField.resolve_segments(registry) -> list[tuple[str, ColorProvider | None, bool]]` — `(text, color, is_emoji)`; `"".join(t for t,_,_ in segs) == resolve()[0]`.
- `draw_with_emoji(..., color_override: Callable[[int], Any] | None = None)` — maps global text-char index → `Color` (override) or `None` (use provider).

- [ ] **Step 1: Failing tests — `resolve_segments`**

Add to `tests/test_sources.py`:

```python
from led_ticker.color_providers import _ConstantColor
from led_ticker._compat import require_graphics


def _prov(rgb):
    return _ConstantColor(require_graphics().Color(*rgb))


def test_resolve_segments_plain_text_single_span():
    reg = DataRegistry()
    f = TokenizedField("hello world")
    assert f.resolve_segments(reg) == [("hello world", None, False)]


def test_resolve_segments_token_carries_source_color():
    reg = DataRegistry()
    s = StaticSource(id="x", value="VAL")
    s.color = _prov([1, 2, 3])
    reg.add(s)
    segs = TokenizedField("a :x: b").resolve_segments(reg)
    assert segs[0] == ("a ", None, False)
    assert segs[1][0] == "VAL" and segs[1][1] is s.color and segs[1][2] is False
    assert segs[2] == (" b", None, False)


def test_resolve_segments_token_without_color_is_none():
    reg = DataRegistry()
    reg.add(StaticSource(id="x", value="VAL"))  # no .color set
    segs = TokenizedField(":x:").resolve_segments(reg)
    assert segs == [("VAL", None, False)]


def test_resolve_segments_emoji_marked_and_literal():
    reg = DataRegistry()
    # :sun: is a real emoji slug -> is_emoji True, color None, text kept as ":sun:"
    segs = TokenizedField("hi :sun: yo").resolve_segments(reg)
    assert segs[0] == ("hi ", None, False)
    assert segs[1][2] is True and segs[1][0] == ":sun:"
    assert segs[2] == (" yo", None, False)


def test_resolve_segments_concat_equals_resolve():
    reg = DataRegistry()
    s = StaticSource(id="x", value="123")
    reg.add(s)
    f = TokenizedField("p :x: :sun: q :missing:")
    flat, _ = f.resolve(reg)
    assert "".join(t for t, _, _ in f.resolve_segments(reg)) == flat
```

- [ ] **Step 2: Run — verify FAIL** (`resolve_segments` / `.color` don't exist).

Run: `uv run --extra dev pytest tests/test_sources.py -k resolve_segments -q` → FAIL.

- [ ] **Step 3: Add `DataSource.color` + `resolve_segments`**

In `sources.py`, add to the `DataSource` attrs class (after `version`):

```python
    # Optional presentation: a color provider for THIS source's inline token.
    # Set post-construction by build_source from the [[source]] `color` field.
    # None => the token inherits the host widget's font_color (today's behavior).
    color: "ColorProvider | None" = attrs.field(default=None, init=False)
```

(Import `ColorProvider` for the annotation: `from led_ticker.color_providers import ColorProvider` at module top — it's already a light import site; if a cycle appears, use a string annotation + `if TYPE_CHECKING`.)

Add to `TokenizedField`:

```python
    def resolve_segments(
        self, registry: DataRegistry
    ) -> list[tuple[str, "ColorProvider | None", bool]]:
        """Typed spans of the resolved text: (text, color, is_emoji).

        Literal runs -> (text, None, False). A `:id:` token -> (value,
        source.color, False). An emoji slug -> (":slug:", None, True). The
        concatenation of the texts equals `resolve()`'s flat string.
        Colors are read live from `registry.get(id).color`.
        """
        segments: list[tuple[str, ColorProvider | None, bool]] = []
        last = 0
        for m in EMOJI_PATTERN.finditer(self._raw):
            if m.start() > last:
                segments.append((self._raw[last : m.start()], None, False))
            slug = m.group()[1:-1]
            if is_emoji_slug(slug):
                segments.append((m.group(), None, True))
            else:
                src = registry.get(slug)
                if src is not None:
                    segments.append((src.current, src.color, False))
                else:
                    segments.append((m.group(), None, False))
            last = m.end()
        if last < len(self._raw):
            segments.append((self._raw[last:], None, False))
        if not segments:
            segments.append((self._raw, None, False))
        return segments
```

- [ ] **Step 4: Run — GREEN.** Run: `uv run --extra dev pytest tests/test_sources.py -k resolve_segments -q` → PASS.

- [ ] **Step 5: Failing test — `build_source` coerces + reserves `color`**

Add to `tests/test_sources.py` (or `tests/test_factories.py` if that's where build_source tests live — check first):

```python
def test_build_source_coerces_color_and_reserves_it(monkeypatch):
    from led_ticker.app.factories import build_source
    from led_ticker.config import SourceConfig

    cfg = SourceConfig(id="clk", type="clock", raw={"format": "%H:%M", "color": [1, 2, 3]})
    src = build_source(cfg)
    assert src.color is not None
    assert (src.color.color_for(0, 0, 1).red,
            src.color.color_for(0, 0, 1).green,
            src.color.color_for(0, 0, 1).blue) == (1, 2, 3)
```

(If `SourceConfig` construction differs, mirror an existing build_source test in the repo.)

- [ ] **Step 6: `build_source` — reserve + coerce `color`**

In `factories.py` `build_source`: add `"color"` to the `_RESERVED` set. Then wrap the return so ALL branches set color. Replace the current body's returns with building `source` then:

```python
    source = _construct_source(cls, cfg, session)  # the existing per-type dispatch
    raw_color = cfg.raw.get("color")
    if raw_color is not None:
        from led_ticker.app.coercion import _coerce_color_provider

        source.color = _coerce_color_provider(raw_color, "source color")
    return source
```

Simplest concrete refactor: keep the existing branch logic but assign to `source` instead of `return`, then do the color block + `return source` once at the end. Add `"color"` to `_RESERVED`.

- [ ] **Step 7: Run — GREEN** (build_source test) + no regression: `uv run --extra dev pytest tests/test_sources.py -q`.

- [ ] **Step 8: Failing test — `draw_with_emoji` color_override**

Add to the emoji-render test module (find it: `grep -rl "draw_with_emoji" tests/`). Use the stub canvas which records SetPixel colors.

```python
def test_draw_with_emoji_color_override_beats_provider(stub_canvas, bdf_font):
    # override maps text-char index -> a color for indices 2,3; else None.
    from led_ticker.pixel_emoji import draw_with_emoji
    from led_ticker._compat import require_graphics

    red = require_graphics().Color(255, 0, 0)

    def override(i):
        return red if i in (2, 3) else None

    # host provider returns green for every char
    class _Green:
        per_char = True
        frame_invariant = False
        def color_for(self, frame, idx, total):
            return require_graphics().Color(0, 255, 0)

    draw_with_emoji(stub_canvas, bdf_font, 0, 8, _Green(), "ABCD",
                    color_override=override)
    # Assert: pixels for chars 2,3 are red; chars 0,1 are green.
    # (Use the stub's recorded (x,y,rgb) pixels + the font's per-char x ranges;
    #  mirror an existing per-char color assertion in this test module.)
```

(Adapt the pixel assertion to the repo's existing stub-canvas color-check helper. If none exists, assert that `override` is CONSULTED for each text-char index by spying on it — a list of indices it was called with must include 0..3.)

- [ ] **Step 9: Run — verify FAIL** (unexpected kwarg `color_override`).

- [ ] **Step 10: `draw_with_emoji` — add `color_override`**

In `pixel_emoji.py` `draw_with_emoji`: add the param to the signature:

```python
    color_override: "Callable[[int], Any] | None" = None,
```

In the text-segment `else` branch (currently `if per_char: ... else: materialize once`), when `color_override is not None` force the per-char path and consult the override first:

```python
        else:
            seg_x = int(cursor_pos + total)
            if per_char or color_override is not None:
                def _cf(idx, tot, _co=color_override, _c=color, _f=frame, _ip=is_provider):
                    if _co is not None:
                        oc = _co(idx)
                        if oc is not None:
                            return oc
                    return _c.color_for(_f, idx, tot) if _ip else _c
                total += draw_text_per_char(
                    canvas, font, seg_x, y + y_offset, value, _cf,
                    char_offset=char_index, total_chars=total_text_chars,
                )
                char_index += len(value)
            else:
                materialized = (
                    color.color_for(frame, char_index, total_text_chars)
                    if is_provider else color
                )
                total += draw_text(canvas, font, seg_x, y + y_offset, materialized, value)
                char_index += len(value)
            prev_was_text = True
```

Keep the existing per-char branch's behavior byte-identical when `color_override is None` and `per_char` is True (the `_cf` returns `color.color_for(...)` exactly as the old lambda did). Verify with the existing emoji per-char tests.

- [ ] **Step 11: Run — GREEN** + full emoji suite: `uv run --extra dev pytest tests/ -k "emoji or draw_with" -q`.

- [ ] **Step 12: validate — dry-run source `color` coercion**

In `validate.py` `_check_sources`, after the type resolves, add (severity error) a coercion dry-run:

```python
        raw_color = src.raw.get("color")
        if raw_color is not None:
            from led_ticker.app.coercion import _coerce_color_provider
            try:
                _coerce_color_provider(raw_color, f"source[{src.id!r}] color")
            except Exception as exc:
                issues.append(ValidationIssue(
                    rule=56, location=f"{loc}.color", severity="error",
                    message=f"[[source]] {src.id!r} color is invalid: {exc}",
                    fix="Use [r,g,b] or {style='...'} — same forms as font_color.",
                ))
```

Add a test to `tests/test_validate.py`: a source with `color = [300,0,0]` yields a rule-56 error; a valid `color = [1,2,3]` yields none.

- [ ] **Step 13: Full suite + lint/format/pyright + commit**

Run: `uv run --extra dev pytest -q`, then ruff check / format --check / pyright on the four modules.

```bash
git add src/led_ticker/sources.py src/led_ticker/app/factories.py src/led_ticker/pixel_emoji.py src/led_ticker/validate.py tests/
git commit -m "feat(tokens): source color + typed token segments + draw_with_emoji override (infra)"
```

---

### Task 2: TickerMessage renders colored tokens

**Files:**
- Modify: `src/led_ticker/widgets/message.py` (build per-char override from segments; thread through the 3 color branches)
- Test: `tests/test_message.py` (or the message widget's test module — find it)

**Interfaces consumed:** `TokenizedField.resolve_segments`, `draw_with_emoji(color_override=...)`, `draw_text_per_char(color_fn=...)`.

- [ ] **Step 1: Write the failing tests (the precise contract)**

Add a `TestColoredTokens` class to the message test module. Use the stub canvas that records `(x, y, r, g, b)` per SetPixel (mirror existing per-char color tests in that module for the pixel-inspection helper).

Tests (each asserts against recorded pixel colors at the relevant character's x-range):
1. `test_token_chars_use_source_color_literal_uses_host` — source `x` value `"99"`, `x.color` = red; `text = "AB :x:"`, `font_color` = green (constant). Assert "AB " pixels green, "99" pixels red.
2. `test_no_color_source_is_byte_identical` — same message but `x.color = None`; assert the recorded pixel set is IDENTICAL to rendering with the pre-feature code path (capture from a message with the token but `font_color` green and no source color — all chars green).
3. `test_colored_token_with_host_rainbow` — `font_color = "rainbow"` (per_char), token color red constant; assert literal chars vary (rainbow) and token chars are all red.
4. `test_colored_token_mixed_with_emoji` — `text = "A :x: :sun:"`, `x.color` red, host green; assert "A " green, "x"-value red, and the `:sun:` sprite pixels are UNCHANGED from a no-color-override render (the emoji override must not touch the sprite, and the token color must still apply). **This is the index-alignment tripwire.**
5. `test_width_unchanged_with_color` — the returned `cursor_pos` from `draw()` equals the same message rendered with no source color (colors never change geometry).

- [ ] **Step 2: Run — verify FAIL** (token chars are host-colored, not source-colored).

- [ ] **Step 3: Implement — override builder + branch threading**

In `message.py`, add a helper (module-level or static) that builds the per-visible-text-char override from segments at a given frame:

```python
def _build_token_color_override(
    segments: list[tuple[Any, Any, bool]], frame: int
) -> list[Any] | None:
    """Return a per-visible-text-char list of Color-or-None from token
    segments, or None if no segment carries a color (common path -> callers
    skip the override entirely). Emoji segments contribute NO text-char
    positions (they're sprites), aligning the index with draw_with_emoji's
    char_index and draw_text_per_char's idx."""
    if not any(color is not None for _text, color, _emoji in segments):
        return None
    override: list[Any] = []
    for text, color, is_emoji in segments:
        if is_emoji:
            continue  # sprite: not a text char
        if color is None:
            override.extend([None] * len(text))
        else:
            c = color.color_for(frame, 0, 1)  # whole-string token provider
            override.extend([c] * len(text))
    return override
```

In `draw()`, after `full_text = self._resolve_into_full_text()` and computing `visible_text`, obtain segments and the override:

```python
        token_override = None
        if self._token is not None and self._token.has_tokens:
            segments = self._token.resolve_segments(get_data_registry())
            token_override = _build_token_color_override(
                segments, self.frame_for("font_color")
            )
```

(Note `visible_text` may be a typewriter PREFIX slice of `full_text`; the override is built over `full_text`'s text chars, indexed from 0 — a prefix slice's indices align. If `animation` is set AND colored tokens are present, that's fine: the override is indexed by the same 0-based text-char position.)

Then thread it through the three branches (only when `token_override is not None`; otherwise the existing code runs UNCHANGED):

- **Emoji branch:** pass `color_override=(lambda i: token_override[i] if i < len(token_override) else None)` to `draw_with_emoji`.
- **Per-char branch:** replace the `color_fn` with one that consults the override first:
  `lambda idx, total: token_override[idx] if (idx < len(token_override) and token_override[idx] is not None) else provider.color_for(self.frame_for("font_color"), idx, total)`.
- **Whole-string (else) branch:** when `token_override is not None`, DON'T take the single-color `draw_text` path — instead route through `draw_text_per_char` with the same override-first `color_fn` (host constant for literal chars): 
  `color_fn = lambda idx, total: token_override[idx] if (idx < len(token_override) and token_override[idx] is not None) else host_const`, where `host_const = provider.color_for(frame, 0, len(visible_text))`.

Keep all three existing branches intact for the `token_override is None` path (byte-identical).

- [ ] **Step 4: Run — GREEN** (all 5 tests) + the full message suite: `uv run --extra dev pytest tests/test_message.py -q` (adjust path).

- [ ] **Step 5: Regression — full suite + engine redraw contract + integration render**

Run: `uv run --extra dev pytest -q` (all green; watch `tests/test_ticker_display.py`, `tests/test_integration_render.py`, `tests/test_engine_redraw_contract.py`).

- [ ] **Step 6: Lint/format/pyright + commit**

```bash
git add src/led_ticker/widgets/message.py tests/
git commit -m "feat(tokens): TickerMessage renders per-token colors composed with font_color"
```

---

### Task 3: Docs + example

**Files:**
- Modify: the value-tokens docs page (`docs/site/src/content/docs/concepts/value-tokens.*` — find it) — a "Token color" section
- Create: `config/config.colored-token.example.toml` (or the repo's example dir) — a message with a colored token
- Test: none (docs); the example must `led-ticker validate` clean

- [ ] **Step 1: Docs "Token color" section** — document `[[source]] color = <provider>` (any font_color form: `[r,g,b]`, `"rainbow"`, `{style=...}`), that it colors the `:id:` token wherever it appears while literal text keeps the widget's `font_color`, the compose behavior (host rainbow + token color), and that it's `message` in this release (two_row/image are a follow-up). Match `docs/DOCS-STYLE.md`.

- [ ] **Step 2: Example config** — a `[[source]]` (e.g. `clock` or a demo `stocks.quote` if the plugin is assumed) with `color = ...`, a `message` using its token + a plain `font_color`. `uv run led-ticker validate <path>` → No issues found.

- [ ] **Step 3: Commit**

```bash
git add docs/ config/
git commit -m "docs(tokens): source-declared token color — value-tokens page + example"
```

---

## Post-implementation (controller, not a task)

- **Visual GIF gate (required):** render a message with `text = "AAPL :stocks.aapl:"`, `font_color = [80,140,255]`, source `color = {style="stocks.trend", symbol="AAPL"}` (install led-ticker-stocks in the render venv) and confirm ONE scrolling line — "AAPL " blue, price segment trend-colored. Plus a no-color regression render (unchanged).
- Final whole-branch review (opus) — focus on the index-alignment (emoji + token), byte-identical default, and geometry-unchanged. Then open the PR.
