"""Snippet/GIF parity tripwire for the flair transition catalogue.

Enforces the DOCS-STYLE.md §4 "Snippet/GIF parity" hard rule for
`transitions/sprite.mdx`: for each pinned flair transition demo listed in
VERBATIM_DEMOS, the TOML body from `[transitions]` to the end of the file
(everything a reader copies; the `[display]` block and render headers are
demo plumbing) must appear character-for-character in the page.

Scope is the demos whose sections promise a verbatim snippet. The older
`flair.laser` section shows a trimmed snippet (no font lines) and is not
listed. Add a demo here when its section reproduces the TOML in full.
"""

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
MDX = (
    REPO_ROOT
    / "docs"
    / "site"
    / "src"
    / "content"
    / "docs"
    / "transitions"
    / "sprite.mdx"
)
DEMOS = REPO_ROOT / "docs" / "site" / "demos-pinned"

VERBATIM_DEMOS = (
    "transition-flair-accordion",
    "transition-flair-interlock",
    "transition-flair-blinds",
)


def _snippet_body(name: str) -> str:
    text = (DEMOS / f"{name}.toml").read_text()
    start = text.find("[transitions]")
    assert start != -1, f"{name}.toml has no [transitions] block"
    return text[start:].rstrip("\n")


@pytest.mark.parametrize("name", VERBATIM_DEMOS)
def test_demo_gif_is_embedded(name: str) -> None:
    assert f"/demos-pinned/{name}.gif" in MDX.read_text(), (
        f"sprite.mdx no longer embeds {name}.gif; drop it from VERBATIM_DEMOS "
        f"or restore the DemoGif"
    )


@pytest.mark.parametrize("name", VERBATIM_DEMOS)
def test_snippet_matches_demo_toml_verbatim(name: str) -> None:
    body = _snippet_body(name)
    assert body in MDX.read_text(), (
        f"snippet/GIF parity violation: {name}.toml renders {name}.gif "
        f"(embedded in sprite.mdx), but its config from [transitions] down "
        f"is not on the page verbatim. Copy it from the TOML (never retype), "
        f"or re-render the GIF if the TOML is the side that changed."
    )
