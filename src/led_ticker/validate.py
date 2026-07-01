"""Config file validator for led-ticker."""

import contextlib
import copy
import datetime
import json
import math
import tempfile
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

import tomli_w

if TYPE_CHECKING:
    from led_ticker.config import AppConfig, DisplayConfig, SectionConfig


@dataclass
class ValidationIssue:
    rule: int | None
    location: str
    message: str
    fix: str
    severity: Literal["error", "warning"]
    fix_key: str | None = None
    fix_replacement_key: str | None = None


@dataclass
class ValidationResult:
    path: Path
    errors: list[ValidationIssue] = field(default_factory=list)
    warnings: list[ValidationIssue] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return len(self.errors) == 0


class MigrationError(Exception):
    """Raised by _build_widget when a widget config uses a removed knob.

    Carries both the human-readable message AND the suggested fix string
    so _run_build_checks can route it without substring-matching against
    _ERROR_PATTERNS.
    """

    def __init__(
        self,
        message: str,
        suggested_fix: str,
        *,
        fix_key: str | None = None,
        fix_replacement_key: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.suggested_fix = suggested_fix
        self.fix_key = fix_key
        self.fix_replacement_key = fix_replacement_key


VALID_MODES: frozenset[str] = frozenset({"slideshow", "ticker", "one_at_a_time"})


def _strftime_test(fmt: str) -> None:
    """Try formatting the current time with `fmt`.

    Raises ValueError (or platform-specific error) when `fmt` is invalid.
    Isolated as a module-level function so tests can monkeypatch it portably —
    datetime.datetime is a C type whose methods cannot be patched directly.
    """
    datetime.datetime.now().strftime(fmt)


# Maps substrings in exception messages to (rule, fix) pairs.
_ERROR_PATTERNS: list[tuple[str, int | None, str]] = [
    (
        "animation is only valid on",
        12,
        (
            "Remove animation from this widget type;"
            " valid on message, countdown, gif, image"
        ),
    ),
    (
        "border is only valid on",
        15,
        (
            "Remove border from this widget type;"
            " valid on message, countdown, two_row, gif, image"
        ),
    ),
    (
        "requires font_size",
        5,
        "Add font_size = <pixels> next to font (e.g. font_size = 24 on bigsign)",
    ),
    (
        "font_threshold",
        10,
        "Use an integer 0–255 for font_threshold (not float, string, or bool)",
    ),
    (
        "got unknown field",
        38,
        (
            "Remove or rename the field. "
            "Run `led-ticker validate --list-fields TYPE` to see valid fields."
        ),
    ),
]


def _classify_error(msg: str) -> tuple[int | None, str]:
    for pattern, rule, fix in _ERROR_PATTERNS:
        if pattern in msg:
            return rule, fix
    return None, "See error message for details."


async def _run_build_checks(
    sections: list[SectionConfig], config_dir: Path
) -> tuple[
    list[tuple[str, str]],
    list[tuple[str, Any]],
    list[tuple[str, str, str, str | None, str | None]],
]:
    """Run validate_widget_cfg for every widget.

    Returns (build_errors, coerce_warnings, migration_errors):
    - build_errors: (location, error_msg) pairs
    - coerce_warnings: (location, CoercionWarning) pairs collected from
      validate_widget_cfg's coercion pass for each widget.
    - migration_errors: (location, message, suggested_fix, fix_key,
      fix_replacement_key) 5-tuples from MigrationError raised by
      validate_widget_cfg for removed knobs. fix_key and
      fix_replacement_key are None when the rename is not auto-fixable.
    """
    from led_ticker.app.factories import validate_widget_cfg

    issues: list[tuple[str, str]] = []
    warnings: list[tuple[str, Any]] = []
    migrations: list[tuple[str, str, str, str | None, str | None]] = []
    for i, section in enumerate(sections):
        for j, widget_cfg in enumerate(section.widgets):
            widget_warnings: list[Any] = []
            try:
                await validate_widget_cfg(
                    copy.deepcopy(widget_cfg),
                    session=None,
                    config_dir=config_dir,
                    coercion_collector=widget_warnings,
                )
            except MigrationError as e:
                migrations.append(
                    (
                        f"section[{i}].widget[{j}]",
                        e.message,
                        e.suggested_fix,
                        e.fix_key,
                        e.fix_replacement_key,
                    )
                )
            except Exception as e:
                issues.append((f"section[{i}].widget[{j}]", str(e)))
            for w in widget_warnings:
                warnings.append((f"section[{i}].widget[{j}]", w))
    return issues, warnings, migrations


def _check_sources(config: AppConfig) -> list[ValidationIssue]:
    """Rule 56: validate [[source]] blocks.

    Errors:
    - duplicate `id` across blocks
    - `id` equal to a registered emoji slug (collision; emoji wins in resolution order)
    - unknown `type` (not in core or plugin registry)
    - clock/date: `format` that strftime rejects
    - clock/date: `timezone` that ZoneInfo cannot find
    - static: missing `value`
    """
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

    from led_ticker.app.factories import get_source_class
    from led_ticker.pixel_emoji import is_emoji_slug
    from led_ticker.sources import ClockSource, DateSource, StaticSource

    issues: list[ValidationIssue] = []
    seen_ids: set[str] = set()

    for src in config.sources:
        loc = f"source[{src.id!r}]"

        # Duplicate id
        if src.id in seen_ids:
            issues.append(
                ValidationIssue(
                    rule=56,
                    location=loc,
                    severity="error",
                    message=(
                        f"Duplicate [[source]] id {src.id!r} — each source must "
                        f"have a unique id."
                    ),
                    fix=(
                        f"Give each [[source]] block a distinct id. "
                        f"Rename one of the {src.id!r} blocks."
                    ),
                )
            )
            continue  # Don't type-check the duplicate; avoid duplicate errors

        seen_ids.add(src.id)

        # id collides with an emoji slug
        if is_emoji_slug(src.id):
            issues.append(
                ValidationIssue(
                    rule=56,
                    location=loc,
                    severity="error",
                    message=(
                        f"[[source]] id {src.id!r} is also a registered emoji slug. "
                        f"Emoji resolution takes priority over source tokens — a "
                        f"widget using :{src.id}: will render the emoji, not the "
                        f"source value."
                    ),
                    fix=(
                        f"Rename the source to a non-emoji id "
                        f'(e.g. id = "my_{src.id}").'
                    ),
                )
            )
            # Fall through: still check type / format / tz for this source

        # Unknown type
        try:
            cls = get_source_class(src.type)
        except ValueError:
            issues.append(
                ValidationIssue(
                    rule=56,
                    location=loc,
                    severity="error",
                    message=(
                        f"Unknown [[source]] type {src.type!r}. "
                        f"Core types: clock, date, static. "
                        f"Plugin types are namespaced (e.g. 'myplugin.weather')."
                    ),
                    fix=(
                        f"Set type to a known source type, or install the plugin "
                        f"that provides {src.type!r}."
                    ),
                )
            )
            continue  # No further per-type checks possible

        # Per-type checks
        if cls in (ClockSource, DateSource):
            fmt = src.raw.get("format", "%H:%M")
            try:
                _strftime_test(fmt)
            except Exception as exc:
                issues.append(
                    ValidationIssue(
                        rule=56,
                        location=f"{loc}.format",
                        severity="error",
                        message=(
                            f"[[source]] {src.id!r} format {fmt!r} is not a "
                            f"valid strftime pattern: {exc}"
                        ),
                        fix=(
                            "Use a valid strftime format string, e.g. "
                            '"%H:%M" for hours:minutes or "%b %d" for month+day.'
                        ),
                    )
                )

            tz = src.raw.get("timezone")
            if tz is not None:
                try:
                    ZoneInfo(tz)
                except ZoneInfoNotFoundError, ValueError, KeyError:
                    issues.append(
                        ValidationIssue(
                            rule=56,
                            location=f"{loc}.timezone",
                            severity="error",
                            message=(
                                f"[[source]] {src.id!r} timezone {tz!r} is not a "
                                f"valid IANA timezone name."
                            ),
                            fix=(
                                "Use an IANA timezone name like 'America/New_York', "
                                "'Europe/London', or 'UTC'. "
                                "Leave it out to use the system local time."
                            ),
                        )
                    )

        elif cls is StaticSource:
            if "value" not in src.raw:
                issues.append(
                    ValidationIssue(
                        rule=56,
                        location=loc,
                        severity="error",
                        message=(
                            f"[[source]] {src.id!r} (type='static') is missing "
                            f"the required `value` field."
                        ),
                        fix=(
                            f'Add `value = "..."` to the [[source]] block with '
                            f"id = {src.id!r}."
                        ),
                    )
                )

    return issues


def _check_static(config: AppConfig) -> list[ValidationIssue]:
    """Synchronous checks on raw widget dicts for errors not caught by _build_widget."""
    issues: list[ValidationIssue] = []
    ph = _panel_h_real(config.display)
    for i, section in enumerate(config.sections):
        # Rule 54: unknown mode value.
        # Old names (swap / forever_scroll / infini_scroll) raise MigrationError
        # at config-load before validate rules run, so this rule only fires for
        # values that are neither valid nor retired — pure unknowns like "wobble".
        if section.mode not in VALID_MODES:
            issues.append(
                ValidationIssue(
                    rule=54,
                    location=f"section[{i}].mode",
                    severity="error",
                    message=(
                        f"section[{i}].mode: unknown mode {section.mode!r}"
                        f" — valid modes: " + ", ".join(sorted(VALID_MODES))
                    ),
                    fix=(
                        "Set mode to one of: "
                        + ", ".join(sorted(VALID_MODES))
                        + ". Old names (swap, forever_scroll, infini_scroll) have"
                        " been renamed — check the migration guide."
                    ),
                )
            )

        # Rule 1: content_height × scale ceiling.
        # content_height × scale > panel_h_real causes the ScaledCanvas
        # wrapper's y_offset_real to go negative, silently clipping top and
        # bottom rows. Promoted from warning to error: any config that
        # trips this check will produce visually broken output on the panel
        # regardless of widget type.
        product = section.content_height * section.scale
        if product > ph:
            issues.append(
                ValidationIssue(
                    rule=1,
                    location=f"section[{i}]",
                    severity="error",
                    message=(
                        f"content_height {section.content_height}"
                        f" × scale {section.scale}"
                        f" = {product} exceeds panel height {ph}px"
                        " — edges will clip"
                    ),
                    fix=(
                        f"Lower content_height to {ph // section.scale}"
                        " (= panel_h ÷ scale)"
                    ),
                )
            )

        # Rule 31: scroll_step_ms must be positive. Zero divides in
        # `ticker.py:_swap_and_scroll` (`int(hold_time / scroll_speed)`)
        # and the wraps_forever branch is the primary user-reachable
        # timing path now that bottom_text_loops ships. Negative values
        # are nonsense — surface as a clear validate-time error rather
        # than letting startup crash with a stack trace.
        if section.scroll_step_ms is not None and section.scroll_step_ms <= 0:
            issues.append(
                ValidationIssue(
                    rule=31,
                    location=f"section[{i}]",
                    severity="error",
                    message=(
                        f"scroll_step_ms must be > 0; got "
                        f"{section.scroll_step_ms}. Section timing math "
                        f"divides by this value — 0 raises ZeroDivisionError "
                        f"at startup, negative values produce nonsensical "
                        f"tick counts."
                    ),
                    fix=(
                        "Set scroll_step_ms to a positive integer "
                        "(typical range: 25–60 ms per logical pixel)."
                    ),
                )
            )

        # Rule 25: start_hold is only meaningful on scroll modes
        # (ticker / one_at_a_time), which are the only modes
        # that call _scroll_and_delay. Setting it on slideshow has
        # no runtime effect — surface as an error so users don't think
        # they're tuning something they're not.
        if section.start_hold is not None:
            if section.mode == "slideshow":
                issues.append(
                    ValidationIssue(
                        rule=25,
                        location=f"section[{i}]",
                        severity="error",
                        message=(
                            f"start_hold has no effect on mode={section.mode!r};"
                            " only ticker / one_at_a_time honor it."
                        ),
                        fix=(
                            "Remove start_hold. For slideshow mode, use hold_time"
                            " (per-widget hold)."
                        ),
                    )
                )
            elif section.start_hold < 0:
                issues.append(
                    ValidationIssue(
                        rule=25,
                        location=f"section[{i}]",
                        severity="error",
                        message=(f"start_hold must be >= 0; got {section.start_hold}"),
                        fix="Set start_hold to 0 or a positive number of seconds.",
                    )
                )

        # Rule 26: separator_* fields are only honored by ticker.
        # On slideshow / one_at_a_time, the engine doesn't intersperse a
        # buffer message, so the fields would silently do nothing. Reject
        # so the misconfiguration surfaces. Single error per section even
        # if multiple separator_* fields are set.
        separator_set = (
            section.separator is not None
            or section.separator_font is not None
            or section.separator_font_size is not None
            or section.separator_color is not None
        )
        if separator_set and section.mode != "ticker":
            issues.append(
                ValidationIssue(
                    rule=26,
                    location=f"section[{i}]",
                    severity="error",
                    message=(
                        f"separator_* fields have no effect on"
                        f" mode={section.mode!r};"
                        " only ticker inserts a separator between loops."
                    ),
                    fix=(
                        "Remove separator / separator_font / separator_font_size"
                        " / separator_color, or change mode to 'ticker'."
                    ),
                )
            )

        for j, widget_cfg in enumerate(section.widgets):
            loc = f"section[{i}].widget[{j}]"
            wtype = widget_cfg.get("type", "")

            # Rule 3: scroll + stretch.
            # Only `text_align="scroll"` paints text BEHIND the image
            # (needs transparent regions). `text_align="scroll_over"`
            # paints text ON TOP and is fine with `fit="stretch"`.
            if (
                widget_cfg.get("text_align") == "scroll"
                and widget_cfg.get("fit") == "stretch"
            ):
                issues.append(
                    ValidationIssue(
                        rule=3,
                        location=loc,
                        severity="error",
                        message=(
                            "text_align='scroll' with fit='stretch':"
                            " no transparent regions for text to walk behind"
                        ),
                        fix=(
                            "Use text_align='scroll_over' to paint text on top"
                            " of the image, or change fit to"
                            " 'pillarbox' / 'letterbox' / 'crop'."
                        ),
                    )
                )

            # Rule 7: text_x_offset + scroll
            if widget_cfg.get("text_x_offset", 0) != 0 and widget_cfg.get(
                "text_align"
            ) in ("scroll", "scroll_over"):
                issues.append(
                    ValidationIssue(
                        rule=7,
                        location=loc,
                        severity="error",
                        message="text_x_offset is invalid with scroll text_align",
                        fix="Remove text_x_offset, or use a non-scroll text_align",
                    )
                )

            # Rule 8: hold_time < 0.05 (positive but below floor)
            # hold_time = 0.0 means "defer to section" and is explicitly allowed.
            hold_s = widget_cfg.get("hold_time")
            if hold_s is not None and hold_s > 0 and float(hold_s) < 0.05:
                issues.append(
                    ValidationIssue(
                        rule=8,
                        location=loc,
                        severity="error",
                        message=(
                            f"hold_time={hold_s} is too short (< 50 ms), likely a typo"
                        ),
                        fix="Raise hold_time to at least 0.05 (50 ms)",
                    )
                )

            # Rule 14: typewriter on gif/image constraints
            is_gif_or_image = wtype in ("gif", "image")
            if is_gif_or_image and widget_cfg.get("animation") == "typewriter":
                if widget_cfg.get("bottom_text", "") != "":
                    issues.append(
                        ValidationIssue(
                            rule=14,
                            location=loc,
                            severity="error",
                            message=(
                                "animation='typewriter' on gif/image is"
                                " single-row only; bottom_text is set"
                            ),
                            fix="Remove animation or remove bottom_text",
                        )
                    )
                if widget_cfg.get("text_align") in ("scroll", "scroll_over"):
                    issues.append(
                        ValidationIssue(
                            rule=14,
                            location=loc,
                            severity="error",
                            message=(
                                "animation='typewriter' on gif/image"
                                " cannot combine with scrolling text_align"
                            ),
                            fix=(
                                "Remove animation, or change text_align"
                                " to 'left'/'right'/'auto'"
                            ),
                        )
                    )
                if not widget_cfg.get("text", ""):
                    issues.append(
                        ValidationIssue(
                            rule=14,
                            location=loc,
                            severity="error",
                            message=(
                                "animation='typewriter' on gif/image"
                                " requires non-empty text"
                            ),
                            fix="Add text = '...' or remove animation",
                        )
                    )

            # Rule 28: bottom_text_loops on two_row requires wrap mode
            # (no concept of cycle without wrap separator). Mirrors the
            # post-init validation in TwoRowMessage so the error
            # surfaces at config-load time, not at runtime.
            # (Rule 27 is taken: it covers bottom_text_wrap mode constraints
            # from PR #59 — a related but distinct concern.)
            if wtype == "two_row":
                btl = widget_cfg.get("bottom_text_loops", 0)
                btw = widget_cfg.get("bottom_text_wrap", False)
                # Reject bool first — bool is an int subclass, so without
                # this check `bottom_text_loops = true` would silently
                # behave as loops=1.
                if isinstance(btl, bool):
                    issues.append(
                        ValidationIssue(
                            rule=28,
                            location=loc,
                            severity="error",
                            message=(
                                f"bottom_text_loops must be an integer; got "
                                f"bool ({btl!r}). Use 0, 1, 2, … not true/false."
                            ),
                            fix=(
                                "Replace true/false with an integer count "
                                "(e.g. bottom_text_loops = 3)."
                            ),
                        )
                    )
                elif isinstance(btl, int) and btl < 0:
                    issues.append(
                        ValidationIssue(
                            rule=28,
                            location=loc,
                            severity="error",
                            message=(f"bottom_text_loops must be >= 0; got {btl}"),
                            fix="Set bottom_text_loops to 0 or a positive integer.",
                        )
                    )
                elif (
                    isinstance(btl, int)
                    and btl > 0
                    and not btw
                    and widget_cfg.get("bottom_text_scroll") != "scroll_through"
                ):
                    issues.append(
                        ValidationIssue(
                            rule=28,
                            location=loc,
                            severity="error",
                            message=(
                                f"bottom_text_loops={btl} requires either "
                                f"bottom_text_wrap=true (seamless tiled "
                                f"marquee) or "
                                f"bottom_text_scroll='scroll_through' "
                                f"(repeat the offscreen pass N times). "
                                f"Without one of these, the bottom row has "
                                f"no cycle to count."
                            ),
                            fix=(
                                "Either set bottom_text_wrap = true, OR set "
                                "bottom_text_scroll = 'scroll_through', OR "
                                "drop bottom_text_loops."
                            ),
                        )
                    )

                # Rule 29: did-you-mean bridge for `text_loops` on two_row.
                # `text_loops` is the image-widget field name for the same
                # concept; users copying a gif/image marquee config to
                # two_row will reach for it out of muscle memory. Without
                # this targeted catch, a generic "unknown field" error
                # (from the unknown-kwarg validator follow-up) won't
                # suggest the correct name — and today the field slips
                # straight through validation and crashes at runtime with
                # `TypeError: TwoRowMessage.__init__() got an unexpected
                # keyword argument 'text_loops'`.
                if "text_loops" in widget_cfg:
                    issues.append(
                        ValidationIssue(
                            rule=29,
                            location=f"{loc}.text_loops",
                            severity="error",
                            message=(
                                "`text_loops` is not a valid field on a "
                                "`two_row` widget — did you mean "
                                "`bottom_text_loops`? The image widgets "
                                "(`gif`, `image`) use `text_loops` because "
                                "they're single-row by default; "
                                "TwoRowMessage uses the bottom-prefixed "
                                "name to match its bottom_text_wrap / "
                                "bottom_text_separator family."
                            ),
                            fix=(
                                "Rename `text_loops` to `bottom_text_loops` "
                                "and set `bottom_text_wrap = true` (loops "
                                "require wrap mode — see rule 28)."
                            ),
                        )
                    )

            # Rule 34b: scroll_step_ms on a gif / image widget.
            # `scroll_step_ms` is a SECTION-level field (engine cursor
            # advance). On a gif/image widget it would be passed as an
            # unknown kwarg and crash at startup. The widget-level
            # equivalent is `scroll_speed_ms` (text-marquee cadence inside
            # the widget's own play() loop). Scoped to gif/image only —
            # those are the widget types that HAVE a scroll_speed_ms to
            # be confused with. Other widget types receiving scroll_step_ms
            # will be caught by a future unknown-kwarg validator.
            if wtype in ("gif", "image") and "scroll_step_ms" in widget_cfg:
                issues.append(
                    ValidationIssue(
                        rule=34,
                        location=f"{loc}.scroll_step_ms",
                        severity="error",
                        message=(
                            "`scroll_step_ms` is a section-level field, not a "
                            "widget field. On a gif/image widget, did you mean "
                            "`scroll_speed_ms`? "
                            "`scroll_step_ms` sets the engine's per-tick cursor "
                            "advance across all widgets in the section; "
                            "`scroll_speed_ms` sets the text-marquee cadence "
                            "inside this widget's play() loop."
                        ),
                        fix=(
                            "Move `scroll_step_ms` to the `[[playlist.section]]` "
                            "block (section level), or rename it to "
                            "`scroll_speed_ms` to control the text-marquee speed "
                            "inside this gif/image widget."
                        ),
                    )
                )

        # Rule 34a: scroll_speed_ms at section level.
        # `scroll_speed_ms` is a per-widget field on gif/image widgets —
        # it controls the text-marquee cadence inside a single widget's
        # play() loop. At section level it is silently ignored (the
        # section loader doesn't know the key). The section-level
        # equivalent is `scroll_step_ms`. Inspect via _raw so the check
        # runs on fields the dataclass discards.
        if "scroll_speed_ms" in section._raw:
            issues.append(
                ValidationIssue(
                    rule=34,
                    location=f"section[{i}].scroll_speed_ms",
                    severity="error",
                    message=(
                        "`scroll_speed_ms` is a widget-level field (gif/image "
                        "text-marquee cadence), not a section field. At section "
                        "level it is silently ignored. Did you mean "
                        "`scroll_step_ms`? "
                        "`scroll_step_ms` sets the engine's per-tick cursor "
                        "advance across all widgets in the section."
                    ),
                    fix=(
                        "Rename `scroll_speed_ms` to `scroll_step_ms` in the "
                        "`[[playlist.section]]` block, or move it inside the "
                        "gif/image `[[playlist.section.widget]]` block if you "
                        "want to control the text-marquee speed on a specific widget."
                    ),
                )
            )

        # Rule 41: title "color" was renamed to "font_color". The translation
        # that used to silently accept the old name was removed; configs still
        # using it will fail at runtime. Surface at validate time so users get
        # the message before deploying.
        if section.title and "color" in section.title:
            issues.append(
                ValidationIssue(
                    rule=41,
                    location=f"section[{i}].title",
                    severity="error",
                    message=(
                        'title field "color" was renamed to "font_color" —'
                        " update your config"
                    ),
                    fix=(
                        'Rename "color" to "font_color" in your'
                        " [playlist.section.title] block."
                    ),
                    fix_key="color",
                    fix_replacement_key="font_color",
                )
            )
    return issues


def _check_transition_names(config: AppConfig) -> list[ValidationIssue]:
    """Rule 39: Named transitions must exist in the transition registry.

    Runs in normal mode — a typo in a transition name always fails at startup
    and has no deploy-target excuse. The "cut" sentinel is always valid.
    """
    from led_ticker.config import TransitionConfig
    from led_ticker.transitions import explain_unknown_transition, list_transition_names

    valid_set = set(list_transition_names())
    issues: list[ValidationIssue] = []

    def _check(trans_cfg: TransitionConfig | None, location: str) -> None:
        if trans_cfg is None or trans_cfg.type == "cut":
            return
        if trans_cfg.type in valid_set:
            return
        message, fix = explain_unknown_transition(trans_cfg.type)
        issues.append(
            ValidationIssue(
                rule=39,
                location=location,
                severity="error",
                message=message,
                fix=fix,
            )
        )

    _check(config.default_transition, "transitions.default")
    if config.between_sections_specified:
        _check(config.between_sections, "transitions.between_sections")
    for i, section in enumerate(config.sections):
        if section.transition_specified:
            _check(section.transition, f"section[{i}].transition")
        if section.entry_transition is not None:
            _check(section.entry_transition, f"section[{i}].entry_transition")
        if section.widget_transition is not None:
            _check(section.widget_transition, f"section[{i}].widget_transition")

    return issues


def _check_separator_color_transition(config: AppConfig) -> list[ValidationIssue]:
    """Rule 57: separator / separator_color / separator_font fields are only
    honored by the scroll transition.

    Any transition home (per-section transition / entry_transition /
    widget_transition, plus the global between_sections) that carries any of
    the separator_* fields but whose type is not 'scroll' will silently ignore
    them at runtime.  Reject it early so the misconfiguration surfaces.
    """
    from led_ticker.config import TransitionConfig

    issues: list[ValidationIssue] = []

    def _check(trans_cfg: TransitionConfig | None, location: str) -> None:
        if trans_cfg is None:
            return
        _SEP_FIELDS = (
            "separator",
            "separator_color",
            "separator_font",
            "separator_font_size",
        )
        sep_set = any(getattr(trans_cfg, f, None) is not None for f in _SEP_FIELDS)
        if not sep_set:
            return
        if trans_cfg.type == "scroll":
            return
        issues.append(
            ValidationIssue(
                rule=57,
                location=location,
                severity="error",
                message=(
                    "separator / separator_color / separator_font fields are "
                    f"only honored by the scroll transition; type="
                    f"{trans_cfg.type!r} ignores them."
                ),
                fix="Use the separator fields only with type='scroll', or remove them.",
            )
        )

    if config.between_sections_specified:
        _check(config.between_sections, "transitions.between_sections")
    for i, section in enumerate(config.sections):
        if section.transition_specified:
            _check(section.transition, f"section[{i}].transition")
        if section.entry_transition is not None:
            _check(section.entry_transition, f"section[{i}].entry_transition")
        if section.widget_transition is not None:
            _check(section.widget_transition, f"section[{i}].widget_transition")

    return issues


def _check_scroll_separator_font(
    config: AppConfig,
) -> tuple[list[ValidationIssue], list[ValidationIssue]]:
    """Resolve `separator_font` on scroll transitions across all four homes.

    Mirrors `_check_separator_fonts` (section-level separator_font) but for
    TransitionConfig homes:
      - UnknownFontError  → rule 24 warning (font may live on the deploy target)
      - ValueError containing "requires a size" → rule 5 error

    When `separator_font_size` is omitted, `resolve_font` raises a generic
    ValueError ("requires a size") before it can confirm the name is known.
    In that case we re-probe with a dummy size (24) so unknown-font cases
    still surface as rule-24 warnings rather than opaque "requires size" errors.

    Only fires for type='scroll' transitions; non-scroll homes are already
    rejected by rule 57 (``_check_separator_color_transition``).
    """
    from led_ticker.config import TransitionConfig
    from led_ticker.fonts import UnknownFontError, resolve_font

    _UNKNOWN_FONT_FIX = (
        "Drop the font file into config/fonts/ on the deploy"
        " target, or pick one of the bundled fonts listed"
        " above (BDF: 5x8 / 6x10 / 6x12 / 7x13; hires:"
        " Inter-Bold / Inter-Regular)."
    )
    _MISSING_SIZE_FIX = (
        "Add separator_font_size = <pixels> next to"
        " separator_font (e.g. separator_font_size = 24)."
    )

    errors: list[ValidationIssue] = []
    warnings: list[ValidationIssue] = []

    def _check(trans_cfg: TransitionConfig | None, location: str) -> None:
        if trans_cfg is None:
            return
        if trans_cfg.type != "scroll":
            return
        if getattr(trans_cfg, "separator_font", None) is None:
            return
        try:
            resolve_font(trans_cfg.separator_font, size=trans_cfg.separator_font_size)
        except UnknownFontError as exc:
            warnings.append(
                ValidationIssue(
                    rule=24,
                    location=f"{location}.separator_font",
                    severity="warning",
                    message=str(exc),
                    fix=_UNKNOWN_FONT_FIX,
                )
            )
        except ValueError as exc:
            msg = str(exc)
            # When separator_font_size is absent, resolve_font raises
            # "requires a size" before confirming whether the font name is
            # valid.  Re-probe with a dummy size so that an unknown-font
            # name still surfaces as a rule-24 warning rather than an
            # opaque "requires size" error.
            if trans_cfg.separator_font_size is None:
                try:
                    resolve_font(trans_cfg.separator_font, size=24)
                except UnknownFontError as probe_exc:
                    warnings.append(
                        ValidationIssue(
                            rule=24,
                            location=f"{location}.separator_font",
                            severity="warning",
                            message=str(probe_exc),
                            fix=_UNKNOWN_FONT_FIX,
                        )
                    )
                    return
                except ValueError:
                    pass  # fall through to the error path below
            # resolve_font's missing-size message is "requires a size"
            # (fonts/__init__.py) — NOT "requires font_size". Match the real
            # text so a hires font with no size classifies as rule 5.
            rule = 5 if "requires a size" in msg else None
            errors.append(
                ValidationIssue(
                    rule=rule,
                    location=f"{location}.separator_font",
                    severity="error",
                    message=msg,
                    fix=_MISSING_SIZE_FIX,
                )
            )

    if config.between_sections_specified:
        _check(config.between_sections, "transitions.between_sections")
    for i, section in enumerate(config.sections):
        if section.transition_specified:
            _check(section.transition, f"section[{i}].transition")
        if section.entry_transition is not None:
            _check(section.entry_transition, f"section[{i}].entry_transition")
        if section.widget_transition is not None:
            _check(section.widget_transition, f"section[{i}].widget_transition")

    return errors, warnings


# Rule 53: plugin transition config kwargs (unknown/missing keys).
def _check_plugin_transition_kwargs(config: AppConfig) -> list[ValidationIssue]:
    """Validate kwargs for plugin (dotted-type) transitions at validate time.

    Attempts to build each dotted-type transition with its `extra` kwargs
    via `_build_trans_obj`. A clean ValueError from `_build_plugin_style`
    (unknown or missing keys) is surfaced as a validation error rather than
    letting it crash at startup.

    Built-in transitions (bare names like "dissolve") are skipped — they
    have no `extra` and are handled by the existing special-cased path.
    """
    from led_ticker.app.factories import _build_trans_obj
    from led_ticker.config import TransitionConfig

    issues: list[ValidationIssue] = []

    def _check(trans_cfg: TransitionConfig | None, location: str) -> None:
        if trans_cfg is None or trans_cfg.type == "cut":
            return
        if "." not in trans_cfg.type:
            return  # built-in transition; kwargs checked by constructor
        try:
            _build_trans_obj(trans_cfg)
        except ValueError as exc:
            issues.append(
                ValidationIssue(
                    rule=53,
                    location=location,
                    severity="error",
                    message=str(exc),
                    fix=(
                        "Check the plugin transition's accepted kwargs. "
                        "Remove unknown keys or add required keys."
                    ),
                )
            )

    _check(config.default_transition, "transitions.default")
    if config.between_sections_specified:
        _check(config.between_sections, "transitions.between_sections")
    for i, section in enumerate(config.sections):
        if section.transition_specified:
            _check(section.transition, f"section[{i}].transition")
        if section.entry_transition is not None:
            _check(section.entry_transition, f"section[{i}].entry_transition")
        if section.widget_transition is not None:
            _check(section.widget_transition, f"section[{i}].widget_transition")

    return issues


def _check_transition_fps(config: AppConfig) -> list[ValidationIssue]:
    """Rule 50: transition_fps must be in the usable range 5–120 fps.

    Values below 5 fps will look like a slideshow and may indicate a
    typo (seconds entered instead of fps). Values above 120 fps exceed
    what a Pi can push to the matrix; the sleep budget goes negative.
    """
    issues: list[ValidationIssue] = []

    def _check(fps: float | None, location: str) -> None:
        if fps is None:
            return
        if fps < 5 or fps > 120:
            issues.append(
                ValidationIssue(
                    rule=50,
                    location=location,
                    severity="warning",
                    message=(
                        f"transition_fps={fps} is outside the usable range 5–120 fps"
                    ),
                    fix=(
                        "Use a value between 5 and 120. "
                        "Typical values: 20 (default), 30, 40. "
                        "Values below 5 may be seconds instead of fps."
                    ),
                )
            )

    _check(config.default_transition.transition_fps, "transitions.default")
    _check(config.between_sections.transition_fps, "transitions.between_sections")
    for i, section in enumerate(config.sections):
        _check(section.transition.transition_fps, f"section[{i}].transition")
        if section.entry_transition is not None:
            _check(
                section.entry_transition.transition_fps,
                f"section[{i}].entry_transition",
            )
        if section.widget_transition is not None:
            _check(
                section.widget_transition.transition_fps,
                f"section[{i}].widget_transition",
            )

    return issues


def _check_asset_paths(config: AppConfig, config_dir: Path) -> list[ValidationIssue]:
    """Rule 40: Asset `path` fields for gif/image widgets must exist on disk.

    Only runs in --strict mode. In normal mode, missing paths are silently
    allowed because the asset might only be present on the deploy target.
    """
    issues: list[ValidationIssue] = []
    for i, section in enumerate(config.sections):
        for j, widget_cfg in enumerate(section.widgets):
            if widget_cfg.get("type") not in ("gif", "image"):
                continue
            raw_path = widget_cfg.get("path")
            if not raw_path:
                continue
            candidate = Path(raw_path)
            resolved = (
                candidate
                if candidate.is_absolute()
                else (config_dir / candidate).resolve()
            )
            if not resolved.exists():
                issues.append(
                    ValidationIssue(
                        rule=40,
                        location=f"section[{i}].widget[{j}]",
                        severity="error",
                        message=(
                            f"asset path {raw_path!r} does not exist"
                            f" (resolved to {resolved})"
                        ),
                        fix=(
                            "Check the path is correct relative to the config "
                            "file. In --strict mode all referenced asset files "
                            "must be present."
                        ),
                    )
                )
    return issues


# Rule 55: advisory warnings contributed by a widget's
# validate_config_warnings(cls, cfg, ctx) hook (plugins + core widgets alike).
def _check_plugin_validation_warnings(
    config: AppConfig, config_dir: Path
) -> list[ValidationIssue]:
    """Collect each widget's advisory ``validate_config_warnings`` output.

    Builds a per-section ``ValidationContext`` (geometry + config_dir) and emits
    every returned string as a warning. The hook is error-isolated inside
    ``collect_validation_warnings`` so a buggy check never breaks validation.
    """
    from led_ticker.app.factories import collect_validation_warnings
    from led_ticker.plugin import ValidationContext

    issues: list[ValidationIssue] = []
    panel_w = _panel_w_real(config.display)
    panel_h = _panel_h_real(config.display)
    for i, section in enumerate(config.sections):
        ctx = ValidationContext(
            scale=section.scale,
            content_height=section.content_height,
            panel_width=panel_w,
            panel_height=panel_h,
            config_dir=config_dir,
        )
        for j, widget_cfg in enumerate(section.widgets):
            for msg in collect_validation_warnings(dict(widget_cfg), ctx):
                issues.append(
                    ValidationIssue(
                        rule=55,
                        location=f"section[{i}].widget[{j}]",
                        severity="warning",
                        message=msg,
                        fix="Advisory check from the widget. "
                        "See the widget's documentation for how to resolve"
                        " this advisory.",
                    )
                )
    return issues


_WEIGHT_SUFFIXES = frozenset(
    [
        "Regular",
        "Bold",
        "Light",
        "Medium",
        "Thin",
        "Black",
        "Heavy",
        "ExtraBold",
        "SemiBold",
        "Italic",
        "BoldItalic",
    ]
)


def _font_family(name: str) -> str:
    """Return the family stem by stripping a trailing weight suffix."""
    parts = name.rsplit("-", 1)
    if len(parts) == 2 and parts[1] in _WEIGHT_SUFFIXES:
        return parts[0]
    return name


def _panel_h_real(display: DisplayConfig) -> int:
    """Best-effort panel height in real pixels."""
    if display.pixel_mapper_config.startswith("Remap:"):
        # "Remap:256,64|..." — second number is total canvas height
        remap = display.pixel_mapper_config[6:]
        dims = remap.split("|")[0]
        return int(dims.split(",")[1])
    return display.rows * display.parallel


def _panel_w_real(display: DisplayConfig) -> int:
    """Best-effort panel width in real pixels."""
    if display.pixel_mapper_config.startswith("Remap:"):
        # "Remap:256,64|..." — first number is total canvas width
        remap = display.pixel_mapper_config[6:]
        dims = remap.split("|")[0]
        return int(dims.split(",")[0])
    return display.cols * display.chain_length


def _check_soft(config: AppConfig) -> list[ValidationIssue]:
    warnings: list[ValidationIssue] = []

    for i, section in enumerate(config.sections):
        # Rule 6: two_row at scale=4
        for j, widget_cfg in enumerate(section.widgets):
            if widget_cfg.get("type") == "two_row" and section.scale == 4:
                warnings.append(
                    ValidationIssue(
                        rule=6,
                        location=f"section[{i}].widget[{j}]",
                        severity="warning",
                        message=(
                            "two_row at scale=4: logical canvas is only 64px wide"
                            " — handles may scroll instead of fitting"
                        ),
                        fix="Add scale = 2 to this section for a 128px logical canvas",
                    )
                )

        # Rule 35: `default = "..."` inside a [[playlist.section]] block.
        # `default` is a [transitions]-block key. Inside a section the
        # equivalent is `transition`. Writing `default = "wipe_left"` in
        # a section silently does nothing — the section loader discards
        # any key it doesn't recognise. Inspect via _raw so we see
        # original TOML keys that the dataclass swallows.
        if "default" in section._raw:
            warnings.append(
                ValidationIssue(
                    rule=35,
                    location=f"section[{i}].default",
                    severity="warning",
                    message=(
                        "`default` is a [transitions]-block key. "
                        "Inside a [[playlist.section]], the equivalent "
                        "is `transition`. The key as written is silently "
                        "ignored."
                    ),
                    fix="Rename `default = '...'` to `transition = '...'`.",
                )
            )

        # Rule 2: font_threshold mismatch within font family
        family_thresholds: dict[str, list[int]] = {}
        for widget_cfg in section.widgets:
            fname = widget_cfg.get("font")
            if fname is None:
                continue
            thr = int(widget_cfg.get("font_threshold", 128))
            family = _font_family(str(fname))
            family_thresholds.setdefault(family, []).append(thr)

        for family, thresholds in family_thresholds.items():
            unique = set(thresholds)
            if len(unique) > 1:
                warnings.append(
                    ValidationIssue(
                        rule=2,
                        location=f"section[{i}]",
                        severity="warning",
                        message=(
                            f"Font family '{family}' used with mismatched"
                            f" font_threshold values: {sorted(unique)}"
                            " — weight contrast may invert on panel"
                        ),
                        fix=(
                            "Set the same font_threshold on all widgets in the same"
                            " font family (e.g. both at 80)"
                        ),
                    )
                )

    # Rule 21: transition_duration plausibility
    trans_checks: list[tuple[str, float]] = [
        ("transitions.default", config.default_transition.duration),
        ("transitions.between_sections", config.between_sections.duration),
    ]
    for i, section in enumerate(config.sections):
        trans_checks.append((f"section[{i}]", section.transition.duration))

    for loc, d in trans_checks:
        if d > 5.0:
            warnings.append(
                ValidationIssue(
                    rule=21,
                    location=loc,
                    severity="warning",
                    message=(
                        f"transition_duration {d} looks like milliseconds"
                        " (> 5 s is unusual)"
                    ),
                    fix=f"Divide by 1000 → {d / 1000:.3f} s",
                )
            )
        elif d < 0.05:
            warnings.append(
                ValidationIssue(
                    rule=21,
                    location=loc,
                    severity="warning",
                    message=f"transition_duration {d} is extremely short (< 50 ms)",
                    fix="Raise to at least 0.05 s",
                )
            )

    # Rule 30: hold_time and bottom_text_loops both set on a two_row
    # widget — max() semantics apply and the larger tick count wins.
    # Surface a warning so users who set both deliberately get a
    # heads-up that one will silently dominate the other depending
    # on text length.
    #
    # SCOPED TO `two_row` ONLY: gif/image widgets in two-row mode also
    # have a `text_loops` field, but it means something different there.
    # On gif/image, `text_loops` is a marquee-traversal floor inside the
    # widget's own play() loop — a minimum number of times the text
    # scrolls across the panel during playback, not a section-duration
    # multiplier the way `bottom_text_loops` works on TwoRowMessage
    # (which the engine uses to extend the section's wraps_forever
    # tick count via max(hold_time_ticks, loops × cycle_width)). The
    # interaction model on gif/image doesn't admit the same kind of
    # silent-dominance trap, so the warning would be misleading.
    # (For the gif `play_count` ↔ `hold_time` interaction, see
    # _play_widget — section.hold_time IS threaded to widget.play() so
    # `play_count = 0` can play through the section's duration.)
    #
    # Only fires when hold_time was EXPLICITLY written in TOML
    # (hold_time_specified); the default 3.0 is universally
    # inherited and would be a false positive otherwise.
    for i, section in enumerate(config.sections):
        if not section.hold_time_specified:
            continue
        for j, widget_cfg in enumerate(section.widgets):
            if widget_cfg.get("type", "") != "two_row":
                continue
            btl = widget_cfg.get("bottom_text_loops", 0)
            if not (isinstance(btl, int) and not isinstance(btl, bool) and btl > 0):
                continue
            warnings.append(
                ValidationIssue(
                    rule=30,
                    location=f"section[{i}].widget[{j}]",
                    severity="warning",
                    message=(
                        f"section sets hold_time={section.hold_time} AND "
                        f"widget sets bottom_text_loops={btl}. The engine "
                        f"runs for max(hold_time_ticks, "
                        f"bottom_text_loops × cycle_width) ticks — "
                        f"whichever is larger dominates. Result: depending "
                        f"on bottom_text length, the user may get more "
                        f"loops than requested (hold_time dominates) or "
                        f"the section runs longer than hold_time (loops "
                        f"dominate)."
                    ),
                    fix=(
                        "For an EXACT loop count (the common case): drop "
                        "hold_time from this section — bottom_text_loops "
                        "becomes the only floor. "
                        "For a FIXED duration: drop bottom_text_loops. "
                        "If you intentionally want both as floors and "
                        "understand max() semantics, ignore this warning."
                    ),
                )
            )

    return warnings


def _check_band_layout(config: AppConfig) -> list[ValidationIssue]:
    """Catch fonts that don't fit a multi-row widget's per-row band.

    Without this, the same check fires only when the widget first
    draws — a config that would crash on first paint passes
    `led-ticker validate` clean. Lifts the same `font_line_height_logical
    > band_h` check from `TwoRowMessage.draw` and
    `_BaseImageWidget._play_with_two_row_text` to the config-load
    surface.

    Applies to:
      - `type = "two_row"` (TwoRowMessage)
      - `type = "gif"` / `type = "image"` with `bottom_text != ""`
        (image/gif two-row text overlay mode)
    """
    from led_ticker.fonts import (
        FONT_DEFAULT,
        FONT_SMALL,
        font_line_height_logical,
        resolve_font,
    )
    from led_ticker.widgets._row_layout import resolve_band_heights

    issues: list[ValidationIssue] = []
    for i, section in enumerate(config.sections):
        scale = section.scale
        content_h = section.content_height
        for j, widget_cfg in enumerate(section.widgets):
            wtype = widget_cfg.get("type", "")

            # Default-font choice mirrors the widget classes:
            # TwoRowMessage's `font` defaults to FONT_SMALL (5x8);
            # _BaseImageWidget's `font` defaults to FONT_DEFAULT (6x12).
            if wtype == "two_row":
                default_font = FONT_SMALL
            elif wtype in ("gif", "image"):
                if widget_cfg.get("bottom_text", "") == "":
                    continue  # single-row mode: no per-band check needed
                default_font = FONT_DEFAULT
            else:
                continue

            top_row_height = widget_cfg.get("top_row_height")
            try:
                top_h, bottom_h = resolve_band_heights(content_h, top_row_height)
            except ValueError as e:
                # top_row_height >= content_height leaves the bottom row zero
                # rows, so TwoRowMessage.draw() raises and freezes the panel
                # (constraint #1). Nothing constructs or draws the widget during
                # validation (validate_widget_cfg is coercion-only), so this is
                # NOT caught downstream — surface it here instead of swallowing.
                issues.append(
                    ValidationIssue(
                        rule=22,
                        location=f"section[{i}].widget[{j}]",
                        severity="error",
                        message=str(e),
                        fix=(
                            "Set top_row_height < the section's content_height "
                            "(omit it for the default 50/50 split)."
                        ),
                    )
                )
                continue

            shared_font_name = widget_cfg.get("font")
            shared_size = widget_cfg.get("font_size")
            for label, band_h, name_key, size_key in (
                ("top", top_h, "top_font", "top_font_size"),
                ("bottom", bottom_h, "bottom_font", "bottom_font_size"),
            ):
                font_name = widget_cfg.get(name_key) or shared_font_name
                font_size = widget_cfg.get(size_key) or shared_size
                try:
                    if font_name is None:
                        font = default_font
                    else:
                        font = resolve_font(font_name, size=font_size)
                except ValueError:
                    # _run_build_checks will surface the resolve_font failure.
                    continue

                lh = font_line_height_logical(font, scale)
                if lh > band_h:
                    issues.append(
                        ValidationIssue(
                            rule=22,
                            location=f"section[{i}].widget[{j}]",
                            severity="error",
                            message=(
                                f"{label} font line-height ({lh} logical rows) "
                                f"exceeds the per-row band ({band_h} rows on a "
                                f"{content_h}-tall canvas)."
                            ),
                            fix=(
                                "Pick a smaller font_size, raise the section's "
                                "content_height, or adjust top_row_height for "
                                "an asymmetric split. BDF aliases (5x8, 6x12) "
                                "have fixed cell heights — use them when you "
                                "need the smallest reliably-fitting text."
                            ),
                        )
                    )
    return issues


def _check_separator_fonts(
    config: AppConfig,
) -> tuple[list[ValidationIssue], list[ValidationIssue]]:
    """Resolve any `separator_font` set on ticker sections.

    Returns (errors, warnings). UnknownFontError → rule 24 warning
    (consistent with widget-font behavior). Other ValueError (e.g.
    "requires font_size") → rule 5 error.
    """
    from led_ticker.fonts import UnknownFontError, resolve_font

    errors: list[ValidationIssue] = []
    warnings: list[ValidationIssue] = []
    for i, section in enumerate(config.sections):
        if section.mode != "ticker":
            continue  # Rule 26 already caught the wrong-mode case
        if section.separator_font is None:
            continue
        try:
            resolve_font(section.separator_font, size=section.separator_font_size)
        except UnknownFontError as exc:
            warnings.append(
                ValidationIssue(
                    rule=24,
                    location=f"section[{i}].separator_font",
                    severity="warning",
                    message=str(exc),
                    fix=(
                        "Drop the font file into config/fonts/ on the deploy"
                        " target, or pick one of the bundled fonts listed"
                        " above (BDF: 5x8 / 6x10 / 6x12 / 7x13; hires:"
                        " Inter-Bold / Inter-Regular)."
                    ),
                )
            )
        except ValueError as exc:
            # e.g. "requires font_size" for hires font with no size — same
            # message pattern as the existing rule 5.
            msg = str(exc)
            rule = 5 if "requires font_size" in msg else None
            errors.append(
                ValidationIssue(
                    rule=rule,
                    location=f"section[{i}].separator_font",
                    severity="error",
                    message=msg,
                    fix=(
                        "Add separator_font_size = <pixels> next to"
                        " separator_font (e.g. separator_font_size = 24)."
                    ),
                )
            )
    return errors, warnings


def _check_wraps_slideshow_only(
    config: AppConfig,
) -> list[ValidationIssue]:
    """Rule 27: bottom_text_wrap=True is only valid in mode='slideshow'.

    In ticker and one_at_a_time modes, widgets must terminate
    naturally (the section advances based on widget completion).
    A wraps_forever widget never terminates on cursor_pos — it would
    block the chain. Catch at config-load with a clear error.
    """
    errors: list[ValidationIssue] = []
    for i, section in enumerate(config.sections):
        if section.mode == "slideshow":
            continue
        for j, widget_cfg in enumerate(section.widgets):
            if widget_cfg.get("bottom_text_wrap") is True:
                errors.append(
                    ValidationIssue(
                        rule=27,
                        location=(f"section[{i}].widget[{j}].bottom_text_wrap"),
                        severity="error",
                        message=(
                            f"bottom_text_wrap=True is only allowed in "
                            f"mode='slideshow'; got mode={section.mode!r}. "
                            f"Other modes expect widgets to terminate "
                            f"naturally — a wrapping widget would block "
                            f"the chain."
                        ),
                        fix=(
                            "Either change the section mode to 'slideshow' "
                            "(time-bounded by hold_time), or drop "
                            "bottom_text_wrap from the widget. The "
                            "default off-right→off-left marquee works "
                            "in any mode."
                        ),
                    )
                )
    return errors


def _check_scroll_through_slideshow_only(
    config: AppConfig,
) -> list[ValidationIssue]:
    """Rule 32: bottom_text_scroll='scroll_through' is only valid in
    mode='slideshow'. Parallel to rule 27 for bottom_text_wrap.

    ticker and one_at_a_time drive widgets via _scroll_one_by_one /
    _scroll_side_by_side, which read the widget's reported cursor_pos as
    physical scroll travel. A scroll_through widget inflates cursor_pos
    to `2 * canvas.width + bottom_width + padding` so the engine's
    slideshow-mode stop math (`stop_pos = -(cursor - canvas.width) + padding`)
    lands at -(canvas.width + bottom_width). In non-slideshow modes that
    same inflated value produces 2× the expected scroll travel —
    visible as a full canvas-width of blank ticks per visit.
    """
    errors: list[ValidationIssue] = []
    for i, section in enumerate(config.sections):
        if section.mode == "slideshow":
            continue
        for j, widget_cfg in enumerate(section.widgets):
            if widget_cfg.get("bottom_text_scroll") == "scroll_through":
                errors.append(
                    ValidationIssue(
                        rule=32,
                        location=(f"section[{i}].widget[{j}].bottom_text_scroll"),
                        severity="error",
                        message=(
                            f"bottom_text_scroll='scroll_through' is only "
                            f"allowed in mode='slideshow'; got mode="
                            f"{section.mode!r}. Other modes interpret the "
                            f"widget's cursor_pos as physical scroll "
                            f"travel; scroll_through inflates it to "
                            f"anchor slideshow-mode stop math, producing 2× "
                            f"the expected travel in non-slideshow modes."
                        ),
                        fix=(
                            "Either change the section mode to 'slideshow' "
                            "(time-bounded by hold_time), or drop "
                            "bottom_text_scroll from the widget. The "
                            "default 'marquee' value works in any mode."
                        ),
                    )
                )
    return errors


_VALID_DAYS = {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}


def _check_schedule(config: AppConfig) -> list[ValidationIssue]:
    from led_ticker.schedule import to_minutes, unreachable_window_indices

    sched = config.display.schedule
    if not sched.enabled:
        return []
    issues: list[ValidationIssue] = []
    if sched.timezone:
        if not isinstance(sched.timezone, str):
            issues.append(
                ValidationIssue(
                    rule=None,
                    location="display.schedule.timezone",
                    message=(
                        f"timezone must be a string IANA name,"
                        f" got {type(sched.timezone).__name__}"
                    ),
                    fix=(
                        "Use an IANA name like 'America/New_York',"
                        " or leave it empty for system local time."
                    ),
                    severity="error",
                )
            )
        else:
            from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

            try:
                ZoneInfo(sched.timezone)
            except ZoneInfoNotFoundError, ValueError, TypeError:
                issues.append(
                    ValidationIssue(
                        rule=None,
                        location="display.schedule.timezone",
                        message=(
                            f"timezone {sched.timezone!r} is not a valid"
                            " IANA timezone name"
                        ),
                        fix=(
                            "Use an IANA name like 'America/New_York',"
                            " or leave it empty for system local time."
                        ),
                        severity="error",
                    )
                )
    if not sched.windows:
        issues.append(
            ValidationIssue(
                rule=None,
                location="display.schedule",
                message=(
                    "schedule is enabled but has no windows"
                    " (no-op; base brightness always applies)"
                ),
                fix=(
                    "Add at least one [[display.schedule.windows]] entry,"
                    " or set enabled = false."
                ),
                severity="warning",
            )
        )
    for i, w in enumerate(sched.windows):
        loc = f"display.schedule.windows[{i}]"
        s, e = to_minutes(w.start), to_minutes(w.end)
        if s is None:
            issues.append(
                ValidationIssue(
                    None,
                    loc,
                    f"start {w.start!r} is not a valid 24h HH:MM time",
                    "Use a zero-padded 24-hour time like '07:00'.",
                    "error",
                )
            )
        if e is None:
            issues.append(
                ValidationIssue(
                    None,
                    loc,
                    f"end {w.end!r} is not a valid 24h HH:MM time",
                    "Use a zero-padded 24-hour time like '23:00'.",
                    "error",
                )
            )
        if s is not None and e is not None and s == e:
            issues.append(
                ValidationIssue(
                    None,
                    loc,
                    "start and end are equal (an empty/ambiguous window)",
                    "Make start and end different times.",
                    "error",
                )
            )
        if (
            not isinstance(w.brightness, int)
            or isinstance(w.brightness, bool)
            or not (0 <= w.brightness <= 100)
        ):
            issues.append(
                ValidationIssue(
                    None,
                    loc,
                    (f"brightness {w.brightness!r} must be an integer 0–100 (0 = off)"),
                    "Set brightness to a whole number from 0 to 100.",
                    "error",
                )
            )
        if isinstance(w.days, list):
            bad_days = [d for d in w.days if d not in _VALID_DAYS]
            if bad_days:
                issues.append(
                    ValidationIssue(
                        rule=None,
                        location=loc,
                        message=f"invalid day name(s) {bad_days!r}",
                        fix=(
                            "Use lowercase 3-letter days: "
                            "mon, tue, wed, thu, fri, sat, sun."
                        ),
                        severity="error",
                    )
                )
        elif w.days:  # present but not a list (e.g. days = "mon")
            issues.append(
                ValidationIssue(
                    rule=None,
                    location=loc,
                    message=f"days must be a list of day names, got {w.days!r}",
                    fix='Use a list, e.g. days = ["mon", "tue"].',
                    severity="error",
                )
            )
    for i in unreachable_window_indices(sched):
        issues.append(
            ValidationIssue(
                rule=None,
                location=f"display.schedule.windows[{i}]",
                message=(
                    "this window can never take effect"
                    " — a later window always covers it (last-wins)"
                ),
                fix="Reorder it after the broader window, or remove it.",
                severity="warning",
            )
        )
    return issues


def _check_held_top_text_overflow(config: AppConfig) -> list[ValidationIssue]:
    """Warn when a held top row is wider than the logical canvas.

    Covers two_row / image-two_row / gif-two_row (static `top_text`).

    The widget renders the top row HELD (no scrolling) and clips silently on
    overflow. Without this check, validation passes clean even though the right
    edge of the held content gets cropped at runtime — typical symptom is "the
    last character of my handle is cut off."

    Bottom rows are exempt: they scroll automatically on overflow, which
    is the documented design.
    """
    from types import SimpleNamespace

    from led_ticker.fonts import FONT_DEFAULT, FONT_SMALL, resolve_font
    from led_ticker.pixel_emoji import measure_width
    from led_ticker.scaled_canvas import ScaledCanvas
    from led_ticker.widgets._row_layout import EMOJI_ROW_CAP, resolve_band_heights

    issues: list[ValidationIssue] = []
    panel_w = _panel_w_real(config.display)
    panel_h = _panel_h_real(config.display)

    for i, section in enumerate(config.sections):
        scale = section.scale
        content_h = section.content_height
        # ScaledCanvas requires content_height × scale ≤ panel_h_real;
        # if the section violates that, _check_static already flags it
        # as rule 1 (error) — skip the width check here to avoid
        # raising on already-known config errors.
        if content_h * scale > panel_h:
            continue
        real = SimpleNamespace(width=panel_w, height=panel_h)
        canvas = ScaledCanvas(real, scale=scale, content_height=content_h)
        canvas_w = canvas.width

        for j, widget_cfg in enumerate(section.widgets):
            wtype = widget_cfg.get("type", "")
            if wtype == "two_row":
                default_font = FONT_SMALL
                top_text = widget_cfg.get("top_text", "")
            elif wtype in ("gif", "image"):
                if widget_cfg.get("bottom_text", "") == "":
                    continue  # single-row mode: top text is the scrolling content
                default_font = FONT_DEFAULT
                top_text = widget_cfg.get("top_text", "")
            else:
                continue

            if not top_text:
                continue

            top_row_height = widget_cfg.get("top_row_height")
            try:
                top_h, _ = resolve_band_heights(content_h, top_row_height)
            except ValueError:
                continue

            shared_font_name = widget_cfg.get("font")
            shared_size = widget_cfg.get("font_size")
            font_name = widget_cfg.get("top_font") or shared_font_name
            font_size = widget_cfg.get("top_font_size") or shared_size
            try:
                font = (
                    default_font
                    if font_name is None
                    else resolve_font(font_name, size=font_size)
                )
            except ValueError:
                continue  # font resolution error caught elsewhere

            emoji_cap = max(EMOJI_ROW_CAP, top_h)
            width = measure_width(font, top_text, canvas, max_emoji_height=emoji_cap)
            if width > canvas_w:
                overflow = width - canvas_w
                message = (
                    f"top_text width ({width} logical px) exceeds the "
                    f"{canvas_w}-wide logical canvas by {overflow} px. "
                    f"The held row will clip its right edge at runtime."
                )
                fix = (
                    "Shorten top_text, drop inline emoji, use a smaller "
                    "top_font_size, or set the section's scale lower "
                    "to widen the logical canvas (scale = 1 gives the "
                    "full panel width)."
                )
                issues.append(
                    ValidationIssue(
                        rule=23,
                        location=f"section[{i}].widget[{j}]",
                        severity="warning",
                        message=message,
                        fix=fix,
                    )
                )
    return issues


def _check_lightbulb_border(config: AppConfig) -> list[ValidationIssue]:
    """Rules 42-49, 51-52: value-range checks for the 'lightbulbs' border style.

    These run BEFORE _coerce_border so users get clear, ruled errors
    instead of ValueError stack traces. Coercion still rejects malformed
    types (e.g. bulb_size as a string); these rules add value-range
    semantics.
    """
    issues: list[ValidationIssue] = []
    panel_h = _panel_h_real(config.display)

    valid_modes = {"chase", "alternate", "unison"}
    valid_directions = {"cw", "ccw"}

    for sec_idx, section in enumerate(config.sections):
        for w_idx, widget_cfg in enumerate(section.widgets):
            border_raw = widget_cfg.get("border")
            # Only inspect inline-table lightbulb borders; shorthand
            # string and other styles are out of scope.
            if not isinstance(border_raw, dict):
                continue
            if border_raw.get("style") != "lightbulbs":
                continue

            loc = f"section[{sec_idx}].widget[{w_idx}].border"
            mode = border_raw.get("mode", "chase")

            # Rule 42: bulb_size must be a positive int (when set).
            bulb_size = border_raw.get("bulb_size")
            if bulb_size is not None:
                if not isinstance(bulb_size, int) or isinstance(bulb_size, bool):
                    issues.append(
                        ValidationIssue(
                            rule=42,
                            location=loc,
                            severity="error",
                            message=(
                                f"bulb_size must be a positive integer; "
                                f"got {type(bulb_size).__name__}"
                            ),
                            fix=(
                                "Set bulb_size to a positive integer, or omit "
                                "it for the panel-size auto-default."
                            ),
                        )
                    )
                elif bulb_size <= 0:
                    issues.append(
                        ValidationIssue(
                            rule=42,
                            location=loc,
                            severity="error",
                            message=(
                                f"bulb_size must be a positive integer; got {bulb_size}"
                            ),
                            fix=(
                                "Set bulb_size to a positive integer, or omit "
                                "it for the panel-size auto-default."
                            ),
                        )
                    )
                else:
                    # Rule 43: bulb_size must fit the panel height.
                    max_bulb = panel_h // 2
                    if bulb_size > max_bulb:
                        issues.append(
                            ValidationIssue(
                                rule=43,
                                location=loc,
                                severity="error",
                                message=(
                                    f"bulb_size={bulb_size} exceeds max={max_bulb} "
                                    f"for a panel of physical height {panel_h}"
                                ),
                                fix=(
                                    f"Reduce bulb_size to ≤ {max_bulb}, or omit it "
                                    f"to use the panel-size auto-default."
                                ),
                            )
                        )

            # Rule 44: mode must be one of {chase, alternate, unison}.
            if mode not in valid_modes:
                issues.append(
                    ValidationIssue(
                        rule=44,
                        location=loc,
                        severity="error",
                        message=(
                            f"mode={mode!r} unknown; expected one of "
                            f"{sorted(valid_modes)}"
                        ),
                        fix=f"Set mode to one of {sorted(valid_modes)}.",
                    )
                )

            # Rule 45: direction (when set) must be 'cw' or 'ccw'.
            direction = border_raw.get("direction")
            if direction is not None and direction not in valid_directions:
                issues.append(
                    ValidationIssue(
                        rule=45,
                        location=loc,
                        severity="error",
                        message=(
                            f"direction={direction!r} unknown; expected 'cw' or 'ccw'"
                        ),
                        fix="Set direction to 'cw' or 'ccw'.",
                    )
                )

            # Rule 46: chase_density (when set) must be ≥ 1.
            chase_density = border_raw.get("chase_density")
            if chase_density is not None and (
                not isinstance(chase_density, int)
                or isinstance(chase_density, bool)
                or chase_density < 1
            ):
                issues.append(
                    ValidationIssue(
                        rule=46,
                        location=loc,
                        severity="error",
                        message=(
                            f"chase_density must be an integer ≥ 1; "
                            f"got {chase_density!r}"
                        ),
                        fix="Set chase_density to a positive integer.",
                    )
                )

            # Rule 47: gap must be ≥ 0 (when set).
            gap = border_raw.get("gap")
            if gap is not None and (
                not isinstance(gap, int) or isinstance(gap, bool) or gap < 0
            ):
                issues.append(
                    ValidationIssue(
                        rule=47,
                        location=loc,
                        severity="error",
                        message=f"gap must be an integer ≥ 0; got {gap!r}",
                        fix=(
                            "Set gap to 0 or a positive integer (bulbs would "
                            "overlap with a negative gap)."
                        ),
                    )
                )

            # Rule 48: chase_density set on non-chase mode is ignored — warn.
            if chase_density is not None and mode in valid_modes and mode != "chase":
                issues.append(
                    ValidationIssue(
                        rule=48,
                        location=loc,
                        severity="warning",
                        message=(
                            f"chase_density is only used by mode='chase'; "
                            f"ignored for mode={mode!r}"
                        ),
                        fix="Remove chase_density, or change mode to 'chase'.",
                    )
                )

            # Rule 49: direction set on non-chase mode is ignored — warn.
            if direction is not None and mode in valid_modes and mode != "chase":
                issues.append(
                    ValidationIssue(
                        rule=49,
                        location=loc,
                        severity="warning",
                        message=(
                            f"direction is only used by mode='chase'; "
                            f"ignored for mode={mode!r}"
                        ),
                        fix="Remove direction, or change mode to 'chase'.",
                    )
                )

            # Rule 51: hue_wraps (when set) must be a positive, finite number.
            # The isfinite guard rejects nan/inf — both are valid TOML floats
            # that would otherwise slip past (`nan <= 0` is False) and crash
            # at render time in hue_color's int() conversion.
            hue_wraps = border_raw.get("hue_wraps")
            if hue_wraps is not None and (
                isinstance(hue_wraps, bool)
                or not isinstance(hue_wraps, int | float)
                or not math.isfinite(hue_wraps)
                or hue_wraps <= 0
            ):
                issues.append(
                    ValidationIssue(
                        rule=51,
                        location=loc,
                        severity="error",
                        message=(
                            f"hue_wraps must be a positive, finite number; "
                            f"got {hue_wraps!r}"
                        ),
                        fix="Set hue_wraps to a positive number (e.g. 1.0 or 2).",
                    )
                )

            # Rule 52: hue_wraps set without lit_color="rainbow" is ignored — warn.
            if hue_wraps is not None and border_raw.get("lit_color") != "rainbow":
                issues.append(
                    ValidationIssue(
                        rule=52,
                        location=loc,
                        severity="warning",
                        message=(
                            'hue_wraps only applies when lit_color = "rainbow"; '
                            "ignored otherwise"
                        ),
                        fix='Set lit_color = "rainbow", or remove hue_wraps.',
                    )
                )

    return issues


def _parse_widget_location(location: str) -> tuple[int, int] | None:
    """Parse 'section[i].widget[j]' → (i, j). Returns None if not a widget location."""
    import re

    m = re.match(r"^section\[(\d+)\]\.widget\[(\d+)\]$", location)
    if m:
        return int(m.group(1)), int(m.group(2))
    return None


def _parse_title_location(location: str) -> int | None:
    """Parse 'section[i].title' → i. Returns None if not a title location."""
    import re

    m = re.match(r"^section\[(\d+)\]\.title$", location)
    return int(m.group(1)) if m else None


def apply_migrations(path: Path, result: ValidationResult) -> int:
    """Apply all auto-fixable migrations from result to the TOML file at path.

    Reads, patches, and rewrites the TOML. Comments are not preserved
    (tomli_w limitation). Returns the number of fixes applied.
    """
    fixable = [
        e
        for e in result.errors
        if e.fix_key
        and e.fix_replacement_key
        and (
            _parse_widget_location(e.location) is not None
            or _parse_title_location(e.location) is not None
        )
    ]
    if not fixable:
        return 0

    raw = path.read_bytes()
    data = tomllib.loads(raw.decode())

    applied = 0
    sections = data.get("playlist", {}).get("section", [])
    for issue in fixable:
        widget_loc = _parse_widget_location(issue.location)
        if widget_loc is not None:
            section_idx, widget_idx = widget_loc
            try:
                widget = sections[section_idx]["widget"][widget_idx]
            except IndexError, KeyError:
                continue
            if issue.fix_key in widget:
                widget[issue.fix_replacement_key] = widget.pop(issue.fix_key)
                applied += 1
            continue

        title_loc = _parse_title_location(issue.location)
        if title_loc is not None:
            try:
                title = sections[title_loc].get("title")
            except IndexError, KeyError:
                continue
            if title and issue.fix_key in title:
                title[issue.fix_replacement_key] = title.pop(issue.fix_key)
                applied += 1

    path.write_bytes(tomli_w.dumps(data).encode())
    return applied


async def validate_config(
    path: Path, *, strict: bool = False, config_dir: Path | None = None
) -> ValidationResult:
    """Validate a TOML config file. Raises FileNotFoundError if path does not exist.

    When ``strict=True``:
    - Asset path existence is checked (rule 40). Paths are allowed to be absent
      in normal mode because assets may only live on the deploy target.
    - All accumulated warnings are promoted to errors before returning.
      ``ValidationResult.warnings`` will be empty; callers check ``result.valid``
      as usual.

    ``config_dir`` overrides the directory used to resolve relative paths
    (fonts, assets, plugin checks). Defaults to ``path.parent`` — pass it when
    the TOML was materialized to a throwaway temp file (the web UI's text
    validate) so resolution anchors to the real config directory.
    """
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    from led_ticker._plugin_loader import load_plugins_for_config

    # A broken-TOML or structural [plugins] error here is re-surfaced below by
    # load_config (Phase 1a) as a clean ValidationResult error, so don't let it
    # escape the validator. (Plugin LOAD failures are already isolated inside
    # load_plugins and recorded in result.failed, not raised.)
    with contextlib.suppress(Exception):
        load_plugins_for_config(path)

    from led_ticker.app import _configure_user_font_dir
    from led_ticker.config import load_config

    errors: list[ValidationIssue] = []
    warnings: list[ValidationIssue] = []

    # Phase 1a: TOML load + structural parse
    try:
        config = load_config(path)
    except Exception as e:
        errors.append(
            ValidationIssue(
                rule=None,
                location="config",
                severity="error",
                message=str(e),
                fix="Fix the TOML syntax or structural error above.",
            )
        )
        return ValidationResult(path=path, errors=errors, warnings=warnings)

    # Phase 1b: [display] backend — must name a registered backend.
    # `from led_ticker.backends import known_backends` triggers the package
    # __init__, which eagerly imports both built-in backends and self-registers
    # them — no separate import statements needed.
    from led_ticker.backends import known_backends  # noqa: PLC0415

    _backend = getattr(config.display, "backend", "rgbmatrix")
    if _backend not in known_backends():
        errors.append(
            ValidationIssue(
                rule=None,
                location="display.backend",
                severity="error",
                message=(
                    f"[display] backend = {_backend!r} is unknown; "
                    f"valid backends: {known_backends()}"
                ),
                fix=(
                    "Set backend to one of the listed values, or omit it "
                    'to use the default ("rgbmatrix").'
                ),
            )
        )

    # Phase 1b: Static dict checks (rules enforced in widget constructors)
    errors.extend(_check_static(config))

    # Phase 1b (cont.): Rule 56 — [[source]] block validation.
    errors.extend(_check_sources(config))

    # Phase 1b (cont.): Rule 39 — transition name registry check.
    # Always runs (not just --strict): a typo in a transition name always
    # fails at startup and has no deploy-target excuse.
    errors.extend(_check_transition_names(config))

    # Phase 1b (cont.): Rule 57 — separator / separator_color / separator_font
    # fields on non-scroll transitions; also resolve separator_font on scroll
    # transition homes (rule-24 warning for unknown, rule-5 error for missing size).
    errors.extend(_check_separator_color_transition(config))
    _scroll_sep_errors, _scroll_sep_warnings = _check_scroll_separator_font(config)
    errors.extend(_scroll_sep_errors)
    warnings.extend(_scroll_sep_warnings)

    # Phase 1b (cont.): Plugin transition kwargs check.
    # For dotted-type (plugin) transitions, attempt to build the transition
    # object to surface unknown/missing kwargs as a clean validation error.
    # Only runs when the name check passed — no point building an unknown type.
    if not any(e.rule == 39 for e in errors):
        errors.extend(_check_plugin_transition_kwargs(config))

    # Phase 1b (cont.): Rules 42-49, 51-52 — lightbulbs border value-range checks.
    # Run before build checks so users see ruled errors rather than
    # ValueError stack traces from _coerce_border.
    for issue in _check_lightbulb_border(config):
        if issue.severity == "warning":
            warnings.append(issue)
        else:
            errors.append(issue)

    # Phase 1c: Build-time checks via validate_widget_cfg.
    # "unknown font" failures are downgraded to warnings (rule 24): the
    # font may live on the deploy target but not the laptop drafting
    # the config. Type / required-field errors stay hard.
    effective_config_dir = config_dir if config_dir is not None else path.parent
    _configure_user_font_dir(effective_config_dir)
    build_errors, build_warnings, migration_errors = await _run_build_checks(
        config.sections, effective_config_dir
    )
    for location, msg, fix, fix_key, fix_replacement_key in migration_errors:
        errors.append(
            ValidationIssue(
                rule=20 if "text_scale" in msg else None,
                location=location,
                severity="error",
                message=msg,
                fix=fix,
                fix_key=fix_key,
                fix_replacement_key=fix_replacement_key,
            )
        )
    for location, msg in build_errors:
        if "unknown font " in msg:
            warnings.append(
                ValidationIssue(
                    rule=24,
                    location=location,
                    severity="warning",
                    message=msg,
                    fix=(
                        "Drop the font file into config/fonts/ on the deploy"
                        " target, or pick one of the bundled fonts listed"
                        " above (BDF: 5x8 / 6x10 / 6x12 / 7x13; hires:"
                        " Inter-Bold / Inter-Regular)."
                    ),
                )
            )
            continue
        rule, fix = _classify_error(msg)
        errors.append(
            ValidationIssue(
                rule=rule,
                location=location,
                severity="error",
                message=msg,
                fix=fix,
            )
        )

    # Rule 37: coerce warnings — widget-level (from _build_widget's pass)
    # and config-load (DisplayConfig + SectionConfig + TransitionConfig).
    # The fix string is derived from the warning at surface time: writing
    # the canonical typed form (`field = <coerced>`) silences the warning.
    def _coerce_fix(w: Any) -> str:
        return f"Set {w.field} to {w.coerced!r} (the canonical typed form)."

    for location, w in build_warnings:
        warnings.append(
            ValidationIssue(
                rule=37,
                location=f"{location}.{w.field}",
                severity="warning",
                message=w.message,
                fix=_coerce_fix(w),
            )
        )
    for w in config._coerce_warnings:
        warnings.append(
            ValidationIssue(
                rule=37,
                location=w.field,
                severity="warning",
                message=w.message,
                fix=_coerce_fix(w),
            )
        )

    # Phase 1c (cont.): separator_font resolution — same warning/error
    # routing as widget fonts above. Runs regardless of build errors so
    # a broken widget doesn't suppress a separator_font warning.
    sep_errors, sep_warnings = _check_separator_fonts(config)
    errors.extend(sep_errors)
    warnings.extend(sep_warnings)

    # Phase 1c (cont.): rule 27 — bottom_text_wrap requires mode=slideshow.
    errors.extend(_check_wraps_slideshow_only(config))

    # Phase 1c (cont.): rule 32 — bottom_text_scroll='scroll_through'
    # requires mode=slideshow (parallel to rule 27).
    errors.extend(_check_scroll_through_slideshow_only(config))

    # Phase 1d: Per-row band-layout checks for two_row / image-two_row.
    # Only meaningful when build succeeded — otherwise the widget might
    # not even have valid fonts to measure. Skipped widgets with a
    # missing font (warning, not error) are handled by the per-widget
    # `except ValueError: continue` inside _check_band_layout.
    if not errors:
        errors.extend(_check_band_layout(config))

    # Phase 2: Soft rule warnings (only run when no hard errors)
    if not errors:
        warnings.extend(_check_soft(config))
        warnings.extend(_check_held_top_text_overflow(config))
        warnings.extend(_check_transition_fps(config))
        warnings.extend(_check_plugin_validation_warnings(config, effective_config_dir))

    # Phase 2 (strict only): asset path existence check.
    # Not in normal mode — asset files may only exist on the deploy target.
    if strict:
        errors.extend(_check_asset_paths(config, effective_config_dir))

    # Schedule validation: timezone, HH:MM times, brightness range, day names,
    # start==end, enabled-with-no-windows (warning), fully-shadowed windows (warning).
    notes: list[str] = []
    _sched_issues = _check_schedule(config)
    errors.extend(i for i in _sched_issues if i.severity == "error")
    warnings.extend(i for i in _sched_issues if i.severity == "warning")
    if config.display.schedule.enabled:
        from led_ticker.schedule import format_schedule_summary

        notes = format_schedule_summary(
            config.display.schedule, config.display.brightness
        )

    # Strict: promote all remaining warnings to errors before returning.
    # ValidationResult.valid checks len(errors) == 0; promoting warnings
    # here means callers don't need to change their result.valid check.
    if strict and warnings:
        errors.extend(warnings)
        warnings = []

    return ValidationResult(path=path, errors=errors, warnings=warnings, notes=notes)


async def validate_config_text(
    text: str, *, strict: bool = False, config_dir: Path | None = None
) -> ValidationResult:
    """Validate TOML config content from a string.

    Same engine as validate_config — the text is materialized to a temp file
    so every path-relative check behaves identically. Used by the web UI's
    POST /api/validate; also handy for tests.

    Pass ``config_dir`` to anchor relative-path resolution (fonts/assets) at
    the real config directory rather than the temp dir.

    Broken TOML is returned as an invalid ValidationResult (not raised),
    matching validate_config's behaviour — callers check result.valid.
    """
    with tempfile.TemporaryDirectory(prefix="led-ticker-validate-") as td:
        p = Path(td) / "config.toml"
        p.write_text(text, encoding="utf-8")
        return await validate_config(p, strict=strict, config_dir=config_dir)


def _issue_to_dict(issue: ValidationIssue) -> dict[str, Any]:
    return {
        "rule": issue.rule,
        "location": issue.location,
        "message": issue.message,
        "fix": issue.fix,
    }


def _format_json(result: ValidationResult) -> str:
    return json.dumps(
        {
            "valid": result.valid,
            "path": str(result.path),
            "errors": [_issue_to_dict(e) for e in result.errors],
            "warnings": [_issue_to_dict(w) for w in result.warnings],
        },
        indent=2,
    )


def _format_human(result: ValidationResult) -> str:
    lines = [f"Validating {result.path}...", ""]
    for issue in result.errors:
        lines.append(f"✗ ERROR   {issue.location}: {issue.message}")
        lines.append(f"          Fix: {issue.fix}")
        lines.append("")
    for issue in result.warnings:
        lines.append(f"⚠ WARNING {issue.location}: {issue.message}")
        lines.append(f"          Fix: {issue.fix}")
        lines.append("")
    n = len(result.errors) + len(result.warnings)
    coerce_count = sum(1 for w in result.warnings if w.rule == 37)
    if n == 0:
        lines.append("No issues found.")
    else:
        lines.append(
            f"{n} issue(s):"
            f" {len(result.errors)} error(s),"
            f" {len(result.warnings)} warning(s)"
        )
        if coerce_count:
            lines.append(
                f"  {coerce_count} coercion warning(s)"
                " — update your config to silence these."
            )
    return "\n".join(lines)
