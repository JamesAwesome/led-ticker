"""Tripwire: `--list-fields` output must not change when the
`from __future__ import annotations` imports are removed (the only place
that observes attrs annotation *form* at runtime is factories._render_field).
The golden files are captured on the current tree; the future-import-removal
task re-runs this and either it still passes (no drift) or the goldens are
updated deliberately.
"""

from pathlib import Path

import pytest

from led_ticker.app.factories import _list_widget_fields

GOLDEN_DIR = Path(__file__).parent / "golden" / "list_fields"

TYPES = ["message", "two_row", "gif", "weather", "mlb", "countdown"]


@pytest.mark.parametrize("widget_type", TYPES)
def test_list_fields_output_is_stable(widget_type):
    golden = GOLDEN_DIR / f"{widget_type}.txt"
    assert golden.exists(), (
        f"missing golden {golden}; regenerate with the snippet in the task"
    )
    assert _list_widget_fields(widget_type) == golden.read_text()
