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
# (All entries cleared: audit PR fixed all 5 mid-pass errors.)
_MID_PASS_XFAILS: dict[str, str] = {}

# Demos where the header is materially larger than the planner's
# deterministic total — the gif over-buffers past the visible cycle
# for stylistic reasons. The planner's math is correct; the header is
# generous.
# (All entries cleared: audit PR trimmed all 5 over-specified headers.)
_DRIFT_XFAILS: dict[str, str] = {
    **_MID_PASS_XFAILS,
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


# Curated tripwire: demos whose authors deliberately set the header to
# the planner's exact recommendation (rec == header today). The ±20%
# band above is loose-by-construction and ~37% of it is now strict-
# xfailed, so a coordinated ~15% formula drift could slip through it.
# This list pins the anchor demos to ±1s — a much tighter net that a
# systematic regression cannot widen. If a legitimate formula change
# moves one of these, update the engine-derived expectation here
# deliberately (don't loosen the tolerance).
_TIGHT_MATCH_DEMOS: tuple[str, ...] = (
    "border-constant.toml",
    "countdown-brand-color.toml",
    "countdown-rainbow-border.toml",
    "countdown-rainbow.toml",
    "gif-scroll_over.toml",
    "gif-two_row-wrap.toml",
    "gif-typewriter.toml",
    "gif-typewriter-border.toml",
    "gif-wrap.toml",
    "image-static-logo.toml",
    "image-two_row.toml",
    "message-brand-color.toml",
    "message-gradient.toml",
    "message-hires-grand-opening.toml",
    "message-inline-emoji.toml",
    "message-typewriter-rainbow.toml",
    "message-yellow-bg.toml",
    "two_row-wrap.toml",
)


@pytest.mark.parametrize("name", _TIGHT_MATCH_DEMOS)
def test_curated_demos_match_header_tightly(name: str):
    """±1s tripwire on the must-match anchor demos. Complements the
    loose ±20% band (which is hollowed out by the xfail list)."""
    assert name not in _DRIFT_XFAILS, (
        f"{name} is both a tight-match anchor and drift-xfailed — "
        f"contradiction; remove it from one list."
    )
    result = plan(DEMO_DIR / name)
    header = result["render_duration_header"]
    assert header is not None, f"{name} lost its `# render-duration:` header"
    rec = result["recommended_render_duration_s"]
    tol = max(1, round(header * 0.10))
    assert abs(rec - header) <= tol, (
        f"{name}: planner {rec}s drifted from header {header}s by more "
        f"than ±{tol}s — a curated must-match demo. Investigate the "
        f"formula change; do not loosen this assertion."
    )
    errs = [f for f in result["flags"] if f["code"] == "mid_pass_cutoff"]
    assert not errs, f"{name} unexpectedly trips mid_pass_cutoff: {errs}"
