"""Injectable shell-out seam for tools/film.

Every ffmpeg / ssh / scp call goes through a ``Runner`` so the tests never
touch hardware: ``SubprocessRunner`` is the real thing, ``FakeRunner`` is
keyed by ``argv[0]`` and records every call.
"""

import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

_BREW_TOOLS = {"ffmpeg", "ffprobe"}


@dataclass(frozen=True)
class Result:
    argv: list[str]
    returncode: int
    stdout: bytes
    stderr: bytes


class ToolMissing(RuntimeError):
    """A required executable is not on PATH."""

    def __init__(self, tool: str) -> None:
        self.tool = tool
        hint = f"; brew install {tool}" if tool in _BREW_TOOLS else ""
        super().__init__(f"{tool} not found on PATH{hint}")


class Runner(Protocol):
    def run(
        self,
        argv: list[str],
        *,
        input: bytes | None = None,
        timeout: float | None = None,
    ) -> Result: ...


class SubprocessRunner:
    def run(
        self,
        argv: list[str],
        *,
        input: bytes | None = None,
        timeout: float | None = None,
    ) -> Result:
        if shutil.which(argv[0]) is None and not Path(argv[0]).exists():
            raise ToolMissing(argv[0])
        try:
            proc = subprocess.run(  # noqa: S603 - argv is built by this package, never from user text
                argv, input=input, capture_output=True, timeout=timeout, check=False
            )
        except FileNotFoundError as exc:
            raise ToolMissing(argv[0]) from exc
        return Result(list(argv), proc.returncode, proc.stdout, proc.stderr)


Response = Result | Callable[[list[str]], Result]


@dataclass
class FakeRunner:
    responses: dict[str, Response]
    calls: list[list[str]] = field(default_factory=list)

    def run(
        self,
        argv: list[str],
        *,
        input: bytes | None = None,
        timeout: float | None = None,
    ) -> Result:
        self.calls.append(list(argv))
        resp = self.responses.get(argv[0])
        if resp is None:
            raise ToolMissing(argv[0])
        return resp(list(argv)) if callable(resp) else resp


def ssh_argv(host: str, remote_cmd: str) -> list[str]:
    return ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", host, remote_cmd]


def scp_argv(local: Path, host: str, remote_path: str) -> list[str]:
    return [
        "scp",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=10",
        str(local),
        f"{host}:{remote_path}",
    ]
