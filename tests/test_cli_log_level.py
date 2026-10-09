"""`led-ticker --log-level` / `LED_TICKER_LOG_LEVEL`, and the ticker's
per-scroll chatter staying out of INFO.

The root logger was hard-wired to INFO with no knob, and `ticker.py` logged
every section visit and every scroll loop at INFO through the ROOT logger
(`logging.info(...)`), so a deployed sign's `docker logs` filled with
`root - INFO - Running Slideshow with loop count 1...` /
`Running _scroll_and_delay ...` lines that drown the plugin messages worth
reading. Two fixes, pinned here: the level is configurable (flag wins over
the environment variable, default INFO), and `ticker.py` logs through its
module logger at DEBUG for the chatter.
"""

import ast
import logging
from pathlib import Path
from unittest import mock

import pytest

import led_ticker.app.cli as cli_mod

REPO_ROOT = Path(__file__).resolve().parent.parent
TICKER_PY = REPO_ROOT / "src" / "led_ticker" / "ticker.py"


@pytest.fixture
def root_logger_reset():
    """Restore the root logger after `main()` configures it, so the level
    and the added StreamHandler don't leak into other tests."""
    root = logging.getLogger()
    level, handlers = root.level, list(root.handlers)
    yield root
    root.setLevel(level)
    for h in list(root.handlers):
        if h not in handlers:
            root.removeHandler(h)


def _run_main(tmp_path: Path, argv: list[str]) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text("[display]\nrows = 16\ncols = 32\n")

    async def fake_run(config_path: Path, backend_override: str | None = None) -> None:
        return None

    with (
        mock.patch.object(cli_mod, "run", fake_run),
        mock.patch("sys.argv", ["led-ticker", "--config", str(config_file), *argv]),
    ):
        cli_mod.main()


def test_default_level_is_info(tmp_path, monkeypatch, root_logger_reset):
    monkeypatch.delenv("LED_TICKER_LOG_LEVEL", raising=False)
    _run_main(tmp_path, [])
    assert root_logger_reset.level == logging.INFO


def test_flag_sets_root_level(tmp_path, monkeypatch, root_logger_reset):
    monkeypatch.delenv("LED_TICKER_LOG_LEVEL", raising=False)
    _run_main(tmp_path, ["--log-level", "debug"])
    assert root_logger_reset.level == logging.DEBUG


def test_env_var_sets_root_level(tmp_path, monkeypatch, root_logger_reset):
    """A Docker deploy has no argv to edit — `.env` is where the knob lives."""
    monkeypatch.setenv("LED_TICKER_LOG_LEVEL", "warning")
    _run_main(tmp_path, [])
    assert root_logger_reset.level == logging.WARNING


def test_flag_beats_env_var(tmp_path, monkeypatch, root_logger_reset):
    monkeypatch.setenv("LED_TICKER_LOG_LEVEL", "error")
    _run_main(tmp_path, ["--log-level", "DEBUG"])
    assert root_logger_reset.level == logging.DEBUG


def test_level_is_case_insensitive_and_validated(
    tmp_path, monkeypatch, root_logger_reset
):
    monkeypatch.delenv("LED_TICKER_LOG_LEVEL", raising=False)
    _run_main(tmp_path, ["--log-level", "Warning"])
    assert root_logger_reset.level == logging.WARNING
    with pytest.raises(SystemExit) as exc:
        _run_main(tmp_path, ["--log-level", "loud"])
    assert exc.value.code == 2  # argparse usage error, not a traceback


def test_handler_follows_the_level(tmp_path, monkeypatch, root_logger_reset):
    """Setting the root to DEBUG is useless if the handler still filters at
    INFO — the handler `main()` installs must sit at (or below) the
    configured level. Only the handler this call added is checked; other
    tests leave their own handlers on the root."""
    monkeypatch.delenv("LED_TICKER_LOG_LEVEL", raising=False)
    before = {id(h) for h in root_logger_reset.handlers}
    _run_main(tmp_path, ["--log-level", "debug"])
    added = [h for h in root_logger_reset.handlers if id(h) not in before]
    assert added and all(h.level <= logging.DEBUG for h in added)


def test_ticker_module_never_logs_through_the_root_logger():
    """AST tripwire: every log call in ticker.py goes through its module
    `logger`, never `logging.<level>(...)`. Root-logger calls print as
    `root - INFO - ...` and can't be filtered per module."""
    tree = ast.parse(TICKER_PY.read_text())
    offenders = [
        f"{TICKER_PY.name}:{node.lineno}: logging.{node.func.attr}(...)"
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "logging"
        and node.func.attr
        in {"debug", "info", "warning", "error", "critical", "exception"}
    ]
    assert not offenders, "\n".join(offenders)


def test_ticker_scroll_chatter_is_debug_not_info():
    """The per-visit / per-scroll-loop messages must be DEBUG. Source-level
    check: none of them may be emitted at info."""
    source = TICKER_PY.read_text()
    for needle in (
        "Running Slideshow with loop count",
        "Running Ticker with loop count",
        "Running One-at-a-time with loop count",
        "Running _scroll_and_delay",
        "Returned to _scroll_one_by_one",
        "Running _scroll_side_by_side",
        "Returned to _scroll_side_by_side",
    ):
        line = next(ln for ln in source.splitlines() if needle in ln)
        assert "logger.debug(" in line, f"not DEBUG: {line.strip()}"
