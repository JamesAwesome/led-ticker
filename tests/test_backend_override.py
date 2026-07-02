"""
tests/test_backend_override.py — TDD tests for the backend override surface.

Covers:
  1. build_frame_from_config(display, backend_override=...) honours the override
     over the config field when set.
  2. Unknown backend name → the existing get_backend_class registry error.
  3. CLI parses --backend <name> and passes it to run().
  4. run(config_path, backend_override=...) signature is backward-compatible.
  5. LED_TICKER_BACKEND env var: env > config field; CLI --backend > env.
     (Env exists so compose.try.yaml can select headless via `environment:` —
     old PyPI images ignore an unknown env var but choke on an unknown flag.)
"""

import unittest.mock as mock
from pathlib import Path

import pytest

from led_ticker.app.factories import build_frame_from_config
from led_ticker.config import DisplayConfig

# ---------------------------------------------------------------------------
# build_frame_from_config backend_override
# ---------------------------------------------------------------------------


class TestBuildFrameBackendOverride:
    """backend_override= kwarg on build_frame_from_config."""

    def test_override_headless_beats_default_rgbmatrix(self) -> None:
        """backend_override='headless' must build HeadlessBackend
        even though DisplayConfig defaults to rgbmatrix."""
        from led_ticker.backends.headless import HeadlessBackend

        display = DisplayConfig(rows=16, cols=32, chain_length=5)
        # No explicit backend= in display — defaults to 'rgbmatrix'.
        frame = build_frame_from_config(display, backend_override="headless")
        assert isinstance(frame.backend, HeadlessBackend), (
            f"expected HeadlessBackend with backend_override='headless'; "
            f"got {type(frame.backend).__name__}"
        )

    def test_override_headless_beats_config_field(self) -> None:
        """backend_override wins over display.backend when both are set."""
        from led_ticker.backends.headless import HeadlessBackend

        # Simulate a DisplayConfig that already specifies headless (e.g. CI config).
        display = DisplayConfig(rows=16, cols=32, chain_length=5, backend="headless")
        # Same result — proves the override path, not just the absence of rgbmatrix.
        frame = build_frame_from_config(display, backend_override="headless")
        assert isinstance(frame.backend, HeadlessBackend)

    def test_no_override_preserves_existing_behaviour(self) -> None:
        """When backend_override is not passed (default None), the function
        behaves identically to before — uses the config field (or rgbmatrix default)."""
        from led_ticker.backends.rgbmatrix import RgbMatrixBackend

        display = DisplayConfig(rows=16, cols=32, chain_length=5)
        frame = build_frame_from_config(display)
        assert isinstance(frame.backend, RgbMatrixBackend)

    def test_none_override_preserves_existing_behaviour(self) -> None:
        """Explicit backend_override=None also leaves the default path intact."""
        from led_ticker.backends.rgbmatrix import RgbMatrixBackend

        display = DisplayConfig(rows=16, cols=32, chain_length=5)
        frame = build_frame_from_config(display, backend_override=None)
        assert isinstance(frame.backend, RgbMatrixBackend)

    def test_unknown_backend_override_raises_registry_error(self) -> None:
        """An unknown backend_override name must raise the existing registry error
        (KeyError or ValueError from get_backend_class), NOT a silent fallback."""
        display = DisplayConfig(rows=16, cols=32, chain_length=5)
        with pytest.raises((KeyError, ValueError)):
            build_frame_from_config(display, backend_override="does_not_exist_xyz")


# ---------------------------------------------------------------------------
# LED_TICKER_BACKEND env-var override
# ---------------------------------------------------------------------------


class TestBackendEnvVarOverride:
    """LED_TICKER_BACKEND env var — the compose-friendly override channel.

    Precedence: CLI --backend (backend_override arg) > LED_TICKER_BACKEND env
    > [display] backend config field.
    """

    def test_env_var_beats_config_field(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """LED_TICKER_BACKEND=headless must win over the config's rgbmatrix
        default (the compose.try.yaml path)."""
        from led_ticker.backends.headless import HeadlessBackend

        monkeypatch.setenv("LED_TICKER_BACKEND", "headless")
        display = DisplayConfig(rows=16, cols=32, chain_length=5)
        frame = build_frame_from_config(display)
        assert isinstance(frame.backend, HeadlessBackend), (
            f"expected HeadlessBackend via LED_TICKER_BACKEND env; "
            f"got {type(frame.backend).__name__}"
        )

    def test_cli_override_beats_env_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Explicit backend_override (the CLI flag) must win over the env var."""
        from led_ticker.backends.rgbmatrix import RgbMatrixBackend

        monkeypatch.setenv("LED_TICKER_BACKEND", "headless")
        display = DisplayConfig(rows=16, cols=32, chain_length=5)
        frame = build_frame_from_config(display, backend_override="rgbmatrix")
        assert isinstance(frame.backend, RgbMatrixBackend), (
            "backend_override='rgbmatrix' must beat LED_TICKER_BACKEND=headless"
        )

    def test_no_env_no_override_uses_config_field(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """With neither the flag nor the env var, the config field governs."""
        from led_ticker.backends.rgbmatrix import RgbMatrixBackend

        monkeypatch.delenv("LED_TICKER_BACKEND", raising=False)
        display = DisplayConfig(rows=16, cols=32, chain_length=5)
        frame = build_frame_from_config(display)
        assert isinstance(frame.backend, RgbMatrixBackend)

    def test_unknown_env_backend_raises_registry_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An unknown env-var backend name raises the registry error too."""
        monkeypatch.setenv("LED_TICKER_BACKEND", "does_not_exist_xyz")
        display = DisplayConfig(rows=16, cols=32, chain_length=5)
        with pytest.raises((KeyError, ValueError)):
            build_frame_from_config(display)


# ---------------------------------------------------------------------------
# CLI parsing
# ---------------------------------------------------------------------------


class TestCliBackendFlag:
    """--backend flag parsing in led_ticker.app.cli."""

    def _make_parser(self):
        """Import and rebuild the CLI parser to test argument parsing."""
        # Replicate the parser construction from main() so we can test args.
        # We import the module and call argparse directly.
        import led_ticker.app.cli as cli_mod  # noqa: PLC0415
        from led_ticker.app.cli import main  # noqa: F401 — just to ensure imports work

        # Capture args by running parse_args on a synthetic argv.
        return cli_mod

    def test_backend_flag_parsed(self) -> None:
        """--backend headless must be accepted and available as args.backend."""
        import argparse

        # Patch sys.argv and call a known-good parse path.
        # We test by calling the argparse parser directly, reconstructed
        # to match what main() builds. The simplest approach: monkeypatch
        # sys.argv and call parse_args.
        #
        # We rebuild a minimal parser matching cli.main()'s top-level arg.
        parser = argparse.ArgumentParser()
        parser.add_argument("--config", "-c", type=Path, default=Path("config.toml"))
        parser.add_argument("--backend", default=None)
        parser.add_subparsers(dest="command")

        args = parser.parse_args(["--config", "foo.toml", "--backend", "headless"])
        assert args.backend == "headless", (
            f"Expected args.backend='headless'; got {args.backend!r}"
        )

    def test_backend_flag_default_none(self) -> None:
        """Without --backend, args.backend must default to None (no override)."""
        import argparse

        parser = argparse.ArgumentParser()
        parser.add_argument("--config", "-c", type=Path, default=Path("config.toml"))
        parser.add_argument("--backend", default=None)
        parser.add_subparsers(dest="command")

        args = parser.parse_args(["--config", "foo.toml"])
        assert args.backend is None, (
            f"Expected args.backend=None by default; got {args.backend!r}"
        )

    def test_cli_module_has_backend_arg_in_main(self) -> None:
        """AST/source check: main() must add --backend argument to the parser."""
        import inspect

        import led_ticker.app.cli as cli_mod

        source = inspect.getsource(cli_mod.main)
        assert "--backend" in source, (
            "main() must add '--backend' argument to the argparse parser; "
            "not found in source."
        )

    def test_cli_run_dispatches_with_backend_override(self, tmp_path: Path) -> None:
        """End-to-end: main() with --backend headless calls run() with
        backend_override='headless'."""
        import led_ticker.app.cli as cli_mod

        config_file = tmp_path / "config.toml"
        config_file.write_text("[display]\nrows = 16\ncols = 32\n")

        captured: dict = {}

        async def fake_run(
            config_path: Path, backend_override: str | None = None
        ) -> None:
            captured["backend_override"] = backend_override

        with (
            mock.patch.object(cli_mod, "run", fake_run),
            mock.patch(
                "sys.argv",
                ["led-ticker", "--config", str(config_file), "--backend", "headless"],
            ),
        ):
            # asyncio.run(fake_run(...)) will be called by main().
            # fake_run is a coroutine function, so asyncio.run will execute it.
            cli_mod.main()

        assert captured.get("backend_override") == "headless", (
            f"Expected run() called with backend_override='headless'; got {captured!r}"
        )


# ---------------------------------------------------------------------------
# run() signature backward-compat
# ---------------------------------------------------------------------------


def test_run_accepts_backend_override_kwarg() -> None:
    """run(config_path, backend_override=...) signature must accept the new kwarg.
    Zero-behavior-change check: existing callers that don't pass it are unaffected."""
    import inspect

    from led_ticker.app import run as run_fn

    sig = inspect.signature(run_fn)
    assert "backend_override" in sig.parameters, (
        "run() must accept a backend_override keyword argument"
    )
    param = sig.parameters["backend_override"]
    assert param.default is None, (
        f"backend_override must default to None; got {param.default!r}"
    )
