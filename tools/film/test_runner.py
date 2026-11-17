import pytest
from tools.film.runner import (
    FakeRunner,
    Result,
    SubprocessRunner,
    ToolMissing,
    ssh_argv,
)


def test_fake_runner_records_calls_and_returns_response():
    r = FakeRunner({"echo": Result(["echo"], 0, b"hi", b"")})
    out = r.run(["echo", "x"])
    assert out.stdout == b"hi"
    assert r.calls == [["echo", "x"]]


def test_fake_runner_callable_response_sees_argv():
    r = FakeRunner({"ffmpeg": lambda argv: Result(argv, 0, b"", b"")})
    assert r.run(["ffmpeg", "-i", "x"]).argv == ["ffmpeg", "-i", "x"]


def test_fake_runner_unknown_tool_raises_tool_missing():
    with pytest.raises(ToolMissing) as e:
        FakeRunner({}).run(["nope"])
    assert e.value.tool == "nope"


def test_subprocess_runner_missing_binary_is_tool_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path))
    with pytest.raises(ToolMissing) as e:
        SubprocessRunner().run(["ffmpeg", "-version"])
    assert "brew install ffmpeg" in str(e.value)


def test_subprocess_runner_captures_output():
    out = SubprocessRunner().run(["/bin/echo", "hello"])
    assert out.returncode == 0 and out.stdout.strip() == b"hello"


def test_ssh_argv_uses_batch_mode():
    argv = ssh_argv("smallsign", "ls")
    assert argv[:3] == ["ssh", "-o", "BatchMode=yes"]
    assert argv[-2:] == ["smallsign", "ls"]


def test_fake_runner_records_timeouts():
    r = FakeRunner({"ssh": Result(["ssh"], 0, b"", b"")})
    r.run(["ssh", "h", "ls"], timeout=30.0)
    assert r.timeouts == [30.0]


def test_subprocess_runner_timeout_is_runtime_error():
    with pytest.raises(RuntimeError, match="timed out"):
        SubprocessRunner().run(["/bin/sleep", "5"], timeout=0.2)
