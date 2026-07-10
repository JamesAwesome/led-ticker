"""Tests for the plugin upgrade resolver + verb (app/plugin_upgrade.py)."""

import pytest

from led_ticker.app import plugin_upgrade as up
from led_ticker.plugins_catalog import (
    Catalog,
    CatalogEntry,
    CatalogSource,
    PluginProvides,
)

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


def test_resolve_latest_pypi_non_dict_response_raises():
    def fetch(package):
        return ["not", "a", "dict"]

    with pytest.raises(up.UpgradeError):
        up.resolve_latest("led-ticker-pool==0.1.0", fetch_json=fetch)


def test_resolve_latest_pypi_malformed_release_files_raises():
    def fetch(package):
        return {
            "releases": {
                "0.1.0": [{"yanked": False}],
                "0.2.0": "not-a-list",
            }
        }

    with pytest.raises(up.UpgradeError):
        up.resolve_latest("led-ticker-pool==0.1.0", fetch_json=fetch)


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


# --- _latest_git: option/command-injection URLs are refused ------------------


def _tracking_runner():
    """A run_git fake that records calls and must NEVER actually be invoked
    for the injection cases below — asserted empty by the caller."""
    calls: list[list[str]] = []

    def run(args):
        calls.append(args)
        return ""

    run.calls = calls
    return run


def test_resolve_latest_git_rejects_ext_transport():
    run = _tracking_runner()
    with pytest.raises(up.UpgradeError):
        up.resolve_latest("git+ext::sh -c touch /tmp/pwned@main", run_git=run)
    assert run.calls == []


def test_resolve_latest_git_rejects_leading_dash_url():
    run = _tracking_runner()
    with pytest.raises(up.UpgradeError):
        up.resolve_latest("git+--upload-pack=touch /tmp/pwned@main", run_git=run)
    assert run.calls == []


def test_latest_git_passes_double_dash_before_url():
    """ls-remote invocations end option parsing with `--` before the url, even
    for an allowlisted scheme — belt-and-suspenders alongside the scheme check."""
    run = _git_runner(LS_REMOTE_TAGS)
    up.resolve_latest(f"{MONOREPO}@pool-v0.1.0#subdirectory=plugins/pool", run_git=run)
    tags_call = next(c for c in run.calls if "--tags" in c)
    assert tags_call == ["ls-remote", "--tags", "--", MONOREPO.removeprefix("git+")]


# --- _run_git -------------------------------------------------------------


def test_run_git_other_oserror_raises_upgrade_error(monkeypatch):
    def raiser(*args, **kwargs):
        raise PermissionError("not executable")

    monkeypatch.setattr(up.subprocess, "run", raiser)
    with pytest.raises(up.UpgradeError):
        up._run_git(["ls-remote", "x"])


# --- cmd_upgrade --------------------------------------------------------------


def _pool_catalog():
    entry = CatalogEntry(
        name="pool",
        namespace="pool",
        summary="Pool.",
        homepage="",
        provides=PluginProvides(widgets=("pool.monitor",)),
        sources=(
            CatalogSource(
                type="git",
                url="https://github.com/JamesAwesome/led-ticker-plugins",
                ref="pool-v0.1.0",
                subdirectory="plugins/pool",
            ),
        ),
    )
    return Catalog(entries=(entry,))


def _manifest(tmp_path, text):
    config = tmp_path / "config.toml"
    config.write_text("")
    (tmp_path / "requirements-plugins.txt").write_text(text)
    return config


def test_cmd_upgrade_rewrites_pin_with_provenance(tmp_path, monkeypatch, capsys):
    old = f"{MONOREPO}@pool-v0.1.0#subdirectory=plugins/pool"
    new = f"{MONOREPO}@pool-v0.2.0#subdirectory=plugins/pool"
    config = _manifest(tmp_path, old + "\n")
    monkeypatch.setattr(up, "resolve_latest", lambda line, **kw: new)
    code = up.cmd_upgrade("pool", config_path=config, catalog=_pool_catalog())
    assert code == 0
    text = (tmp_path / "requirements-plugins.txt").read_text()
    assert new in text
    assert "# upgraded" in text and "was" in text
    assert "restart" in capsys.readouterr().out.lower()


def test_cmd_upgrade_up_to_date_writes_nothing(tmp_path, monkeypatch, capsys):
    line = f"{MONOREPO}@pool-v0.2.0#subdirectory=plugins/pool"
    config = _manifest(tmp_path, line + "\n")
    monkeypatch.setattr(up, "resolve_latest", lambda ln, **kw: ln)
    before = (tmp_path / "requirements-plugins.txt").read_text()
    assert up.cmd_upgrade("pool", config_path=config, catalog=_pool_catalog()) == 0
    assert (tmp_path / "requirements-plugins.txt").read_text() == before
    out = capsys.readouterr().out.lower()
    assert "up to date" in out
    assert "installs on next startup" not in out


def test_cmd_upgrade_all_up_to_date_omits_restart_hint(tmp_path, monkeypatch, capsys):
    lines = [
        f"{MONOREPO}@pool-v0.2.0#subdirectory=plugins/pool",
        "led-ticker-crypto==0.9.0",
    ]
    config = _manifest(tmp_path, "\n".join(lines) + "\n")
    monkeypatch.setattr(up, "resolve_latest", lambda line, **kw: line)
    code = up.cmd_upgrade(
        None, config_path=config, catalog=_pool_catalog(), all_plugins=True
    )
    assert code == 0
    out = capsys.readouterr().out.lower()
    assert "installs on next startup" not in out


def test_cmd_upgrade_not_declared_is_error(tmp_path, capsys):
    config = _manifest(tmp_path, "# nothing declared\n")
    assert up.cmd_upgrade("pool", config_path=config, catalog=_pool_catalog()) == 2
    assert "not declared" in capsys.readouterr().err.lower()


def test_cmd_upgrade_resolver_failure_leaves_manifest(tmp_path, monkeypatch, capsys):
    old = f"{MONOREPO}@pool-v0.1.0#subdirectory=plugins/pool"
    config = _manifest(tmp_path, old + "\n")

    def boom(line, **kw):
        raise up.UpgradeError("no matching tags")

    monkeypatch.setattr(up, "resolve_latest", boom)
    assert up.cmd_upgrade("pool", config_path=config, catalog=_pool_catalog()) == 1
    assert (tmp_path / "requirements-plugins.txt").read_text() == old + "\n"
    assert "no matching tags" in capsys.readouterr().err


def test_cmd_upgrade_dry_run_writes_nothing(tmp_path, monkeypatch, capsys):
    old = f"{MONOREPO}@pool-v0.1.0#subdirectory=plugins/pool"
    new = f"{MONOREPO}@pool-v0.2.0#subdirectory=plugins/pool"
    config = _manifest(tmp_path, old + "\n")
    monkeypatch.setattr(up, "resolve_latest", lambda line, **kw: new)
    code = up.cmd_upgrade(
        "pool", config_path=config, catalog=_pool_catalog(), dry_run=True
    )
    assert code == 0
    assert (tmp_path / "requirements-plugins.txt").read_text() == old + "\n"
    out = capsys.readouterr().out
    assert "Dry run" in out and new in out


def test_cmd_upgrade_all_upgrades_every_line(tmp_path, monkeypatch):
    lines = [
        f"{MONOREPO}@pool-v0.1.0#subdirectory=plugins/pool",
        "led-ticker-crypto==0.1.0",
    ]
    config = _manifest(tmp_path, "\n".join(lines) + "\n")
    monkeypatch.setattr(
        up,
        "resolve_latest",
        lambda line, **kw: line.replace("0.1.0", "0.9.0"),
    )
    code = up.cmd_upgrade(
        None, config_path=config, catalog=_pool_catalog(), all_plugins=True
    )
    assert code == 0
    text = (tmp_path / "requirements-plugins.txt").read_text()
    assert "pool-v0.9.0" in text
    assert "led-ticker-crypto==0.9.0" in text


def test_cmd_upgrade_all_aggregates_failures(tmp_path, monkeypatch):
    lines = [
        f"{MONOREPO}@pool-v0.1.0#subdirectory=plugins/pool",
        "led-ticker-crypto==0.1.0",
    ]
    config = _manifest(tmp_path, "\n".join(lines) + "\n")

    def flaky(line, **kw):
        if "crypto" in line:
            raise up.UpgradeError("pypi down")
        return line.replace("0.1.0", "0.9.0")

    monkeypatch.setattr(up, "resolve_latest", flaky)
    code = up.cmd_upgrade(
        None, config_path=config, catalog=_pool_catalog(), all_plugins=True
    )
    assert code == 1  # partial failure
    text = (tmp_path / "requirements-plugins.txt").read_text()
    assert "pool-v0.9.0" in text  # the good one still upgraded
    assert "led-ticker-crypto==0.1.0" in text  # the bad one untouched


# --- non-default-source declaration ------------------------------------------
# Regression: a catalog entry ships multiple sources (pypi default + git); a
# plugin declared via `--source git` must still be found by the upgrade verb
# (was 404/"not declared" when keyed only off the pypi-default source).

from led_ticker.app.plugin_cmd import (  # noqa: E402
    _entry_match_keys,
    _find_requirement_lines_for_keys,
)


def _pool_multisource_entry():
    return CatalogEntry(
        name="pool",
        namespace="pool",
        summary="Pool.",
        homepage="",
        provides=PluginProvides(widgets=("pool.monitor",)),
        sources=(
            CatalogSource(type="pypi", package="led-ticker-pool", version="0.1.0"),
            CatalogSource(
                type="git",
                url="https://github.com/JamesAwesome/led-ticker-plugins",
                ref="pool-v0.1.0",
                subdirectory="plugins/pool",
            ),
        ),
    )


def test_entry_match_keys_covers_all_sources():
    keys = _entry_match_keys(_pool_multisource_entry())
    # pypi key (from the default source) AND the git repo#subdir key.
    assert "led-ticker-pool" in keys
    assert "led-ticker-plugins#plugins/pool" in keys


def test_find_requirement_lines_for_keys_matches_any(tmp_path):
    path = tmp_path / "requirements-plugins.txt"
    path.write_text(
        "led-ticker-crypto==0.1.0\n"
        f"{MONOREPO}.git@pool-v0.1.0#subdirectory=plugins/pool\n"
    )
    found = _find_requirement_lines_for_keys(path, {"led-ticker-plugins#plugins/pool"})
    assert len(found) == 1
    assert "pool-v0.1.0" in found[0]


def test_cmd_upgrade_finds_non_default_source_declaration(tmp_path, monkeypatch):
    """pool's catalog default is pypi, but it's declared here via its git
    source — the upgrade verb must still find + rewrite that line, not 404."""
    entry = _pool_multisource_entry()
    git_line = entry.requirement(source="git")  # git+...@pool-v0.1.0#subdirectory=...
    config = _manifest(tmp_path, git_line + "\n")
    new_line = git_line.replace("pool-v0.1.0", "pool-v0.2.0")
    monkeypatch.setattr(up, "resolve_latest", lambda line, **kw: new_line)
    code = up.cmd_upgrade("pool", config_path=config, catalog=Catalog(entries=(entry,)))
    assert code == 0
    text = (tmp_path / "requirements-plugins.txt").read_text()
    assert "pool-v0.2.0" in text
    assert "# upgraded" in text
