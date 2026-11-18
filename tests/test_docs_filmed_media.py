"""Filmed-media tripwire: `docs/site/public/filmed/` and the pages that embed
it stay in lockstep.

Real-hardware footage of the smallsign (dark-room takes from session 0,
2026-11-17) is committed as GIFs plus one web mp4. Every `/filmed/...`
reference on the site must point at a file that exists, every committed
file must be used by some page (116 MB of binaries earns its place or goes),
sizes stay inside the clip tool's budgets, the CDN cache rule covers the
directory, and `DemoGif.astro` keeps the `video` / `filmed` props the hero
depends on.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SITE = REPO_ROOT / "docs" / "site"
FILMED = SITE / "public" / "filmed"
CONTENT = SITE / "src" / "content" / "docs"
DEMO_GIF = SITE / "src" / "components" / "DemoGif.astro"
HEADERS = SITE / "public" / "_headers"

GIF_BUDGET = 2_600_000
HERO_BUDGET = 4_000_000
# Clips the clip tool reported OVER BUDGET at its smallest rung; accepted
# as-is rather than trimmed (2026-11-17).
OVER_BUDGET_ACCEPTED = {"animation-fisheye.gif": 3_500_000}


def _references() -> set[str]:
    refs: set[str] = set()
    for page in CONTENT.rglob("*.mdx"):
        refs.update(re.findall(r"/filmed/([\w./-]+\.(?:gif|mp4))", page.read_text()))
    return refs


def _files() -> set[str]:
    return {
        str(p.relative_to(FILMED))
        for p in FILMED.rglob("*")
        if p.suffix in {".gif", ".mp4"}
    }


def test_every_filmed_reference_exists():
    missing = sorted(_references() - _files())
    assert not missing, f"pages reference filmed media that is not committed: {missing}"


def test_every_filmed_file_is_referenced():
    unused = sorted(_files() - _references())
    assert not unused, f"committed filmed media no page uses: {unused}"


def test_filmed_sizes_stay_inside_budget():
    over = {}
    for rel in _files():
        size = (FILMED / rel).stat().st_size
        name = Path(rel).name
        budget = OVER_BUDGET_ACCEPTED.get(name) or (
            HERO_BUDGET if rel.endswith(".mp4") else GIF_BUDGET
        )
        if size > budget:
            over[rel] = size
    assert not over, f"filmed media over budget (bytes): {over}"


def test_headers_cache_filmed_dir():
    assert "/filmed/*" in HEADERS.read_text()


def test_demo_gif_component_supports_video_and_filmed():
    src = DEMO_GIF.read_text()
    assert re.search(r"\bvideo\?: string", src), "DemoGif.astro lacks a `video` prop"
    assert re.search(r"\bfilmed\?: boolean", src), "DemoGif.astro lacks a `filmed` prop"
    assert "<video" in src and 'type="video/mp4"' in src


def test_homepage_hero_is_the_filmed_video():
    index = (CONTENT / "index.mdx").read_text()
    assert 'video="/filmed/hero.mp4"' in index
