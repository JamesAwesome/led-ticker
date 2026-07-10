"""Guard tests for the declarative plugin-requirements file.

See docs/superpowers/specs/2026-06-03-plugin-requirements-file-design.md.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _noncomment_lines(text: str) -> list[str]:
    out = []
    for raw in text.splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            out.append(line)
    return out


def test_example_requirements_exists_and_lists_pool():
    example = REPO_ROOT / "config" / "requirements-plugins.example.txt"
    assert example.exists(), "config/requirements-plugins.example.txt must exist"
    lines = _noncomment_lines(example.read_text())
    assert any(
        line == "led-ticker-pool" or line.startswith("led-ticker-pool==")
        for line in lines
    ), "the example should ship the pool plugin as a PyPI install (led-ticker-pool)"
    for line in lines:
        assert " " not in line, f"malformed requirement line: {line!r}"


def test_live_requirements_file_is_gitignored():
    gitignore = (REPO_ROOT / ".gitignore").read_text()
    assert "config/requirements-plugins.txt" in gitignore, (
        "the live requirements-plugins.txt must be gitignored"
    )


def test_dockerfile_does_not_bake_plugins():
    """Layer-2b (build-time plugin install) was dropped; plugins are now
    installed at runtime onto the ticker-plugins volume by plugin_reconcile.py.
    This test guards against accidentally re-introducing the baked layer."""
    dockerfile = (REPO_ROOT / "Dockerfile").read_text()
    assert "-r /code/config/requirements-plugins.txt" not in dockerfile, (
        "Dockerfile must NOT pip-install plugins at build time — "
        "plugins install at runtime via plugin_reconcile.py"
    )
    assert "config/requirements-plugins.tx[t]" not in dockerfile, (
        "Dockerfile must NOT COPY the requirements-plugins file — "
        "runtime reconcile reads it from the config volume"
    )
    # Core constraints generation is still present in Layer 2 (plugins need it
    # at runtime reconcile time via the constraints-core.txt the image ships).
    assert "pip list --format=freeze" in dockerfile, (
        "Dockerfile should still generate constraints-core.txt from the core env"
    )
    assert "plugin_reconcile" in dockerfile, (
        "Dockerfile should reference plugin_reconcile.py (in the comment "
        "replacing the removed Layer-2b block)"
    )
    assert "POOL_PLUGIN_CACHE_BUST" not in dockerfile, (
        "the per-plugin cache-bust ARG should be removed"
    )
    assert "led-ticker-pool.git" not in dockerfile, (
        "no hardcoded plugin git URL should remain in the Dockerfile"
    )


# test_install_sh_installs_plugin_requirements was removed in the
# systemd/bare-metal path drop (Task A1).  The constrained-install invariants
# it covered are now enforced by test_dockerfile_does_not_bake_plugins
# (Dockerfile layer) and the plugin_reconcile runtime path.
# The bare-metal deploy files were deleted in the same commit.


# --- _strip_comment -----------------------------------------------------------


def test_strip_comment_plain_line():
    from led_ticker.app.plugin_cmd import _strip_comment

    assert _strip_comment("led-ticker-pool==0.1.0") == "led-ticker-pool==0.1.0"


def test_strip_comment_removes_trailing_comment():
    from led_ticker.app.plugin_cmd import _strip_comment

    assert (
        _strip_comment("led-ticker-pool==0.1.0  # upgraded 2026-07-09, was @main")
        == "led-ticker-pool==0.1.0"
    )


def test_strip_comment_preserves_url_fragment():
    from led_ticker.app.plugin_cmd import _strip_comment

    line = "git+https://github.com/x/y@main#subdirectory=plugins/pool"
    assert _strip_comment(line) == line


def test_strip_comment_url_fragment_plus_real_comment():
    from led_ticker.app.plugin_cmd import _strip_comment

    assert (
        _strip_comment("git+https://github.com/x/y@v1#subdirectory=p/q  # note")
        == "git+https://github.com/x/y@v1#subdirectory=p/q"
    )


def test_update_requirements_comment_param_overrides_carry(tmp_path):
    """comment= writes the given provenance comment instead of carrying the old
    line's comment."""
    from led_ticker.app.plugin_cmd import _update_requirements

    path = tmp_path / "requirements-plugins.txt"
    path.write_text("led-ticker-pool==0.1.0  # old note\n")
    _update_requirements(
        path, "led-ticker-pool==0.2.0", comment="# upgraded 2026-07-09, was ==0.1.0"
    )
    assert path.read_text() == (
        "led-ticker-pool==0.2.0  # upgraded 2026-07-09, was ==0.1.0\n"
    )
