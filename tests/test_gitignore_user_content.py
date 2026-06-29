import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _ignored(relpath: str) -> bool:
    # git check-ignore exits 0 if the path IS ignored.
    return (
        subprocess.run(["git", "check-ignore", "-q", relpath], cwd=REPO).returncode == 0
    )


def test_user_content_locations_are_gitignored():
    # The operator's running config + private content must never show as untracked.
    assert _ignored("config/config.toml")
    assert _ignored("config/requirements-plugins.txt")
    assert _ignored("config/local/my-sign.toml")
    assert _ignored("config/local/media/logo.gif")


def test_committed_samples_are_not_ignored():
    # Tracked fixtures + examples must stay visible to git.
    assert not _ignored("config/config.example.toml")
    assert not _ignored("config/config.baseball.toml")
    assert not _ignored("config/assets/phoenix.png")
