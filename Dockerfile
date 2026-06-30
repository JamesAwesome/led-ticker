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

# Layer 2: app dependencies (only rebuilds if pyproject.toml changes). The
# constraints-core.txt snapshot (so runtime plugin installs can pull their own
# new deps but cannot move core's stack) is generated AFTER the source install
# below — at this layer led-ticker-core has only the 0.0.0 scm fallback (no .git
# yet), which must not leak into the constraints. `pip list --format=freeze`
# renders core as `led-ticker-core==<v>` (a valid constraint), unlike `pip
# freeze` which emits an unusable `-e ...` line.
FROM rgbmatrix
WORKDIR /code
# pyproject now declares readme + license-files (PEP 639), which hatchling reads
# at install/metadata time — copy README.md + LICENSE alongside pyproject so the
# editable install in this deps-only layer doesn't fail on the missing files.
COPY pyproject.toml README.md LICENSE /code/
RUN pip install --no-cache-dir -e ".[dev]"

# Plugins are NOT baked — they install at runtime onto the ticker-plugins volume (see plugin_reconcile.py).

# Layer 3: app source (rebuilds on any code change — but fast, no pip)
COPY . /code/
# Version for the in-image build: the container has no .git, so the host
# computes the hatch-vcs version and passes it (setuptools-scm reads this env
# and skips git). See Makefile/compose. Empty -> scm fallback (bare dev build).
# Use the GLOBAL setuptools-scm var, NOT the per-dist
# SETUPTOOLS_SCM_PRETEND_VERSION_FOR_LED_TICKER_CORE — hatch-vcs does not pass a
# dist name to setuptools-scm, so the _FOR_<name> variant never matches and the
# build silently falls back to 0.0.0 (verified 2026-06-30). Scope it to the RUN
# (not a persistent ENV) so the pretend version can't leak into runtime plugin
# installs on the volume.
ARG SETUPTOOLS_SCM_PRETEND_VERSION=
# Install core at its real version (PRETEND scoped to this RUN), THEN snapshot the
# constraints — so constraints-core.txt records led-ticker-core at the real
# version, not the 0.0.0 fallback the deps layer would have (it had no version).
RUN SETUPTOOLS_SCM_PRETEND_VERSION="$SETUPTOOLS_SCM_PRETEND_VERSION" pip install --no-deps . \
 && CORE_VER="$(pip show led-ticker-core | awk '/^Version:/{print $2}')" \
 && if [ "$CORE_VER" = "0.0.0" ]; then \
        echo "ERROR: led-ticker-core built as 0.0.0 — no version was passed to the build." >&2; \
        echo "Deploy with 'make setup' (first time) or 'make update' (subsequent); they compute it." >&2; \
        exit 1; \
    fi \
 && pip list --format=freeze > /code/constraints-core.txt

# Build stamp — branch@shortsha, computed on the host by `make build` /
# `make update` and passed as BUILD_REF. A bare `docker compose build` (no arg)
# leaves it empty and the header shows "unknown" — deploy with `make update` to
# stamp the commit. Placed last so it invalidates only this tiny layer.
ARG BUILD_REF=
ENV LED_TICKER_BUILD_REF=$BUILD_REF
LABEL org.opencontainers.image.revision=$BUILD_REF

CMD ["led-ticker", "--config", "/code/config/config.toml"]
