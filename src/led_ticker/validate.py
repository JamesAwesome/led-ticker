"""Config file validator for led-ticker."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from led_ticker.config import AppConfig, SectionConfig


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


def _check_soft(config: AppConfig) -> list[ValidationIssue]:
    return []


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

    # Phase 2: Soft rule warnings (only run when no hard errors)
    if not errors:
        warnings.extend(_check_soft(config))

    return ValidationResult(path=path, errors=errors, warnings=warnings)


def main() -> None:
    raise NotImplementedError
