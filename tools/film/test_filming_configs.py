"""The committed filming configs must validate clean, stay deterministic
(no schedule, no busy light, no file assets) and carry the `# film:` names
the clip tool zips with detected segments."""

import json
import subprocess
from pathlib import Path

import pytest
from tools.film.manifest import film_names

REPO = Path(__file__).resolve().parents[2]
FILMING = REPO / "docs/site/filming"
CONFIGS = ["hero", "features", "youtube"]


@pytest.mark.slow
@pytest.mark.parametrize("name", CONFIGS)
def test_filming_config_validates_clean(name):
    pytest.importorskip("led_ticker_flair")
    rc = subprocess.run(
        [
            "uv",
            "run",
            "--no-sync",
            "led-ticker",
            "validate",
            str(FILMING / f"{name}.toml"),
            "--json",
        ],
        capture_output=True,
        text=True,
        cwd=REPO,
        check=False,
    )
    report = json.loads(rc.stdout)
    assert report["errors"] == [], report


@pytest.mark.parametrize("name", CONFIGS)
def test_filming_configs_have_no_schedule_busy_or_paths(name):
    text = (FILMING / f"{name}.toml").read_text()
    assert "[display.schedule]" not in text
    assert "path =" not in text and 'type = "image"' not in text
    assert "enabled = false" in text.split("[busy_light]")[1]
    assert "hot_reload = true" in text


def test_hero_has_one_name_and_a_two_second_anchor_slate():
    text = (FILMING / "hero.toml").read_text()
    assert film_names(text) == ["hero"]
    assert "hold_time = 2.0" in text  # the loop-anchor slate


def test_features_names_are_many_and_unique():
    names = film_names((FILMING / "features.toml").read_text())
    assert len(names) >= 30
    assert len(set(names)) == len(names)
    assert names[0] == "color-rainbow"


def test_youtube_has_one_name():
    assert film_names((FILMING / "youtube.toml").read_text()) == ["youtube"]


def test_runbook_exists():
    assert (FILMING / "README.md").exists()


@pytest.mark.parametrize("name", CONFIGS)
def test_filming_configs_enable_the_status_board(name):
    # Without [web] the display never writes status.json, so film deploy's
    # wait-for-display would time out and strand the sign (review C1).
    text = (FILMING / f"{name}.toml").read_text()
    assert "\n[web]\n" in text


@pytest.mark.parametrize("name", CONFIGS)
def test_every_film_section_is_preceded_by_a_slate(name):
    text = (FILMING / f"{name}.toml").read_text()
    headers = [ln for ln in text.splitlines() if ln.startswith("[[playlist.section]]")]
    for i, h in enumerate(headers):
        if "# film:" in h:
            assert i > 0 and "# film:" not in headers[i - 1], h
    first_body = text.split("\n[[playlist.section]]", 2)[1]  # line-anchored; skip prose
    assert (
        "bg_color = [255, 255, 255]" in first_body and "hold_time = 2.0" in first_body
    )
