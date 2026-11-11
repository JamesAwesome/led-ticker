"""Snippet/GIF parity tripwire for the flair twinkle / blink / snow docs.

Enforces the DOCS-STYLE.md §4 "Snippet/GIF parity" hard rule for the
flair-pack effect demos on the animations and backgrounds concept pages:
every pinned `animation-flair-{twinkle,blink}` / `background-flair-*` demo
whose GIF a page embeds must have its widget config lines (`text`,
`center`, `font_color`, `animation`, `background`) reproduced
character-for-character on that page. A snippet that drifts from the TOML
that rendered the GIF shows readers a config that produces a different
look than the picture.
"""

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS = REPO_ROOT / "docs" / "site" / "src" / "content" / "docs" / "concepts"
DEMOS = REPO_ROOT / "docs" / "site" / "demos-pinned"

# page -> regex of the demo names it must keep in parity
PAGES = {
    "animations.mdx": r"animation-flair-(?:twinkle|blink)",
    "backgrounds.mdx": r"background-flair-[\w-]+",
}
PARITY_KEYS = ("text = ", "center = ", "font_color = ", "animation = ", "background = ")


def _embedded(page: str) -> list[str]:
    text = (DOCS / page).read_text()
    pattern = rf"/demos-pinned/({PAGES[page]})\.gif"
    return sorted(set(re.findall(pattern, text)))


@pytest.mark.parametrize("page", sorted(PAGES))
def test_page_embeds_at_least_one_demo(page: str):
    """Meta-guard against the parity test below passing vacuously."""
    assert _embedded(page), f"{page} no longer embeds any flair effect demo GIF"


@pytest.mark.parametrize("page", sorted(PAGES))
def test_embedded_gifs_have_demo_toml_and_gif(page: str):
    for name in _embedded(page):
        assert (DEMOS / f"{name}.toml").exists(), (
            f"{page} embeds {name}.gif but docs/site/demos-pinned/{name}.toml "
            f"is missing — the GIF can't be re-rendered or parity-checked"
        )
        gif = REPO_ROOT / "docs" / "site" / "public" / "demos-pinned" / f"{name}.gif"
        assert gif.exists(), f"{page} embeds {name}.gif but the file is missing"


@pytest.mark.parametrize("page", sorted(PAGES))
def test_snippets_match_demo_tomls_verbatim(page: str):
    """Each embedded demo's widget config lines must appear verbatim on
    the page. On failure: copy the line from the TOML into the snippet
    (never retype), or re-render the GIF if the TOML is the side that
    changed."""
    mdx_text = (DOCS / page).read_text()
    for name in _embedded(page):
        toml_text = (DEMOS / f"{name}.toml").read_text()
        widget = toml_text.split("[[playlist.section.widget]]", 1)[1]
        lines = [ln for ln in widget.splitlines() if ln.startswith(PARITY_KEYS)]
        assert any(ln.startswith(("animation = ", "background = ")) for ln in lines), (
            f"{name}.toml has no `animation = ` / `background = ` line"
        )
        # Whole-line match (a substring check would let `text = "OPEN"` match
        # a longer line). Snippet lines may open with `code={\`` or close
        # with `\`}` inside a <TomlExample>; strip those wrappers.
        page_lines = {
            ln.strip().removeprefix("code={`").removesuffix("`}")
            for ln in mdx_text.splitlines()
        }
        for line in lines:
            assert line in page_lines, (
                f"snippet/GIF parity violation: {name}.toml renders {name}.gif "
                f"(embedded in {page}), but this config line is not on the "
                f"page verbatim:\n  {line}"
            )
