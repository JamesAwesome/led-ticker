"""Build identity baked into the image at build time.

The Dockerfile sets `ENV LED_TICKER_BUILD_REF` from the `BUILD_REF` build arg
(see `make build-docker` / `compose.yaml`). The container has no git at runtime,
so this is the only source of "what commit is deployed". Default `"unknown"`
means the image was not built via a stamping build path.
"""

import os


def build_ref() -> str:
    return os.environ.get("LED_TICKER_BUILD_REF", "unknown")
