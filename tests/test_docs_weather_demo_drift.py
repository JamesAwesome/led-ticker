"""Snippet/GIF parity tripwire for the weather.current widget docs.

Enforces the DOCS-STYLE.md §4 "Snippet/GIF parity" hard rule for
`widgets/weather.mdx`: the page tells the reader its TOML snippet is the
widget block from the demo that rendered the GIF above it, so that block
must appear on the page character-for-character. Same pattern and the
same reason as `test_docs_weather_forecast_demo_drift.py`.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MDX = (
    REPO_ROOT / "docs" / "site" / "src" / "content" / "docs" / "widgets" / "weather.mdx"
)
DEMOS = REPO_ROOT / "docs" / "site" / "demos-pinned"

# The demo the page promises parity with ("That is the whole widget block
# from docs/site/demos-pinned/weather-current-bigsign.toml").
PINNED = "weather-current-bigsign"


def _embedded_demos() -> list[str]:
    """Names of weather.current demo GIFs referenced by the page."""
    return sorted(
        set(re.findall(r"/demos-pinned/(weather-current-[\w-]+)\.gif", MDX.read_text()))
    )


def test_weather_page_embeds_at_least_one_demo():
    """Meta-guard: if the page drops all its GIFs, the parity test below
    would pass vacuously — fail loudly instead."""
    assert _embedded_demos(), (
        "weather.mdx no longer embeds any weather-current demo GIF"
    )


def test_embedded_weather_gifs_have_matching_demo_toml():
    """Every embedded GIF must have its source TOML committed."""
    for name in _embedded_demos():
        assert (DEMOS / f"{name}.toml").exists(), (
            f"weather.mdx embeds {name}.gif but docs/site/demos-pinned/{name}.toml "
            f"is missing — the GIF can't be re-rendered or parity-checked"
        )


def test_weather_snippet_matches_demo_toml_verbatim():
    """The pinned demo's playlist block must appear character-for-character
    in the page. On failure: copy the lines out of the TOML (never
    retype) — or, if the demo TOML changed, re-render the GIF AND update
    the snippet together."""
    assert PINNED in _embedded_demos(), (
        f"weather.mdx no longer embeds {PINNED}.gif, but its TOML is still the "
        f"snippet source this test pins — update both together"
    )
    toml_text = (DEMOS / f"{PINNED}.toml").read_text()
    _, _, playlist = toml_text.partition("[[playlist.section]]")
    block = f"[[playlist.section]]{playlist}".strip()
    assert "weather.current" in block, (
        f"{PINNED}.toml has no weather.current widget block"
    )
    assert block in MDX.read_text(), (
        f"snippet/GIF parity violation: {PINNED}.toml renders {PINNED}.gif (embedded "
        f"in weather.mdx), but its playlist block is not on the page verbatim:\n{block}"
    )
