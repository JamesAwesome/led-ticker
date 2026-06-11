"""Snippet/GIF parity tripwire for the bands border docs.

Enforces the DOCS-STYLE.md §4 "Snippet/GIF parity" hard rule for the
borders concept page: every `border-bands-*.toml` pinned demo whose GIF
is embedded in `concepts/borders.mdx` must have its exact `border = ...`
line reproduced character-for-character somewhere on the page. A snippet
that drifts from the TOML that rendered the GIF shows readers a config
that produces a different look than the picture — the failure mode this
guards against (James, 2026-06-11).

Scope is deliberately the bands family only: pairing a GIF to "its"
snippet can't be detected mechanically in general, so this test pins the
specific demos where the page promises parity. Extend the same pattern
to other border families if their sections adopt GIF-paired snippets.
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
    / "concepts"
    / "borders.mdx"
)
DEMOS = REPO_ROOT / "docs" / "site" / "demos-pinned"


def _embedded_bands_demos() -> list[str]:
    """Names of border-bands demo GIFs referenced by the borders page."""
    text = MDX.read_text()
    return sorted(set(re.findall(r"/demos-pinned/(border-bands-[\w-]+)\.gif", text)))


def test_bands_page_embeds_at_least_one_demo():
    """Meta-guard: if the page drops all bands GIFs, the parity test
    below would pass vacuously — fail loudly instead."""
    assert _embedded_bands_demos(), "borders.mdx no longer embeds any border-bands GIF"


def test_embedded_bands_gifs_have_matching_demo_toml():
    """Every embedded bands GIF must have its source TOML committed."""
    for name in _embedded_bands_demos():
        assert (DEMOS / f"{name}.toml").exists(), (
            f"borders.mdx embeds {name}.gif but docs/site/demos-pinned/{name}.toml "
            f"is missing — the GIF can't be re-rendered or parity-checked"
        )


def test_bands_snippets_match_demo_tomls_verbatim():
    """The `border = ...` line of each embedded bands demo TOML must
    appear character-for-character in borders.mdx (DOCS-STYLE §4
    snippet/GIF parity). On failure: fix the snippet by copying the
    line from the TOML — or, if the demo TOML changed, re-render the
    GIF AND update the snippet together."""
    mdx_text = MDX.read_text()
    for name in _embedded_bands_demos():
        toml_text = (DEMOS / f"{name}.toml").read_text()
        border_lines = [
            line for line in toml_text.splitlines() if line.startswith("border = ")
        ]
        assert border_lines, f"{name}.toml has no `border = ` line"
        for line in border_lines:
            assert line in mdx_text, (
                f"snippet/GIF parity violation: {name}.toml renders "
                f"{name}.gif (embedded in borders.mdx), but its config line "
                f"is not in the page verbatim:\n  {line}\n"
                f"Copy the line from the TOML into the snippet (never retype), "
                f"or re-render the GIF if the TOML is the side that changed."
            )
