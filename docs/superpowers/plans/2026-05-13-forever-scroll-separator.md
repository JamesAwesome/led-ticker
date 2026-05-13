# Per-Section `forever_scroll` Separator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add four per-section TOML fields (`separator`, `separator_font`, `separator_font_size`, `separator_color`) that customize the bullet-style separator interspersed between widgets in `forever_scroll` mode. Validation rule 26 rejects them on other modes. Missing `separator_font` flows through the existing rule 24 (missing-font warning).

**Architecture:** Four new fields on `SectionConfig`. New helper `_resolve_buffer_msg(section)` in `app.py` builds a `TickerMessage` from those fields (or returns `None` to inherit today's `DEFAULT_BUFFER_MSG`). Pass to `Ticker` via the existing `buffer_msg` kwarg — no `Ticker` or `_scroll_side_by_side` changes. Validator rule 26 + rule 24 hooks for separator_font.

**Tech Stack:** Python 3.13, pytest, `@dataclass` (`field` default factories), `tomllib`. Docs in Astro Starlight MDX.

**Spec reference:** `docs/superpowers/specs/2026-05-13-forever-scroll-separator-design.md`.

---

## Pre-flight

Use `superpowers:using-git-worktrees` to create an isolated workspace. Suggested name: `forever-scroll-separator`. Run `make test` baseline to confirm clean state (1504 passing at HEAD after the start_hold PR merged).

---

### Task 1: Add four `separator_*` fields to `SectionConfig`

**Files:**
- Modify: `src/led_ticker/config.py` (`SectionConfig` dataclass + section loader)
- Test: `tests/test_config.py` (new tests)

**Note:** The `test_docs_config_options_drift.py` allow-list update for the four new fields is DEFERRED to Task 4 — the meta-tripwire compares allow-list vs docs page, not allow-list vs dataclass, so adding to the allow-list before the docs row makes the test red.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_config.py`:

```python
import textwrap
from pathlib import Path

from led_ticker.config import load_config


def _write_separator_cfg(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "config.toml"
    p.write_text(textwrap.dedent(body))
    return p


def test_section_separator_defaults_to_none(tmp_path):
    cfg = _write_separator_cfg(tmp_path, """\
        [display]
        rows = 16
        cols = 32
        chain = 5

        [[playlist.section]]
        mode = "forever_scroll"

        [[playlist.section.widget]]
        type = "message"
        text = "hi"
        """)
    app = load_config(cfg)
    s = app.sections[0]
    assert s.separator is None
    assert s.separator_font is None
    assert s.separator_font_size is None
    assert s.separator_color is None


def test_section_separator_text_parses(tmp_path):
    cfg = _write_separator_cfg(tmp_path, """\
        [display]
        rows = 16
        cols = 32
        chain = 5

        [[playlist.section]]
        mode = "forever_scroll"
        separator = " * "

        [[playlist.section.widget]]
        type = "message"
        text = "hi"
        """)
    app = load_config(cfg)
    assert app.sections[0].separator == " * "


def test_section_separator_empty_string_parses(tmp_path):
    cfg = _write_separator_cfg(tmp_path, """\
        [display]
        rows = 16
        cols = 32
        chain = 5

        [[playlist.section]]
        mode = "forever_scroll"
        separator = ""

        [[playlist.section.widget]]
        type = "message"
        text = "hi"
        """)
    app = load_config(cfg)
    # Empty string is a meaningful value distinct from None — it triggers the
    # "two-space gap, no glyph" path in _resolve_buffer_msg. Must NOT collapse
    # to None during parsing.
    assert app.sections[0].separator == ""


def test_section_separator_font_parses(tmp_path):
    cfg = _write_separator_cfg(tmp_path, """\
        [display]
        rows = 16
        cols = 32
        chain = 5

        [[playlist.section]]
        mode = "forever_scroll"
        separator_font = "Inter-Bold"
        separator_font_size = 24

        [[playlist.section.widget]]
        type = "message"
        text = "hi"
        """)
    app = load_config(cfg)
    s = app.sections[0]
    assert s.separator_font == "Inter-Bold"
    assert s.separator_font_size == 24


def test_section_separator_color_parses_rgb_list(tmp_path):
    cfg = _write_separator_cfg(tmp_path, """\
        [display]
        rows = 16
        cols = 32
        chain = 5

        [[playlist.section]]
        mode = "forever_scroll"
        separator_color = [225, 48, 108]

        [[playlist.section.widget]]
        type = "message"
        text = "hi"
        """)
    app = load_config(cfg)
    # Color is raw at this stage (list[int]); the parser doesn't normalize
    # to ColorProvider — _resolve_buffer_msg does that in app.py at build
    # time. Keep parsing trivial.
    assert app.sections[0].separator_color == [225, 48, 108]


def test_section_separator_color_parses_rainbow_string(tmp_path):
    cfg = _write_separator_cfg(tmp_path, """\
        [display]
        rows = 16
        cols = 32
        chain = 5

        [[playlist.section]]
        mode = "forever_scroll"
        separator_color = "rainbow"

        [[playlist.section.widget]]
        type = "message"
        text = "hi"
        """)
    app = load_config(cfg)
    assert app.sections[0].separator_color == "rainbow"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_config.py -k "separator" -v`

Expected: all six FAIL with `AttributeError: 'SectionConfig' object has no attribute 'separator'` (or similar).

- [ ] **Step 3: Add the fields to `SectionConfig`**

In `src/led_ticker/config.py`, after the `start_hold` field (added in the previous PR), append:

```python
    # Per-section override for the forever_scroll loop separator
    # (the small bullet "•" between widgets in side-by-side scroll).
    # `None` inherits today's DEFAULT_BUFFER_MSG (white "•"). An empty
    # string `""` renders as two spaces (no glyph, minimum gap). Any
    # non-empty string is rendered as-is (no auto-padding — caller
    # controls spacing). Only honored on mode = "forever_scroll";
    # rule 26 rejects on other modes.
    separator: str | None = None
    # Font name (BDF alias or hires) for the separator glyph. `None`
    # uses TickerMessage's default font (FONT_DEFAULT). Useful when the
    # section's widget uses a custom display font and the separator
    # should match.
    separator_font: str | None = None
    # Required for hires fonts; ignored for BDF.
    separator_font_size: int | None = None
    # Color provider config. Accepts the same shapes as widget
    # `font_color`: [r, g, b], "rainbow", "color_cycle", or
    # {style = "gradient", ...}. Raw value here; normalized to
    # ColorProvider by app._resolve_buffer_msg at build time.
    separator_color: list[int] | str | dict | None = None
```

- [ ] **Step 4: Update the section loader**

In `src/led_ticker/config.py`, append four lines to the `SectionConfig(...)` constructor call (after `start_hold`):

```python
            start_hold=section_raw.get("start_hold"),
            separator=section_raw.get("separator"),
            separator_font=section_raw.get("separator_font"),
            separator_font_size=section_raw.get("separator_font_size"),
            separator_color=section_raw.get("separator_color"),
        )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_config.py -k "separator" -v`

Expected: all six PASS.

Run: `uv run pytest tests/test_docs_config_options_drift.py -v` to confirm we did NOT accidentally break the meta-tripwire (which we'd do if we'd touched the allow-list here).

Expected: all 6 drift tests PASS. The dataclass now has four new fields; the allow-list is unchanged; the drift test only compares allow-list ↔ docs page, so it stays green.

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker/config.py tests/test_config.py
git commit -m "config: add separator_* fields to SectionConfig

Four per-section TOML fields for the forever_scroll loop separator:
separator, separator_font, separator_font_size, separator_color.
All default to None (inherit today's white-bullet DEFAULT_BUFFER_MSG).
Wiring + validation in follow-up commits."
```

---

### Task 2: `_resolve_buffer_msg` helper + `app.py` wiring

**Files:**
- Modify: `src/led_ticker/app.py` (new helper + ticker_kwargs wiring)
- Test: `tests/test_app.py` (new tests)

- [ ] **Step 1: Find the existing color-provider parser**

```bash
grep -nE "def _resolve_color|font_color.*Color|def _parse_color|ColorProvider.*from" src/led_ticker/app.py | head -10
```

Find the function that converts raw `font_color` config values (`list[int]`, `"rainbow"`, dict) into `ColorProvider` instances. Note its exact name and signature — you'll call it from `_resolve_buffer_msg`. If multiple candidates exist, pick the one that's already a public-shaped helper (used by `_build_widget`).

If no such helper exists as a standalone function, look at how `_build_widget` handles `font_color` and extract that logic into a helper as part of this task. Name it `_resolve_color_provider(raw, default)`. Document the choice in the commit message.

- [ ] **Step 2: Write the failing tests**

Append to `tests/test_app.py`:

```python
def test_resolve_buffer_msg_returns_none_when_all_fields_unset():
    """Unset everything → None → Ticker falls back to DEFAULT_BUFFER_MSG."""
    from led_ticker.app import _resolve_buffer_msg
    from led_ticker.config import SectionConfig

    section = SectionConfig(mode="forever_scroll")
    assert _resolve_buffer_msg(section) is None


def test_resolve_buffer_msg_with_separator_text_only():
    """separator='*' → TickerMessage with text='*', default font/color."""
    from led_ticker.app import _resolve_buffer_msg
    from led_ticker.config import SectionConfig
    from led_ticker.widgets.message import TickerMessage

    section = SectionConfig(mode="forever_scroll", separator="*")
    msg = _resolve_buffer_msg(section)
    assert isinstance(msg, TickerMessage)
    assert msg.text == "*"


def test_resolve_buffer_msg_empty_string_maps_to_two_spaces():
    """Load-bearing case for the 'no glyph but breathing room' semantic."""
    from led_ticker.app import _resolve_buffer_msg
    from led_ticker.config import SectionConfig

    section = SectionConfig(mode="forever_scroll", separator="")
    msg = _resolve_buffer_msg(section)
    assert msg is not None
    assert msg.text == "  "


def test_resolve_buffer_msg_with_custom_font_inherits_default_text():
    """separator_font alone (no separator) → default '•' in custom font."""
    from led_ticker.app import _resolve_buffer_msg
    from led_ticker.config import SectionConfig

    section = SectionConfig(mode="forever_scroll", separator_font="5x8")
    msg = _resolve_buffer_msg(section)
    assert msg is not None
    assert msg.text == "•"


def test_resolve_buffer_msg_with_constant_color():
    """separator_color = [r, g, b] → ColorProvider wraps the constant."""
    from led_ticker.app import _resolve_buffer_msg
    from led_ticker.config import SectionConfig

    section = SectionConfig(
        mode="forever_scroll", separator="*", separator_color=[225, 48, 108]
    )
    msg = _resolve_buffer_msg(section)
    assert msg is not None
    # TickerMessage stores font_color as a ColorProvider. Assert the
    # provider returns the expected color when called. Exact attribute
    # path depends on TickerMessage internals — adapt if needed; the
    # invariant is that the requested RGB lands in the message somehow.
    color = msg.font_color.color_for(frame=0, char_index=0, total_chars=1)
    assert (color.red, color.green, color.blue) == (225, 48, 108)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_app.py -k "resolve_buffer_msg" -v`

Expected: all FAIL with `ImportError: cannot import name '_resolve_buffer_msg'`.

- [ ] **Step 4: Add the helper to `src/led_ticker/app.py`**

Place near `_resolve_title_delay` (the helper from the previous PR). Use whatever color-provider helper you found/extracted in Step 1:

```python
def _resolve_buffer_msg(section: SectionConfig) -> TickerMessage | None:
    """Build a per-section forever_scroll separator TickerMessage.

    Returns None when all four separator_* fields are unset — Ticker
    will fall back to its DEFAULT_BUFFER_MSG default (white "•").
    """
    if (
        section.separator is None
        and section.separator_font is None
        and section.separator_font_size is None
        and section.separator_color is None
    ):
        return None

    # Empty string => "no glyph, minimum gap" semantic per the spec.
    # Bare default => the historical "•" glyph.
    text = section.separator if section.separator is not None else "•"
    if text == "":
        text = "  "

    kwargs: dict[str, Any] = {"text": text, "center": False}
    if section.separator_font is not None:
        kwargs["font"] = section.separator_font
    if section.separator_font_size is not None:
        kwargs["font_size"] = section.separator_font_size
    kwargs["font_color"] = _resolve_color_provider(
        section.separator_color, default=RGB_WHITE
    )
    return TickerMessage(**kwargs)
```

Imports needed at the top of `app.py` if not already present:
- `from led_ticker.widgets.message import TickerMessage`
- `from led_ticker.colors import RGB_WHITE`
- whatever the color-provider helper's module is

- [ ] **Step 5: Wire into the section build loop**

In `src/led_ticker/app.py`, after the `ticker_kwargs` dict construction (around line 917-919, where `_resolve_title_delay` is called), add:

```python
buffer_msg = _resolve_buffer_msg(section)
if buffer_msg is not None:
    ticker_kwargs["buffer_msg"] = buffer_msg
```

When `buffer_msg` is `None`, the kwarg is omitted and Ticker's default applies.

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_app.py -k "resolve_buffer_msg" -v`

Expected: all five PASS.

Run: `uv run pytest tests/test_app.py -v` for regressions in the rest of the file.

- [ ] **Step 7: Commit**

```bash
git add src/led_ticker/app.py tests/test_app.py
git commit -m "app: _resolve_buffer_msg builds per-section separator TickerMessage

Builds a TickerMessage from the section's separator_* fields. Returns
None when all four are unset — Ticker keeps its DEFAULT_BUFFER_MSG
default. Empty-string separator maps to two spaces (no glyph but
minimum gap). Validation in follow-up commit."
```

---

### Task 3: Validator rule 26 + rule 24 hook for `separator_font`

**Files:**
- Modify: `src/led_ticker/validate.py` (`_check_static` for rule 26; either `_check_static` or a new helper for the separator_font resolution check)
- Test: `tests/test_validate.py` (new tests)

This task has TWO sub-features:

**3a) Rule 26:** error when any of the four `separator_*` fields is set on `mode != "forever_scroll"`.

**3b) Font resolution check:** when `separator_font` is set on a `forever_scroll` section, try to resolve the font. If `UnknownFontError`, route through rule 24 (warning, not error — consistent with widget-font behavior). If other `ValueError` (e.g. hires font requires `font_size`), route through rule 5 or a generic error.

- [ ] **Step 1: Write the failing tests for rule 26**

Append to `tests/test_validate.py`:

```python
async def test_rule26_separator_on_swap_errors(conf):
    cfg = """\
        [display]
        rows = 16
        cols = 32
        chain = 5
        default_scale = 1

        [[playlist.section]]
        mode = "swap"
        hold_time = 3
        separator = "*"

        [[playlist.section.widget]]
        type = "message"
        text = "hello"
        """
    result = await validate_config(conf(cfg))
    assert not result.valid
    assert any(e.rule == 26 for e in result.errors)


async def test_rule26_separator_on_gif_errors(conf):
    cfg = """\
        [display]
        rows = 16
        cols = 32
        chain = 5
        default_scale = 1

        [[playlist.section]]
        mode = "gif"
        separator = "*"

        [[playlist.section.widget]]
        type = "gif"
        path = "x.gif"
        """
    result = await validate_config(conf(cfg))
    assert not result.valid
    assert any(e.rule == 26 for e in result.errors)


async def test_rule26_separator_on_infini_scroll_errors(conf):
    cfg = """\
        [display]
        rows = 16
        cols = 32
        chain = 5
        default_scale = 1

        [[playlist.section]]
        mode = "infini_scroll"
        separator = "*"

        [[playlist.section.widget]]
        type = "message"
        text = "hello"
        """
    result = await validate_config(conf(cfg))
    assert not result.valid
    assert any(e.rule == 26 for e in result.errors)


async def test_rule26_separator_on_forever_scroll_is_allowed(conf):
    cfg = """\
        [display]
        rows = 16
        cols = 32
        chain = 5
        default_scale = 1

        [[playlist.section]]
        mode = "forever_scroll"
        separator = "*"
        separator_color = [225, 48, 108]

        [[playlist.section.widget]]
        type = "message"
        text = "hello"
        """
    result = await validate_config(conf(cfg))
    assert all(e.rule != 26 for e in result.errors)


async def test_rule26_separator_font_alone_on_swap_errors(conf):
    """Rule 26 fires on ANY of the four fields, not just `separator`."""
    cfg = """\
        [display]
        rows = 16
        cols = 32
        chain = 5
        default_scale = 1

        [[playlist.section]]
        mode = "swap"
        hold_time = 3
        separator_font = "Inter-Bold"

        [[playlist.section.widget]]
        type = "message"
        text = "hello"
        """
    result = await validate_config(conf(cfg))
    assert not result.valid
    assert any(e.rule == 26 for e in result.errors)


async def test_rule24_separator_font_missing_emits_warning(conf):
    """A separator_font that isn't bundled / in config/fonts/ must flow
    through rule 24 (warning) — same treatment as widget fonts.
    """
    cfg = """\
        [display]
        rows = 16
        cols = 32
        chain = 5
        default_scale = 1

        [[playlist.section]]
        mode = "forever_scroll"
        separator_font = "Some-Custom-Font"
        separator_font_size = 24

        [[playlist.section.widget]]
        type = "message"
        text = "hello"
        """
    result = await validate_config(conf(cfg))
    # Warnings allowed → result.valid is True
    assert result.valid is True
    assert any(w.rule == 24 for w in result.warnings), (
        f"expected rule 24 warning for unknown separator_font; got "
        f"warnings={[w.rule for w in result.warnings]}, "
        f"errors={[(e.rule, e.message) for e in result.errors]}"
    )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_validate.py -k "rule26 or rule24_separator_font" -v`

Expected: 4 fail (rule 26 ones), 1 passes vacuously (`_is_allowed`), 1 fails (rule 24 for separator_font — the existing rule 24 logic only catches font errors from `_build_widget`, not from separator).

- [ ] **Step 3: Add rule 26 to `_check_static`**

In `src/led_ticker/validate.py`, find `_check_static` (around line 110). Inside the outer section loop, immediately after the rule 25 block (the one added in the previous PR), append:

```python
        # Rule 26: separator_* fields are only honored by forever_scroll.
        # On swap / gif / infini_scroll, the engine doesn't intersperse a
        # buffer message, so the fields would silently do nothing. Reject
        # so the misconfiguration surfaces. Single error per section even
        # if multiple separator_* fields are set.
        separator_set = (
            section.separator is not None
            or section.separator_font is not None
            or section.separator_font_size is not None
            or section.separator_color is not None
        )
        if separator_set and section.mode != "forever_scroll":
            issues.append(
                ValidationIssue(
                    rule=26,
                    location=f"section[{i}]",
                    severity="error",
                    message=(
                        f"separator_* fields have no effect on"
                        f" mode={section.mode!r};"
                        " only forever_scroll inserts a separator between loops."
                    ),
                    fix=(
                        "Remove separator / separator_font / separator_font_size"
                        " / separator_color, or change mode to 'forever_scroll'."
                    ),
                )
            )
```

- [ ] **Step 4: Add separator_font resolution check**

`_check_band_layout` (in the same file) already shows the pattern for calling `resolve_font` defensively. Mirror it for `separator_font`. Add a new helper or extend an existing one.

Cleanest path: add a new function near `_check_band_layout`. The validator main flow (`validate_config`) calls this after `_run_build_checks` so font failures from BOTH widgets and separators go through the same warning/error pipeline.

```python
def _check_separator_fonts(config: AppConfig) -> tuple[list[ValidationIssue], list[ValidationIssue]]:
    """Resolve any `separator_font` set on forever_scroll sections.

    Returns (errors, warnings). UnknownFontError → rule 24 warning
    (consistent with widget-font behavior). Other ValueError (e.g.
    "requires font_size") → rule 5 error.
    """
    from led_ticker.fonts import UnknownFontError, resolve_font

    errors: list[ValidationIssue] = []
    warnings: list[ValidationIssue] = []
    for i, section in enumerate(config.sections):
        if section.mode != "forever_scroll":
            continue  # Rule 26 already caught the wrong-mode case
        if section.separator_font is None:
            continue
        try:
            resolve_font(section.separator_font, size=section.separator_font_size)
        except UnknownFontError as exc:
            warnings.append(
                ValidationIssue(
                    rule=24,
                    location=f"section[{i}].separator_font",
                    severity="warning",
                    message=str(exc),
                    fix=(
                        "Drop the font file into config/fonts/ on the deploy"
                        " target, or pick one of the bundled fonts listed"
                        " above (BDF: 5x8 / 6x10 / 6x12 / 7x13; hires:"
                        " Inter-Bold / Inter-Regular)."
                    ),
                )
            )
        except ValueError as exc:
            # e.g. "requires font_size" for hires font with no size — same
            # message pattern as the existing rule 5.
            msg = str(exc)
            rule = 5 if "requires font_size" in msg else None
            errors.append(
                ValidationIssue(
                    rule=rule,
                    location=f"section[{i}].separator_font",
                    severity="error",
                    message=msg,
                    fix=(
                        "Add separator_font_size = <pixels> next to"
                        " separator_font (e.g. separator_font_size = 24)."
                    ),
                )
            )
    return errors, warnings
```

Wire into `validate_config` (around the phase 1c/1d boundary, near line 590-615). After `_run_build_checks` returns and its errors/warnings are appended:

```python
sep_errors, sep_warnings = _check_separator_fonts(config)
errors.extend(sep_errors)
warnings.extend(sep_warnings)
```

Place this BEFORE the `if not errors:` gate that runs `_check_band_layout` — separator font issues shouldn't cascade-suppress widget-level checks.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_validate.py -k "rule26 or rule24_separator_font" -v`

Expected: all six PASS.

Run: `uv run pytest tests/test_validate.py -v` for regressions.

- [ ] **Step 6: Commit**

```bash
git add src/led_ticker/validate.py tests/test_validate.py
git commit -m "validate: rule 26 + rule 24 hook for separator_font

Rule 26: any separator_* field on non-forever_scroll → error (same
shape as rule 25). Separator_font missing fonts route through rule 24
(warning, not hard error) — consistent with widget-font behavior on
configs drafted off-target."
```

---

### Task 4: Docs + drift-test allow-list

**Files:**
- Modify: `docs/site/src/content/docs/reference/config-options.mdx`
- Modify: `docs/site/src/content/docs/pitfalls.mdx`
- Modify: `docs/site/src/content/docs/tools/validate.mdx`
- Modify: `tests/test_docs_config_options_drift.py`
- Optional: `docs/site/src/content/docs/concepts/sections-and-modes.mdx`

- [ ] **Step 1: Add four rows to `config-options.mdx`**

In the per-section table (starts around line 68), add four rows after the `start_hold` row (added in the previous PR). Adjust trailing whitespace per the table style — `pnpm run format` will normalize:

```markdown
| `separator`            | string         | `null` (= white `•`)              | Per-section override for the bullet between `forever_scroll` widgets. Empty string `""` renders as two spaces (no glyph, minimum gap). Non-empty strings render as-is — include surrounding spaces if you want padding (e.g. `" * "`). Rejected on non-`forever_scroll` modes.                                                              |
| `separator_font`       | string         | `null`                            | Font name (BDF alias or hires file) for the separator glyph. `null` uses the default 6×12 BDF. Useful for matching the section's widget font.                                                                                                                                                                                                |
| `separator_font_size`  | int            | `null`                            | Required when `separator_font` is a hires font. Ignored for BDF (fixed cell height).                                                                                                                                                                                                                                                          |
| `separator_color`      | `[r, g, b]` / string / table | `null` (= white)    | Color for the separator. Accepts the same shapes as widget `font_color`: constant `[r, g, b]`, `"rainbow"`, `"color_cycle"`, or `{style = "gradient", from = [...], to = [...]}`.                                                                                                                                                              |
```

- [ ] **Step 2: Add rule 26 entry to `pitfalls.mdx`**

In the Errors section, after rule 25 (the existing last error rule):

```markdown
### Rule 26 — `separator_*` is only valid on `forever_scroll`

The `separator`, `separator_font`, `separator_font_size`, and `separator_color` fields customize the small bullet that `forever_scroll` mode inserts between widgets in the side-by-side stream. `swap` and `gif` modes don't intersperse anything; `infini_scroll` fully exits each widget before the next, so no separator is needed. Setting any of these fields on a non-`forever_scroll` section would silently do nothing — the validator rejects it. Either remove the fields, or change `mode` to `"forever_scroll"`.
```

- [ ] **Step 3: Add row to `validate.mdx`**

In the errors group of the reference table:

```markdown
| `separator_*` set on a non-`forever_scroll` section              | error    | remove the field, or switch to `forever_scroll`   |
```

- [ ] **Step 4: Update the drift-test allow-list**

In `tests/test_docs_config_options_drift.py`, add four entries to `DOCUMENTED_KEYS["section"]` alphabetically:

```python
        "separator",
        "separator_color",
        "separator_font",
        "separator_font_size",
```

The new fields land between `scroll_step_ms` and `start_hold` (alphabetical: scroll, separator, start).

- [ ] **Step 5: Optional concepts page**

```bash
ls docs/site/src/content/docs/concepts/sections-and-modes.mdx 2>/dev/null
```

If the page exists AND discusses the bullet, add a short paragraph near the existing prose:

> Between forever_scroll widgets the engine inserts a small white bullet (`•`) so adjacent widgets don't visually touch. Override per section with `separator` (any string, including `""` for no glyph), `separator_font`, `separator_font_size`, and `separator_color` — all four mirror the widget `font*` / `font_color` knobs.

If no relevant anchor exists, skip.

- [ ] **Step 6: Verify**

```bash
make docs-lint
make docs-build
uv run pytest tests/test_docs_config_options_drift.py -v
```

All three must PASS.

- [ ] **Step 7: Commit**

```bash
git add docs/site/src/content/docs/reference/config-options.mdx \
        docs/site/src/content/docs/pitfalls.mdx \
        docs/site/src/content/docs/tools/validate.mdx \
        tests/test_docs_config_options_drift.py
# Plus concepts page if you actually edited it.
git commit -m "docs: per-section forever_scroll separator + rule 26"
```

---

### Task 5: Final verification + PR

**Files:** none modified.

- [ ] **Step 1: Full test suite**

```bash
make test
```

Expected: PASS. Test count delta: +17 (6 config + 5 app + 6 validate). Final count ~1521.

- [ ] **Step 2: Lint + typecheck + docs-lint**

```bash
make lint
uv run pyright src/
make docs-lint
```

All PASS.

- [ ] **Step 3: Example-config sweep**

```bash
find config docs/site -name "*.toml" -not -path "*/node_modules/*" | while read -r f; do
  out=$(uv run led-ticker validate "$f" --json 2>/dev/null)
  r26=$(echo "$out" | python -c "import json,sys; d=json.load(sys.stdin); print(len([e for e in d.get('errors',[]) if e.get('rule')==26]))" 2>/dev/null || echo 0)
  if [ "$r26" -gt 0 ]; then
    echo "FLAG: $f → $r26 rule-26 error(s)"
  fi
done
echo "sweep done"
```

Expected: zero flagged. No example config sets `separator_*` today.

- [ ] **Step 4: Smoke test the K-POP marquee scenario**

Write `/tmp/separator_smoke.toml`:

```toml
[display]
rows = 32
cols = 64
chain = 8
default_scale = 4
pixel_mapper = "Remap:256,64|U-mapper"

[[playlist.section]]
mode = "forever_scroll"
loop_count = 4
start_hold = 0.0
separator = " * "
separator_color = [225, 48, 108]

[[playlist.section.widget]]
type = "message"
text = "K-POP DANCE CLASS"
font_size = 24
```

Run: `uv run led-ticker validate /tmp/separator_smoke.toml`. Expected: `No issues found.` (separator_font omitted on purpose — exercise the default-font + custom-color path.)

Then with a custom font that doesn't exist:

```toml
separator_font = "Hunters-Kpop"
separator_font_size = 24
```

Expected: rule 24 warning fires (not an error), `result.valid` is True.

- [ ] **Step 5: `superpowers:finishing-a-development-branch`** — push + PR.

PR title: `validate: per-section forever_scroll separator (rule 26)`.

PR body includes: spec link, plan link, summary of the 4 commits, test plan checkboxes, mention of back-compat (zero behavior change for configs that don't set the fields).

---

## Self-review

- **Spec coverage:** every requirement in the spec maps to a task. Fields + parsing → Task 1. Helper + wiring → Task 2. Validation (rules 26 + 24) → Task 3. Docs → Task 4.
- **No placeholders:** all code blocks pasteable. Test bodies are complete. Two ambiguous-spots are explicitly flagged: Task 2 Step 1 has a "find the existing color helper" investigation step with a fallback (extract one), and Task 5 Step 4's "Hunters-Kpop" font test exercises the rule 24 path.
- **Type consistency:** `str | None` / `int | None` / `list[int] | str | dict | None` throughout. `_resolve_buffer_msg` returns `TickerMessage | None`. `_check_separator_fonts` returns `tuple[list, list]`.
- **Test naming:** `test_section_separator_*` for config tests, `test_resolve_buffer_msg_*` for app tests, `test_rule26_*` for validation, `test_rule24_separator_font_*` for the cross-rule hook.

## Tradeoffs explicitly chosen

- **Four separate fields instead of an inline table.** Matches existing flat-field convention on widgets (`font` / `font_size` / `font_color`). Discoverability via flat TOML keys beats compactness.
- **`None` as the unset sentinel; `""` is a distinct meaningful value.** Empty string maps to "two spaces" — distinct from inheriting the default `•`. The config parser must preserve this distinction (tested explicitly).
- **Rule 26 fires once per section, not once per field.** A user who sets two separator fields on a swap section gets one error listing all four field names, not two duplicate errors.
- **Separator_font flows through rule 24 (warning), not a new error path.** Consistent with the previous rule-24 work: missing fonts are draft-time warnings, not hard blocks.
- **No global `[forever_scroll] separator_default` in this change.** Sections that don't set `separator_*` inherit the existing hardcoded `DEFAULT_BUFFER_MSG`. A future cleanup could add a playlist-wide default; out of scope here.
