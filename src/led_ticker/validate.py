"""Config file validator for led-ticker."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


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


def validate_config(path: Path) -> ValidationResult:
    """Validate a TOML config file. Raises FileNotFoundError if path does not exist."""
    raise NotImplementedError


def main() -> None:
    raise NotImplementedError
