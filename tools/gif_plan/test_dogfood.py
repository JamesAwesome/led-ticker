"""Dogfood: run the planner against every pinned demo config.

Two assertions:
  1. No false-positive mid_pass_cutoff errors on already-shipped demos.
  2. recommended_render_duration_s is within ±20% of each demo's
     `# render-duration:` header. Catches drift in formulas or canonical
     demos.

The 20% band is intentionally loose — the planner's content-width
estimates are approximations and we're not trying to match the render
engine's measurements exactly.

Some demos deliberately under- or over-buffer their `# render-duration:`
header for visual focus (e.g. capture the type-out + a clean hold,
truncate mid-scroll so the design hierarchy reads clearly, leave extra
room past the deterministic cycle). Those demos are listed in
`_DRIFT_XFAILS` and `_MID_PASS_XFAILS` below with the reason — the
planner's math is correct for these, the header just isn't trying to
match it.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from tools.gif_plan.plan import plan

REPO_ROOT = Path(__file__).resolve().parents[2]
DEMO_DIR = REPO_ROOT / "docs" / "site" / "demos-pinned"


# Demos that deliberately set render-duration shorter than the full
# deterministic playback — the gif captures a visual focus window,
# not the entire scroll/hold cycle. Planner correctly flags the
# mid-pass cutoff; the demo intent overrides.
_MID_PASS_XFAILS: dict[str, str] = {
    "image-typewriter.toml": (
        "hold_seconds=8 deliberately exceeds render-duration=5 so the "
        "captured window contains a clean type-out + comfortable hold "
        "without re-entering the next cycle."
    ),
    "image-typewriter-border.toml": (
        "hold_seconds=8 deliberately exceeds render-duration=5 — see "
        "image-typewriter.toml header comment."
    ),
    "two_row-asymmetric.toml": (
        "Bigsign scale=2 + long bottom row: render-duration=14 captures "
        "the hold + most of the scroll for visual focus on hierarchy; "
        "the full deterministic scroll takes ~18s."
    ),
    "two_row-brand-handle.toml": (
        "Bigsign scale=2 + long bottom row: render-duration=12 captures "
        "the brand handle hold + scroll start; the full scroll takes "
        "~15s."
    ),
    "two_row-font-hierarchy.toml": (
        "Bigsign scale=2 + hires bottom row: render-duration=8 captures "
        "the hold (7s) + a sliver of scroll; the full deterministic "
        "scroll takes ~14s."
    ),
    "two_row-hires-emoji.toml": (
        "Bigsign scale=2 + long BDF bottom row: render-duration=12 "
        "captures hold + scroll start; the full scroll takes ~18s."
    ),
}

# Demos where the header is materially larger than the planner's
# deterministic total — the gif over-buffers past the visible cycle
# for stylistic reasons. The planner's math is correct; the header is
# generous.
_DRIFT_XFAILS: dict[str, str] = {
    **_MID_PASS_XFAILS,
    "two_row-bottom_text_loops.toml": (
        "Wrap floor + bottom_text_loops=2 takes ~6s of deterministic "
        "playback; header=14 over-buffers for an extra hold beyond the "
        "loop floor."
    ),
    "two_row-scroll_through.toml": (
        "scroll_through with hold_time=10s yields ~10s of playback; "
        "header=20 over-buffers so a second pass renders fully."
    ),
}


def _all_demo_configs() -> list[Path]:
    return sorted(DEMO_DIR.glob("*.toml"))


@pytest.mark.parametrize("cfg_path", _all_demo_configs(), ids=lambda p: p.name)
def test_no_false_positive_mid_pass(cfg_path: Path, request: pytest.FixtureRequest):
    """Each shipped demo's `# render-duration:` should NOT trigger a
    mid_pass_cutoff error. If one trips, either the demo is genuinely
    miscalibrated (file a bug) or the planner's math is off."""
    if cfg_path.name in _MID_PASS_XFAILS:
        request.applymarker(
            pytest.mark.xfail(reason=_MID_PASS_XFAILS[cfg_path.name], strict=True)
        )
    result = plan(cfg_path)
    errs = [f for f in result["flags"] if f["code"] == "mid_pass_cutoff"]
    assert not errs, (
        f"{cfg_path.name} would trip mid_pass_cutoff: {errs}. "
        f"Either the demo header is wrong or the planner overestimates."
    )


@pytest.mark.parametrize("cfg_path", _all_demo_configs(), ids=lambda p: p.name)
def test_recommendation_within_loose_band(
    cfg_path: Path, request: pytest.FixtureRequest
):
    """Drift tripwire — recommendation within ±20% of header."""
    if cfg_path.name in _DRIFT_XFAILS:
        request.applymarker(
            pytest.mark.xfail(reason=_DRIFT_XFAILS[cfg_path.name], strict=True)
        )
    result = plan(cfg_path)
    header = result["render_duration_header"]
    if header is None:
        pytest.skip("no header to compare against")
    if result["total_ms"] == 0:
        pytest.skip("data-fetch widget — visit time not deterministic")
    rec = result["recommended_render_duration_s"]
    low = max(1, int(header * 0.8))
    high = int(header * 1.2) + 1
    assert low <= rec <= high, (
        f"{cfg_path.name}: header {header}s vs planner {rec}s out of "
        f"±20% band ({low}-{high})."
    )
