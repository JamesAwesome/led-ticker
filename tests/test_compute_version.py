"""Tripwire for scripts/compute-version.sh — the uv-free version source.

Regression lock for the silent-0.0.0 bug that broke every plugin install. The
script must emit a real PEP 440 version from git, bumping the patch in the dev
case to match setuptools-scm (guess-next-dev) so plugin `>=2.x` floors clear.
"""

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_SRC = (REPO_ROOT / "scripts" / "compute-version.sh").read_text()


def _git(repo, *args):
    subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _place_script(repo):
    scripts_dir = repo / "scripts"
    scripts_dir.mkdir(exist_ok=True)
    dest = scripts_dir / "compute-version.sh"
    dest.write_text(SCRIPT_SRC)
    dest.chmod(0o755)


def _init_repo(repo):
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@t.t")
    _git(repo, "config", "user.name", "t")
    _place_script(repo)
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "init")


def _run(repo):
    return subprocess.run(
        ["sh", "scripts/compute-version.sh"],
        cwd=repo,
        capture_output=True,
        text=True,
    )


def test_on_tag_emits_clean_version(tmp_path):
    _init_repo(tmp_path)
    _git(tmp_path, "tag", "v2.4.0")
    r = _run(tmp_path)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "2.4.0"


def test_commits_past_tag_bumps_patch(tmp_path):
    _init_repo(tmp_path)
    _git(tmp_path, "tag", "v2.4.0")
    for i in range(3):
        (tmp_path / f"f{i}").write_text("x")
        _git(tmp_path, "add", ".")
        _git(tmp_path, "commit", "-q", "-m", f"c{i}")
    r = _run(tmp_path)
    assert r.returncode == 0, r.stderr
    # guess-next-dev bumps the patch: tag 2.4.0 + 3 commits -> 2.4.1.dev3
    assert r.stdout.strip() == "2.4.1.dev3"


def test_no_tags_fails_loud_with_empty_stdout(tmp_path):
    _init_repo(tmp_path)  # has a commit, no tags
    r = _run(tmp_path)
    assert r.returncode != 0
    assert r.stdout.strip() == ""
    assert "no release tags" in r.stderr.lower()


def test_not_a_git_clone_fails_with_zip_hint(tmp_path):
    _place_script(tmp_path)  # no `git init` — simulates a ZIP download
    r = subprocess.run(
        ["sh", "scripts/compute-version.sh"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert r.returncode != 0
    assert r.stdout.strip() == ""
    assert "git clone" in r.stderr.lower()
