import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from tools.film.runner import FakeRunner, Result
from tools.film.sign import (
    REMOTE_CONFIG,
    DeployRefused,
    RestoreRefused,
    deploy,
    film_bak_name,
    restore,
    wait_for_display,
    with_brightness,
)

NOW = datetime(2026, 11, 17, 15, 0, 0, tzinfo=UTC)
BAK = "config.toml.film-bak-20261117T150000Z"


def _ok(text: str = "") -> Result:
    return Result(["ssh"], 0, text.encode(), b"")


class FakeSign:
    """ssh/scp responder keyed on substrings of the remote command."""

    def __init__(
        self, *, sha: str = "a" * 64, baks=(), statuses=None, bak_sha: str = "z" * 64
    ):
        self.sha = sha
        self.bak_sha = bak_sha
        self.baks = list(baks)
        self.statuses = list(statuses or [{"started_at": 1.0, "swap_count": 5}])
        self.cmds: list[str] = []
        self.runner = FakeRunner(
            {"ssh": self._ssh, "scp": lambda a: Result(a, 0, b"", b"")}
        )

    def _ssh(self, argv):
        cmd = argv[-1]
        self.cmds.append(cmd)
        if "sha256sum" in cmd:
            return _ok(self.bak_sha if "film-bak" in cmd else self.sha)
        if cmd.startswith("ls "):
            return _ok("\n".join(self.baks))
        if "status.json" in cmd:
            st = self.statuses.pop(0) if len(self.statuses) > 1 else self.statuses[0]
            return _ok(json.dumps(st))
        return _ok()

    @property
    def mutations(self) -> list[str]:
        return [c for c in self.cmds if "sudo" in c or "docker restart" in c]


@pytest.fixture
def cfg(tmp_path) -> Path:
    p = tmp_path / "hero.toml"
    p.write_text(
        "[display]\nrows = 16\nbrightness = 60\n\n[busy_light]\nenabled = false\n"
    )
    return p


def test_film_bak_name_is_utc_stamp():
    assert film_bak_name(NOW) == BAK


def test_with_brightness_rewrites_display_line_only():
    assert with_brightness("[display]\nrows = 16\nbrightness = 60\n", 40) == (
        "[display]\nrows = 16\nbrightness = 40\n"
    )
    assert (
        with_brightness("[display]\nbrightness = 60\n", None)
        == "[display]\nbrightness = 60\n"
    )


def test_deploy_refuses_when_film_bak_exists_without_restore_first(cfg, tmp_path):
    sign = FakeSign(baks=[f"/home/small/led-ticker/config/{BAK}"])
    with pytest.raises(DeployRefused, match="film-bak"):
        deploy("smallsign", cfg, sign.runner, now=NOW, state_file=tmp_path / "s.json")
    assert sign.mutations == []


def test_deploy_backs_up_copies_restarts_waits_and_writes_state(cfg, tmp_path):
    sign = FakeSign(
        statuses=[
            {"started_at": 1.0, "swap_count": 9},
            {"started_at": 2.0, "swap_count": 3},
        ]
    )
    state = deploy(
        "smallsign",
        cfg,
        sign.runner,
        now=NOW,
        state_file=tmp_path / "s.json",
        sleep=lambda s: None,
    )
    joined = " ".join(sign.mutations)
    assert f"sudo cp {REMOTE_CONFIG} ~/led-ticker/config/{BAK}" in joined
    assert "docker restart led-ticker" in joined
    assert joined.index("sudo cp " + REMOTE_CONFIG) < joined.index("docker restart")
    scp = next(c for c in sign.runner.calls if c[0] == "scp")
    assert scp[-1] == "smallsign:/tmp/film-deploy.toml"
    assert state["sha256"] == hashlib.sha256(cfg.read_bytes()).hexdigest()
    assert state["bak"] == BAK and state["host"] == "smallsign"
    assert json.loads((tmp_path / "s.json").read_text()) == state


def test_deploy_brightness_override_changes_staged_file_and_hash(cfg, tmp_path):
    sign = FakeSign(
        statuses=[
            {"started_at": 1.0, "swap_count": 9},
            {"started_at": 2.0, "swap_count": 3},
        ]
    )
    state = deploy(
        "smallsign",
        cfg,
        sign.runner,
        now=NOW,
        brightness=40,
        state_file=tmp_path / "s.json",
        sleep=lambda s: None,
    )
    scp = next(c for c in sign.runner.calls if c[0] == "scp")
    staged = Path(scp[-2]).read_bytes() if Path(scp[-2]).exists() else None
    assert (
        state["sha256"]
        == hashlib.sha256(cfg.read_text().replace("60", "40").encode()).hexdigest()
    )
    assert staged is None or b"brightness = 40" in staged


def test_wait_for_display_polls_until_started_at_changes_and_swapping():
    sign = FakeSign(
        statuses=[
            {"started_at": 1.0, "swap_count": 9},
            {"started_at": 2.0, "swap_count": 0},
            {"started_at": 2.0, "swap_count": 5},
        ]
    )
    slept: list[float] = []
    st = wait_for_display(
        "smallsign", sign.runner, previous_started_at=1.0, sleep=slept.append
    )
    assert st == {"started_at": 2.0, "swap_count": 5}
    assert len(slept) == 2


def test_wait_for_display_times_out():
    sign = FakeSign(statuses=[{"started_at": 1.0, "swap_count": 9}])
    clock = iter(range(0, 1000, 2))
    with pytest.raises(TimeoutError):
        wait_for_display(
            "smallsign",
            sign.runner,
            previous_started_at=1.0,
            timeout=10.0,
            sleep=lambda s: None,
            clock=lambda: float(next(clock)),
        )


def _state(tmp_path, sha) -> Path:
    p = tmp_path / "s.json"
    p.write_text(
        json.dumps(
            {
                "host": "smallsign",
                "bak": BAK,
                "sha256": sha,
                "deployed_at": NOW.isoformat(),
            }
        )
    )
    return p


def test_restore_refuses_on_hash_drift(tmp_path):
    sign = FakeSign(sha="b" * 64, baks=[f"/home/small/led-ticker/config/{BAK}"])
    with pytest.raises(RestoreRefused, match="changed"):
        restore(
            "smallsign", sign.runner, now=NOW, state_file=_state(tmp_path, "a" * 64)
        )
    assert sign.mutations == []


def test_restore_force_restores_newest_bak_and_cleans_up(tmp_path):
    older = "config.toml.film-bak-20261117T140000Z"
    sign = FakeSign(
        sha="b" * 64,
        baks=[
            f"/home/small/led-ticker/config/{older}",
            f"/home/small/led-ticker/config/{BAK}",
        ],
        statuses=[
            {"started_at": 1.0, "swap_count": 9},
            {"started_at": 2.0, "swap_count": 3},
        ],
    )
    state = _state(tmp_path, "a" * 64)
    bak = restore(
        "smallsign",
        sign.runner,
        now=NOW,
        force=True,
        state_file=state,
        sleep=lambda s: None,
    )
    assert bak == BAK
    joined = " ".join(sign.mutations)
    assert f"sudo cp ~/led-ticker/config/{BAK} {REMOTE_CONFIG}" in joined
    assert "docker restart led-ticker" in joined
    assert f"sudo rm ~/led-ticker/config/{BAK}" in sign.mutations[-1]
    assert older not in joined.split("sudo rm")[-1]
    assert not state.exists()


def test_restore_matching_hash_needs_no_force(tmp_path):
    sign = FakeSign(
        sha="a" * 64,
        baks=[f"/home/small/led-ticker/config/{BAK}"],
        statuses=[
            {"started_at": 1.0, "swap_count": 9},
            {"started_at": 2.0, "swap_count": 3},
        ],
    )
    assert (
        restore(
            "smallsign",
            sign.runner,
            now=NOW,
            state_file=_state(tmp_path, "a" * 64),
            sleep=lambda s: None,
        )
        == BAK
    )


def test_restore_with_nothing_is_noop(tmp_path, capsys):
    sign = FakeSign(baks=[])
    assert (
        restore("smallsign", sign.runner, now=NOW, state_file=tmp_path / "missing.json")
        is None
    )
    assert "nothing to restore" in capsys.readouterr().out
    assert sign.mutations == []


def test_deploy_writes_state_before_waiting_and_names_restore_on_timeout(cfg, tmp_path):
    sign = FakeSign(statuses=[{"started_at": 1.0, "swap_count": 9}])  # never changes
    clock = iter(range(0, 10_000, 50))
    with pytest.raises(TimeoutError, match="film restore"):
        deploy(
            "smallsign",
            cfg,
            sign.runner,
            now=NOW,
            state_file=tmp_path / "s.json",
            sleep=lambda s: None,
            clock=lambda: float(next(clock)),
        )
    assert (tmp_path / "s.json").exists()
    assert json.loads((tmp_path / "s.json").read_text())["bak"] == BAK


def test_every_remote_call_carries_a_timeout(cfg, tmp_path):
    sign = FakeSign(
        statuses=[
            {"started_at": 1.0, "swap_count": 9},
            {"started_at": 2.0, "swap_count": 3},
        ]
    )
    deploy(
        "smallsign",
        cfg,
        sign.runner,
        now=NOW,
        state_file=tmp_path / "s.json",
        sleep=lambda s: None,
    )
    assert sign.runner.timeouts and all(t is not None for t in sign.runner.timeouts)


def test_deploy_restore_first_without_state_points_at_restore_force(cfg, tmp_path):
    sign = FakeSign(baks=[f"/home/small/led-ticker/config/{BAK}"])
    with pytest.raises(DeployRefused, match="film restore --force"):
        deploy(
            "smallsign",
            cfg,
            sign.runner,
            now=NOW,
            restore_first=True,
            state_file=tmp_path / "s.json",
        )
    assert sign.mutations == []


def test_restore_detects_already_restored_sign_and_just_cleans_up(tmp_path):
    # A previous restore's wait timed out: the live config is back (sign sha == bak sha)
    # but the state file still holds the FILMING sha. Not an edit — clean up.
    sign = FakeSign(
        sha="c" * 64, baks=[f"/home/small/led-ticker/config/{BAK}"], bak_sha="c" * 64
    )
    state = _state(tmp_path, "a" * 64)
    assert restore("smallsign", sign.runner, now=NOW, state_file=state) == BAK
    assert any("sudo rm" in c for c in sign.mutations)
    assert not any("docker restart" in c for c in sign.mutations)
    assert not state.exists()


def test_with_brightness_without_a_brightness_line_raises():
    with pytest.raises(ValueError, match="brightness"):
        with_brightness("[display]\nrows = 16\n", 40)
