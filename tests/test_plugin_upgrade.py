"""Tests for the plugin upgrade resolver + verb (app/plugin_upgrade.py)."""

from led_ticker.app import plugin_upgrade as up

# --- _parse_version -----------------------------------------------------------


def test_parse_version_basic():
    assert up._parse_version("0.2.0") == (0, 2, 0)
    assert up._parse_version("10.31") == (10, 31)


def test_parse_version_rejects_prerelease_and_garbage():
    assert up._parse_version("1.2.0rc1") is None
    assert up._parse_version("1.2.0-beta") is None
    assert up._parse_version("main") is None
    assert up._parse_version("") is None


def test_parse_version_orders_numerically_not_lexically():
    assert up._parse_version("0.10.0") > up._parse_version("0.9.9")


# --- git line split / join ----------------------------------------------------

MONOREPO = "git+https://github.com/JamesAwesome/led-ticker-plugins"


def test_split_git_line_full():
    base, ref, frag = up._split_git_line(
        f"{MONOREPO}@pool-v0.1.0#subdirectory=plugins/pool"
    )
    assert base == MONOREPO
    assert ref == "pool-v0.1.0"
    assert frag == "subdirectory=plugins/pool"


def test_split_git_line_no_ref():
    base, ref, frag = up._split_git_line(f"{MONOREPO}#subdirectory=plugins/pool")
    assert base == MONOREPO
    assert ref is None
    assert frag == "subdirectory=plugins/pool"


def test_split_git_line_no_fragment():
    base, ref, frag = up._split_git_line(f"{MONOREPO}@main")
    assert (base, ref, frag) == (MONOREPO, "main", None)


def test_split_git_line_ref_with_slash():
    # A ref may contain '/'; the '@' cut must happen after the URL path begins.
    base, ref, frag = up._split_git_line(f"{MONOREPO}@feature/foo")
    assert ref == "feature/foo"


def test_join_git_line_roundtrip():
    line = f"{MONOREPO}@pool-v0.2.0#subdirectory=plugins/pool"
    assert up._join_git_line(*up._split_git_line(line)) == line


def test_join_git_line_no_fragment():
    assert up._join_git_line(MONOREPO, "abc123", None) == f"{MONOREPO}@abc123"
