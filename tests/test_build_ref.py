import re

import led_ticker._build as _build
from led_ticker._build import build_ref


def test_env_wins(monkeypatch):
    # The Docker-baked env var takes precedence over everything.
    monkeypatch.setenv("LED_TICKER_BUILD_REF", "feat/x@abc1234")
    assert build_ref() == "feat/x@abc1234"


def test_git_fallback_when_env_unset(monkeypatch):
    # Non-Docker from a checkout (systemd/venv, dev): fall back to git.
    monkeypatch.delenv("LED_TICKER_BUILD_REF", raising=False)
    monkeypatch.setattr(_build, "_git_ref", lambda: "feat/y@def5678")
    assert build_ref() == "feat/y@def5678"


def test_unknown_when_no_env_and_no_git(monkeypatch):
    # pip install with no checkout (no env, git returns nothing).
    monkeypatch.delenv("LED_TICKER_BUILD_REF", raising=False)
    monkeypatch.setattr(_build, "_git_ref", lambda: None)
    assert build_ref() == "unknown"


def test_git_ref_resolves_in_this_checkout():
    # The tests run inside the repo, so the real fallback must produce a
    # branch@shortsha ref (proves the fallback actually works end-to-end).
    ref = _build._git_ref()
    assert ref is not None
    assert re.match(r"^.+@[0-9a-f]{7,}(\+dirty)?$", ref), ref
