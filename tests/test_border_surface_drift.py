"""Tripwire binding border discovery surfaces to _BORDER_REGISTRY.

Two discovery surfaces must stay in sync with `_BORDER_REGISTRY` (the
source of truth in `src/led_ticker/borders.py`):

1. **CLI `--list-fields` hint** — `FIELD_HINTS["border"]` in
   `src/led_ticker/app/factories.py`. It carries a display-type string
   that lists both shorthand style names (e.g. `"rainbow"`) and the
   inline-table `{style="rainbow"|"color_cycle"|..., ...}` form. Either
   half can rot independently of the registry.

2. **Fact-pack border rows** — the `border` table row in each of the five
   widget fact-packs under `docs/content-source/widgets/`. These are the
   primary docs that users read when reaching for a border; if they omit
   a style name the user discovers it by accident, not by reading docs.

**Motivating failure (PR #193 final review, 2026-06-11):** `FIELD_HINTS["border"]`
had rotted to `{style="rainbow_chase", speed=N, width=N}` — a style name
that has never existed in `_BORDER_REGISTRY`. The `bands` style was also
absent from the hint's inline-table segment. Both were fixed in PR #193,
but the golden files under `tests/golden/list_fields/` only pin the hint's
text — they do not validate it against the registry. This file is that
validation.

The tests are split into two directions for each surface:
- **No phantom names**: every quoted style token in the surface is a
  registry key (catches ``rainbow_chase``-style typos).
- **Full coverage**: every registry key appears in the surface (catches
  a newly-added style that nobody wired into the docs).
"""

import re
from pathlib import Path

# Snapshot registry keys at import time.  Plugins can add styles at
# runtime, but in the test environment (no plugin install) only the five
# core styles exist.  Snapshotting avoids a hypothetical future where a
# test fixture installs a plugin and causes false failures here.
from led_ticker.app.factories import FIELD_HINTS
from led_ticker.borders import _BORDER_REGISTRY  # noqa: PLC2701

REPO_ROOT = Path(__file__).resolve().parent.parent

REGISTRY_KEYS: frozenset[str] = frozenset(_BORDER_REGISTRY.keys())

FACT_PACK_FILES: dict[str, Path] = {
    name: REPO_ROOT / "docs" / "content-source" / "widgets" / f"{name}.md"
    for name in ("message", "countdown", "two_row", "gif", "image", "clock")
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _border_display_type() -> str:
    """Return the display_type string from FIELD_HINTS['border']."""
    return FIELD_HINTS["border"].display_type


def _all_quoted_tokens(text: str) -> list[str]:
    """Return every double-quoted token from *text* (e.g. "rainbow" -> 'rainbow')."""
    return re.findall(r'"([a-z_]+)"', text)


def _border_row_from_file(path: Path) -> str:
    """Return the single table row (line) containing the `border` field.

    Searches for a markdown table row whose first non-whitespace token
    after `|` is the backtick-quoted string `` `border` ``.  Raises
    AssertionError if no such row is found so callers get a clear
    message rather than a silent empty-string match.
    """
    lines = path.read_text().splitlines()
    for line in lines:
        # Match table rows: starts with optional whitespace then `|`, and
        # the first cell content is exactly `border` (optionally backtick-
        # quoted).  This is more precise than "border" anywhere in the
        # line, which would match description prose mentioning the field
        # on some other row.
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        # Split on | and inspect the first data cell.
        cells = stripped.split("|")
        # cells[0] is empty (before leading |), cells[1] is first column.
        if len(cells) < 2:
            continue
        first_cell = cells[1].strip().strip("`")
        if first_cell == "border":
            return line
    raise AssertionError(
        f"No `border` table row found in {path}. "
        f"Add a border row to the fact-pack or update this test's search logic."
    )


# ---------------------------------------------------------------------------
# FIELD_HINTS["border"] tests
# ---------------------------------------------------------------------------


def test_field_hint_styles_are_registry_keys():
    """Every quoted style token in FIELD_HINTS['border'] must be a _BORDER_REGISTRY key.

    This catches phantom names like ``rainbow_chase`` that were in the hint
    string but have never existed in the registry.

    Fix: update ``FIELD_HINTS["border"]`` in
    ``src/led_ticker/app/factories.py`` to use only names that exist in
    ``_BORDER_REGISTRY``, then re-run
    ``make validate`` or ``PYTHONPATH=tests/stubs uv run pytest
    tests/test_list_fields_golden.py`` to regenerate ``tests/golden/list_fields/``.
    """
    display_type = _border_display_type()
    tokens = _all_quoted_tokens(display_type)
    # There must be at least some tokens — guard against an empty hint.
    assert tokens, (
        "FIELD_HINTS['border'].display_type contains no quoted tokens at all; "
        "the hint may have been accidentally cleared. "
        "Restore it in src/led_ticker/app/factories.py."
    )
    phantom = [t for t in tokens if t not in REGISTRY_KEYS]
    assert not phantom, (
        f"FIELD_HINTS['border'] names style(s) that are not in _BORDER_REGISTRY: "
        f"{phantom!r}. "
        f"Registry keys are: {sorted(REGISTRY_KEYS)!r}. "
        f"Update FIELD_HINTS['border'] in src/led_ticker/app/factories.py and "
        f"regenerate tests/golden/list_fields/ (run: "
        f"PYTHONPATH=tests/stubs uv run pytest "
        f"tests/test_list_fields_golden.py --regen "
        f"(or check that test for the regen flag name)."
    )


def test_field_hint_covers_all_registry_styles():
    """Every _BORDER_REGISTRY key must appear somewhere in FIELD_HINTS['border'].

    This catches a new style added to the registry without updating the hint
    (how the ``bands`` style was initially missing from the inline-table segment).

    Fix: add the missing style name(s) to ``FIELD_HINTS["border"].display_type``
    in ``src/led_ticker/app/factories.py``, then regenerate
    ``tests/golden/list_fields/`` as described in
    ``test_field_hint_styles_are_registry_keys``.
    """
    display_type = _border_display_type()
    missing = [key for key in sorted(REGISTRY_KEYS) if key not in display_type]
    assert not missing, (
        f"FIELD_HINTS['border'] does not mention _BORDER_REGISTRY style(s): "
        f"{missing!r}. "
        f"Add the missing name(s) to FIELD_HINTS['border'] in "
        f"src/led_ticker/app/factories.py and regenerate "
        f"tests/golden/list_fields/ (run: "
        f"PYTHONPATH=tests/stubs uv run pytest "
        f"tests/test_list_fields_golden.py --regen "
        f"(or check that test for the regen flag name)."
    )


# ---------------------------------------------------------------------------
# Fact-pack border row tests
# ---------------------------------------------------------------------------


def test_fact_pack_border_rows_cover_all_registry_styles():
    """Each fact-pack's border row must mention every _BORDER_REGISTRY key.

    The test reads only the border TABLE ROW (not the whole file) so a style
    name elsewhere in the file cannot mask a stale row.

    If this test fails for a file, update the `border` row in that file to
    include the missing style name(s) in the type column or description
    column of the row.
    """
    failures: list[str] = []
    for _widget, path in FACT_PACK_FILES.items():
        border_row = _border_row_from_file(path)
        missing = [key for key in sorted(REGISTRY_KEYS) if key not in border_row]
        if missing:
            failures.append(
                f"  {path.name}: border row is missing style(s) {missing!r}. "
                f"Update the border row in "
                f"docs/content-source/widgets/{path.name}."
            )
    assert not failures, (
        "Fact-pack border rows do not cover all _BORDER_REGISTRY styles:\n"
        + "\n".join(failures)
    )


def test_fact_pack_border_rows_have_no_phantom_styles():
    """Each fact-pack border row must not contain style=\"<name>\" tokens that
    are not in _BORDER_REGISTRY.

    This is the same anti-``rainbow_chase`` direction as
    ``test_field_hint_styles_are_registry_keys``, applied to the prose
    docs.  The regex targets explicit ``style="<name>"`` tokens only —
    shorthand-form mentions like ``"rainbow"`` in the *type* column are
    already covered by
    ``test_fact_pack_border_rows_cover_all_registry_styles``.

    Fix: remove or correct the phantom style token in the affected file's
    border row.
    """
    # Match style="<name>" in the row text (same form as TOML inline-table
    # notation used in the type column).
    style_token_re = re.compile(r'style="([a-z_]+)"')
    failures: list[str] = []
    for _widget, path in FACT_PACK_FILES.items():
        border_row = _border_row_from_file(path)
        tokens = style_token_re.findall(border_row)
        phantom = [t for t in tokens if t not in REGISTRY_KEYS]
        if phantom:
            failures.append(
                f"  {path.name}: border row contains phantom style(s) "
                f"{phantom!r} not in _BORDER_REGISTRY. "
                f"Update the border row in "
                f"docs/content-source/widgets/{path.name}."
            )
    assert not failures, (
        "Fact-pack border rows reference style names not in _BORDER_REGISTRY:\n"
        + "\n".join(failures)
    )
