"""Release order guard (spec: 2026-07-16-release-order-guard-design.md).

The invariant: version order == commit-ancestry order. Born from the
v4.16.1/v4.17.0 incident — a parallel session shipped v4.17.0, then a
background pipeline with a stale plan cut v4.16.1 on NEWER code, hiding
the #405 freeze fix from resolver-visible "latest".
"""

import importlib.util
import pathlib

_spec = importlib.util.spec_from_file_location(
    "release_guard",
    pathlib.Path(__file__).parent.parent / "scripts" / "release_guard.py",
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
check_release_order = _mod.check_release_order


def _ancestry(pairs):
    """is_ancestor(a, b) == True iff (a, b) in pairs (a is ancestor of b)."""

    def is_ancestor(a: str, b: str) -> bool:
        return (a, b) in pairs

    return is_ancestor


def test_newer_version_on_newer_commit_ok():
    err = check_release_order(
        "v4.17.1", ["v4.16.0", "v4.17.0"], _ancestry({("v4.17.0", "v4.17.1")})
    )
    assert err is None


def test_the_incident_lower_version_on_newer_commit_fails():
    """v4.16.1 cut after v4.17.0 existed — must fail on monotonicity."""
    err = check_release_order(
        "v4.16.1", ["v4.16.0", "v4.17.0"], _ancestry({("v4.17.0", "v4.16.1")})
    )
    assert err is not None and "4.17.0" in err


def test_the_mirror_higher_version_on_older_commit_fails():
    """A higher version tagged on code that does NOT descend from the
    previous latest — equally wrong (latest would LOSE shipped code)."""
    err = check_release_order("v4.18.0", ["v4.17.0"], _ancestry(set()))
    assert err is not None and "ancestor" in err


def test_equal_version_fails():
    err = check_release_order(
        "v4.17.0", ["v4.17.0"], _ancestry({("v4.17.0", "v4.17.0")})
    )
    assert err is not None


def test_first_release_passes_trivially():
    assert check_release_order("v1.0.0", [], _ancestry(set())) is None


def test_malformed_historical_tags_are_ignored():
    err = check_release_order(
        "v4.18.0",
        ["v4.17.0", "vNext", "test-tag", "v4.17.0-rc1"],
        _ancestry({("v4.17.0", "v4.18.0")}),
    )
    assert err is None


def test_malformed_new_tag_is_rejected():
    err = check_release_order("v4.18", ["v4.17.0"], _ancestry(set()))
    assert err is not None and "X.Y.Z" in err


# --- cut_release.compute_next (the live-derivation half) --------------------

_cut_spec = importlib.util.spec_from_file_location(
    "cut_release",
    pathlib.Path(__file__).parent.parent / "scripts" / "cut_release.py",
)


def _load_cut_release():
    import sys

    sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "scripts"))
    mod = importlib.util.module_from_spec(_cut_spec)
    _cut_spec.loader.exec_module(mod)
    return mod


def test_compute_next_bumps_from_the_highest_existing():
    cr = _load_cut_release()
    tags = ["v4.16.0", "v4.17.0", "v4.16.1", "junk-tag"]
    assert cr.compute_next(tags, "patch") == "v4.17.1"
    assert cr.compute_next(tags, "minor") == "v4.18.0"
    assert cr.compute_next(tags, "major") == "v5.0.0"


def test_compute_next_first_release():
    cr = _load_cut_release()
    assert cr.compute_next([], "patch") == "v0.1.0"
