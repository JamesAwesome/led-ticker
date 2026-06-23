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
# As of June 2026 the library defaults the Pi 5 backend to RP1 RIO; the
# backend-selection option is now rp1_pio (1 = force PIO; renamed from
# rp1_rio, which had the inverse meaning).

ENV DEBIAN_FRONTEND=noninteractive

WORKDIR /code

RUN apt-get update && \
    apt-get install -y build-essential git cmake && \
    rm -rf /var/lib/apt/lists/*

# Layer 1: rgbmatrix (only rebuilds if the pinned ref changes)
# Increment RGBMATRIX_CACHE_BUST to force a fresh clone when the fork's main
# branch changes but the clone instruction text hasn't — Docker caches by
# instruction hash, not by remote content.
ARG RGBMATRIX_CACHE_BUST=4
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

# Layer 2: app dependencies (only rebuilds if pyproject.toml changes). After
# installing, snapshot the exact installed versions into a pip constraints file
# (constraints-core.txt) so runtime plugin installs can pull their own new
# deps but cannot move core's stack. `pip list --format=freeze` renders the
# editable led-ticker as `led-ticker==<v>` (a valid constraint), unlike
# `pip freeze` which emits an unusable `-e ...` line.
FROM rgbmatrix
WORKDIR /code
# pyproject now declares readme + license-files (PEP 639), which hatchling reads
# at install/metadata time — copy README.md + LICENSE alongside pyproject so the
# editable install in this deps-only layer doesn't fail on the missing files.
COPY pyproject.toml README.md LICENSE /code/
RUN pip install --no-cache-dir -e ".[dev]" \
 && pip list --format=freeze > /code/constraints-core.txt

# Plugins are NOT baked — they install at runtime onto the ticker-plugins volume (see plugin_reconcile.py).

# Layer 3: app source (rebuilds on any code change — but fast, no pip)
COPY . /code/
RUN pip install --no-deps .

CMD ["led-ticker", "--config", "/code/config/config.toml"]
