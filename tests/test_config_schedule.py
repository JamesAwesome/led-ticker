import textwrap

from led_ticker.config import ScheduleConfig, ScheduleWindow, load_config


def _write(tmp_path, body):
    p = tmp_path / "config.toml"
    p.write_text(textwrap.dedent(body))
    return p


def test_schedule_absent_defaults_to_disabled(tmp_path):
    cfg = load_config(_write(tmp_path, "[display]\nrows=16\ncols=64\n"))
    assert isinstance(cfg.display.schedule, ScheduleConfig)
    assert cfg.display.schedule.enabled is False
    assert cfg.display.schedule.windows == []


def test_malformed_windows_non_list_loads_without_raising(tmp_path):
    """windows = 'oops' (string, not array) must load without raising (FIX 3)."""
    cfg = load_config(
        _write(
            tmp_path,
            """
            [display]
            rows = 16
            cols = 64

            [display.schedule]
            enabled = true
            windows = "oops"
            """,
        )
    )
    assert cfg.display.schedule.windows == []


def test_malformed_window_non_dict_skipped(tmp_path):
    """A window entry that isn't a table (e.g. an int) is skipped (FIX 3)."""
    # TOML doesn't allow [[array]] entries that are not tables, so test
    # _coerce_schedule directly with a hand-crafted raw dict.
    from led_ticker.config import _coerce_schedule

    result = _coerce_schedule(
        {
            "enabled": True,
            "windows": [
                {"start": "07:00", "end": "18:00", "brightness": 100},
                "not-a-dict",
                42,
            ],
        }
    )
    assert len(result.windows) == 1
    assert result.windows[0].start == "07:00"


def test_schedule_parses_windows_and_lowercases_days(tmp_path):
    cfg = load_config(
        _write(
            tmp_path,
            """
            [display]
            rows = 16
            cols = 64

            [display.schedule]
            enabled = true
            timezone = "America/New_York"

            [[display.schedule.windows]]
            start = "07:00"
            end = "18:00"
            brightness = 100

            [[display.schedule.windows]]
            start = "23:00"
            end = "07:00"
            brightness = 0
            days = ["Fri", "SAT"]
            """,
        )
    )
    s = cfg.display.schedule
    assert s.enabled is True
    assert s.timezone == "America/New_York"
    assert len(s.windows) == 2
    assert s.windows[0] == ScheduleWindow(
        start="07:00", end="18:00", brightness=100, days=[]
    )
    assert s.windows[1].days == ["fri", "sat"]  # lowercased
