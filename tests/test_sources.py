import asyncio
import datetime

import attrs
import pytest

from led_ticker.sources import (
    ClockSource,
    DataRegistry,
    DateSource,
    PolledDataSource,
    StaticSource,
    TokenizedField,
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
    assert s.compute() == datetime.datetime.now(datetime.UTC).astimezone(
        __import__("zoneinfo").ZoneInfo("America/New_York")
    ).strftime("%Y")


def test_refresh_bumps_version_only_on_change():
    s = StaticSource(id="x", value="a")
    s.refresh()  # first refresh sets current, version -> 1
    assert s.current == "a"
    v1 = s.version
    changed = s.refresh()  # unchanged value
    assert changed is False
    assert s.version == v1  # NO bump when value is identical


def test_refresh_writes_current_before_version():
    # Write-order contract: a stub that flips value, assert current is set
    # before version is read by a notional reader (here: current updated when
    # changed=True, and version strictly increments).
    s = StaticSource(id="x", value="a")
    s.refresh()
    s.value = "b"  # change the underlying value
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


# --- TokenizedField tests ---


def _reg(*srcs):
    r = DataRegistry()
    for s in srcs:
        s.refresh()
        r.add(s)
    return r


def test_field_with_no_tokens_is_inert():
    f = TokenizedField("plain text, no tokens")
    assert f.has_tokens is False
    assert f.resolve(DataRegistry()) == ("plain text, no tokens", False)


def test_declared_source_is_substituted():
    f = TokenizedField("now: :clock.now:!")
    reg = _reg(StaticSource(id="clock.now", value="9:01"))
    assert f.resolve(reg) == ("now: 9:01!", True)


def test_emoji_slug_is_preserved_not_substituted():
    # :heart: is an emoji slug, not a source — left intact for draw_with_emoji
    f = TokenizedField("love :heart: it")
    assert f.has_tokens is False  # emoji slugs are not source candidates
    assert f.resolve(_reg()) == ("love :heart: it", False)


def test_unknown_token_falls_through_to_literal():
    f = TokenizedField("hi :nope.x: bye")
    assert f.resolve(_reg()) == ("hi :nope.x: bye", False)


def test_changed_flips_only_on_version_move():
    s = StaticSource(id="x", value="a")
    reg = _reg(s)
    f = TokenizedField("v=:x:")
    assert f.resolve(reg) == ("v=a", True)  # first resolve: changed
    assert f.resolve(reg) == ("v=a", False)  # no version move: unchanged
    s.value = "b"
    s.refresh()
    assert f.resolve(reg) == ("v=b", True)  # version moved: changed


def test_source_colliding_with_emoji_name_is_left_for_emoji():
    # If a name is an emoji slug, the pre-pass must NOT substitute it even
    # if a same-named source somehow exists (emoji wins).
    f = TokenizedField(":heart:")
    reg = _reg(StaticSource(id="heart", value="X"))
    assert f.resolve(reg) == (":heart:", False)


class TestSourceFactory:
    def test_get_source_class_known_types(self):
        from led_ticker.app.factories import get_source_class
        from led_ticker.sources import ClockSource, DateSource, StaticSource

        assert get_source_class("clock") is ClockSource
        assert get_source_class("date") is DateSource
        assert get_source_class("static") is StaticSource

    def test_get_source_class_unknown_type_raises(self):
        from led_ticker.app.factories import get_source_class

        with pytest.raises(ValueError, match="Unknown source type"):
            get_source_class("nope")

    def test_build_source_clock_passes_format_and_tz(self):
        from led_ticker.app.factories import build_source
        from led_ticker.config import SourceConfig
        from led_ticker.sources import ClockSource

        sc = SourceConfig(
            id="clock.now",
            type="clock",
            raw={"id": "clock.now", "type": "clock", "format": "%H", "timezone": None},
        )
        src = build_source(sc)
        assert isinstance(src, ClockSource)
        assert src.id == "clock.now"
        assert src.fmt == "%H"

    def test_build_source_clock_defaults_format(self):
        from led_ticker.app.factories import build_source
        from led_ticker.config import SourceConfig

        sc = SourceConfig(
            id="clock.now",
            type="clock",
            raw={"id": "clock.now", "type": "clock"},
        )
        src = build_source(sc)
        assert src.fmt == "%H:%M"

    def test_build_source_date_is_date_source(self):
        from led_ticker.app.factories import build_source
        from led_ticker.config import SourceConfig
        from led_ticker.sources import DateSource

        sc = SourceConfig(
            id="date.today",
            type="date",
            raw={"id": "date.today", "type": "date", "format": "%Y-%m-%d"},
        )
        src = build_source(sc)
        assert isinstance(src, DateSource)
        assert src.fmt == "%Y-%m-%d"

    def test_build_source_static_passes_value(self):
        from led_ticker.app.factories import build_source
        from led_ticker.config import SourceConfig
        from led_ticker.sources import StaticSource

        sc = SourceConfig(
            id="brand.tag",
            type="static",
            raw={"id": "brand.tag", "type": "static", "value": "Open 9-5"},
        )
        src = build_source(sc)
        assert isinstance(src, StaticSource)
        assert src.id == "brand.tag"
        assert src.value == "Open 9-5"

    def test_build_source_static_default_value(self):
        from led_ticker.app.factories import build_source
        from led_ticker.config import SourceConfig

        sc = SourceConfig(
            id="empty",
            type="static",
            raw={"id": "empty", "type": "static"},
        )
        src = build_source(sc)
        assert src.value == ""


def test_set_value_write_order_and_bump_only_on_change():
    s = StaticSource(id="x", value="a")
    assert s._set_value("a") is True  # first set bumps from version 0
    assert (s.current, s.version) == ("a", 1)
    assert s._set_value("a") is False  # unchanged → no bump
    assert s.version == 1
    assert s._set_value("b") is True  # changed → bump
    assert (s.current, s.version) == ("b", 2)


def test_polled_source_is_polled_and_holds_session_interval():
    @attrs.define(eq=False)
    class _Fake(PolledDataSource):
        async def update(self) -> None:
            self._set_value("hello")

    s = _Fake(id="acme.live", session="SESS", interval=42)
    assert s.polled is True
    assert s.session == "SESS"
    assert s.interval == 42
    assert s.current == "" and s.version == 0  # nothing until update()


@pytest.mark.asyncio
async def test_polled_update_sets_value_write_order():
    @attrs.define(eq=False)
    class _Fake(PolledDataSource):
        async def update(self) -> None:
            await asyncio.sleep(0)  # the fetch await happens BEFORE...
            self._set_value("123")  # ...the synchronous current+version set

    s = _Fake(id="acme.live")
    await s.update()
    assert (s.current, s.version) == ("123", 1)


def test_polled_compute_raises():
    @attrs.define(eq=False)
    class _Fake(PolledDataSource):
        async def update(self) -> None: ...

    with pytest.raises(NotImplementedError):
        _Fake(id="x").compute()


def test_sync_refresh_still_works():
    s = StaticSource(id="x", value="z")
    assert s.refresh() is True and s.current == "z" and s.version == 1
    assert s.refresh() is False and s.version == 1


def test_resolve_reresolves_when_registry_object_changes():
    # Hot-reload installs a FRESH DataRegistry; sources start at version=1
    # after their first refresh. A surviving TokenizedField must NOT use its
    # stale cached text when handed the new registry object, even if the new
    # registry's version numbers happen to match the saved _last_versions.
    reg_a = _reg(StaticSource(id="x", value="a"))  # refresh → version=1
    f = TokenizedField(":x:")
    assert f.resolve(reg_a) == ("a", True)
    assert f.resolve(reg_a) == ("a", False)  # same registry: fast-path

    reg_b = _reg(StaticSource(id="x", value="NEWVAL"))  # fresh registry, also version=1
    # Version dict would be {'x': 1} == {'x': 1} → stale code returns ("a", False)
    result_text, result_changed = f.resolve(reg_b)
    assert result_text == "NEWVAL", (
        f"Expected 'NEWVAL' from new registry, got {result_text!r}"
    )
    assert result_changed is True
