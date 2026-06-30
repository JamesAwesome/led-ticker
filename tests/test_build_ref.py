import re

import led_ticker._build as _build
from led_ticker._build import build_ref


def test_env_wins(monkeypatch):
    # The host-passed build ref (make update) takes precedence.
    monkeypatch.setenv("LED_TICKER_BUILD_REF", "feat/x@abc1234")
    assert build_ref() == "feat/x@abc1234"


def test_git_fallback_when_env_unset(monkeypatch):
    # Running from a checkout (local dev / custom supervisor): fall back to git.
    monkeypatch.delenv("LED_TICKER_BUILD_REF", raising=False)
    monkeypatch.setattr(_build, "_git_ref", lambda: "feat/y@def5678")
    assert build_ref() == "feat/y@def5678"


def test_literal_unknown_env_falls_through(monkeypatch):
    # A bare `docker compose build` leaves the env empty/"unknown"; with no git
    # in the image that resolves to "unknown" — deploy via `make update`.
    monkeypatch.setenv("LED_TICKER_BUILD_REF", "unknown")
    monkeypatch.setattr(_build, "_git_ref", lambda: None)
    monkeypatch.setattr(_build, "_package_version", lambda: None)
    assert build_ref() == "unknown"


def test_unknown_when_no_env_no_git(monkeypatch):
    monkeypatch.delenv("LED_TICKER_BUILD_REF", raising=False)
    monkeypatch.setattr(_build, "_git_ref", lambda: None)
    monkeypatch.setattr(_build, "_package_version", lambda: None)
    assert build_ref() == "unknown"


def test_package_version_when_no_env_no_git(monkeypatch):
    # PyPI / bare-docker install: fall back to the VCS-derived release version.
    monkeypatch.delenv("LED_TICKER_BUILD_REF", raising=False)
    monkeypatch.setattr(_build, "_git_ref", lambda: None)
    monkeypatch.setattr(_build, "_package_version", lambda: "2.2.1.dev3+gabc1234")
    assert build_ref() == "2.2.1.dev3+gabc1234"


def test_unknown_only_when_nothing(monkeypatch):
    monkeypatch.delenv("LED_TICKER_BUILD_REF", raising=False)
    monkeypatch.setattr(_build, "_git_ref", lambda: None)
    monkeypatch.setattr(_build, "_package_version", lambda: None)
    assert build_ref() == "unknown"


def test_package_version_resolves_in_env():
    v = _build._package_version()
    assert v is not None and v != "0.0.0", v


def test_git_ref_resolves_in_this_checkout():
    # The tests run inside the repo, so the git tier must produce a
    # branch@shortsha ref (proves the git fallback works end-to-end).
    ref = _build._git_ref()
    assert ref is not None
    assert re.match(r"^.+@[0-9a-f]{7,}(\+dirty)?$", ref), ref
