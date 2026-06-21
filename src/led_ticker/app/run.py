"""Main application async loop.

Loads config, builds the LED frame, and iterates over playlist sections
indefinitely. Widget construction and coercion happen in factories.py;
the run loop here only orchestrates.
"""

import asyncio
import contextlib
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import aiohttp

from led_ticker import reload as _reload
from led_ticker import status_board
from led_ticker._plugin_loader import (
    _guarded_overlay,
    _run_shutdown_hooks,
    _run_startup_hooks,
    load_plugins_for_config,
)
from led_ticker.app.factories import (
    RUN_MODES,
    _build_title,
    _build_trans_obj,
    _build_widget,
    _cache_key,
    _configure_user_font_dir,
    _resolve_buffer_msg,
    _resolve_title_delay,
    build_frame_from_config,
)
from led_ticker.busy_http import serve_busy
from led_ticker.config import load_config
from led_ticker.plugin import StartupContext
from led_ticker.ticker import Ticker, _expand_sources, _maybe_wrap
from led_ticker.transitions import Transition, run_transition
from led_ticker.widget import _build_sink, run_monitor_loop, spawn_tracked


async def _ttl_ticker(busy: Any, interval: float = 1.0) -> None:
    """Clear pushed busy state once its TTL expires. 1 Hz; no-op when no
    deadline is armed."""
    while True:
        await asyncio.sleep(interval)
        busy.tick_ttl()


_SCHEDULE_TICK_SECONDS = 30.0


async def _schedule_ticker(
    led_frame: Any,
    scheduler: Any,
    tz: Any,
    base: int,
    *,
    override: Any = None,
    interval: float = _SCHEDULE_TICK_SECONDS,
) -> None:
    """Set matrix.brightness from the schedule every `interval` seconds.

    Applies immediately (correct on frame 1), logs only on change, and guards
    each tick so a transient exception keeps the ticker alive. `override`, when
    given, is a `Callable[[], int | None]` whose non-None value wins over the
    schedule (forward-looking seam for a future webhook)."""
    from datetime import datetime

    last: int | None = None

    def apply() -> None:
        nonlocal last
        try:
            o = override() if override is not None else None
            level = (
                o if o is not None else scheduler.brightness_for(datetime.now(tz), base)
            )
            led_frame.matrix.brightness = level
            if level != last:
                logging.info("schedule: brightness -> %d", level)
                last = level
        except Exception:
            logging.exception("schedule: brightness compute failed; holding")

    apply()
    while True:
        await asyncio.sleep(interval)
        apply()


async def _supervised_schedule(
    led_frame: Any,
    scheduler: Any,
    tz_name: Any,
    base: int,
    *,
    override: Any = None,
) -> None:
    """Run the schedule ticker; on a fatal error, reset brightness to base and
    log (a crashed scheduler must never leave the panel stuck dark)."""
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError  # noqa: PLC0415

    tz = None
    if tz_name:
        try:
            tz = ZoneInfo(tz_name)
        except ZoneInfoNotFoundError, ValueError, TypeError:
            logging.warning(
                "schedule: invalid timezone %r; using system local time", tz_name
            )
    try:
        await _schedule_ticker(led_frame, scheduler, tz, base, override=override)
    except asyncio.CancelledError:
        raise
    except Exception:
        logging.warning(
            "schedule ticker crashed; resetting brightness to base %d",
            base,
            exc_info=True,
        )
        try:
            led_frame.matrix.brightness = base
        except Exception:
            logging.exception("schedule: failed to reset brightness to base")


async def _respawn_schedule(old_task: Any, config: Any, led_frame: Any) -> Any:
    """Cancel the running schedule ticker (if any) and start a fresh one from the
    new config. Disabled -> set brightness to the new base and return None."""
    if old_task is not None:
        old_task.cancel()
        await asyncio.sleep(0)  # let the old ticker observe the cancel before respawn
    if config.display.schedule.enabled:
        from led_ticker.schedule import Scheduler  # noqa: PLC0415

        sched = Scheduler.from_config(config.display.schedule)
        return spawn_tracked(
            _supervised_schedule(
                led_frame,
                sched,
                config.display.schedule.timezone,
                config.display.brightness,
            )
        )
    led_frame.matrix.brightness = config.display.brightness
    return None


async def _build_title_guarded(
    section_title: Any,
    *,
    session: Any,
    config_dir: Any,
    default_bg_color: Any,
    panel_h_for_warning: Any,
) -> Any:
    """Build a section title, but never let a build error freeze the panel: on
    failure log + return None (skip the title this pass; a later good edit retries)."""
    try:
        return await _build_title(
            section_title,
            session=session,
            config_dir=config_dir,
            default_bg_color=default_bg_color,
            panel_h_for_warning=panel_h_for_warning,
        )
    except Exception as exc:  # noqa: BLE001 - a title build error must not freeze the panel
        logging.exception("title build failed; skipping title this pass: %s", exc)
        return None


async def _build_widget_guarded(
    widget_cfg: Any,
    *,
    session: Any,
    config_dir: Any,
    default_bg_color: Any,
    panel_h_for_warning: Any,
    coercion_collector: Any,
    widget_cache: dict,
    widget_tasks: dict,
) -> Any:
    """Build one widget (cache-aware), capturing its background tasks in a per-build
    sink so a config reload can cancel exactly those. On a build error, log + skip
    (return None) without caching, so a later good edit retries. Returns the widget
    or None."""
    key = _cache_key(widget_cfg)
    if key in widget_cache:
        return widget_cache[key]
    sink: set = set()
    token = _build_sink.set(sink)
    try:
        widget = await _build_widget(
            dict(widget_cfg),
            session,
            config_dir=config_dir,
            default_bg_color=default_bg_color,
            panel_h_for_warning=panel_h_for_warning,
            coercion_collector=coercion_collector,
        )
    except Exception as exc:  # noqa: BLE001 - a bad reloaded widget must not freeze the panel
        logging.exception("widget build failed; skipping for this pass: %s", exc)
        for t in sink:
            t.cancel()
        return None
    finally:
        _build_sink.reset(token)
    widget_cache[key] = widget
    widget_tasks[key] = sink
    return widget


async def _serve_busy_supervised(busy: Any, cfg: Any) -> None:
    """Run the HTTP listener for the process lifetime. A bind failure logs
    and returns — the display loop must never die because the busy port is
    taken."""
    try:
        runner = await serve_busy(
            busy, host=cfg.http_host, port=cfg.http_port, token=cfg.token
        )
    except OSError as e:
        logging.error(
            "busy-light HTTP listener failed to bind %s:%d (%s); "
            "continuing without remote trigger",
            cfg.http_host,
            cfg.http_port,
            e,
        )
        return
    try:
        await asyncio.Event().wait()  # keep the runner alive
    finally:
        await runner.cleanup()


async def _start_busy_light(cfg: Any, led_frame: Any) -> Any:
    """Build the BusyLight, register its paint hook, and start the source
    (file poller or HTTP listener) plus an optional TTL ticker. Returns the
    BusyLight."""
    from led_ticker.busy_light import BusyLight

    busy = BusyLight(
        file_path=cfg.file_path,
        corner=cfg.corner,
        color=cfg.color,
        size=cfg.size,
        ttl_seconds=cfg.ttl_seconds,
    )
    led_frame.overlay_hooks.append(busy.paint)
    if cfg.source == "http":
        spawn_tracked(_serve_busy_supervised(busy, cfg))
        # Always run the ticker for the HTTP source so a per-request ?ttl=
        # (or the configured ttl_seconds default) is enforced. The file
        # source never arms a deadline, so it needs no ticker.
        spawn_tracked(_ttl_ticker(busy))
    else:
        await busy.update()  # fast initial read so the dot is correct on frame 1
        spawn_tracked(run_monitor_loop(busy, cfg.poll_interval, splay=False))
    return busy


def _load_plugins_for_config(config_path: Path):
    """Load plugins honoring the [plugins] config block (enable/dir/disable)."""
    return load_plugins_for_config(config_path)


async def _status_heartbeat(
    board: Any,
    tee: Any = None,
    marker_ttl: float | None = None,
    busy: Any = None,
    busy_source: str = "file",
) -> None:
    """Republish at the throttle cadence so the sidecar's staleness verdict
    measures process liveness, not event frequency. Without this, a widget
    held longer than 3x min_interval flips the page to "stale" while the
    panel is happily playing. Also toggles the preview mirror from the
    watched-marker mtime (one tmpfs stat per beat, off the render path).
    Exits once the board self-disables or is deactivated (teardown), so it
    needs no explicit cancellation."""
    from led_ticker import status_board as _sb  # noqa: PLC0415
    from led_ticker.preview import MARKER_TTL  # noqa: PLC0415

    if marker_ttl is None:
        marker_ttl = MARKER_TTL
    marker = None
    if tee is not None:
        marker = tee._frame_path.parent / "preview-requested"
    try:
        while not board.disabled and _sb.get_active_board() is board:
            if busy is not None:
                try:
                    state = {
                        "enabled": True,
                        "active": busy.is_busy,
                        "source": busy_source,
                        "ttl_remaining": busy.ttl_remaining(),
                    }
                except Exception:
                    state = {
                        "enabled": True,
                        "active": getattr(busy, "is_busy", False),
                        "source": busy_source,
                    }
                    logging.warning("busy state read failed; publishing without ttl")
                _sb.record_busy(state)
            board.publish()
            # Narrow on marker (not tee): they're set together, and pyright
            # can only carry the None-check through the variable it stat()'s.
            if marker is not None:
                try:
                    fresh = (time.time() - marker.stat().st_mtime) < marker_ttl
                except OSError:
                    fresh = False
                tee.set_watched(fresh)
            await asyncio.sleep(board.min_interval)
    finally:
        # The heartbeat is the only thing that can turn the mirror OFF.
        # If it exits (board self-disabled / teardown), the mirror must not
        # stay stranded ON paying the watched tax forever.
        if tee is not None:
            tee.set_watched(False)


def _setup_preview(config: Any, led_frame: Any) -> Any:
    """Install the preview tee when [web] is configured. The tee is sized to
    the physical panel and writes frames next to status.json (the tmpfs
    volume both processes share). Returns the tee, or None."""
    if config.web is None:
        return None
    from led_ticker.preview import PreviewTee  # noqa: PLC0415

    frame_path = Path(config.web.status_path).expanduser().parent / "preview.bin"
    # Size from the CANVAS, never from config arithmetic: pixel_mapper_config
    # (e.g. the bigsign's Remap) reshapes the real canvas, and a wrong tee
    # height makes ScaledCanvas's panel-height check raise at the first wrap
    # — the panel down because of preview machinery (review-team finding).
    hw = led_frame.matrix.CreateFrameCanvas()
    tee = PreviewTee(
        hw=hw,
        width=hw.width,
        height=hw.height,
        frame_path=frame_path,
    )
    led_frame.install_preview(tee)
    return tee


def _teardown_status_board(handle: tuple[Any, logging.Handler] | None) -> None:
    """Undo _setup_status_board: detach the log handler and clear the active
    board. Safe to call with None (when [web] was absent)."""
    if handle is None:
        return
    _board, handler = handle
    logging.getLogger().removeHandler(handler)
    status_board.clear_active_board()


def _setup_status_board(
    config: Any, config_path: Path, plugins: Any
) -> tuple[Any, logging.Handler] | None:
    """Build + activate the StatusBoard and its log handler when [web] is
    configured. Returns (board, handler) so run() can tear both down, or
    None when [web] is absent."""
    if config.web is None:
        return None

    from led_ticker.status_board import (  # noqa: PLC0415
        StatusBoard,
        StatusLogHandler,
        set_active_board,
    )

    board = StatusBoard(path=Path(config.web.status_path))
    board.config_path = str(config_path)
    board.geometry = {
        "rows": config.display.rows,
        "cols": config.display.cols,
        "chain_length": config.display.chain_length,
        "parallel": config.display.parallel,
        "default_scale": config.display.default_scale,
        "panel_width": config.display.cols * config.display.chain_length,
        "panel_height": config.display.rows * config.display.parallel,
    }
    board.plugins = [
        {
            "namespace": info.namespace,
            "source": info.source,
            "counts": dict(info.counts or {}),
            "names": dict(getattr(info, "names", None) or {}),
        }
        for info in plugins.loaded
    ]
    board.failed_plugins = [
        {"namespace": ns, "error": str(err)} for ns, err in plugins.failed
    ]
    set_active_board(board)
    handler = StatusLogHandler(board)
    logging.getLogger().addHandler(handler)
    # Runs pre-frame-build, i.e. while the process is still root: opens the
    # status dir so publishes keep working after the rgbmatrix library
    # drops privileges during RGBMatrix() construction.
    board.prepare_dir()
    board.publish(force=True)
    return board, handler


async def run(config_path: Path) -> None:
    """Main application loop."""
    # Plugins must load before load_config so plugin-provided easings (and any
    # other config-load-validated surface) are visible to validation.
    plugins = _load_plugins_for_config(config_path)
    for ns, err in plugins.failed:
        logging.warning("plugin %r failed to load: %s", ns, err)

    config = await asyncio.to_thread(load_config, config_path)
    # Seed the watcher immediately after load so any edit that lands between
    # load and the while-True loop is captured in the seed hash (not absorbed
    # into a stale baseline that would make the first-edit invisible).
    watcher = _reload.ConfigWatcher(config_path, enabled=config.display.hot_reload)
    # Surface any coerce warnings recorded by load_config (string-of-digits
    # int/float fields, mixed-case enum strings). Same messages that
    # `led-ticker validate` shows as rule-37 warnings; logging at startup
    # lets users who skip pre-flight still see the fixes.
    for w in config._coerce_warnings:
        logging.warning("config coerce: %s", w.message)
    _configure_user_font_dir(config_path)

    # Status board setup must precede frame construction: RGBMatrix() drops
    # root privileges (default drop_privileges in the rgbmatrix library), and
    # prepare_dir needs root to open the status directory on the root-owned
    # volume mountpoint. Tripwire: test_setup_runs_before_frame_build.
    _status_handle = _setup_status_board(config, config_path, plugins)
    try:
        led_frame = build_frame_from_config(config.display)
        from led_ticker.render_breaker import RenderBreaker  # noqa: PLC0415

        render_breaker = RenderBreaker()
        preview_tee = _setup_preview(config, led_frame)

        # Busy light first so the heartbeat (spawned below) can read its state.
        busy = None
        if config.busy_light.enabled:
            busy = await _start_busy_light(config.busy_light, led_frame)

        # Plugin overlays composite over every render path via LedFrame.swap(),
        # same as the busy-light. Each is exception-wrapped so a raising plugin
        # overlay disables itself (logged once) rather than freezing the panel.
        for ns, paint in plugins.overlays:
            led_frame.overlay_hooks.append(_guarded_overlay(ns, paint))

        # Publish the static overlay roster once: names come from the
        # registration sites here (a raw overlay_hooks callable has no clean
        # name). busy.enabled and the busy_light roster entry both derive from
        # the one config gate, so they can't disagree.
        if _status_handle is not None:
            from led_ticker.status_board import set_overlay_roster  # noqa: PLC0415

            roster: list[dict[str, str]] = []
            if busy is not None:
                roster.append({"name": "busy_light", "kind": "core"})
            roster.extend({"name": ns, "kind": "plugin"} for ns, _ in plugins.overlays)
            set_overlay_roster(roster)

            spawn_tracked(
                _status_heartbeat(
                    _status_handle[0],
                    tee=preview_tee,
                    busy=busy,
                    busy_source=config.busy_light.source,
                )
            )

        schedule_task: Any = await _respawn_schedule(None, config, led_frame)

        # Default inter-section transition built once at startup. Used for
        # sections that don't specify their own `transition` field — see
        # the per-section override logic below.
        default_section_trans: Transition | None = _build_trans_obj(
            config.between_sections
        )

        # Compute the panel height to use for hi-res font_size warnings.
        # Only meaningful on the small sign (default_scale == 1) — bigsign
        # users intentionally pick large sizes, no warning needed there.
        panel_h_for_warning: int | None = (
            config.display.rows if config.display.default_scale == 1 else None
        )

        async with aiohttp.ClientSession() as session:
            last_widget: Any = None  # track for section-to-section transitions
            last_scroll_pos: int = 0  # track scroll pos for between-section transitions
            last_scale: int = config.display.default_scale  # outgoing section's scale
            last_content_height: int = 16  # outgoing section's content_height
            last_bg_color: tuple[int, int, int] | None = (
                None  # outgoing section's bg_color (for run_transition's t<0.5 reset)
            )
            widget_cache: dict[str, Any] = {}
            widget_tasks: dict[str, set] = {}

            # Plugin startup hooks run once now that the frame + session exist.
            await _run_startup_hooks(
                plugins.startup_hooks,
                StartupContext(frame=led_frame, session=session, config=config),
            )

            try:
                while True:
                    if watcher.changed():
                        new_config, errors, transient = await _reload.load_and_validate(
                            config_path
                        )
                        if transient:
                            pass  # file mid-write; retry next cycle, no record
                        elif new_config is None:
                            ts = datetime.now().isoformat()
                            logging.error(
                                "config reload rejected: %s", "; ".join(errors)
                            )
                            status_board.record_reload(
                                ok=False, ts=ts, error="; ".join(errors)
                            )
                        else:
                            ts = datetime.now().isoformat()
                            (
                                schedule_task,
                                restart_required,
                            ) = await _reload._apply_reload(
                                new_config,
                                old_config=config,
                                widget_cache=widget_cache,
                                widget_tasks=widget_tasks,
                                render_breaker=render_breaker,
                                schedule_task=schedule_task,
                                respawn_schedule=lambda ot, cfg: _respawn_schedule(
                                    ot, cfg, led_frame
                                ),
                            )
                            default_section_trans = _build_trans_obj(
                                new_config.between_sections
                            )
                            for w in getattr(new_config, "_coerce_warnings", []):
                                logging.warning("config coerce: %s", w.message)
                            config = new_config  # the swap
                            if restart_required:
                                logging.warning(
                                    "config reloaded (partial); restart required "
                                    "for: %s",
                                    ", ".join(restart_required),
                                )
                            else:
                                logging.info("config reloaded")
                            status_board.record_reload(
                                ok=True, ts=ts, restart_required=restart_required
                            )
                    for section_index, section in enumerate(config.sections):
                        status_board.record_section(
                            index=section_index,
                            total=len(config.sections),
                            mode=section.mode,
                            title=str((section.title or {}).get("text", "")),
                            widget_count=len(section.widgets),
                        )
                        notif_queue: asyncio.Queue[Any] = asyncio.Queue()
                        widgets: list[Any] = []
                        runtime_coerce: list[Any] = []
                        for widget_cfg in section.widgets:
                            # Cache async widgets to avoid leaking background tasks.
                            # _build_widget_guarded handles both cache hits and
                            # cache-miss builds, capturing background tasks in
                            # widget_tasks so a reload can cancel exactly those.
                            # Containers (Protocol in widget.py) are expanded by the
                            # engine on every cycle pass via _expand_sources — pushing
                            # the container itself (not its current feed_stories)
                            # keeps the displayed content in sync with the container's
                            # background update() task. PoolMonitor satisfies Container
                            # structurally (has feed_stories), so no isinstance check
                            # is needed here.
                            widget = await _build_widget_guarded(
                                widget_cfg,
                                session=session,
                                config_dir=config_path.parent,
                                default_bg_color=section.bg_color,
                                panel_h_for_warning=panel_h_for_warning,
                                coercion_collector=runtime_coerce,
                                widget_cache=widget_cache,
                                widget_tasks=widget_tasks,
                            )
                            if widget is None:
                                continue  # build failed; skip this widget this pass
                            widgets.append(widget)
                        # Drain coerce warnings collected during this section's
                        # widget build. Empty in the common case; one log line per
                        # CoercionWarning otherwise.
                        for w in runtime_coerce:
                            logging.warning("config coerce: %s", w.message)

                        title = await _build_title_guarded(
                            section.title,
                            session=session,
                            config_dir=config_path.parent,
                            default_bg_color=section.bg_color,
                            panel_h_for_warning=panel_h_for_warning,
                        )
                        run_method = RUN_MODES.get(
                            section.mode,
                            "run_forever_scroll",
                        )

                        # Entry transition precedence:
                        #   1. entry_transition (explicit per-section entry override)
                        #   2. transition (when transition_specified)
                        #   3. between_sections (global default)
                        if section.entry_transition is not None:
                            entry_trans = _build_trans_obj(section.entry_transition)
                            entry_duration = section.entry_transition.duration
                            entry_easing = section.entry_transition.easing
                            entry_fps = section.entry_transition.transition_fps
                        elif section.transition_specified:
                            entry_trans = _build_trans_obj(section.transition)
                            entry_duration = section.transition.duration
                            entry_easing = section.transition.easing
                            entry_fps = section.transition.transition_fps
                        else:
                            entry_trans = default_section_trans
                            entry_duration = config.between_sections.duration
                            entry_easing = config.between_sections.easing
                            entry_fps = config.between_sections.transition_fps

                        # Run section-to-section transition.
                        # Wrap at the OUTGOING section's scale so the outgoing widget
                        # keeps its on-screen size during the dissolve. Any visual jolt
                        # from the scale change happens at the very end of the
                        # transition (one frame), where the new section's first render
                        # immediately overwrites it.
                        #
                        # Containers (RSS / data-widget monitors) don't implement
                        # draw() — they expose `feed_stories` instead. If a section
                        # starts with a container and has no [section.title], expand
                        # to the container's first current story so the transition's
                        # `incoming.draw()` call has a real widget to render.
                        if title:
                            first_widget = title
                        elif widgets:
                            expanded = _expand_sources(widgets, render_breaker)
                            first_widget = expanded[0] if expanded else None
                        else:
                            first_widget = None
                        just_transitioned = (
                            last_widget is not None
                            and first_widget is not None
                            and entry_trans is not None
                        )
                        if just_transitioned:
                            assert (
                                entry_trans is not None
                            )  # narrowed: just_transitioned requires it
                            canvas = _maybe_wrap(
                                led_frame.get_clean_canvas(),
                                last_scale,
                                last_content_height,
                            )
                            canvas = await run_transition(
                                canvas,
                                led_frame,
                                last_widget,
                                first_widget,
                                transition=entry_trans,
                                duration=entry_duration,
                                easing=entry_easing,
                                scroll_speed=(1.0 / entry_fps)
                                if entry_fps is not None
                                else 0.05,
                                outgoing_scroll_pos=last_scroll_pos,
                                # Smoothly cross between scales: outgoing fades out
                                # at last_scale; at t >= 0.5 the wrapper switches
                                # to section.scale so incoming dissolves IN at its
                                # native size (no wrong-scale flash, no snap-in
                                # after the dissolve completes). Content height
                                # must also match the new section so widgets like
                                # two_row don't shift vertically when the section
                                # actually starts running.
                                incoming_scale=section.scale,
                                incoming_content_height=section.content_height,
                                # Preserve bg color through the transition.
                                # `outgoing_bg_color` keeps the previous
                                # section's bg painted at t<0.5 so it doesn't
                                # vanish to black the instant the transition
                                # starts; `incoming_bg_color` ramps in the
                                # new bg at t>=0.5 (and the hires snap respects
                                # it too) so the last transition frame matches
                                # the section's first reset_canvas. Both
                                # default to None — the legacy behavior was
                                # `Clear()` for the entire transition.
                                outgoing_bg_color=last_bg_color,
                                incoming_bg_color=section.bg_color,
                            )

                        # Widget transition precedence:
                        #   1. widget_transition (explicit per-section widget override)
                        #   2. transition (when transition_specified)
                        #   3. None (cut)
                        widget_trans_cfg = section.widget_transition or (
                            section.transition if section.transition_specified else None
                        )
                        if (
                            widget_trans_cfg is not None
                            and widget_trans_cfg.type != "cut"
                        ):
                            transition_fn = _build_trans_obj(widget_trans_cfg)
                            transition_config = widget_trans_cfg
                        else:
                            transition_fn = None
                            transition_config = None

                        ticker_kwargs: dict[str, Any] = {
                            "monitors": widgets,
                            "frame": led_frame,
                            "title": title,
                            "title_delay": _resolve_title_delay(
                                section.start_hold, config.title_delay
                            ),
                            "notif_queue": notif_queue,
                            "transition_config": transition_config,
                            "transition_fn": transition_fn,
                            "hold_time": section.hold_time,
                            "continuous_scroll": section.continuous_scroll,
                            "scale": section.scale,
                            "content_height": section.content_height,
                            "breaker": render_breaker,
                        }
                        if section.scroll_step_ms is not None:
                            ticker_kwargs["scroll_speed"] = (
                                section.scroll_step_ms / 1000
                            )
                        buffer_msg = _resolve_buffer_msg(section)
                        if buffer_msg is not None:
                            ticker_kwargs["buffer_msg"] = buffer_msg
                        ticker = Ticker(**ticker_kwargs)

                        # If a between-section transition just ran, the title is
                        # already on-screen at t=1.0 of the dissolve. Tell the section
                        # to start at pos=0 (no scroll-in) so we don't blank the panel
                        # before redrawing.
                        run_kwargs: dict[str, Any] = {"loop_count": section.loop_count}
                        # `start_pos` is only meaningful for scrolling modes —
                        # `run_swap` and `run_gif` don't have a scroll position
                        # to skip past.
                        if just_transitioned and run_method in (
                            "run_forever_scroll",
                            "run_infini_scroll",
                        ):
                            run_kwargs["start_pos"] = 0

                        try:
                            await getattr(ticker, run_method)(**run_kwargs)
                        except asyncio.CancelledError:
                            raise
                        finally:
                            if (
                                ticker._enqueue_task is not None
                                and not ticker._enqueue_task.done()
                            ):
                                ticker._enqueue_task.cancel()
                                with contextlib.suppress(
                                    asyncio.CancelledError, Exception
                                ):
                                    await ticker._enqueue_task

                        # Brief pause before between-sections transition
                        if section.continuous_scroll:
                            await asyncio.sleep(1.0)

                        # Track the last widget and scroll pos for the
                        # next section transition
                        last_scroll_pos = ticker.last_scroll_pos
                        last_scale = section.scale
                        last_content_height = section.content_height
                        last_bg_color = section.bg_color
                        # Containers (RSS / data-widget monitors) don't implement
                        # draw() — the next section's transition would crash on
                        # `outgoing.draw()` if last_widget were a container. Expand
                        # to the container's last current story; if the container
                        # is currently empty, keep the previous last_widget (the
                        # next transition will use whatever was last on-screen).
                        if widgets:
                            expanded = _expand_sources(widgets, render_breaker)
                            if expanded:
                                last_widget = expanded[-1]
                            # else: container is empty this cycle — keep prior
                            # last_widget so the next transition still has a real
                            # widget to render as outgoing.
                        elif title:
                            last_widget = title
            finally:
                # Best-effort: run plugin shutdown hooks when the loop exits
                # (normally via cancellation on Ctrl-C / SIGTERM).
                await _run_shutdown_hooks(plugins.shutdown_hooks)
    finally:
        # Tear down the status board and its log handler so a second run()
        # call in the same process (or a cancellation between setup and the
        # main loop) doesn't accumulate stale handlers.
        _teardown_status_board(_status_handle)
