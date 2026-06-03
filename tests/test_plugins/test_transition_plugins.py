import textwrap

import pytest

from led_ticker import _plugin_loader as L
from led_ticker.app.factories import _build_trans_obj
from led_ticker.config import TransitionConfig, _parse_transition
from led_ticker.validate import validate_config as run_validate


def _load(tmp_path, body):
    L.reset_plugins()
    (tmp_path / "plugins").mkdir(exist_ok=True)
    (tmp_path / "plugins" / "acme.py").write_text(textwrap.dedent(body))
    L.load_plugins(tmp_path / "plugins", entry_points_enabled=False)


def test_parse_transition_collects_unknown_keys_into_extra():
    cfg = _parse_transition(
        {"type": "acme.swoosh", "speed": 3, "trail": "x"}, TransitionConfig()
    )
    assert cfg.type == "acme.swoosh"
    assert cfg.extra == {"speed": 3, "trail": "x"}


def test_builtin_transition_keys_do_not_leak_into_extra():
    cfg = _parse_transition(
        {"type": "dissolve", "duration": 0.9, "transition_color": [1, 2, 3]},
        TransitionConfig(),
    )
    assert cfg.extra == {}


def test_plugin_transition_receives_its_config_kwargs(tmp_path):
    _load(
        tmp_path,
        """
        from led_ticker.plugin import Transition
        def register(api):
            @api.transition("swoosh")
            class Swoosh:
                min_frames = 0
                def __init__(self, speed=1):
                    self.speed = speed
                def frame_at(self, t, canvas, outgoing, incoming, **kw):
                    return canvas
        """,
    )
    try:
        obj = _build_trans_obj(
            _parse_transition({"type": "acme.swoosh", "speed": 7}, TransitionConfig())
        )
        assert obj.speed == 7
    finally:
        L.reset_plugins()


def test_plugin_transition_unknown_kwarg_raises_clean_valueerror(tmp_path):
    _load(
        tmp_path,
        """
        def register(api):
            @api.transition("swoosh")
            class Swoosh:
                min_frames = 0
                def __init__(self, speed=1):
                    self.speed = speed
                def frame_at(self, t, canvas, outgoing, incoming, **kw):
                    return canvas
        """,
    )
    try:
        with pytest.raises(ValueError, match="unknown keys"):
            _build_trans_obj(
                _parse_transition(
                    {"type": "acme.swoosh", "nope": 1}, TransitionConfig()
                )
            )
    finally:
        L.reset_plugins()


def test_plugin_transition_missing_required_kwarg_raises_clean_valueerror(tmp_path):
    _load(
        tmp_path,
        """
        def register(api):
            @api.transition("swoosh")
            class Swoosh:
                min_frames = 0
                def __init__(self, speed):  # required, no default
                    self.speed = speed
                def frame_at(self, t, canvas, outgoing, incoming, **kw):
                    return canvas
        """,
    )
    try:
        with pytest.raises(ValueError, match="missing required keys"):
            _build_trans_obj(
                _parse_transition({"type": "acme.swoosh"}, TransitionConfig())
            )
    finally:
        L.reset_plugins()


async def test_validate_surfaces_plugin_transition_bad_kwarg(tmp_path):
    L.reset_plugins()
    (tmp_path / "plugins").mkdir(exist_ok=True)
    (tmp_path / "plugins" / "acme.py").write_text(
        textwrap.dedent(
            """
            def register(api):
                @api.transition("swoosh")
                class Swoosh:
                    min_frames = 0
                    def __init__(self, speed=1):
                        self.speed = speed
                    def frame_at(self, t, canvas, outgoing, incoming, **kw):
                        return canvas
            """
        )
    )
    (tmp_path / "config.toml").write_text(
        textwrap.dedent(
            """
            [display]
            rows = 16
            cols = 64

            [[playlist.section]]
            transition = {type = "acme.swoosh", nope = 1}
            [[playlist.section.widget]]
            type = "message"
            text = "hi"
            """
        )
    )
    try:
        result = await run_validate(tmp_path / "config.toml")
        joined = " ".join(e.message for e in result.errors)
        assert "acme.swoosh" in joined and "unknown keys" in joined
        assert not result.valid
        assert any(e.rule == 53 for e in result.errors)
    finally:
        L.reset_plugins()
