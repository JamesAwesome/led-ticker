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


def test_baked_ref_used_before_git(monkeypatch):
    # In a Docker image the ref is baked into the package; it wins over runtime
    # git (git is what catches a stale branch, so the baked git ref is the truth).
    monkeypatch.delenv("LED_TICKER_BUILD_REF", raising=False)
    monkeypatch.setattr(_build, "_baked_ref", lambda: "main@deadbee")
    monkeypatch.setattr(_build, "_git_ref", lambda: "WRONG@0000000")
    assert build_ref() == "main@deadbee"


def test_baked_ref_absent_without_the_module():
    # _build_ref.py is git-ignored and only generated inside the Docker image,
    # so a source checkout has no baked ref (falls through to runtime git).
    assert _build._baked_ref() is None


def test_literal_unknown_env_falls_through(monkeypatch):
    # A bare `docker compose build` bakes the literal "unknown" — it must NOT
    # short-circuit; fall through to the next tier (package version here).
    monkeypatch.setenv("LED_TICKER_BUILD_REF", "unknown")
    monkeypatch.setattr(_build, "_git_ref", lambda: None)
    monkeypatch.setattr(_build, "_package_version", lambda: "v2.1.0")
    assert build_ref() == "v2.1.0"


def test_empty_env_falls_through(monkeypatch):
    monkeypatch.setenv("LED_TICKER_BUILD_REF", "  ")
    monkeypatch.setattr(_build, "_git_ref", lambda: "main@cafe123")
    assert build_ref() == "main@cafe123"


def test_package_version_when_no_env_no_git(monkeypatch):
    # PyPI install with no checkout: fall back to the release version.
    monkeypatch.delenv("LED_TICKER_BUILD_REF", raising=False)
    monkeypatch.setattr(_build, "_git_ref", lambda: None)
    monkeypatch.setattr(_build, "_package_version", lambda: "v2.1.0")
    assert build_ref() == "v2.1.0"


def test_unknown_when_nothing(monkeypatch):
    # No env, no checkout, no installed metadata — genuinely nothing to name.
    monkeypatch.delenv("LED_TICKER_BUILD_REF", raising=False)
    monkeypatch.setattr(_build, "_git_ref", lambda: None)
    monkeypatch.setattr(_build, "_package_version", lambda: None)
    assert build_ref() == "unknown"


def test_git_ref_resolves_in_this_checkout():
    # The tests run inside the repo, so the real fallback must produce a
    # branch@shortsha ref (proves the git fallback works end-to-end).
    ref = _build._git_ref()
    assert ref is not None
    assert re.match(r"^.+@[0-9a-f]{7,}(\+dirty)?$", ref), ref


def test_package_version_resolves_in_env():
    # led-ticker-core is installed in the dev/test env, so this resolves to a
    # `v<version>` string (proves the metadata fallback works end-to-end).
    ver = _build._package_version()
    assert ver is not None
    assert re.match(r"^v\d", ver), ver
