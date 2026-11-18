"""Swap the sign's live config for a filming config and put it back.

Every mutation is ONE ssh call of ``&&``-joined commands, so a failed copy
never reaches ``docker restart``. The pre-filming config is kept on the sign
as ``config.toml.film-bak-<UTC stamp>``; a local state file (written the
moment the sign has been changed, before any waiting) records the sha256 of
what we wrote so ``restore`` can refuse if someone else (the webui editor, a
hand edit) changed the config mid-session.

NOTHING here runs without James's go-ahead for that step (see the plan's
Global Constraints); the tests drive it only through FakeRunner.
"""

import hashlib
import json
import re
import tempfile
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from tools.film.runner import Runner, scp_argv, ssh_argv

REMOTE_CONFIG = "~/led-ticker/config/config.toml"
REMOTE_CONFIG_DIR = "~/led-ticker/config"
REMOTE_STAGE = "/tmp/film-deploy.toml"
CONTAINER = "led-ticker"
STATE_FILE = Path("captures/.film-state.json")
POLL_SECONDS = 2.0
SSH_TIMEOUT = 30.0  # queries
MUTATE_TIMEOUT = (
    180.0  # cp + docker restart (restart waits for the old process to stop)
)
SCP_TIMEOUT = 60.0

_BRIGHTNESS = re.compile(r"^(brightness\s*=\s*)\d+", re.MULTILINE)


class DeployRefused(RuntimeError):
    pass


class RestoreRefused(RuntimeError):
    pass


def film_bak_name(now: datetime) -> str:
    return "config.toml.film-bak-" + now.strftime("%Y%m%dT%H%M%SZ")


def with_brightness(toml_text: str, brightness: int | None) -> str:
    if brightness is None:
        return toml_text
    text, n = _BRIGHTNESS.subn(rf"\g<1>{brightness}", toml_text, count=1)
    if n == 0:
        raise ValueError("config has no `brightness = N` line to override")
    return text


def _ssh(host: str, runner: Runner, cmd: str, *, timeout: float = SSH_TIMEOUT) -> str:
    res = runner.run(ssh_argv(host, cmd), timeout=timeout)
    if res.returncode != 0:
        raise RuntimeError(
            f"ssh {host} failed ({cmd}): {res.stderr.decode(errors='replace')}"
        )
    return res.stdout.decode(errors="replace")


def remote_sha256(host: str, runner: Runner, path: str = REMOTE_CONFIG) -> str:
    return _ssh(host, runner, f"sha256sum {path} | cut -d' ' -f1").strip()


def remote_list_film_baks(host: str, runner: Runner) -> list[str]:
    out = _ssh(
        host,
        runner,
        f"ls -1 {REMOTE_CONFIG_DIR}/config.toml.film-bak-* 2>/dev/null || true",
    )
    return sorted(Path(line.strip()).name for line in out.splitlines() if line.strip())


def remote_status(host: str, runner: Runner) -> dict:
    res = runner.run(
        ssh_argv(host, f"docker exec {CONTAINER} cat /run/led-ticker/status.json"),
        timeout=SSH_TIMEOUT,
    )
    if res.returncode != 0:
        return {}
    try:
        return json.loads(res.stdout.decode(errors="replace"))
    except ValueError:
        return {}


def wait_for_display(
    host: str,
    runner: Runner,
    *,
    previous_started_at: float | None,
    timeout: float = 90.0,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> dict:
    """Poll status.json until the display process has restarted and is swapping."""
    start = clock()
    while True:
        st = remote_status(host, runner)
        started = st.get("started_at")
        if (
            started is not None
            and started != previous_started_at
            and st.get("swap_count", 0) > 0
        ):
            return st
        if clock() - start > timeout:
            raise TimeoutError(f"display on {host} not up after {timeout:.0f}s")
        sleep(POLL_SECONDS)


def _load_state(state_file: Path) -> dict | None:
    if not state_file.exists():
        return None
    return json.loads(state_file.read_text())


def deploy(
    host: str,
    config: Path,
    runner: Runner,
    *,
    now: datetime,
    restore_first: bool = False,
    brightness: int | None = None,
    state_file: Path = STATE_FILE,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> dict:
    baks = remote_list_film_baks(host, runner)
    if baks:
        if not restore_first:
            raise DeployRefused(
                f"a film-bak already exists on {host} ({', '.join(baks)}); "
                "a previous session did not restore. Run `film restore` "
                "(or deploy with --restore-first)."
            )
        try:
            restore(
                host, runner, now=now, state_file=state_file, sleep=sleep, clock=clock
            )
        except RestoreRefused as exc:
            raise DeployRefused(
                f"cannot restore the existing film-bak automatically ({exc}); "
                "run `film restore --force` first"
            ) from exc
    previous = remote_status(host, runner).get("started_at")
    text = with_brightness(config.read_text(), brightness)
    sha = hashlib.sha256(text.encode()).hexdigest()
    bak = film_bak_name(now)
    with tempfile.NamedTemporaryFile("w", suffix=".toml", delete=False) as tmp:
        tmp.write(text)
        staged = Path(tmp.name)
    try:
        res = runner.run(scp_argv(staged, host, REMOTE_STAGE), timeout=SCP_TIMEOUT)
        if res.returncode != 0:
            raise RuntimeError(
                f"scp to {host} failed: {res.stderr.decode(errors='replace')}"
            )
    finally:
        staged.unlink(missing_ok=True)
    _ssh(
        host,
        runner,
        f"sudo cp {REMOTE_CONFIG} {REMOTE_CONFIG_DIR}/{bak} && "
        f"sudo cp {REMOTE_STAGE} {REMOTE_CONFIG} && sudo rm -f {REMOTE_STAGE} && "
        f"docker restart {CONTAINER}",
        timeout=MUTATE_TIMEOUT,
    )
    # The sign is now on the filming config: record that BEFORE waiting, so a
    # slow or failed boot can never leave a film-bak with no local state.
    state = {"host": host, "bak": bak, "sha256": sha, "deployed_at": now.isoformat()}
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps(state, indent=2) + "\n")
    try:
        wait_for_display(
            host, runner, previous_started_at=previous, sleep=sleep, clock=clock
        )
    except TimeoutError as exc:
        raise TimeoutError(
            f"{exc}. The sign IS on {config.name} (backup {bak}); "
            "run `film restore` to put the live config back."
        ) from exc
    return state


def restore(
    host: str,
    runner: Runner,
    *,
    now: datetime,
    force: bool = False,
    state_file: Path = STATE_FILE,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> str | None:
    state = _load_state(state_file)
    baks = remote_list_film_baks(host, runner)
    if not baks:
        print(f"nothing to restore on {host}: no film-bak present")
        state_file.unlink(missing_ok=True)
        return None
    bak = state["bak"] if state and state.get("bak") in baks else baks[-1]
    if len(baks) > 1:
        print(
            f"note: {len(baks)} film-baks on {host}; restoring {bak}, leaving the rest"
        )
    if not force:
        if state is None:
            raise RestoreRefused(
                f"film-bak {bak} is on {host} but there is no local deploy state "
                "to verify against; re-run with --force to restore it anyway"
            )
        current = remote_sha256(host, runner)
        if current != state["sha256"]:
            if current == remote_sha256(host, runner, f"{REMOTE_CONFIG_DIR}/{bak}"):
                # A previous restore's wait timed out after the copy: the live
                # config is already back. Just clean up.
                print(f"{host} already carries {bak}'s contents; cleaning up")
                _ssh(host, runner, f"sudo rm {REMOTE_CONFIG_DIR}/{bak}")
                state_file.unlink(missing_ok=True)
                return bak
            raise RestoreRefused(
                "the sign's config.toml changed since deploy "
                f"(deployed {state['sha256'][:12]}, now {current[:12]}); "
                "someone edited it mid-session. Re-run with --force to overwrite "
                "it with the film-bak"
            )
    previous = remote_status(host, runner).get("started_at")
    _ssh(
        host,
        runner,
        f"sudo cp {REMOTE_CONFIG_DIR}/{bak} {REMOTE_CONFIG} && "
        f"docker restart {CONTAINER}",
        timeout=MUTATE_TIMEOUT,
    )
    wait_for_display(
        host, runner, previous_started_at=previous, sleep=sleep, clock=clock
    )
    _ssh(host, runner, f"sudo rm {REMOTE_CONFIG_DIR}/{bak}")
    state_file.unlink(missing_ok=True)
    return bak
