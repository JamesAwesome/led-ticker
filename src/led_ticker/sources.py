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
import logging
import re
from typing import Any
from zoneinfo import ZoneInfo

import attrs

from led_ticker.color_providers import ColorProvider
from led_ticker.pixel_emoji import EMOJI_PATTERN, is_emoji_slug
from led_ticker.widget import run_monitor_loop, spawn_tracked


@attrs.define(eq=False)
class DataSource:
    """Base class. Subclasses implement compute(); refresh() applies it."""

    id: str
    polled: bool = attrs.field(default=False, kw_only=True)
    current: str = attrs.field(default="", init=False)
    version: int = attrs.field(default=0, init=False)
    # Optional presentation: a color provider for THIS source's inline token.
    # Set post-construction by build_source from the [[source]] `color` field.
    # None => the token inherits the host widget's font_color (today's behavior).
    color: ColorProvider | None = attrs.field(default=None, init=False)

    def compute(self) -> str:
        raise NotImplementedError

    def _set_value(self, new: str) -> bool:
        """Apply a new value with the write-order contract: write `current`
        BEFORE `version`, with no await between, and bump `version` only when
        the value actually changed. Returns whether it changed. This is the
        SINGLE enforcement point for the contract (sync refresh + polled
        update both go through it)."""
        if new == self.current and self.version != 0:
            return False
        self.current = new  # current BEFORE version (contract)
        self.version += 1
        return True

    def refresh(self) -> bool:
        """Recompute (sync) and apply via _set_value."""
        return self._set_value(self.compute())


@attrs.define(eq=False)
class StaticSource(DataSource):
    value: str = ""

    def compute(self) -> str:
        return self.value


_MAX_ANIM_FRAMES = 60
_MIN_FRAME_MS = 20


def _bake(im, target_h, cap_w) -> list[tuple[int, int, int, int, int]]:
    """Downscale an RGBA frame to `target_h` px tall (width proportional,
    capped at `cap_w`) and return the lit (alpha >= 110) pixels as
    `(x, y, r, g, b)` tuples — the Noto bake recipe, shared by the static
    and animated decode paths so behavior stays byte-identical."""
    from PIL import Image  # noqa: PLC0415

    w = max(1, round(im.width * target_h / im.height))
    if w > cap_w:
        im2 = im.resize((cap_w, target_h), Image.Resampling.LANCZOS)
    else:
        im2 = im.resize((w, target_h), Image.Resampling.LANCZOS)
    px = im2.load()
    out: list[tuple[int, int, int, int, int]] = []
    for y in range(im2.height):
        for x in range(im2.width):
            r, g, b, a = px[x, y]
            if a >= 110:
                out.append((x, y, r, g, b))
    return out


def load_image_sprites(path):
    """Decode an image file into the inline-sprite forms.

    Returns ``(lowres, hires_frame0, animation)``: an 8x8 ``PixelData``, a
    32-px-tall ``HiResEmoji`` (width proportional, capped at 128 px; RGBA
    alpha >= 110 keeps a pixel — the Noto bake recipe), and — for a
    multi-frame file — a `pixel_emoji._ImageAnimation` record (`None` for a
    single-frame file). `hires_frame0` IS `animation.hires_frames[0]`
    (identity): the registry's committed static sprite is the same object
    the frame-swap tick will overwrite on a later index change, so a
    no-change tick is identity-stable.

    For a multi-frame file, frames are decoded up to a hard cap of
    `_MAX_ANIM_FRAMES` (raises `ValueError` above it — the caller decides
    posture: build_source_registry skips + logs; validate errors loudly).
    Every frame's `HiResEmoji` shares one `physical_width` = the union
    EXTENT across frames (`max` over frames of `max_x + 1`; pixels are NOT
    origin-shifted), so any frame measures identically regardless of which
    one happens to be current when a widget lays out around it. Frame
    durations come from Pillow's per-frame `duration` (default 100ms),
    clamped to a `_MIN_FRAME_MS` floor so a malformed 0/near-0 duration
    can't spin the tick.

    Raises on a missing/undecodable file — the CALLER decides posture
    (build_source_registry skips + logs; validate errors loudly).

    Memory cost: the full source frame is decoded to RGBA BEFORE the
    downscale, so peak memory scales with the ORIGINAL image dimensions
    (1x-2x of Pillow's MAX_IMAGE_PIXELS band for a very large source), not the
    tiny sprite it becomes. The >512x512 validate warning (rule 70) is the
    guard against pathologically large sources. Frames are Python pixel
    tuples (~88 B each); the 60-frame cap bounds one slug at roughly 23 MB
    worst-case.  # Phase-2 candidate: bounded decode still on the table.
    """
    from PIL import Image  # noqa: PLC0415

    from led_ticker.pixel_emoji import HiResEmoji, _ImageAnimation  # noqa: PLC0415

    img = Image.open(path)  # frame 0 of a multi-frame file by default
    n_frames = getattr(img, "n_frames", 1)
    if n_frames > _MAX_ANIM_FRAMES:
        raise ValueError(
            f"{path}: {n_frames} frames exceeds the {_MAX_ANIM_FRAMES}-frame "
            f"cap for inline animation"
        )

    frames_px: list[list[tuple[int, int, int, int, int]]] = []
    durations: list[int] = []
    for i in range(n_frames):
        img.seek(i)
        rgba = img.convert("RGBA")
        frames_px.append(_bake(rgba, 32, 128))
        durations.append(max(int(img.info.get("duration", 100)), _MIN_FRAME_MS))
    img.seek(0)
    lowres = _bake(img.convert("RGBA"), 8, 8)

    # Union EXTENT across frames (spec rev 2): max (max_x + 1); no shifting.
    union_w = max(
        (max((p[0] for p in fpx), default=0) + 1 for fpx in frames_px), default=1
    )
    hires_frames = tuple(
        HiResEmoji(pixels=tuple(fpx), physical_size=32, physical_width=union_w)
        for fpx in frames_px
    )
    if n_frames == 1:
        return lowres, hires_frames[0], None

    cum: list[int] = []
    run = 0
    for d in durations:
        run += d
        cum.append(run)
    anim = _ImageAnimation(
        hires_frames=hires_frames, cumulative_ms=tuple(cum), total_ms=run
    )
    return lowres, hires_frames[0], anim


@attrs.define(eq=False)
class ImageSource(DataSource):
    """Declaration-only source: registers a config-declared image as an
    inline emoji slug (`:id:`). No polling, no monitor entry. `prepare()`
    decodes + STAGES (pixel_emoji.stage_image_emoji); the boot/reload path
    commits atomically alongside set_data_registry. `compute()` returns the
    literal token as a defensive value — once the slug is committed,
    `is_emoji_slug` excludes it from TokenizedField._candidate_ids and the
    emoji parser owns the token outright."""

    path: str = ""

    def prepare(self) -> None:
        from led_ticker.pixel_emoji import stage_image_emoji  # noqa: PLC0415

        # An id that can't form a `:token:` (EMOJI_PATTERN's
        # `[a-z_][a-z0-9_.]*` body) would commit a slug the emoji parser can
        # never match — the token renders as literal text. validate errors on
        # this (rule 70); the runtime just skips staging so it never commits
        # an unusable slug. One WARNING, no raise (a bad id must not go dark).
        if not re.fullmatch(r"[a-z_][a-z0-9_.]*", self.id):
            logging.getLogger(__name__).warning(
                "image source id %r can't form a :token: (needs lowercase "
                "letters, digits, underscore, or dot; must start with a "
                "letter or underscore) — skipping; the token will not render",
                self.id,
            )
            return
        lowres, hires, anim = load_image_sprites(self.path)
        stage_image_emoji(self.id, lowres, hires, animation=anim)

    def compute(self) -> str:
        return f":{self.id}:"


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


@attrs.define(eq=False)
class PolledDataSource(DataSource):
    """Base for asynchronous (network-backed) sources — weather, prices, etc.

    The subclass implements `async def update()`, which performs its awaited
    fetch and then calls `self._set_value(<formatted string>)` (synchronous —
    honoring the write-order contract). Core spawns a supervised
    `run_monitor_loop(self, self.interval)` per polled source (backoff +
    survives exceptions); the 1 Hz sync ticker skips it (`polled` is True).
    `draw()` only ever reads `current` — it never awaits.
    """

    # `session` is an injected shared aiohttp.ClientSession (typed Any here to
    # keep core import-light; the plugin source types it). `interval` is the
    # poll period in seconds (from the [[source]] block; default 30 min).
    polled: bool = attrs.field(default=True, kw_only=True)
    session: Any = attrs.field(default=None, kw_only=True)
    interval: int = attrs.field(default=1800, kw_only=True)

    # Set when the first real value is applied (version 0 -> 1). Startup awaits
    # this (bounded) so token widgets show real data on first display instead
    # of the placeholder. Created per instance; binds to the running loop lazily.
    first_value: asyncio.Event = attrs.field(factory=asyncio.Event, init=False)

    def _set_value(self, new: str) -> bool:
        changed = super()._set_value(new)
        if self.version > 0:
            self.first_value.set()
        return changed

    async def update(self) -> None:
        """Fetch + `self._set_value(...)`. Subclass responsibility."""
        raise NotImplementedError

    def compute(self) -> str:
        raise NotImplementedError("polled sources update via async update()")


# Plugin-registered source types (namespaced, e.g. "acme.live"). Populated by
# the plugin loader via _commit(); read by factories.get_source_class(). Kept
# here (not in factories.py) so the loader can import it from sources without
# pulling in the heavier factories module.
_PLUGIN_SOURCE_TYPES: dict[str, type[DataSource]] = {}


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


PRIME_TIMEOUT: float = 2.5


async def prime_polled_sources(
    registry: DataRegistry, timeout: float = PRIME_TIMEOUT
) -> None:
    """Wait (bounded) for each polled source's first real value so token
    widgets render real data on their first display instead of a placeholder.

    Bounded: a source slower than `timeout` degrades to the placeholder and
    self-corrects on its next tick — the wait never blocks boot indefinitely.
    Sync sources (clock/date/static) are already correct at build time and are
    not awaited.
    """
    polled = [s for s in registry.sources() if isinstance(s, PolledDataSource)]
    if not polled:
        return
    try:
        await asyncio.wait_for(
            asyncio.gather(*(s.first_value.wait() for s in polled)),
            timeout=timeout,
        )
    except TimeoutError:
        not_ready = [s.id for s in polled if not s.first_value.is_set()]
        logging.info(
            "source prime: %d/%d polled sources ready within %.1fs; still waiting: %s",
            len(polled) - len(not_ready),
            len(polled),
            timeout,
            not_ready,
        )


async def run_source_refresh_loop(
    registry: DataRegistry, interval: float = 1.0
) -> None:
    """1 Hz: refresh every synchronous source; version bumps drive widgets."""
    while True:
        for source in registry.sources():
            if not source.polled:
                source.refresh()
        await asyncio.sleep(interval)


def spawn_source_refresh(registry: DataRegistry) -> list:
    """Prime sync sources, spawn the shared 1 Hz sync loop, AND spawn a
    supervised ``run_monitor_loop`` per POLLED source. Returns every task
    handle (the 1 Hz sync task + one per polled source) so the caller can
    cancel them all on hot-reload."""
    tasks: list = []
    for source in registry.sources():
        if not source.polled:
            source.refresh()
    tasks.append(spawn_tracked(run_source_refresh_loop(registry)))
    for source in registry.sources():
        if isinstance(source, PolledDataSource):
            # immediate=True: fetch once right away so the token shows real data
            # within a request instead of after a full `interval` (a 15-30 min
            # blank for weather). The fetch runs concurrently — it never blocks
            # startup or the render loop.
            tasks.append(
                spawn_tracked(
                    run_monitor_loop(
                        source, source.interval, splay=False, immediate=True
                    )
                )
            )
    return tasks


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
        self._last_registry_id: int = 0  # id() of the last registry resolved against
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
                return match.group()  # emoji wins; leave intact
            src = registry.get(slug)
            return src.current if src is not None else match.group()

        new_text = EMOJI_PATTERN.sub(_sub, self._raw)
        changed = new_text != self._cached
        self._cached = new_text
        return self._cached, changed

    def resolve_segments(
        self, registry: DataRegistry
    ) -> list[tuple[str, ColorProvider | None, bool]]:
        """Typed spans of the resolved text: (text, color, is_emoji).

        Literal runs -> (text, None, False). A `:id:` token -> (value,
        source.color, False). An emoji slug -> (":slug:", None, True). The
        concatenation of the texts equals `resolve()`'s flat string.
        Colors are read live from `registry.get(id).color`.
        """
        segments: list[tuple[str, ColorProvider | None, bool]] = []
        last = 0
        for m in EMOJI_PATTERN.finditer(self._raw):
            if m.start() > last:
                segments.append((self._raw[last : m.start()], None, False))
            slug = m.group()[1:-1]
            if is_emoji_slug(slug):
                segments.append((m.group(), None, True))
            else:
                src = registry.get(slug)
                if src is not None:
                    segments.append((src.current, src.color, False))
                else:
                    segments.append((m.group(), None, False))
            last = m.end()
        if last < len(self._raw):
            segments.append((self._raw[last:], None, False))
        if not segments:
            segments.append((self._raw, None, False))
        return segments


def build_token_color_override(
    segments: list[tuple[Any, Any, bool]],
    visible_text: str,
    frame: int,
    has_emoji: bool,
) -> list[Any] | None:
    """Return a per-visible-text-char list of ``Color``-or-``None`` aligned
    to ``draw_with_emoji``'s emoji-excluding ``char_index`` space for the
    ACTUAL ``visible_text`` being drawn, or ``None`` if no token carries a
    color.

    ``segments`` is the FROZEN ``resolve_segments`` snapshot (typed spans of
    the flat resolved string) — see ``TickerMessage._resolved_segments``.
    Using the snapshot (not a live re-resolve) keeps the override the same
    length as ``full_text`` / ``visible_text`` when resolution is frozen
    (scroll / transition / typewriter), so a value that changes length under
    the freeze can't shift a trailing literal into the token color (M1).

    ``None`` is the common path: callers then skip the override entirely and
    the existing color branches run byte-identically.

    Alignment (M2): the override must land in the SAME char-index space
    ``draw_with_emoji`` uses, which re-parses ``visible_text`` with
    ``_parse_segments`` and renders ANY emoji slug or Unicode-emoji run
    (INCLUDING ones that appear inside a token's resolved VALUE, e.g. a
    source that yields ``:taco:9``) as a sprite that consumes zero text-char
    positions. We therefore:

      1. Build ``raw_colors`` one entry per char of the flat resolved string
         (from ``segments``), so colored-token value chars carry the
         materialized color and everything else is ``None``.
      2. Prefix it to ``len(visible_text)`` (``visible_text`` is a prefix of
         the flat string under typewriter, equal otherwise).
      3. If ``has_emoji`` (the raw template has emoji, so the draw goes through
         ``draw_with_emoji``): re-walk ``_parse_segments(visible_text)`` tracking
         a flat-string offset — a text run appends its ``raw_colors`` slice; an
         emoji / uemoji run is SKIPPED (no text-char position). The offset
         advances by the run's flat-string span — ``len(value) + 2`` for a
         ``:slug:`` emoji (the colons survive in the flat string;
         ``_parse_segments`` strips them from ``value``) and ``len(value)`` for
         text / uemoji. Otherwise (non-emoji draw path renders every char
         literally): the override is ``raw_colors`` as-is — an emoji slug
         embedded in a token VALUE is drawn literally there and must NOT skip.

    A token's provider is whole-string (materialized once at
    ``color_for(frame, 0, 1)``) and applied to each of its value chars.
    """
    from led_ticker.pixel_emoji import _parse_segments  # noqa: PLC0415

    raw_colors: list[Any] = []
    has_color = False
    for text, color, _is_emoji in segments:
        if color is None:
            raw_colors.extend([None] * len(text))
        else:
            has_color = True
            c = color.color_for(frame, 0, 1)  # whole-string token provider
            raw_colors.extend([c] * len(text))
    if not has_color:
        return None

    # Align to the drawn prefix; pad with None if somehow shorter.
    rc = raw_colors[: len(visible_text)]
    if len(rc) < len(visible_text):
        rc = rc + [None] * (len(visible_text) - len(rc))

    # The override's char space must match the DRAW PATH's. `_has_emoji`
    # (computed from the RAW template) selects the path: the emoji branch
    # (`draw_with_emoji`) renders emoji slugs / uemoji as sprites (0 text-chars)
    # via `_parse_segments`, so the override must skip them (the re-walk below).
    # The non-emoji branches (`draw_text_per_char` / `draw_text`) render EVERY
    # visible char literally, so the override is `rc` as-is — an emoji slug
    # embedded in a TOKEN VALUE is drawn as literal characters there and must
    # NOT be skipped (else later chars mis-align).
    if not has_emoji:
        return rc

    override: list[Any] = []
    offset = 0
    for seg_type, value in _parse_segments(visible_text):
        if seg_type == "text":
            override.extend(rc[offset : offset + len(value)])
            offset += len(value)
        elif seg_type == "emoji":
            offset += len(value) + 2  # `:` + slug + `:` in the flat string
        else:  # uemoji: raw codepoints, no colons
            offset += len(value)
    return override
