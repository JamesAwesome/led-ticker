"""Tripwire for the docker-lifecycle make targets (2026-06-30 rename).

Locks: build-docker->build, rebuild->update, new up/down/restart/logs, the
profile-agnostic invariant (no recipe hardcodes COMPOSE_PROFILES), and the
`make dev` uv preflight. A cross-file "no retired names in shipped docs"
assertion is added in the docs-sweep task.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MAKEFILE = (REPO_ROOT / "Makefile").read_text()

LIFECYCLE_TARGETS = [
    "setup",
    "build",
    "up",
    "update",
    "restart",
    "down",
    "logs",
    "try",
    "try-down",
    "clean",
]
RETIRED_TARGETS = ["build-docker", "rebuild"]
NEW_PHONY = ["build", "up", "update", "restart", "down", "logs"]


def _target_defined(name):
    return re.search(rf"(?m)^{re.escape(name)}:", MAKEFILE) is not None


def test_lifecycle_targets_defined():
    missing = [t for t in LIFECYCLE_TARGETS if not _target_defined(t)]
    assert not missing, f"missing make targets: {missing}"


def test_retired_targets_gone():
    present = [t for t in RETIRED_TARGETS if _target_defined(t)]
    assert not present, f"retired make targets still defined: {present}"


def test_phony_updated():
    phony = next(ln for ln in MAKEFILE.splitlines() if ln.startswith(".PHONY:"))
    for t in NEW_PHONY:
        assert re.search(rf"(?<![\w-]){re.escape(t)}(?![\w-])", phony), (
            f"{t} not in .PHONY"
        )  # noqa: E501
    for t in RETIRED_TARGETS:
        assert not re.search(rf"(?<![\w-]){re.escape(t)}(?![\w-])", phony), (
            f"{t} still in .PHONY"
        )  # noqa: E501


def test_no_recipe_hardcodes_compose_profiles():
    # Only recipe lines (tab-indented) matter; help text/comments may mention it.
    offenders = [
        ln
        for ln in MAKEFILE.splitlines()
        if ln.startswith("\t") and "COMPOSE_PROFILES=" in ln
    ]
    assert not offenders, f"recipe hardcodes COMPOSE_PROFILES: {offenders}"


def test_dev_preflights_uv():
    m = re.search(r"(?ms)^dev:.*?(?=^\S)", MAKEFILE)
    assert m, "dev target not found"
    assert "command -v uv" in m.group(0), "make dev must preflight uv"
