"""Tripwires for the Why led-ticker? comparison page."""

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SITE = REPO / "docs" / "site"


def test_why_page_exists():
    assert (SITE / "src" / "content" / "docs" / "why-led-ticker.mdx").is_file()


def test_why_page_registered_in_sidebar():
    # The page must be in the sidebar or it silently 404s from nav.
    cfg = (SITE / "astro.config.mjs").read_text()
    assert "/why-led-ticker/" in cfg, "why-led-ticker not registered in the sidebar"
