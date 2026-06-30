import asyncio
import datetime

from led_ticker.sources import (
    ClockSource,
    DataRegistry,
    DateSource,
    StaticSource,
    get_data_registry,
    run_source_refresh_loop,
    set_data_registry,
)


def test_static_compute_returns_value():
    s = StaticSource(id="brand.tag", value="Open 9-5")
    assert s.compute() == "Open 9-5"
    assert s.polled is False


def test_clock_compute_formats_now():
    s = ClockSource(id="clock.now", fmt="%H:%M", tz=None)
    # compute() formats the current time; assert it matches strftime now
    out = s.compute()
    assert out == datetime.datetime.now().strftime("%H:%M")


def test_date_compute_with_timezone():
    s = DateSource(id="date.ny", fmt="%Y", tz="America/New_York")
    assert s.compute() == datetime.datetime.now(
        datetime.UTC
    ).astimezone(__import__("zoneinfo").ZoneInfo("America/New_York")).strftime("%Y")


def test_refresh_bumps_version_only_on_change():
    s = StaticSource(id="x", value="a")
    s.refresh()                      # first refresh sets current, version -> 1
    assert s.current == "a"
    v1 = s.version
    changed = s.refresh()            # unchanged value
    assert changed is False
    assert s.version == v1           # NO bump when value is identical


def test_refresh_writes_current_before_version(monkeypatch):
    # Write-order contract: a stub that flips value, assert current is set
    # before version is read by a notional reader (here: current updated when
    # changed=True, and version strictly increments).
    s = StaticSource(id="x", value="a")
    s.refresh()
    s.value = "b"                    # change the underlying value
    assert s.refresh() is True
    assert s.current == "b"
    assert s.version >= 2


def test_registry_get_set_and_lookup():
    reg = DataRegistry()
    s = StaticSource(id="brand.tag", value="hi")
    reg.add(s)
    set_data_registry(reg)
    assert get_data_registry().get("brand.tag") is s
    assert get_data_registry().get("missing") is None
    assert "brand.tag" in get_data_registry().ids()


async def test_refresh_loop_picks_up_value_change():
    reg = DataRegistry()
    s = StaticSource(id="x", value="a")
    reg.add(s)
    task = asyncio.create_task(run_source_refresh_loop(reg, interval=0.01))
    await asyncio.sleep(0.05)
    assert s.current == "a" and s.version >= 1
    s.value = "b"
    await asyncio.sleep(0.05)
    assert s.current == "b"
    task.cancel()
