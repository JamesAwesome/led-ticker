"""Live value sources for inline `:source.id:` tokens.

A DataSource produces a string value (`current`) and an integer `version`
that bumps ONLY when the value changes. v1 ships synchronous sources
(clock/date/static); the `polled` field is part of the contract but the
background-loop wiring is deferred to v2.

Write-order contract (binds future polled sources): write `current` BEFORE
`version`, with no `await` between, so a reader sampling version-then-current
can never pair a new version with a stale value.
"""

import asyncio
import datetime
import re
from typing import Any
from zoneinfo import ZoneInfo

import attrs

from led_ticker.pixel_emoji import EMOJI_PATTERN, is_emoji_slug
from led_ticker.widget import spawn_tracked


@attrs.define(eq=False)
class DataSource:
    """Base class. Subclasses implement compute(); refresh() applies it."""

    id: str
    polled: bool = attrs.field(default=False, kw_only=True)
    current: str = attrs.field(default="", init=False)
    version: int = attrs.field(default=0, init=False)

    def compute(self) -> str:
        raise NotImplementedError

    def refresh(self) -> bool:
        """Recompute; bump version iff the value changed. Returns changed."""
        value = self.compute()
        if value == self.current and self.version != 0:
            return False
        self.current = value          # current BEFORE version (contract)
        self.version += 1
        return True


@attrs.define(eq=False)
class StaticSource(DataSource):
    value: str = ""

    def compute(self) -> str:
        return self.value


@attrs.define(eq=False)
class ClockSource(DataSource):
    fmt: str = "%H:%M"
    tz: str | None = None

    def compute(self) -> str:
        now = (
            datetime.datetime.now(ZoneInfo(self.tz))
            if self.tz
            else datetime.datetime.now()
        )
        return now.strftime(self.fmt)


@attrs.define(eq=False)
class DateSource(ClockSource):
    """Same machinery as ClockSource; separate type for config clarity."""


class DataRegistry:
    def __init__(self) -> None:
        self._by_id: dict[str, DataSource] = {}

    def add(self, source: DataSource) -> None:
        self._by_id[source.id] = source

    def get(self, source_id: str) -> DataSource | None:
        return self._by_id.get(source_id)

    def ids(self) -> set[str]:
        return set(self._by_id)

    def sources(self) -> list[DataSource]:
        return list(self._by_id.values())


_REGISTRY: DataRegistry = DataRegistry()


def get_data_registry() -> DataRegistry:
    return _REGISTRY


def set_data_registry(registry: DataRegistry) -> None:
    """Atomically swap the process registry (used at startup + hot-reload)."""
    global _REGISTRY
    _REGISTRY = registry


async def run_source_refresh_loop(
    registry: DataRegistry, interval: float = 1.0
) -> None:
    """1 Hz: refresh every synchronous source; version bumps drive widgets."""
    while True:
        for source in registry.sources():
            if not source.polled:
                source.refresh()
        await asyncio.sleep(interval)


def spawn_source_refresh(registry: DataRegistry) -> Any:
    """Prime each source once, then spawn the 1 Hz loop (tracked task)."""
    for source in registry.sources():
        if not source.polled:
            source.refresh()
    return spawn_tracked(run_source_refresh_loop(registry))


class TokenizedField:
    """Compile-once template for one text field; substitutes declared-source
    tokens, leaves emoji/unknown/literal intact, and re-substitutes only when
    a referenced source's version moves.
    """

    def __init__(self, text: str) -> None:
        self._raw = text
        # Candidate source ids = :slug: tokens that are NOT emoji slugs.
        self._candidate_ids: list[str] = []
        for m in EMOJI_PATTERN.finditer(text):
            slug = m.group()[1:-1]
            if not is_emoji_slug(slug) and slug not in self._candidate_ids:
                self._candidate_ids.append(slug)
        self._last_versions: dict[str, int] = {}
        self._last_registry_id: int = 0   # id() of the last registry resolved against
        self._cached: str = text
        self._first: bool = True

    @property
    def has_tokens(self) -> bool:
        return bool(self._candidate_ids)

    def resolve(self, registry: DataRegistry) -> tuple[str, bool]:
        if not self._candidate_ids:
            return self._raw, False
        versions = {
            cid: (s.version if (s := registry.get(cid)) is not None else -1)
            for cid in self._candidate_ids
        }
        registry_id = id(registry)
        same_registry = registry_id == self._last_registry_id
        if not self._first and same_registry and versions == self._last_versions:
            return self._cached, False
        self._first = False
        self._last_versions = versions
        self._last_registry_id = registry_id

        def _sub(match: re.Match[str]) -> str:
            slug = match.group()[1:-1]
            if is_emoji_slug(slug):
                return match.group()           # emoji wins; leave intact
            src = registry.get(slug)
            return src.current if src is not None else match.group()

        new_text = EMOJI_PATTERN.sub(_sub, self._raw)
        changed = new_text != self._cached
        self._cached = new_text
        return self._cached, changed
