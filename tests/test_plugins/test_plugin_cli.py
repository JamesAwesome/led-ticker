"""`led-ticker plugin list/search/install` command behavior.

pip is always mocked — no real install, no network. The filesystem uses tmp_path.
"""

from pathlib import Path
from types import SimpleNamespace

import pytest

from led_ticker.app import plugin_cmd
from led_ticker.plugins_catalog import (
    Catalog,
    CatalogEntry,
    CatalogSource,
    PluginProvides,
)


def _catalog():
    return Catalog(
        entries=(
            CatalogEntry(
                name="pool",
                namespace="pool",
                summary="Pool water temperature",
                homepage="https://github.com/JamesAwesome/led-ticker-pool",
                provides=PluginProvides(widgets=("pool.monitor",)),
                sources=(
                    CatalogSource(
                        type="git",
                        url="https://github.com/JamesAwesome/led-ticker-pool",
                        ref="v1.2.0",
                    ),
                    CatalogSource(
                        type="pypi", package="led-ticker-pool", version="1.2.0"
                    ),
                ),
            ),
        )
    )


class _FakePip:
    """Records pip subprocess calls; configurable exit codes."""

    def __init__(self, freeze_rc=0, install_rc=0, uninstall_rc=0):
        self.calls: list[list[str]] = []
        self.freeze_rc = freeze_rc
        self.install_rc = install_rc
        self.uninstall_rc = uninstall_rc

    def run(self, cmd, **kwargs):
        self.calls.append(cmd)
        if "list" in cmd:  # pip list --format=freeze
            return SimpleNamespace(
                returncode=self.freeze_rc, stdout="led-ticker==1.0\n", stderr="err"
            )
        if "uninstall" in cmd:
            return SimpleNamespace(returncode=self.uninstall_rc, stdout="", stderr="")
        return SimpleNamespace(returncode=self.install_rc, stdout="", stderr="boom")

    @property
    def install_cmd(self):
        return next((c for c in self.calls if "install" in c), None)

    @property
    def uninstall_cmd(self):
        return next((c for c in self.calls if "uninstall" in c), None)


@pytest.fixture
def fakepip(monkeypatch):
    fp = _FakePip()
    monkeypatch.setattr(plugin_cmd.subprocess, "run", fp.run)
    return fp


def _reqfile(tmp_path):
    return tmp_path / "requirements-plugins.txt"


def _install(tmp_path, target, **kw):
    return plugin_cmd.cmd_install(
        target, config_path=tmp_path / "config.toml", catalog=_catalog(), **kw
    )


def _add(tmp_path, target, **kw):
    return plugin_cmd.cmd_add(
        target, config_path=tmp_path / "config.toml", catalog=_catalog(), **kw
    )


def _remove(tmp_path, target, **kw):
    return plugin_cmd.cmd_remove(
        target, config_path=tmp_path / "config.toml", catalog=_catalog(), **kw
    )


def _uninstall(tmp_path, target, **kw):
    return plugin_cmd.cmd_uninstall(
        target, config_path=tmp_path / "config.toml", catalog=_catalog(), **kw
    )


def test_install_catalog_git_pinned(tmp_path, fakepip):
    code = _install(tmp_path, "pool")
    assert code == 0
    line = "git+https://github.com/JamesAwesome/led-ticker-pool.git@v1.2.0"
    assert _reqfile(tmp_path).read_text().strip().splitlines()[-1] == line
    assert fakepip.install_cmd[-1] == line
    assert "-c" in fakepip.install_cmd  # constraint-based


def test_install_unpinned_writes_main(tmp_path, fakepip):
    _install(tmp_path, "pool", pinned=False)
    assert _reqfile(tmp_path).read_text().strip().endswith("led-ticker-pool.git@main")


def test_install_source_pypi(tmp_path, fakepip):
    _install(tmp_path, "pool", source="pypi")
    assert "led-ticker-pool==1.2.0" in _reqfile(tmp_path).read_text()
    assert fakepip.install_cmd[-1] == "led-ticker-pool==1.2.0"


def test_install_raw_pip_spec_bypasses_catalog(tmp_path, fakepip):
    spec = "git+https://github.com/acme/led-ticker-acme.git@main"
    code = _install(tmp_path, spec)
    assert code == 0
    assert spec in _reqfile(tmp_path).read_text()
    assert fakepip.install_cmd[-1] == spec


def test_install_source_on_raw_spec_errors(tmp_path, fakepip):
    code = _install(tmp_path, "led-ticker-acme==1.0", source="git")
    assert code == 2
    assert fakepip.install_cmd is None  # never installed
    assert not _reqfile(tmp_path).exists()


def test_add_writes_manifest_without_pip(tmp_path, fakepip):
    code = _add(tmp_path, "pool")
    assert code == 0
    line = "git+https://github.com/JamesAwesome/led-ticker-pool.git@v1.2.0"
    assert _reqfile(tmp_path).read_text().strip().splitlines()[-1] == line
    assert fakepip.calls == []  # pip never invoked


def test_install_dry_run_changes_nothing(tmp_path, fakepip, capsys):
    code = _install(tmp_path, "pool", dry_run=True)
    assert code == 0
    assert not _reqfile(tmp_path).exists()
    assert fakepip.calls == []
    assert "Dry run" in capsys.readouterr().out


def test_install_dedup_replaces_existing_line(tmp_path, fakepip):
    _install(tmp_path, "pool")  # pinned
    _install(tmp_path, "pool", pinned=False)  # re-install unpinned
    body = _reqfile(tmp_path).read_text()
    assert body.count("led-ticker-pool") == 1  # replaced, not duplicated
    assert "@main" in body


def _monorepo_catalog():
    """Two plugins sharing ONE repo (`led-ticker-plugins`) — the monorepo layout.
    Distinguished only by their `#subdirectory=` fragment."""
    repo = "https://github.com/JamesAwesome/led-ticker-plugins"

    def _entry(name):
        return CatalogEntry(
            name=name,
            namespace=name,
            summary=f"{name} plugin",
            homepage=repo,
            provides=PluginProvides(widgets=(f"{name}.thing",)),
            sources=(
                CatalogSource(
                    type="git",
                    url=repo,
                    ref=f"{name}-v0.1.0",
                    subdirectory=f"plugins/{name}",
                ),
            ),
        )

    return Catalog(entries=(_entry("pool"), _entry("baseball")))


def test_add_monorepo_siblings_do_not_collide(tmp_path, fakepip):
    # Regression: before the subdirectory-aware key, all monorepo plugins keyed to
    # `led-ticker-plugins`, so adding `baseball` after `pool` REPLACED pool's line
    # (dedup collision). Both lines must now survive.
    catalog = _monorepo_catalog()
    cfg = tmp_path / "config.toml"
    assert plugin_cmd.cmd_add("pool", config_path=cfg, catalog=catalog) == 0
    assert plugin_cmd.cmd_add("baseball", config_path=cfg, catalog=catalog) == 0
    body = _reqfile(tmp_path).read_text()
    assert "subdirectory=plugins/pool" in body
    assert "subdirectory=plugins/baseball" in body
    assert fakepip.calls == []  # add never touches pip


def test_install_preserves_comments_and_other_plugins(tmp_path, fakepip):
    rf = _reqfile(tmp_path)
    rf.write_text(
        "# my plugins\ngit+https://github.com/acme/led-ticker-acme.git@main\n"
    )
    _install(tmp_path, "pool")
    body = rf.read_text()
    assert "# my plugins" in body
    assert "led-ticker-acme" in body
    assert "led-ticker-pool" in body


def test_install_creates_missing_requirements_file(tmp_path, fakepip):
    assert not _reqfile(tmp_path).exists()
    _install(tmp_path, "pool")
    assert _reqfile(tmp_path).exists()


def test_install_pip_failure_returns_nonzero(tmp_path, monkeypatch):
    fp = _FakePip(install_rc=1)
    monkeypatch.setattr(plugin_cmd.subprocess, "run", fp.run)
    code = _install(tmp_path, "pool")
    assert code == 1  # surfaced pip exit code
    # the requirements file was still updated (documented behavior)
    assert _reqfile(tmp_path).exists()


def test_install_freeze_failure_aborts_before_install(tmp_path, monkeypatch):
    fp = _FakePip(freeze_rc=2)
    monkeypatch.setattr(plugin_cmd.subprocess, "run", fp.run)
    code = _install(tmp_path, "pool")
    assert code == 2
    assert fp.install_cmd is None  # never reached install


# --- catalog name resolution (case + typo did-you-mean) ---


def test_install_catalog_name_is_case_insensitive(tmp_path, fakepip):
    # `install Pool` must resolve the catalog entry, not fall through to raw pip.
    _install(tmp_path, "Pool")
    line = "git+https://github.com/JamesAwesome/led-ticker-pool.git@v1.2.0"
    assert _reqfile(tmp_path).read_text().strip().splitlines()[-1] == line


def test_install_typo_suggests_catalog_name_without_installing(
    tmp_path, fakepip, capsys
):
    code = _install(tmp_path, "poool")  # typo close to "pool"
    assert code == 2
    assert fakepip.install_cmd is None  # never pip-installed an arbitrary package
    assert not _reqfile(tmp_path).exists()
    # the hint steers an `install` user back to `install` (the pip verb)
    assert "led-ticker plugin install pool" in capsys.readouterr().err


def test_add_typo_suggests_add_verb_not_install(tmp_path, fakepip, capsys):
    # A Docker user who typos `add` must be steered back to `add` (no pip),
    # NOT to `install` (the whole point of the Docker-first verb split).
    code = _add(tmp_path, "poool")  # typo close to "pool"
    assert code == 2
    assert fakepip.calls == []
    assert not _reqfile(tmp_path).exists()
    err = capsys.readouterr().err
    assert "led-ticker plugin add pool" in err
    assert "plugin install" not in err


def test_install_unrelated_bare_name_still_raw_installs(tmp_path, fakepip):
    # A bare name that ISN'T close to any catalog name is a legit raw PyPI install.
    code = _install(tmp_path, "requests")
    assert code == 0
    assert "requests" in _reqfile(tmp_path).read_text()
    assert fakepip.install_cmd[-1] == "requests"


def test_install_dedup_handles_slash_ref(tmp_path, fakepip):
    # Re-pinning the same plugin to a slash branch must replace, not duplicate.
    _install(tmp_path, "git+https://h/o/led-ticker-pool.git@main")
    _install(tmp_path, "git+https://h/o/led-ticker-pool.git@feature/x")
    assert _reqfile(tmp_path).read_text().count("led-ticker-pool") == 1


# --- requirements-file location (config/ default + warning) ---


def test_install_defaults_to_config_dir_without_explicit_config(
    tmp_path, fakepip, monkeypatch
):
    # No explicit --config -> the canonical config/requirements-plugins.txt,
    # not the cwd (so Docker reads it from the config volume).
    monkeypatch.chdir(tmp_path)
    plugin_cmd.cmd_install(
        "pool",
        config_path=Path("config.toml"),
        config_explicit=False,
        catalog=_catalog(),
    )
    assert (tmp_path / "config" / "requirements-plugins.txt").exists()
    assert not (tmp_path / "requirements-plugins.txt").exists()


def test_install_warns_when_writing_outside_config_dir(tmp_path, fakepip, capsys):
    # An explicit config not under config/ -> the file lands there but warns.
    plugin_cmd.cmd_install(
        "pool",
        config_path=tmp_path / "config.toml",
        config_explicit=True,
        catalog=_catalog(),
    )
    assert "not under a 'config/'" in capsys.readouterr().err


def test_install_unwritable_path_clean_error(tmp_path, fakepip, monkeypatch, capsys):
    # A write failure (read-only dir / root-owned config) must be a clean message
    # + exit 2, not a raw traceback (matches validate/webui/status).
    def boom(*a, **k):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(plugin_cmd, "_update_requirements", boom)
    code = _install(tmp_path, "pool")
    assert code == 2
    assert "could not write" in capsys.readouterr().err
    assert fakepip.install_cmd is None  # never reached pip


def test_install_preserves_inline_comment_and_echoes_old(tmp_path, fakepip, capsys):
    # Re-installing over a hand-pinned, annotated line must keep the comment and
    # surface the old line (not silently drop a deliberate prod pin).
    rf = _reqfile(tmp_path)
    rf.write_text("led-ticker-pool==1.4.0  # pinned for prod, do NOT bump\n")
    _install(tmp_path, "pool", source="pypi")  # -> led-ticker-pool==1.2.0
    body = rf.read_text()
    assert "# pinned for prod, do NOT bump" in body  # comment retained
    assert body.count("led-ticker-pool") == 1  # still deduped
    out = capsys.readouterr().out
    assert "1.4.0" in out and "Replaced" in out  # old line surfaced


def test_update_does_not_mangle_egg_fragment_on_replace(tmp_path):
    # A '#egg=' fragment is part of a git URL, NOT a pip comment — re-adding over
    # an egg-bearing line must not carry it as a trailing comment (which would
    # duplicate it or demote a URL fragment into a comment, changing the spec).
    rf = _reqfile(tmp_path)
    rf.write_text("git+https://h/o/led-ticker-pool.git@main#egg=led-ticker-pool\n")
    # re-add catalog-style (no egg) — the egg must NOT reappear as a comment
    new = "git+https://h/o/led-ticker-pool.git@v2"
    plugin_cmd._update_requirements(rf, new)
    body = rf.read_text()
    assert "#" not in body  # no stray '  #egg=' comment
    assert body.strip() == new


def test_update_still_carries_a_real_inline_comment(tmp_path):
    # Whitespace-delimited '#' is a genuine comment and must still be carried.
    rf = _reqfile(tmp_path)
    rf.write_text("led-ticker-pool==1.4.0  # prod pin\n")
    plugin_cmd._update_requirements(rf, "led-ticker-pool==1.5.0")
    body = rf.read_text()
    assert "led-ticker-pool==1.5.0" in body
    assert "# prod pin" in body


@pytest.mark.parametrize(
    "line,comment",
    [
        ("pkg==1.0  # prod pin", "# prod pin"),
        ("pkg==1.0\t#note", "#note"),
        ("# whole line comment", "# whole line comment"),
        ("git+https://h/o/p.git@main#egg=p", None),  # URL fragment, not a comment
        ("git+https://h/o/p.git@main#subdirectory=x", None),
        ("pkg==1.0", None),
    ],
)
def test_trailing_comment_matches_pip_rules(line, comment):
    assert plugin_cmd._trailing_comment(line) == comment


# --- list / search ---


def test_cmd_list_prints_catalog(capsys):
    plugin_cmd.cmd_list(catalog=_catalog())
    out = capsys.readouterr().out
    assert "pool" in out
    assert "pool.monitor" in out


def test_cmd_list_marks_installed(monkeypatch, capsys):
    # _installed_namespaces() goes through importlib.metadata.entry_points, which
    # the hermetic stub patches — so this also proves that path is reachable.
    import importlib.metadata
    from types import SimpleNamespace

    def fake_eps(*a, **k):
        if k.get("group") == "led_ticker.plugins":
            return [SimpleNamespace(name="pool")]
        return []

    monkeypatch.setattr(importlib.metadata, "entry_points", fake_eps)
    plugin_cmd.cmd_list(catalog=_catalog())
    out = capsys.readouterr().out
    assert "[installed]" in out


def test_cmd_search_filters(capsys):
    plugin_cmd.cmd_search("water", catalog=_catalog())
    assert "pool" in capsys.readouterr().out


def test_cmd_search_no_match(capsys):
    plugin_cmd.cmd_search("zzznope", catalog=_catalog())
    assert "No plugins match" in capsys.readouterr().out


# --- dedup key normalization ---


@pytest.mark.parametrize(
    "requirement,key",
    [
        ("git+https://h/o/led-ticker-pool.git@v1.2.0", "led-ticker-pool"),
        ("git+https://h/o/led-ticker-pool.git@main", "led-ticker-pool"),
        # slash-containing refs (feature/, release/) must NOT leak into the key
        ("git+https://h/o/led-ticker-pool.git@feature/foo", "led-ticker-pool"),
        ("git+https://h/o/led-ticker-pool.git@release/1.x", "led-ticker-pool"),
        ("git+https://h/o/led-ticker-pool@main", "led-ticker-pool"),  # no .git
        # #egg= fragment is stripped (it's a name hint, not identity)
        (
            "git+https://h/o/led-ticker-pool.git@main#egg=led-ticker-pool",
            "led-ticker-pool",
        ),
        # monorepo: #subdirectory= is PRESERVED so siblings don't collide. The
        # subdirectory path is kept verbatim (not case-folded / '_'->'-').
        (
            "git+https://github.com/JamesAwesome/led-ticker-plugins.git"
            "@pool-v0.1.0#subdirectory=plugins/pool",
            "led-ticker-plugins#plugins/pool",
        ),
        (
            "git+https://github.com/JamesAwesome/led-ticker-plugins.git"
            "@sailor_moon-v0.1.0#subdirectory=plugins/sailor_moon",
            "led-ticker-plugins#plugins/sailor_moon",
        ),
        # #egg= + subdirectory together: egg dropped, subdirectory kept.
        (
            "git+https://h/o/led-ticker-plugins.git@main"
            "#egg=led-ticker-pool&subdirectory=plugins/pool",
            "led-ticker-plugins#plugins/pool",
        ),
        ("led-ticker-pool==1.2.0", "led-ticker-pool"),
        ("led_ticker_pool", "led-ticker-pool"),
        ("led-ticker-pool>=1.0", "led-ticker-pool"),
        # a genuine trailing comment (pip semantics: '#' at line-start or after
        # whitespace) must be stripped BEFORE parsing so it can't fuse with a
        # '#subdirectory=' fragment and corrupt the key.
        (
            "git+https://github.com/JamesAwesome/led-ticker-plugins@main"
            "#subdirectory=plugins/pool  # upgraded 2026-07-09",
            "led-ticker-plugins#plugins/pool",
        ),
        (
            "led-ticker-pool==0.2.0  # upgraded 2026-07-09, was ==0.1.0",
            "led-ticker-pool",
        ),
    ],
)
def test_requirement_key_normalizes(requirement, key):
    assert plugin_cmd._requirement_key(requirement) == key


# --- add / remove / uninstall (manifest verbs) ---


def test_add_prints_restart_hint(tmp_path, fakepip, capsys):
    _add(tmp_path, "pool")
    out = capsys.readouterr().out.lower()
    assert "restart" in out
    assert "no rebuild" in out


def test_add_dry_run_changes_nothing(tmp_path, fakepip):
    code = _add(tmp_path, "pool", dry_run=True)
    assert code == 0
    assert not _reqfile(tmp_path).exists()
    assert fakepip.calls == []


def test_remove_drops_line_no_pip(tmp_path, fakepip):
    _add(tmp_path, "pool")
    code = _remove(tmp_path, "pool")
    assert code == 0
    assert "led-ticker-pool" not in _reqfile(tmp_path).read_text()
    assert fakepip.calls == []  # remove never touches pip


def test_remove_by_raw_spec(tmp_path, fakepip):
    rf = _reqfile(tmp_path)
    rf.write_text("git+https://h/o/led-ticker-pool.git@feature/x\n")
    _remove(tmp_path, "git+https://h/o/led-ticker-pool.git@main")
    assert "led-ticker-pool" not in rf.read_text()


def test_remove_not_in_manifest_is_clean(tmp_path, fakepip, capsys):
    code = _remove(tmp_path, "pool")  # nothing declared
    assert code == 0
    assert "not in" in capsys.readouterr().out
    assert fakepip.calls == []


def test_remove_preserves_other_lines_and_comments(tmp_path, fakepip):
    rf = _reqfile(tmp_path)
    rf.write_text(
        "# my plugins\n"
        "git+https://github.com/JamesAwesome/led-ticker-pool.git@main\n"
        "git+https://h/o/led-ticker-acme.git@main\n"
    )
    _remove(tmp_path, "pool")
    body = rf.read_text()
    assert "# my plugins" in body
    assert "led-ticker-acme" in body
    assert "led-ticker-pool" not in body


def test_remove_drifted_manifest_drops_all_and_reports_count(tmp_path, fakepip, capsys):
    # A drifted manifest with two lines normalizing to the same key: BOTH are
    # removed, and the report names the count (not just the last line).
    rf = _reqfile(tmp_path)
    rf.write_text(
        "git+https://github.com/JamesAwesome/led-ticker-pool.git@main\n"
        "led-ticker-pool==1.2.0\n"
    )
    code = _remove(tmp_path, "pool")
    assert code == 0
    assert "led-ticker-pool" not in rf.read_text()  # both gone
    out = capsys.readouterr().out
    assert "2 lines" in out and "led-ticker-pool" in out


def test_remove_dry_run_drifted_manifest_reports_count(tmp_path, fakepip, capsys):
    rf = _reqfile(tmp_path)
    rf.write_text(
        "git+https://github.com/JamesAwesome/led-ticker-pool.git@main\n"
        "led-ticker-pool==1.2.0\n"
    )
    code = _remove(tmp_path, "pool", dry_run=True)
    assert code == 0
    assert "2 lines" in capsys.readouterr().out
    # dry-run leaves the file untouched
    assert rf.read_text().count("led-ticker-pool") == 2


def test_uninstall_removes_line_and_pip_uninstalls(tmp_path, fakepip):
    _add(tmp_path, "pool")
    code = _uninstall(tmp_path, "pool")
    assert code == 0
    assert "led-ticker-pool" not in _reqfile(tmp_path).read_text()
    assert fakepip.uninstall_cmd[-1] == "led-ticker-pool"


def test_uninstall_not_in_manifest_still_pip_uninstalls(tmp_path, fakepip, capsys):
    code = _uninstall(tmp_path, "pool")  # never added
    assert code == 0
    assert "was not in" in capsys.readouterr().out
    assert fakepip.uninstall_cmd[-1] == "led-ticker-pool"


def test_uninstall_monorepo_uses_dist_name_not_subdir_key(tmp_path, fakepip):
    # For a monorepo plugin the manifest line is keyed by repo#subdirectory, but
    # pip must uninstall the real package name `led-ticker-<name>` — NOT
    # `led-ticker-plugins` (the shared repo) or the subdirectory key.
    catalog = _monorepo_catalog()
    cfg = tmp_path / "config.toml"
    assert plugin_cmd.cmd_add("pool", config_path=cfg, catalog=catalog) == 0
    plugin_cmd.cmd_add("baseball", config_path=cfg, catalog=catalog)
    code = plugin_cmd.cmd_uninstall("pool", config_path=cfg, catalog=catalog)
    assert code == 0
    body = _reqfile(tmp_path).read_text()
    # only pool's line removed; baseball's survives (no collision on removal)
    assert "subdirectory=plugins/pool" not in body
    assert "subdirectory=plugins/baseball" in body
    # pip uninstalled the real dist name, not the shared repo
    assert fakepip.uninstall_cmd[-1] == "led-ticker-pool"


def test_uninstall_dry_run(tmp_path, fakepip):
    code = _uninstall(tmp_path, "pool", dry_run=True)
    assert code == 0
    assert fakepip.calls == []


def test_uninstall_pip_failure_returns_nonzero_after_removing_line(
    tmp_path, monkeypatch, capsys
):
    # The manifest line is removed first; a non-zero pip uninstall is then
    # surfaced as the exit code (the line stays removed — documented behavior).
    fp = _FakePip(uninstall_rc=1)
    monkeypatch.setattr(plugin_cmd.subprocess, "run", fp.run)
    _add(tmp_path, "pool")  # manifest-only, never touches pip
    code = _uninstall(tmp_path, "pool")
    assert code == 1  # surfaced pip exit code
    assert "led-ticker-pool" not in _reqfile(tmp_path).read_text()  # line removed
    assert "may not have been installed" in capsys.readouterr().err


# --- idempotent add / dry-run wording / config-dir warnings on remove ---


def test_add_twice_is_idempotent_byte_identical(tmp_path, fakepip, capsys):
    # Re-adding the same pin reports "already declared" and leaves the file
    # byte-for-byte unchanged (no churn, no spurious "Replaced").
    _add(tmp_path, "pool")
    first = _reqfile(tmp_path).read_bytes()
    capsys.readouterr()  # drain
    code = _add(tmp_path, "pool")
    assert code == 0
    assert _reqfile(tmp_path).read_bytes() == first  # unchanged
    assert "already declared" in capsys.readouterr().out


def test_remove_dry_run_not_found_wording(tmp_path, fakepip, capsys):
    code = _remove(tmp_path, "pool", dry_run=True)  # nothing declared
    assert code == 0
    out = capsys.readouterr().out
    assert "nothing to remove" in out
    assert fakepip.calls == []


def test_remove_dry_run_shows_line_to_remove(tmp_path, fakepip, capsys):
    _add(tmp_path, "pool")
    capsys.readouterr()  # drain
    code = _remove(tmp_path, "pool", dry_run=True)
    assert code == 0
    out = capsys.readouterr().out
    assert "would remove" in out and "led-ticker-pool" in out
    # dry-run must not actually modify the file
    assert "led-ticker-pool" in _reqfile(tmp_path).read_text()


def test_remove_warns_when_outside_config_dir(tmp_path, fakepip, capsys):
    rf = _reqfile(tmp_path)
    rf.write_text("git+https://h/o/led-ticker-pool.git@main\n")
    plugin_cmd.cmd_remove(
        "pool",
        config_path=tmp_path / "config.toml",
        config_explicit=True,
        catalog=_catalog(),
    )
    assert "not under a 'config/'" in capsys.readouterr().err


def test_uninstall_warns_when_outside_config_dir(tmp_path, fakepip, capsys):
    rf = _reqfile(tmp_path)
    rf.write_text("git+https://h/o/led-ticker-pool.git@main\n")
    plugin_cmd.cmd_uninstall(
        "pool",
        config_path=tmp_path / "config.toml",
        config_explicit=True,
        catalog=_catalog(),
    )
    assert "not under a 'config/'" in capsys.readouterr().err


# --- list [declared] / [installed] ---


def test_cmd_list_marks_declared(tmp_path, fakepip, capsys):
    _add(tmp_path, "pool")  # writes tmp_path/requirements-plugins.txt
    plugin_cmd.cmd_list(
        catalog=_catalog(),
        config_path=tmp_path / "config.toml",
        config_explicit=True,
    )
    out = capsys.readouterr().out
    # the pool line should be marked [declared]
    pool_line = next(ln for ln in out.splitlines() if ln.strip().startswith("pool"))
    assert "[declared]" in pool_line


def _pool_line(out):
    return next(ln for ln in out.splitlines() if ln.strip().startswith("pool"))


def test_cmd_list_marks_neither_when_clean_env(tmp_path, capsys):
    # No manifest passed, nothing installed -> the entry line carries no markers
    # (the trailing legend always names both markers, so check the entry itself).
    plugin_cmd.cmd_list(catalog=_catalog())
    line = _pool_line(capsys.readouterr().out)
    assert "[declared]" not in line
    assert "[installed]" not in line


def test_cmd_list_missing_manifest_no_declared_no_error(tmp_path, capsys):
    # A config_path whose manifest doesn't exist -> no [declared], no crash.
    code = plugin_cmd.cmd_list(
        catalog=_catalog(),
        config_path=tmp_path / "config.toml",
        config_explicit=True,
    )
    assert code == 0
    assert "[declared]" not in _pool_line(capsys.readouterr().out)


def test_cmd_list_groups_by_kind(capsys):
    cat = Catalog(
        entries=(
            CatalogEntry(
                name="baseball",
                namespace="baseball",
                summary="MLB stuff",
                homepage="",
                provides=PluginProvides(
                    widgets=("baseball.scores",),
                    transitions=("baseball.roll",),
                    emoji=("baseball.ball",),
                ),
                sources=(CatalogSource(type="git", url="https://h/o/r", ref="main"),),
            ),
        )
    )
    plugin_cmd.cmd_list(catalog=cat)
    out = capsys.readouterr().out
    assert "widgets: baseball.scores" in out
    assert "transitions: baseball.roll" in out
    assert "emoji: :baseball.ball:" in out  # emoji shown in :slug: form


def _install_only_catalog(provides):
    return Catalog(
        entries=(
            CatalogEntry(
                name="x",
                namespace="x",
                summary="x",
                homepage="",
                provides=provides,
                sources=(CatalogSource(type="git", url="https://h/o/x", ref="main"),),
            ),
        )
    )


def test_install_hint_widget(tmp_path, fakepip, capsys):
    cat = _install_only_catalog(PluginProvides(widgets=("x.thing",)))
    plugin_cmd.cmd_install("x", config_path=tmp_path / "config.toml", catalog=cat)
    assert 'type = "x.thing"' in capsys.readouterr().out


def test_install_hint_transition_only(tmp_path, fakepip, capsys):
    cat = _install_only_catalog(PluginProvides(transitions=("x.forward",)))
    plugin_cmd.cmd_install("x", config_path=tmp_path / "config.toml", catalog=cat)
    out = capsys.readouterr().out
    assert 'transition = "x.forward"' in out
    assert "type =" not in out  # the old bug: must NOT call a transition a widget type


def test_install_hint_emoji_only(tmp_path, fakepip, capsys):
    cat = _install_only_catalog(PluginProvides(emoji=("x.ball",)))
    plugin_cmd.cmd_install("x", config_path=tmp_path / "config.toml", catalog=cat)
    assert ":x.ball:" in capsys.readouterr().out


def test_install_hint_raises_on_unknown_kind():
    assert "easing" in plugin_cmd._install_hint("easing", "x.ease")
    with pytest.raises(ValueError, match="no install hint"):
        plugin_cmd._install_hint("bogus", "x.y")


def test_install_hint_covers_every_surface_kind():
    # cmd_install calls _install_hint(*provides.primary()); primary() can return
    # ANY kind in _PRIMARY_ORDER (== _SURFACE_KINDS), so every kind needs a hint
    # or `plugin install` crashes AFTER pip runs. Keep the if/elif in lockstep.
    from led_ticker.plugins_catalog import _SURFACE_KINDS

    for kind in _SURFACE_KINDS:
        assert plugin_cmd._install_hint(kind, "x"), kind  # non-empty, no raise


# --- Fix 4: empty-provides paths for CLI consumers ---


def test_install_hint_empty_provides_fallback(tmp_path, fakepip, capsys):
    cat = _install_only_catalog(PluginProvides())
    plugin_cmd.cmd_install("x", config_path=tmp_path / "config.toml", catalog=cat)
    out = capsys.readouterr().out
    assert "Restart led-ticker to load" in out
    assert "type =" not in out and "transition =" not in out


def test_cmd_list_empty_provides_no_surface_lines(capsys):
    cat = _install_only_catalog(PluginProvides())
    plugin_cmd.cmd_list(catalog=cat)
    out = capsys.readouterr().out
    assert any(ln.strip().startswith("x") for ln in out.splitlines())  # name line
    labels = (
        "widgets:",
        "transitions:",
        "emoji:",
        "fonts:",
        "borders:",
        "color providers:",
        "animations:",
        "easing:",
    )
    assert not any(lbl in out for lbl in labels)  # no surface lines


# --- Task 4: parameterize pip by target python ---


def test_pip_install_uses_given_python(monkeypatch):
    seen = []
    import subprocess as sp

    from led_ticker.app import plugin_cmd

    def fake_run(cmd, **kw):
        seen.append(cmd)
        return sp.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(plugin_cmd.subprocess, "run", fake_run)
    plugin_cmd._pip_install("led-ticker-pool", python_exe="/venv/bin/python")
    assert all(c[0] == "/venv/bin/python" for c in seen)


# --- pip subprocess: timeouts + argument-like-requirement guard ---


def test_pip_install_passes_timeout_and_net_args(monkeypatch):
    """The install (and freeze) subprocess.run calls are wall-clock bounded and
    the install carries pip --timeout/--retries so a flaky link can't hang boot."""
    import subprocess as sp

    from led_ticker.app import plugin_cmd

    seen = []

    def fake_run(cmd, **kw):
        seen.append((cmd, kw))
        return sp.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(plugin_cmd.subprocess, "run", fake_run)
    plugin_cmd._pip_install("led-ticker-pool", python_exe="/venv/bin/python")
    # both calls carry a timeout= kwarg
    assert all("timeout" in kw and kw["timeout"] for _, kw in seen)
    install_cmd = next(c for c, _ in seen if "install" in c)
    assert "--timeout" in install_cmd and "--retries" in install_cmd


def test_pip_uninstall_passes_timeout(monkeypatch):
    import subprocess as sp

    from led_ticker.app import plugin_cmd

    seen = []

    def fake_run(cmd, **kw):
        seen.append((cmd, kw))
        return sp.CompletedProcess(cmd, 0)

    monkeypatch.setattr(plugin_cmd.subprocess, "run", fake_run)
    plugin_cmd._pip_uninstall("led-ticker-pool", python_exe="/venv/bin/python")
    assert seen and all("timeout" in kw and kw["timeout"] for _, kw in seen)


def test_pip_install_refuses_argument_like_requirement(monkeypatch):
    """A manifest line starting with '-' (e.g. --pre) is rejected, never shelled
    out as a pip flag."""
    import pytest

    from led_ticker.app import plugin_cmd

    called = []
    monkeypatch.setattr(plugin_cmd.subprocess, "run", lambda *a, **k: called.append(a))
    for bad in ("--pre", "--index-url=evil", "-e"):
        with pytest.raises(ValueError, match="argument-like"):
            plugin_cmd._pip_install(bad, python_exe="/venv/bin/python")
    assert called == []  # never reached subprocess


def test_pip_install_allows_editable_spec(monkeypatch):
    """`-e <spec>` is the one '-' form allowed (intentional editable install)."""
    import subprocess as sp

    from led_ticker.app import plugin_cmd

    seen = []
    monkeypatch.setattr(
        plugin_cmd.subprocess,
        "run",
        lambda cmd, **kw: seen.append(cmd) or sp.CompletedProcess(cmd, 0, "", ""),
    )
    plugin_cmd._pip_install("-e git+https://x/y.git", python_exe="/venv/bin/python")
    assert seen  # reached subprocess, not rejected


def test_pip_uninstall_refuses_argument_like_dist(monkeypatch):
    import pytest

    from led_ticker.app import plugin_cmd

    called = []
    monkeypatch.setattr(plugin_cmd.subprocess, "run", lambda *a, **k: called.append(a))
    with pytest.raises(ValueError, match="argument-like"):
        plugin_cmd._pip_uninstall("--yes", python_exe="/venv/bin/python")
    assert called == []
