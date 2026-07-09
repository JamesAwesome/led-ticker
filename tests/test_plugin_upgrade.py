"""Tests for the plugin upgrade resolver + verb (app/plugin_upgrade.py)."""

import pytest

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


# --- resolve_latest: pypi -----------------------------------------------------


def _pypi_fetcher(releases):
    """Fake fetch_json returning a minimal PyPI JSON payload."""

    def fetch(package):
        return {"releases": releases}

    return fetch


def test_resolve_latest_pypi_pinned_moves_to_newest():
    fetch = _pypi_fetcher(
        {
            "0.1.0": [{"yanked": False}],
            "0.2.0": [{"yanked": False}],
            "0.10.0": [{"yanked": False}],
        }
    )
    got = up.resolve_latest("led-ticker-pool==0.1.0", fetch_json=fetch)
    assert got == "led-ticker-pool==0.10.0"


def test_resolve_latest_pypi_unpinned_gets_pin():
    fetch = _pypi_fetcher({"0.3.0": [{"yanked": False}]})
    assert up.resolve_latest("led-ticker-pool", fetch_json=fetch) == (
        "led-ticker-pool==0.3.0"
    )


def test_resolve_latest_pypi_skips_yanked_and_prerelease_and_empty():
    fetch = _pypi_fetcher(
        {
            "0.2.0": [{"yanked": False}],
            "0.3.0": [{"yanked": True}],  # all files yanked
            "0.4.0rc1": [{"yanked": False}],  # prerelease (unparseable)
            "0.5.0": [],  # no files uploaded
        }
    )
    got = up.resolve_latest("led-ticker-pool==0.1.0", fetch_json=fetch)
    assert got == "led-ticker-pool==0.2.0"


def test_resolve_latest_pypi_no_candidates_raises():
    fetch = _pypi_fetcher({"0.4.0rc1": [{"yanked": False}]})
    with pytest.raises(up.UpgradeError):
        up.resolve_latest("led-ticker-pool==0.1.0", fetch_json=fetch)


def test_resolve_latest_pypi_fetch_failure_raises():
    def boom(package):
        raise up.UpgradeError("network down")

    with pytest.raises(up.UpgradeError, match="network down"):
        up.resolve_latest("led-ticker-pool==0.1.0", fetch_json=boom)


# --- resolve_latest: git ------------------------------------------------------

LS_REMOTE_TAGS = """\
aaa111\trefs/tags/baseball-v0.3.0
bbb222\trefs/tags/pool-v0.1.0
ccc333\trefs/tags/pool-v0.2.0
ddd444\trefs/tags/pool-v0.2.0^{}
eee555\trefs/tags/pool-v0.3.0rc1
"""


def _git_runner(tags_output, head_output="fff999\tHEAD\n"):
    calls = []

    def run(args):
        calls.append(args)
        if "--tags" in args:
            return tags_output
        return head_output

    run.calls = calls
    return run


def test_resolve_latest_git_bumps_ref_to_newest_matching_tag():
    run = _git_runner(LS_REMOTE_TAGS)
    got = up.resolve_latest(
        f"{MONOREPO}@pool-v0.1.0#subdirectory=plugins/pool", run_git=run
    )
    assert got == f"{MONOREPO}@pool-v0.2.0#subdirectory=plugins/pool"


def test_resolve_latest_git_prefix_from_subdirectory_basename():
    # Prefix comes from the subdirectory basename even when tracking a branch.
    run = _git_runner(LS_REMOTE_TAGS)
    got = up.resolve_latest(f"{MONOREPO}@main#subdirectory=plugins/pool", run_git=run)
    assert got == f"{MONOREPO}@pool-v0.2.0#subdirectory=plugins/pool"


def test_resolve_latest_git_prefix_from_catalog_name():
    # No subdirectory: fall back to the catalog entry name.
    run = _git_runner("abc\trefs/tags/pool-v0.9.0\n")
    got = up.resolve_latest(f"{MONOREPO}@main", catalog_name="pool", run_git=run)
    assert got == f"{MONOREPO}@pool-v0.9.0"


def test_resolve_latest_git_plain_v_tags_for_single_plugin_repo():
    run = _git_runner("abc\trefs/tags/v1.2.0\nxyz\trefs/tags/v1.10.0\n")
    got = up.resolve_latest(
        "git+https://github.com/x/led-ticker-solo@main", run_git=run
    )
    assert got == "git+https://github.com/x/led-ticker-solo@v1.10.0"


def test_resolve_latest_git_no_tags_falls_back_to_branch_sha():
    run = _git_runner("", head_output="fff999\trefs/heads/main\n")
    got = up.resolve_latest(f"{MONOREPO}@main#subdirectory=plugins/pool", run_git=run)
    assert got == f"{MONOREPO}@fff999#subdirectory=plugins/pool"
    # SHA lookup asked for the branch the line was tracking.
    assert run.calls[-1][-1] == "main"


def test_resolve_latest_git_sha_fallback_empty_raises():
    run = _git_runner("", head_output="")
    with pytest.raises(up.UpgradeError):
        up.resolve_latest(f"{MONOREPO}@main", run_git=run)


def test_resolve_latest_rejects_editable_and_unknown_forms():
    with pytest.raises(up.UpgradeError):
        up.resolve_latest("-e git+https://github.com/x/y@main")
    with pytest.raises(up.UpgradeError):
        up.resolve_latest("https://example.com/wheel.whl")
