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
    for i, section in enumerate(config.sections):
        for j, widget_cfg in enumerate(section.widgets):
            loc = f"section[{i}].widget[{j}]"
            wtype = widget_cfg.get("type", "")

            # Rule 3: scroll + stretch
            if (
                widget_cfg.get("text_align")
                in (
                    "scroll",
                    "scroll_over",
                )
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
                            "Change fit to 'pillarbox', 'letterbox', or 'crop';"
                            " or change text_align to 'left'/'right'"
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


def _check_soft(config: AppConfig) -> list[ValidationIssue]:
    warnings: list[ValidationIssue] = []
    ph = _panel_h_real(config.display)

    for i, section in enumerate(config.sections):
        # Rule 1: content_height overflow
        product = section.content_height * section.scale
        if product > ph:
            warnings.append(
                ValidationIssue(
                    rule=1,
                    location=f"section[{i}]",
                    severity="warning",
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

    # Phase 1c: Build-time checks via _build_widget(validate_only=True)
    _configure_user_font_dir(path)
    build_errors = await _run_build_checks(config.sections, path.parent)
    for location, msg in build_errors:
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

    # Phase 1d: Per-row band-layout checks for two_row / image-two_row.
    # Only meaningful when build succeeded — otherwise the widget might
    # not even have valid fonts to measure.
    if not errors:
        errors.extend(_check_band_layout(config))

    # Phase 2: Soft rule warnings (only run when no hard errors)
    if not errors:
        warnings.extend(_check_soft(config))

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
