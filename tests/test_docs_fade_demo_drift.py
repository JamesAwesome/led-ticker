"""Snippet/GIF parity tripwire for the `fade` section of transitions/special.mdx
(DOCS-STYLE.md "Snippet/GIF parity", hard rule): the `TomlExample` beside the
`transitions-fade.gif` must reproduce `docs/site/demos/transitions-fade.toml`
from `[transitions]` to the end of the file character-for-character, and the
page must embed the GIF the TOML rendered. Pattern:
tests/test_docs_flair_transitions_demo_drift.py."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MDX = REPO_ROOT / "docs/site/src/content/docs/transitions/special.mdx"
DEMO = REPO_ROOT / "docs/site/demos/transitions-fade.toml"
GIF = REPO_ROOT / "docs/site/public/demos/transitions-fade.gif"


def _snippet_body() -> str:
    text = DEMO.read_text()
    start = text.find("[transitions]")
    assert start != -1, "transitions-fade.toml has no [transitions] block"
    return text[start:].rstrip("\n")


def test_demo_gif_is_embedded_and_committed() -> None:
    assert "/demos/transitions-fade.gif" in MDX.read_text()
    assert GIF.exists(), (
        "render it: make render-demo CONFIG=docs/site/demos/transitions-fade.toml "
        "OUT=docs/site/public/demos/transitions-fade.gif"
    )


def test_fade_snippet_matches_demo_toml_verbatim() -> None:
    body = _snippet_body()
    assert body in MDX.read_text(), (
        "special.mdx's fade TomlExample drifted from "
        "docs/site/demos/transitions-fade.toml; copy the TOML from [transitions] "
        "to EOF into the snippet"
    )


def test_demo_header_covers_the_fades() -> None:
    """plan-gif models hold + scroll only; the header pads for five 0.8 s fades."""
    lines = DEMO.read_text().splitlines()
    header = next(line for line in lines if line.startswith("# render-duration:"))
    assert int(header.split(":")[1]) >= 15
