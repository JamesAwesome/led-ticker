"""The site emits valid SoftwareApplication structured data."""

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SITE = REPO / "docs" / "site"


def test_structured_data_is_valid_software_application():
    data = json.loads((SITE / "src" / "structured-data.json").read_text())
    assert data["@context"] == "https://schema.org"
    assert data["@type"] == "SoftwareApplication"
    assert data["name"] == "led-ticker"
    assert data["url"].startswith("https://docs.ledticker.dev")
    assert data["applicationCategory"]
    assert "offers" in data  # free / open-source


def test_structured_data_injected_into_head():
    cfg = (SITE / "astro.config.mjs").read_text()
    assert "application/ld+json" in cfg, "JSON-LD not injected into <head>"
    assert "structured-data.json" in cfg, "structured data file not imported"
