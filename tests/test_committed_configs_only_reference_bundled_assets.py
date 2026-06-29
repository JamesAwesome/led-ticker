"""
Tripwire: every active `path = "assets/<x>"` reference in committed config/*.toml
must point at a file that exists under config/assets/. Operator media belongs in
config/local/ (gitignored), not in a committed config.
"""

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CONFIG_DIR = REPO / "config"
ASSETS_DIR = CONFIG_DIR / "assets"

# Match active (non-comment) lines containing `path = "assets/<something>"`.
# The group captures the relative filename after "assets/".
_ASSET_PATH_RE = re.compile(r'^[^#]*\bpath\s*=\s*"assets/([^"]+)"')


def _committed_toml_files() -> list[Path]:
    """Return all *.toml files directly under config/ (not in subdirs)."""
    return sorted(CONFIG_DIR.glob("*.toml"))


def test_committed_configs_only_reference_bundled_assets():
    """
    Every active `path = "assets/<file>"` line in a committed config must resolve
    to a file that exists in config/assets/. This catches accidental references to
    operator/private media that belongs under config/local/ instead.
    """
    violations: list[str] = []

    for toml_path in _committed_toml_files():
        for lineno, line in enumerate(toml_path.read_text().splitlines(), start=1):
            m = _ASSET_PATH_RE.match(line)
            if m:
                asset_file = m.group(1)
                if not (ASSETS_DIR / asset_file).exists():
                    violations.append(
                        f"{toml_path.relative_to(REPO)}:{lineno}: "
                        f'path = "assets/{asset_file}" — not in config/assets/. '
                        f"Operator media belongs in config/local/ (gitignored)."
                    )

    assert not violations, (
        "Committed config(s) reference non-bundled assets:\n" + "\n".join(violations)
    )
