# Base: python:3.14-bookworm (Debian 12, GCC 12). Migrated from
# python:3.13-bullseye (Debian 11, EOL June 2026) together with the 3.13->3.14
# Python bump. The rgbmatrix fork compiles cleanly here against the image's
# Python 3.14 headers with Cython >= 3.2.5 (verified by the Phase 0 arm64 spike).
# The GCC10 anonymous-param patch in pio_rp1.c compiles under GCC 12.
# Future optimization (deferred): multi-stage build copying only the compiled
# rgbmatrix .so into python:3.14-slim-bookworm (~200MB smaller).
FROM python:3.14-bookworm AS rgbmatrix

# rpi-rgb-led-matrix: jamesawesome/main — Pi5 RP1 support (hzeller#1886, now
# merged upstream) plus three patches: GCC10 anonymous-param fix (pio_rp1.c),
# Pillow shim (graphics.py), SubFill Python binding (core.pyx). Validated
# 2026-04-29 to run on both Pi 4 (BCM2711 GPIO) and Pi 5 (RP1 PIO/RIO).

ENV DEBIAN_FRONTEND=noninteractive

WORKDIR /code

RUN apt-get update && \
    apt-get install -y build-essential git cmake && \
    rm -rf /var/lib/apt/lists/*

# Layer 1: rgbmatrix (only rebuilds if the pinned ref changes)
# Increment RGBMATRIX_CACHE_BUST to force a fresh clone when the fork's main
# branch changes but the clone instruction text hasn't — Docker caches by
# instruction hash, not by remote content.
ARG RGBMATRIX_CACHE_BUST=3
# The fork builds via scikit-build-core (PEP 517), so `pip install .` runs in an
# isolated build env that resolves its own Cython. A plain `pip install Cython`
# here would NOT control that build. PIP_CONSTRAINT is inherited by the isolated
# build-env pip, so it enforces the Cython>=3.2.5 floor (required for Python 3.14
# C-API support) where it actually matters.
RUN cd /opt && \
    git clone --depth=1 --branch main \
        https://github.com/jamesawesome/rpi-rgb-led-matrix.git rgbmatrix-src && \
    cd rgbmatrix-src && \
    printf 'Cython>=3.2.5\n' > /tmp/build-constraints.txt && \
    PIP_CONSTRAINT=/tmp/build-constraints.txt pip install .

# Layer 2: app dependencies (only rebuilds if pyproject.toml changes)
FROM rgbmatrix
WORKDIR /code
COPY pyproject.toml /code/
RUN pip install --no-cache-dir -e ".[dev]"

# Layer 2b: external plugins (led_ticker.plugins entry points auto-register at
# startup). Installed --no-deps on purpose: led-ticker is not on PyPI (it's the
# editable install above) and the plugins' runtime deps (aiohttp) are already
# present as app dependencies, so dependency resolution would only fail trying
# to fetch led-ticker from PyPI. Bump POOL_PLUGIN_CACHE_BUST to pull a newer
# plugin revision (Docker caches by instruction text, not remote content).
ARG POOL_PLUGIN_CACHE_BUST=1
RUN pip install --no-cache-dir --no-deps \
    "git+https://github.com/JamesAwesome/led-ticker-pool.git@main"

# Layer 3: app source (rebuilds on any code change — but fast, no pip)
COPY . /code/
RUN pip install --no-deps .

CMD ["led-ticker", "--config", "/code/config/config.toml"]
