"""Snippet/GIF parity tripwire for the tennis.scores widget docs.

Enforces the DOCS-STYLE.md §4 "Snippet/GIF parity" hard rule for
`widgets/tennis.mdx`: the page tells the reader its TOML snippet is
lifted from the demo that rendered the GIF above it, so the whole
`[[playlist.section]]` block of `tennis-scoreboard-longboi.toml` must
appear on the page character-for-character. A snippet that drifts shows
readers a config that produces a different look than the picture.

Same pattern as `test_docs_borders_demo_drift.py`, same reason: pairing
a GIF to "its" snippet can't be detected mechanically in general, so the
test pins the one demo whose parity the page explicitly promises.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MDX = (
    REPO_ROOT / "docs" / "site" / "src" / "content" / "docs" / "widgets" / "tennis.mdx"
)
DEMOS = REPO_ROOT / "docs" / "site" / "demos-pinned"

# The demo the page promises parity with ("That is the whole widget block
# from docs/site/demos-pinned/tennis-scoreboard-longboi.toml").
PINNED = "tennis-scoreboard-longboi"


def _embedded_tennis_demos() -> list[str]:
    """Names of tennis demo GIFs referenced by the widget page."""
    text = MDX.read_text()
    return sorted(set(re.findall(r"/demos-pinned/(tennis-[\w-]+)\.gif", text)))


def test_tennis_page_embeds_at_least_one_demo():
    """Meta-guard: if the page drops all tennis GIFs, the parity test
    below would pass vacuously — fail loudly instead."""
    assert _embedded_tennis_demos(), "tennis.mdx no longer embeds any tennis demo GIF"


def test_embedded_tennis_gifs_have_matching_demo_toml():
    """Every embedded GIF must have its source TOML committed."""
    for name in _embedded_tennis_demos():
        assert (DEMOS / f"{name}.toml").exists(), (
            f"tennis.mdx embeds {name}.gif but docs/site/demos-pinned/{name}.toml "
            f"is missing — the GIF can't be re-rendered or parity-checked"
        )


def test_tennis_snippet_matches_demo_toml_verbatim():
    """The pinned demo's playlist block must appear character-for-character
    in tennis.mdx. On failure: copy the lines out of the TOML (never
    retype) — or, if the demo TOML changed, re-render the GIF AND update
    the snippet together."""
    assert PINNED in _embedded_tennis_demos(), (
        f"tennis.mdx no longer embeds {PINNED}.gif, but its TOML is still "
        f"the snippet source this test pins — update both together"
    )
    toml_text = (DEMOS / f"{PINNED}.toml").read_text()
    _, _, playlist = toml_text.partition("[[playlist.section]]")
    block = f"[[playlist.section]]{playlist}".strip()
    assert "tennis.scores" in block, f"{PINNED}.toml has no tennis.scores widget block"
    assert block in MDX.read_text(), (
        f"snippet/GIF parity violation: {PINNED}.toml renders {PINNED}.gif "
        f"(embedded in tennis.mdx), but its playlist block is not on the page "
        f"verbatim:\n{block}"
    )
