import textwrap

from led_ticker.validate import validate_config


def _cfg(tmp_path, body):
    p = tmp_path / "config.toml"
    p.write_text(textwrap.dedent(body))
    return p


def _base(extra):
    return f"[display]\nrows=16\ncols=64\nbrightness=60\n{extra}"


async def _validate(tmp_path, extra):
    return await validate_config(_cfg(tmp_path, _base(extra)))


async def test_bad_timezone_is_error(tmp_path):
    res = await _validate(
        tmp_path,
        '[display.schedule]\nenabled=true\ntimezone="Not/AZone"\n'
        '[[display.schedule.windows]]\nstart="07:00"\nend="18:00"\nbrightness=100\n',
    )
    assert any("timezone" in e.message.lower() for e in res.errors)


async def test_bad_hhmm_and_brightness_are_errors(tmp_path):
    res = await _validate(
        tmp_path,
        "[display.schedule]\nenabled=true\n"
        '[[display.schedule.windows]]\nstart="7am"\nend="18:00"\nbrightness=150\n',
    )
    msgs = " ".join(e.message.lower() for e in res.errors)
    assert "start" in msgs or "hh:mm" in msgs
    assert "brightness" in msgs


async def test_start_equals_end_is_error(tmp_path):
    res = await _validate(
        tmp_path,
        "[display.schedule]\nenabled=true\n"
        '[[display.schedule.windows]]\nstart="08:00"\nend="08:00"\nbrightness=50\n',
    )
    assert any(
        "start" in e.message.lower() and "end" in e.message.lower() for e in res.errors
    )


async def test_bad_day_is_error(tmp_path):
    res = await _validate(
        tmp_path,
        "[display.schedule]\nenabled=true\n"
        '[[display.schedule.windows]]\nstart="07:00"\nend="18:00"\nbrightness=100\ndays=["funday"]\n',
    )
    assert any("day" in e.message.lower() for e in res.errors)


async def test_enabled_empty_windows_warns(tmp_path):
    res = await _validate(tmp_path, "[display.schedule]\nenabled=true\n")
    assert any("window" in w.message.lower() for w in res.warnings)


async def test_fully_shadowed_window_warns(tmp_path):
    res = await _validate(
        tmp_path,
        "[display.schedule]\nenabled=true\n"
        '[[display.schedule.windows]]\nstart="12:00"\nend="13:00"\nbrightness=30\n'
        '[[display.schedule.windows]]\nstart="07:00"\nend="23:00"\nbrightness=100\n',
    )
    assert any(
        "shadow" in w.message.lower() or "never" in w.message.lower()
        for w in res.warnings
    )


async def test_valid_schedule_has_summary_notes(tmp_path):
    res = await _validate(
        tmp_path,
        "[display.schedule]\nenabled=true\n"
        '[[display.schedule.windows]]\nstart="23:00"\nend="07:00"\nbrightness=0\n',
    )
    assert res.valid
    assert any("overnight" in n for n in res.notes)


async def test_omitted_days_is_valid(tmp_path):
    res = await _validate(
        tmp_path,
        "[display.schedule]\nenabled=true\n"
        '[[display.schedule.windows]]\nstart="07:00"\nend="18:00"\nbrightness=80\n',
    )
    assert not any("day" in e.message.lower() for e in res.errors)


async def test_brightness_true_bool_is_error(tmp_path):
    res = await _validate(
        tmp_path,
        "[display.schedule]\nenabled=true\n"
        '[[display.schedule.windows]]\nstart="07:00"\nend="18:00"\nbrightness=true\n',
    )
    assert any("brightness" in e.message.lower() for e in res.errors)
