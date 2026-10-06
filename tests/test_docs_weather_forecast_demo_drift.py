"""Snippet/GIF parity tripwire for the weather.forecast widget docs.

Enforces the DOCS-STYLE.md §4 "Snippet/GIF parity" hard rule for
`widgets/weather_forecast.mdx`: the page tells the reader its TOML
snippet is the widget block from the demo that rendered the GIF above
it, so that block must appear on the page character-for-character. A
snippet that drifts shows readers a config that produces a different
card than the picture.

Same pattern and the same reason as `test_docs_borders_demo_drift.py`:
pairing a GIF to "its" snippet can't be detected mechanically in
general, so the test pins the one demo whose parity the page promises.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MDX = (
    REPO_ROOT
    / "docs"
    / "site"
    / "src"
    / "content"
    / "docs"
    / "widgets"
    / "weather_forecast.mdx"
)
DEMOS = REPO_ROOT / "docs" / "site" / "demos-pinned"

# The demo the page promises parity with ("That is the whole widget block
# from docs/site/demos-pinned/weather-forecast-hero-longboi.toml").
PINNED = "weather-forecast-hero-longboi"


def _embedded_forecast_demos() -> list[str]:
    """Names of weather.forecast demo GIFs referenced by the page."""
    text = MDX.read_text()
    return sorted(
        set(re.findall(r"/demos-pinned/(weather-forecast-[\w-]+)\.gif", text))
    )


def test_forecast_page_embeds_at_least_one_demo():
    """Meta-guard: if the page drops all its GIFs, the parity test below
    would pass vacuously — fail loudly instead."""
    assert _embedded_forecast_demos(), (
        "weather_forecast.mdx no longer embeds any weather-forecast demo GIF"
    )


def test_embedded_forecast_gifs_have_matching_demo_toml():
    """Every embedded GIF must have its source TOML committed."""
    for name in _embedded_forecast_demos():
        assert (DEMOS / f"{name}.toml").exists(), (
            f"weather_forecast.mdx embeds {name}.gif but "
            f"docs/site/demos-pinned/{name}.toml is missing — the GIF can't "
            f"be re-rendered or parity-checked"
        )


def test_forecast_snippet_matches_demo_toml_verbatim():
    """The pinned demo's playlist block must appear character-for-character
    in the page. On failure: copy the lines out of the TOML (never
    retype) — or, if the demo TOML changed, re-render the GIF AND update
    the snippet together."""
    assert PINNED in _embedded_forecast_demos(), (
        f"weather_forecast.mdx no longer embeds {PINNED}.gif, but its TOML is "
        f"still the snippet source this test pins — update both together"
    )
    toml_text = (DEMOS / f"{PINNED}.toml").read_text()
    _, _, playlist = toml_text.partition("[[playlist.section]]")
    block = f"[[playlist.section]]{playlist}".strip()
    assert "weather.forecast" in block, (
        f"{PINNED}.toml has no weather.forecast widget block"
    )
    assert block in MDX.read_text(), (
        f"snippet/GIF parity violation: {PINNED}.toml renders {PINNED}.gif "
        f"(embedded in weather_forecast.mdx), but its playlist block is not "
        f"on the page verbatim:\n{block}"
    )
