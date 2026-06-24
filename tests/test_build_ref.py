import re

import led_ticker._build as _build
from led_ticker._build import build_ref


def test_env_wins(monkeypatch):
    # The host-passed build ref (make rebuild) takes precedence.
    monkeypatch.setenv("LED_TICKER_BUILD_REF", "feat/x@abc1234")
    assert build_ref() == "feat/x@abc1234"


def test_git_fallback_when_env_unset(monkeypatch):
    # Non-Docker from a checkout (systemd/venv, dev): fall back to git.
    monkeypatch.delenv("LED_TICKER_BUILD_REF", raising=False)
    monkeypatch.setattr(_build, "_git_ref", lambda: "feat/y@def5678")
    assert build_ref() == "feat/y@def5678"


def test_literal_unknown_env_falls_through(monkeypatch):
    # A bare `docker compose build` leaves the env empty/"unknown"; with no git
    # in the image that resolves to "unknown" — deploy via `make rebuild`.
    monkeypatch.setenv("LED_TICKER_BUILD_REF", "unknown")
    monkeypatch.setattr(_build, "_git_ref", lambda: None)
    assert build_ref() == "unknown"


def test_unknown_when_no_env_no_git(monkeypatch):
    monkeypatch.delenv("LED_TICKER_BUILD_REF", raising=False)
    monkeypatch.setattr(_build, "_git_ref", lambda: None)
    assert build_ref() == "unknown"


def test_git_ref_resolves_in_this_checkout():
    # The tests run inside the repo, so the git tier must produce a
    # branch@shortsha ref (proves the git fallback works end-to-end).
    ref = _build._git_ref()
    assert ref is not None
    assert re.match(r"^.+@[0-9a-f]{7,}(\+dirty)?$", ref), ref
