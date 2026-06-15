"""`led-ticker plugin list/search/install` command behavior.

pip is always mocked — no real install, no network. The filesystem uses tmp_path.
"""

from pathlib import Path
from types import SimpleNamespace

import pytest

from led_ticker.app import plugin_cmd
from led_ticker.plugins_catalog import Catalog, CatalogEntry, CatalogSource


def _catalog():
    return Catalog(
        entries=(
            CatalogEntry(
                name="pool",
                namespace="pool",
                summary="Pool water temperature",
                homepage="https://github.com/JamesAwesome/led-ticker-pool",
                provides=("pool.monitor",),
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

    def __init__(self, freeze_rc=0, install_rc=0):
        self.calls: list[list[str]] = []
        self.freeze_rc = freeze_rc
        self.install_rc = install_rc

    def run(self, cmd, **kwargs):
        self.calls.append(cmd)
        if "list" in cmd:  # pip list --format=freeze
            return SimpleNamespace(
                returncode=self.freeze_rc, stdout="led-ticker==1.0\n", stderr="err"
            )
        return SimpleNamespace(returncode=self.install_rc, stdout="", stderr="boom")

    @property
    def install_cmd(self):
        return next((c for c in self.calls if "install" in c), None)


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


def test_install_save_only_skips_pip(tmp_path, fakepip):
    code = _install(tmp_path, "pool", save_only=True)
    assert code == 0
    assert _reqfile(tmp_path).exists()
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


def test_install_typo_suggests_catalog_name_without_installing(tmp_path, fakepip):
    code = _install(tmp_path, "poool")  # typo close to "pool"
    assert code == 2
    assert fakepip.install_cmd is None  # never pip-installed an arbitrary package
    assert not _reqfile(tmp_path).exists()


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
    # not the cwd (so Docker/install.sh actually read it).
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
        # #egg= fragment is stripped
        (
            "git+https://h/o/led-ticker-pool.git@main#egg=led-ticker-pool",
            "led-ticker-pool",
        ),
        ("led-ticker-pool==1.2.0", "led-ticker-pool"),
        ("led_ticker_pool", "led-ticker-pool"),
        ("led-ticker-pool>=1.0", "led-ticker-pool"),
    ],
)
def test_requirement_key_normalizes(requirement, key):
    assert plugin_cmd._requirement_key(requirement) == key
