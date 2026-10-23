"""Tripwire: the production Dockerfile must install core's deps from uv.lock.

Regression lock for 2026-10-22: the deps layer ran ``pip install -e ".[dev]"``,
which re-resolved pyproject's loose ranges on every build — a `make update`
pulled Pillow 13.0.0 (pyproject: ``Pillow>=10.0``; uv.lock: 12.1.1) and crashed
every hi-res font on the sign. The lock must govern what ships:

* a stage renders uv.lock with ``uv export --frozen`` (never re-resolves),
* the deps layer ``pip install --no-deps -r``'s that export (exact pins, nothing
  added), and
* NO ``pip install`` of the project itself may resolve dependencies — core goes
  in with ``--no-deps`` so it can't drag unlocked versions back in.

Cheap text checks, no Docker. Dockerfile.try is out of scope (it intentionally
installs the latest released core from PyPI; see that file's header).
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCKERFILE = REPO_ROOT / "Dockerfile"


def _instructions(text: str) -> list[str]:
    """Dockerfile instructions with backslash continuations joined, comments dropped."""
    lines = [ln for ln in text.splitlines() if not ln.lstrip().startswith("#")]
    joined = "\n".join(lines).replace("\\\n", " ")
    return [ln.strip() for ln in joined.splitlines() if ln.strip()]


def _pip_install_cmds(text: str) -> list[str]:
    """Every individual `pip install ...` command inside RUN instructions."""
    cmds: list[str] = []
    for instr in _instructions(text):
        if not instr.upper().startswith("RUN "):
            continue
        for part in re.split(r"&&|;|\|\|", instr):
            if re.search(r"\bpip install\b", part):
                cmds.append(" ".join(part.split()))
    return cmds


def test_lock_is_exported_frozen_without_the_project():
    instrs = _instructions(DOCKERFILE.read_text())
    assert any(i.startswith("COPY") and "uv.lock" in i for i in instrs), (
        "uv.lock must be COPY'd into the build so the deps layer is lock-driven"
    )
    exports = [i for i in instrs if "uv export" in i]
    assert exports, "Dockerfile must render uv.lock via `uv export`"
    for flag in ("--frozen", "--no-emit-project", "--no-hashes"):
        assert all(flag in e for e in exports), f"`uv export` must pass {flag}"


def test_uv_is_version_pinned():
    text = DOCKERFILE.read_text()
    m = re.search(r"ARG UV_VERSION=(\S+)", text)
    assert m and re.fullmatch(r"\d+\.\d+\.\d+", m.group(1)), (
        "uv must be pinned to an exact X.Y.Z version (ARG UV_VERSION=...)"
    )
    assert '"uv==${UV_VERSION}"' in text


def test_deps_layer_installs_the_lock_export_with_no_deps():
    cmds = _pip_install_cmds(DOCKERFILE.read_text())
    lock_installs = [c for c in cmds if "requirements.lock.txt" in c]
    assert lock_installs, "deps layer must `pip install -r` the uv.lock export"
    for c in lock_installs:
        assert "--no-deps" in c, f"lock install must be --no-deps (exact set): {c}"


def test_project_is_never_installed_with_dependency_resolution():
    """`pip install .` / `-e .` / `.[extra]` must carry --no-deps."""
    project_target = re.compile(
        r"""(?:^|\s)(?:-e\s+)?["']?\.(?:\[[^\]]*\])?["']?(?:\s|$)"""
    )
    offenders = [
        c
        for c in _pip_install_cmds(DOCKERFILE.read_text())
        # the rgbmatrix fork build (`cd rgbmatrix-src && ... pip install .`) is
        # a separate, non-lock package with no Python deps — exempt it.
        if project_target.search(c.split("pip install", 1)[1])
        and "--no-deps" not in c
        and "PIP_CONSTRAINT=/tmp/build-constraints.txt" not in c
    ]
    assert not offenders, (
        "led-ticker-core must be installed with --no-deps (deps come from the "
        f"uv.lock export, not a fresh resolve): {offenders}"
    )


def test_constraints_snapshot_follows_the_core_install():
    """constraints-core.txt is frozen after core lands, so it reflects the lock."""
    instrs = _instructions(DOCKERFILE.read_text())
    lock_idx = next(
        i
        for i, s in enumerate(instrs)
        if "requirements.lock.txt" in s and s.startswith("RUN")
    )
    snap_idx = next(
        i
        for i, s in enumerate(instrs)
        if "constraints-core.txt" in s and s.startswith("RUN")
    )
    assert lock_idx < snap_idx
