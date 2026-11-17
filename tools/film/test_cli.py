from pathlib import Path

import pytest
from tools.film import cli
from tools.film.analyze import BBox
from tools.film.clip import CountMismatch
from tools.film.runner import FakeRunner, Result, ToolMissing
from tools.film.sign import DeployRefused

LIST = (
    b"[AVFoundation indev @ 0x1] AVFoundation video devices:\n"
    b"[AVFoundation indev @ 0x1] [0] Insta360 Link\n"
    b"[AVFoundation indev @ 0x1] AVFoundation audio devices:\n"
)


def test_cli_record_list_devices_exit_0(capsys, monkeypatch):
    monkeypatch.setattr(
        cli,
        "default_runner",
        lambda: FakeRunner({"ffmpeg": Result(["ffmpeg"], 1, b"", LIST)}),
    )
    assert cli.main(["record", "o.mp4", "--list-devices"]) == 0
    assert "Insta360 Link" in capsys.readouterr().out


def test_cli_clip_count_mismatch_exit_1(capsys, monkeypatch):
    def boom(*a, **k):
        raise CountMismatch("3 segment(s) detected but 2 name(s)")

    monkeypatch.setattr(cli, "clip_footage", boom)
    monkeypatch.setattr(cli, "default_runner", lambda: FakeRunner({}))
    assert cli.main(["clip", "in.mp4", "m.toml", "out/"]) == 1
    assert "3 segment(s)" in capsys.readouterr().err


def test_cli_clip_passes_crop_take_and_name_sets(monkeypatch):
    seen = {}

    def fake(src, manifest, out_dir, **kw):
        seen.update(kw, src=src, manifest=manifest, out_dir=out_dir)
        return []

    monkeypatch.setattr(cli, "clip_footage", fake)
    monkeypatch.setattr(cli, "default_runner", lambda: FakeRunner({}))
    rc = cli.main(
        [
            "clip",
            "in.mp4",
            "m.toml",
            "out/",
            "--crop",
            "1:2:3:4",
            "--take",
            "2",
            "--mp4",
            "hero,x",
            "--hero",
            "hero",
        ]
    )
    assert rc == 0
    assert seen["crop"] == BBox(1, 2, 3, 4) and seen["take"] == 2
    assert seen["mp4_names"] == {"hero", "x"} and seen["hero_budget_names"] == {"hero"}
    assert seen["src"] == Path("in.mp4") and seen["out_dir"] == Path("out/")


def test_cli_deploy_refused_exit_1(capsys, monkeypatch):
    def refuse(*a, **k):
        raise DeployRefused("a film-bak already exists")

    monkeypatch.setattr(cli, "deploy", refuse)
    monkeypatch.setattr(cli, "default_runner", lambda: FakeRunner({}))
    assert cli.main(["deploy", "hero.toml"]) == 1
    assert "film-bak" in capsys.readouterr().err


def test_cli_deploy_passes_host_brightness_restore_first(monkeypatch):
    seen = {}

    def fake(host, config, runner, **kw):
        seen.update(kw, host=host, config=config)
        return {}

    monkeypatch.setattr(cli, "deploy", fake)
    monkeypatch.setattr(cli, "default_runner", lambda: FakeRunner({}))
    assert (
        cli.main(
            [
                "deploy",
                "hero.toml",
                "--host",
                "h",
                "--brightness",
                "40",
                "--restore-first",
            ]
        )
        == 0
    )
    assert (
        seen["host"] == "h"
        and seen["brightness"] == 40
        and seen["restore_first"] is True
    )


def test_cli_tool_missing_exit_2(capsys, monkeypatch):
    def missing(*a, **k):
        raise ToolMissing("ffmpeg")

    monkeypatch.setattr(cli, "record", missing)
    monkeypatch.setattr(cli, "default_runner", lambda: FakeRunner({}))
    assert cli.main(["record", "o.mp4", "--seconds", "3"]) == 2
    assert "brew install ffmpeg" in capsys.readouterr().err


def test_cli_session_restores_in_finally(monkeypatch):
    calls = []
    monkeypatch.setattr(cli, "deploy", lambda *a, **k: calls.append("deploy") or {})
    monkeypatch.setattr(
        cli, "restore", lambda *a, **k: calls.append("restore") or "bak"
    )

    def fail(*a, **k):
        calls.append("record")
        raise RuntimeError("camera unplugged")

    monkeypatch.setattr(cli, "record", fail)
    monkeypatch.setattr(cli, "default_runner", lambda: FakeRunner({}))
    assert cli.main(["session", "hero.toml", "o.mp4", "--seconds", "5"]) == 1
    assert calls == ["deploy", "record", "restore"]


def test_cli_restore_force_flag(monkeypatch):
    seen = {}
    monkeypatch.setattr(
        cli, "restore", lambda host, runner, **kw: seen.update(kw, host=host) or None
    )
    monkeypatch.setattr(cli, "default_runner", lambda: FakeRunner({}))
    assert cli.main(["restore", "--force"]) == 0
    assert seen["force"] is True and seen["host"] == "smallsign"


def test_cli_bad_crop_is_usage_error(monkeypatch):
    monkeypatch.setattr(cli, "default_runner", lambda: FakeRunner({}))
    with pytest.raises(SystemExit) as e:
        cli.main(["clip", "in.mp4", "m.toml", "out/", "--crop", "1:2:3"])
    assert e.value.code == 2


def test_cli_session_deploy_failure_after_mutation_still_restores(monkeypatch):
    calls = []

    def deploy_times_out(*a, **k):
        calls.append("deploy")
        raise TimeoutError("display not up; run film restore")

    monkeypatch.setattr(cli, "deploy", deploy_times_out)
    monkeypatch.setattr(cli, "record", lambda *a, **k: calls.append("record"))
    monkeypatch.setattr(
        cli, "restore", lambda *a, **k: calls.append("restore") or "bak"
    )
    monkeypatch.setattr(cli, "default_runner", lambda: FakeRunner({}))
    assert cli.main(["session", "hero.toml", "o.mp4", "--seconds", "5"]) == 1
    assert calls == ["deploy", "restore"]


def test_cli_clip_full_frame_and_mp4_only_and_thresholds(monkeypatch):
    seen = {}
    monkeypatch.setattr(cli, "clip_footage", lambda *a, **kw: seen.update(kw) or [])
    monkeypatch.setattr(cli, "default_runner", lambda: FakeRunner({}))
    rc = cli.main(
        [
            "clip",
            "in.mp4",
            "m.toml",
            "out/",
            "--full-frame",
            "--mp4-only",
            "--mp4",
            "youtube",
            "--slate-threshold",
            "150",
            "--change-threshold",
            "40",
        ]
    )
    assert rc == 0
    assert seen["full_frame"] is True and seen["gif"] is False
    assert seen["slate_threshold"] == 150.0 and seen["change_threshold"] == 40


def test_cli_missing_file_is_exit_1_not_traceback(capsys, monkeypatch):
    def missing(*a, **k):
        raise FileNotFoundError("nope.toml")

    monkeypatch.setattr(cli, "deploy", missing)
    monkeypatch.setattr(cli, "default_runner", lambda: FakeRunner({}))
    assert cli.main(["deploy", "nope.toml"]) == 1
    assert "nope.toml" in capsys.readouterr().err


def test_cli_aim_defaults_to_the_shelf_preset_and_prints_state(capsys, monkeypatch):
    seen = {}

    def fake_aim(preset, runner, **kw):
        seen["preset"] = preset
        seen.update(kw)
        return {
            "absolute_pan_tilt": [preset.pan, preset.tilt],
            "absolute_zoom": preset.zoom,
        }

    monkeypatch.setattr(cli, "aim", fake_aim)
    monkeypatch.setattr(cli, "default_runner", lambda: FakeRunner({}))
    assert cli.main(["aim"]) == 0
    assert seen["preset"] == cli.SMALLSIGN_SHELF
    assert "zoom=350" in capsys.readouterr().out
    assert (
        cli.main(
            ["aim", "--pan", "-100", "--tilt", "200", "--zoom", "400", "--wb", "4800"]
        )
        == 0
    )
    p = seen["preset"]
    assert (p.pan, p.tilt, p.zoom, p.white_balance) == (-100, 200, 400, 4800)
    assert cli.main(["aim", "--auto-wb"]) == 0
    assert seen["preset"].white_balance is None


def test_cli_session_aim_runs_after_deploy_before_record(monkeypatch):
    order = []
    monkeypatch.setattr(cli, "deploy", lambda *a, **k: order.append("deploy"))
    monkeypatch.setattr(cli, "aim", lambda *a, **k: order.append("aim") or {})
    monkeypatch.setattr(cli, "record", lambda *a, **k: order.append("record"))
    monkeypatch.setattr(cli, "restore", lambda *a, **k: order.append("restore"))
    monkeypatch.setattr(cli, "default_runner", lambda: FakeRunner({}))
    assert cli.main(["session", "c.toml", "o.mp4", "--seconds", "5"]) == 0
    assert order == ["deploy", "record", "restore"]
    order.clear()
    assert cli.main(["session", "c.toml", "o.mp4", "--seconds", "5", "--aim"]) == 0
    assert order == ["deploy", "aim", "record", "restore"]
