"""led-ticker: Asyncio LED matrix display for news, weather, crypto, and more."""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version

try:
    # Set by hatch-vcs at install/build time (source = "vcs").
    __version__ = _pkg_version("led-ticker-core")
except PackageNotFoundError:  # not installed (raw source tree)
    __version__ = "0.0.0+unknown"
