"""Tripwire: no legacy section-mode names survive in the live tree.

Phase 1 of the modes rename renamed:
  swap        -> slideshow
  forever_scroll -> ticker
  infini_scroll  -> one_at_a_time

Phase 2 swept the docs, demos, and content-source to use the new names.
This test ensures no new occurrence of the old mode names sneaks in.

Allowlisted survivors (intentional):
  - src/led_ticker/config.py      : _MODE_RENAMES migration map
  - tests/test_config.py          : TestModeMigration parametrize inputs
  - tests/test_validate.py        : legacy-name docstring / comment
  - tests/test_no_legacy_mode_names.py : this file (contains the patterns)
  - docs/superpowers/             : archived plans; old names are historical refs

The grep covers:
  - mode value patterns: mode = "swap", forever_scroll, infini_scroll
  - Any bare occurrence of forever_scroll / infini_scroll
  - Prose/backtick form: `swap`, `forever_scroll`, `infini_scroll` in docs
    (docs-only pattern so Python string literals like n.func.attr == "swap"
     and test-recording strings like order.append("swap") are not flagged)
  - Excluded from the check: the allowlisted files above and docs/superpowers/
"""

import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]

# Files that may legitimately contain old mode names.
_ALLOWLIST = frozenset(
    [
        "src/led_ticker/config.py",  # _MODE_RENAMES migration map
        "src/led_ticker/validate.py",  # user-facing migration error message text
        "tests/test_config.py",  # TestModeMigration parametrize inputs
        "tests/test_validate.py",  # docstring / comment mentioning old names
        # this file (contains the patterns as literal strings):
        "tests/test_no_legacy_mode_names.py",
    ]
)

# Directory prefixes (relative to _REPO_ROOT) to exclude entirely.
# These are not live content and legitimately reference old names for context.
_EXCLUDED_DIR_PREFIXES: tuple[str, ...] = (
    # archived plans — old names are historical refs, not live config:
    "docs/superpowers",
    # agent task reports — historical records, not live content:
    ".superpowers",
    # build output; regenerated from live sources already checked:
    "docs/site/dist",
    # third-party npm packages bundled with the docs site:
    "docs/site/node_modules",
    ".git",
)

# Patterns applied to ALL text files.
_PATTERNS = [
    # mode value as a TOML assignment — catches both quote styles (valid TOML)
    re.compile(r"""mode\s*=\s*['"]swap['"]"""),
    # the old mode names as bare identifiers or in prose
    re.compile(r"\bforever_scroll\b"),
    re.compile(r"\binfini_scroll\b"),
]

# Patterns applied ONLY to docs/markdown files (.md, .mdx).
# Catches prose leaks like `swap` mode / `forever_scroll` / `infini_scroll`
# written as backtick-quoted or double-quoted mode names.
# Scoped to docs to avoid false-positives from Python string literals that
# legitimately contain "swap" as a method/attribute name (e.g.
# n.func.attr == "swap" in AST tests, order.append("swap") in frame tests).
_DOCS_PATTERNS = [
    re.compile(r'[`"](swap|forever_scroll|infini_scroll)[`"]'),
]

# File suffixes that are prose/docs (eligible for _DOCS_PATTERNS).
_DOCS_SUFFIXES = frozenset({".md", ".mdx"})


def _all_text_files() -> list[Path]:
    """Return all text source files under _REPO_ROOT, excluding excluded dirs."""
    results: list[Path] = []
    for path in _REPO_ROOT.rglob("*"):
        if not path.is_file():
            continue
        # Skip excluded dir trees (match by relative path prefix)
        rel_str = str(path.relative_to(_REPO_ROOT))
        if any(
            rel_str == prefix or rel_str.startswith(prefix + "/")
            for prefix in _EXCLUDED_DIR_PREFIXES
        ):
            continue
        # Only scan text-like files
        suffix = path.suffix.lower()
        if suffix not in {
            ".py",
            ".toml",
            ".md",
            ".mdx",
            ".ts",
            ".tsx",
            ".js",
            ".json",
            ".yaml",
            ".yml",
            ".txt",
            ".sh",
            ".env",
        }:
            continue
        results.append(path)
    return results


def _is_allowlisted(path: Path) -> bool:
    rel = str(path.relative_to(_REPO_ROOT))
    return rel in _ALLOWLIST


def test_no_legacy_mode_names_in_live_tree():
    """No old mode names survive in the live source tree."""
    violations: list[str] = []

    for path in _all_text_files():
        if _is_allowlisted(path):
            continue

        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue

        is_docs = path.suffix.lower() in _DOCS_SUFFIXES
        patterns = _PATTERNS + (_DOCS_PATTERNS if is_docs else [])

        for lineno, line in enumerate(text.splitlines(), start=1):
            for pattern in patterns:
                if pattern.search(line):
                    rel = str(path.relative_to(_REPO_ROOT))
                    violations.append(f"  {rel}:{lineno}: {line.strip()}")
                    break  # one violation per line is enough

    if violations:
        joined = "\n".join(violations[:40])
        count = len(violations)
        truncated = f" (showing first 40 of {count})" if count > 40 else ""
        raise AssertionError(
            f"Legacy mode name(s) found in {count} location(s){truncated}.\n"
            f"Rename: swap→slideshow, forever_scroll→ticker, "
            f"infini_scroll→one_at_a_time\n\n"
            f"Violations:\n{joined}\n\n"
            f"If this is intentional (e.g. a new migration hint), add the file "
            f"to _ALLOWLIST in tests/test_no_legacy_mode_names.py."
        )
