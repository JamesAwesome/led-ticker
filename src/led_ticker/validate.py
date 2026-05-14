"""Config file validator for led-ticker."""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from led_ticker.config import AppConfig, DisplayConfig, SectionConfig


@dataclass
class ValidationIssue:
    rule: int | None
    location: str
    message: str
    fix: str
    severity: Literal["error", "warning"]


@dataclass
class ValidationResult:
    path: Path
    errors: list[ValidationIssue] = field(default_factory=list)
    warnings: list[ValidationIssue] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return len(self.errors) == 0


# Maps substrings in exception messages to (rule, fix) pairs.
_ERROR_PATTERNS: list[tuple[str, int | None, str]] = [
    (
        "text_scale removed",
        20,
        (
            "Replace text_scale with font_size = N × cell_h"
            " (e.g. font_size=24 for 6×12 BDF at 2×)"
        ),
    ),
    (
        "presentation removed",
        None,
        "Use font_color / animation instead of presentation",
    ),
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
]


def _classify_error(msg: str) -> tuple[int | None, str]:
    for pattern, rule, fix in _ERROR_PATTERNS:
        if pattern in msg:
            return rule, fix
    return None, "See error message for details."


async def _run_build_checks(
    sections: list[SectionConfig], config_dir: Path
) -> list[tuple[str, str]]:
    """Run _build_widget(validate_only=True) for every widget.

    Returns (location, error_msg) pairs.
    """
    from led_ticker.app import _build_widget

    issues: list[tuple[str, str]] = []
    for i, section in enumerate(sections):
        for j, widget_cfg in enumerate(section.widgets):
            try:
                await _build_widget(
                    copy.deepcopy(widget_cfg),
                    session=None,  # type: ignore[arg-type]
                    config_dir=config_dir,
                    validate_only=True,
                )
            except Exception as e:
                issues.append((f"section[{i}].widget[{j}]", str(e)))
    return issues


def _check_static(config: AppConfig) -> list[ValidationIssue]:
    """Synchronous checks on raw widget dicts for errors not caught by _build_widget."""
    issues: list[ValidationIssue] = []
    ph = _panel_h_real(config.display)
    for i, section in enumerate(config.sections):
        # Rule 1: content_height × scale ceiling.
        # content_height × scale > panel_h_real causes the ScaledCanvas
        # wrapper's _y_offset to go negative, silently clipping top and
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
        # (forever_scroll / infini_scroll), which are the only modes
        # that call _scroll_and_delay. Setting it on swap / gif has
        # no runtime effect — surface as an error so users don't think
        # they're tuning something they're not.
        if section.start_hold is not None:
            if section.mode in ("swap", "gif"):
                issues.append(
                    ValidationIssue(
                        rule=25,
                        location=f"section[{i}]",
                        severity="error",
                        message=(
                            f"start_hold has no effect on mode={section.mode!r};"
                            " only forever_scroll / infini_scroll honor it."
                        ),
                        fix=(
                            "Remove start_hold. For swap mode, use hold_time"
                            " (per-widget hold). For gif mode, the gif's own"
                            " duration controls timing."
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

        # Rule 26: separator_* fields are only honored by forever_scroll.
        # On swap / gif / infini_scroll, the engine doesn't intersperse a
        # buffer message, so the fields would silently do nothing. Reject
        # so the misconfiguration surfaces. Single error per section even
        # if multiple separator_* fields are set.
        separator_set = (
            section.separator is not None
            or section.separator_font is not None
            or section.separator_font_size is not None
            or section.separator_color is not None
        )
        if separator_set and section.mode != "forever_scroll":
            issues.append(
                ValidationIssue(
                    rule=26,
                    location=f"section[{i}]",
                    severity="error",
                    message=(
                        f"separator_* fields have no effect on"
                        f" mode={section.mode!r};"
                        " only forever_scroll inserts a separator between loops."
                    ),
                    fix=(
                        "Remove separator / separator_font / separator_font_size"
                        " / separator_color, or change mode to 'forever_scroll'."
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

            # Rule 8: hold_seconds < 0.05
            hold_s = widget_cfg.get("hold_seconds")
            if hold_s is not None and float(hold_s) < 0.05:
                issues.append(
                    ValidationIssue(
                        rule=8,
                        location=loc,
                        severity="error",
                        message=(
                            f"hold_seconds={hold_s} is too short"
                            " (< 50 ms), likely a typo"
                        ),
                        fix="Raise hold_seconds to at least 0.05 (50 ms)",
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
                elif isinstance(btl, int) and btl > 0 and not btw:
                    issues.append(
                        ValidationIssue(
                            rule=28,
                            location=loc,
                            severity="error",
                            message=(
                                f"bottom_text_loops={btl} requires "
                                f"bottom_text_wrap=true. Without wrap, the "
                                f"bottom row scrolls once over its "
                                f"overflow — there's no cycle to count."
                            ),
                            fix=(
                                "Set bottom_text_wrap = true alongside "
                                "bottom_text_loops, or drop bottom_text_loops."
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
    if display.pixel_mapper.startswith("Remap:"):
        # "Remap:256,64|..." — second number is total canvas height
        remap = display.pixel_mapper[6:]
        dims = remap.split("|")[0]
        return int(dims.split(",")[1])
    return display.rows * display.parallel


def _panel_w_real(display: DisplayConfig) -> int:
    """Best-effort panel width in real pixels."""
    if display.pixel_mapper.startswith("Remap:"):
        # "Remap:256,64|..." — first number is total canvas width
        remap = display.pixel_mapper[6:]
        dims = remap.split("|")[0]
        return int(dims.split(",")[0])
    return display.cols * display.chain


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
    # SCOPED TO `two_row` ONLY: gif/image widgets in two-row mode
    # also have a `text_loops` field, but on those widgets `play()`
    # owns its own timing loop — `hold_time` from the section is
    # NOT passed through to `_play_widget`. The two values can't
    # interact there, so a warning would be misleading.
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
            except ValueError:
                # Caught separately by _run_build_checks; don't double-report.
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
    """Resolve any `separator_font` set on forever_scroll sections.

    Returns (errors, warnings). UnknownFontError → rule 24 warning
    (consistent with widget-font behavior). Other ValueError (e.g.
    "requires font_size") → rule 5 error.
    """
    from led_ticker.fonts import UnknownFontError, resolve_font

    errors: list[ValidationIssue] = []
    warnings: list[ValidationIssue] = []
    for i, section in enumerate(config.sections):
        if section.mode != "forever_scroll":
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


def _check_wraps_forever_swap_only(
    config: AppConfig,
) -> list[ValidationIssue]:
    """Rule 27: bottom_text_wrap=True is only valid in mode='swap'.

    In forever_scroll and infini_scroll modes, widgets must terminate
    naturally (the section advances based on widget completion).
    A wraps_forever widget never terminates on cursor_pos — it would
    block the chain. Catch at config-load with a clear error.
    """
    errors: list[ValidationIssue] = []
    for i, section in enumerate(config.sections):
        if section.mode == "swap":
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
                            f"mode='swap'; got mode={section.mode!r}. "
                            f"Other modes expect widgets to terminate "
                            f"naturally — a wrapping widget would block "
                            f"the chain."
                        ),
                        fix=(
                            "Either change the section mode to 'swap' "
                            "(time-bounded by hold_time), or drop "
                            "bottom_text_wrap from the widget. The "
                            "default off-right→off-left marquee works "
                            "in any mode."
                        ),
                    )
                )
    return errors


def _check_held_top_text_overflow(config: AppConfig) -> list[ValidationIssue]:
    """Warn when held top_text on a two_row / image-two_row / gif-two_row
    widget is wider than the logical canvas.

    The widget renders top_text as a HELD row (no scrolling) and clips
    silently on overflow. Without this check, validation passes clean
    even though the right edge of the held content gets cropped at
    runtime — typical symptom is "the last character of my handle is
    cut off."

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
        # if the section violates that, _check_soft already flags it as
        # rule 1 — skip the width check here to avoid raising on
        # already-known config errors.
        if content_h * scale > panel_h:
            continue
        real = SimpleNamespace(width=panel_w, height=panel_h)
        canvas = ScaledCanvas(real, scale=scale, content_height=content_h)
        canvas_w = canvas.width

        for j, widget_cfg in enumerate(section.widgets):
            wtype = widget_cfg.get("type", "")
            if wtype == "two_row":
                default_font = FONT_SMALL
            elif wtype in ("gif", "image"):
                if widget_cfg.get("bottom_text", "") == "":
                    continue  # single-row mode: top text is the scrolling content
                default_font = FONT_DEFAULT
            else:
                continue

            top_text = widget_cfg.get("top_text", "")
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
                issues.append(
                    ValidationIssue(
                        rule=23,
                        location=f"section[{i}].widget[{j}]",
                        severity="warning",
                        message=(
                            f"top_text width ({width} logical px) exceeds the "
                            f"{canvas_w}-wide logical canvas by {overflow} px. "
                            f"The held row will clip its right edge at runtime."
                        ),
                        fix=(
                            "Shorten top_text, drop inline emoji, use a smaller "
                            "top_font_size, or set the section's scale lower "
                            "to widen the logical canvas (scale = 1 gives the "
                            "full panel width)."
                        ),
                    )
                )
    return issues


async def validate_config(path: Path) -> ValidationResult:
    """Validate a TOML config file. Raises FileNotFoundError if path does not exist."""
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

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

    # Phase 1b: Static dict checks (rules enforced in widget constructors)
    errors.extend(_check_static(config))

    # Phase 1c: Build-time checks via _build_widget(validate_only=True).
    # "unknown font" failures are downgraded to warnings (rule 24): the
    # font may live on the deploy target but not the laptop drafting
    # the config. Type / required-field errors stay hard.
    _configure_user_font_dir(path)
    build_errors = await _run_build_checks(config.sections, path.parent)
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

    # Phase 1c (cont.): separator_font resolution — same warning/error
    # routing as widget fonts above. Runs regardless of build errors so
    # a broken widget doesn't suppress a separator_font warning.
    sep_errors, sep_warnings = _check_separator_fonts(config)
    errors.extend(sep_errors)
    warnings.extend(sep_warnings)

    # Phase 1c (cont.): rule 27 — bottom_text_wrap requires mode=swap.
    errors.extend(_check_wraps_forever_swap_only(config))

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

    return ValidationResult(path=path, errors=errors, warnings=warnings)


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
    if n == 0:
        lines.append("No issues found.")
    else:
        lines.append(
            f"{n} issue(s):"
            f" {len(result.errors)} error(s),"
            f" {len(result.warnings)} warning(s)"
        )
    return "\n".join(lines)
