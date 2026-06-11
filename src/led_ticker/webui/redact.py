"""Sensitive-value redaction for the config view.

Key-NAME based, value-blind: any key whose name contains a sensitive word has
its value replaced. Works on raw TOML text (preserves comments/formatting) and
inside inline tables. Over-redaction (e.g. ``monkey``) is accepted — the safe
direction for a read-only UI.

The key match is anchored to line-starts or inline-table delimiters ({, ,) so
that a sensitive word appearing INSIDE a quoted value (e.g.
``note = "set token = abc"`` ) does not corrupt the surrounding text.
"""

import re

REDACTED = '"•••"'

# Key must start at: beginning of line, or after { or , (inline-table context),
# with optional surrounding whitespace.  This prevents matching `token` inside a
# quoted string value like ``note = "set token = abc here"``.
_KV = re.compile(
    r"""(?P<prefix>^|(?<=[{,])\s*)
        (?P<key>[A-Za-z0-9_.-]*(?:token|key|secret|password|webhook)[A-Za-z0-9_.-]*)
        (?P<eq>\s*=\s*)
        (?P<val>"[^"]*"|'[^']*'|\[[^\]]*\]|[^,}\s#]+)""",
    re.IGNORECASE | re.VERBOSE | re.MULTILINE,
)


def redact_toml(text: str) -> str:
    """Replace values of sensitive-named keys with a redaction marker."""
    return _KV.sub(
        lambda m: m.group("prefix") + m.group("key") + m.group("eq") + REDACTED,
        text,
    )
