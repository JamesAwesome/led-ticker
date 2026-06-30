import asyncio
import datetime

from led_ticker.sources import (
    ClockSource,
    DataRegistry,
    DateSource,
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
    assert f.has_tokens is False           # emoji slugs are not source candidates
    assert f.resolve(_reg()) == ("love :heart: it", False)


def test_unknown_token_falls_through_to_literal():
    f = TokenizedField("hi :nope.x: bye")
    assert f.resolve(_reg()) == ("hi :nope.x: bye", False)


def test_changed_flips_only_on_version_move():
    s = StaticSource(id="x", value="a")
    reg = _reg(s)
    f = TokenizedField("v=:x:")
    assert f.resolve(reg) == ("v=a", True)     # first resolve: changed
    assert f.resolve(reg) == ("v=a", False)    # no version move: unchanged
    s.value = "b"
    s.refresh()
    assert f.resolve(reg) == ("v=b", True)     # version moved: changed


def test_source_colliding_with_emoji_name_is_left_for_emoji():
    # If a name is an emoji slug, the pre-pass must NOT substitute it even
    # if a same-named source somehow exists (emoji wins).
    f = TokenizedField(":heart:")
    reg = _reg(StaticSource(id="heart", value="X"))
    assert f.resolve(reg) == (":heart:", False)


def test_resolve_reresolves_when_registry_object_changes():
    # Hot-reload installs a FRESH DataRegistry; sources start at version=1
    # after their first refresh. A surviving TokenizedField must NOT use its
    # stale cached text when handed the new registry object, even if the new
    # registry's version numbers happen to match the saved _last_versions.
    reg_a = _reg(StaticSource(id="x", value="a"))   # refresh → version=1
    f = TokenizedField(":x:")
    assert f.resolve(reg_a) == ("a", True)
    assert f.resolve(reg_a) == ("a", False)          # same registry: fast-path

    reg_b = _reg(StaticSource(id="x", value="NEWVAL"))  # fresh registry, also version=1
    # Version dict would be {'x': 1} == {'x': 1} → stale code returns ("a", False)
    result_text, result_changed = f.resolve(reg_b)
    assert result_text == "NEWVAL", (
        f"Expected 'NEWVAL' from new registry, got {result_text!r}"
    )
    assert result_changed is True
