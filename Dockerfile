# Base image migration note (M14):
# python:3.13-bullseye (Debian 11) reaches EOL June 2026. Migrate to
# python:3.13-bookworm (Debian 12, GCC 12) when ready. Before migrating:
#   1. Verify the RP1 build patch (named anonymous PIO params in pio_rp1.c)
#      still compiles cleanly under GCC 12 — it was written for GCC 10.
#   2. Test a multi-stage build: copy only the compiled rgbmatrix .so from
#      the build stage into a python:3.13-bookworm-slim final stage (~200MB
#      smaller). Verify libstdc++/libgcc links are satisfied by the slim image.
#   3. Run make test + test on both Pi 4 and Pi 5 hardware before merging.
FROM python:3.13-bullseye AS rgbmatrix

# rpi-rgb-led-matrix: jamesawesome/main — Pi5 RP1 support (hzeller#1886, now
# merged upstream) plus three patches: GCC10 anonymous-param fix (pio_rp1.c),
# Pillow shim (graphics.py), SubFill Python binding (core.pyx). Validated
# 2026-04-29 to run on both Pi 4 (BCM2711 GPIO) and Pi 5 (RP1 PIO/RIO).

ENV DEBIAN_FRONTEND=noninteractive

WORKDIR /code

RUN apt-get update && \
    apt-get install -y build-essential git python3-dev cmake && \
    rm -rf /var/lib/apt/lists/*

# Layer 1: rgbmatrix (only rebuilds if the pinned ref changes)
# Increment RGBMATRIX_CACHE_BUST to force a fresh clone when the fork's main
# branch changes but the clone instruction text hasn't — Docker caches by
# instruction hash, not by remote content.
ARG RGBMATRIX_CACHE_BUST=2
RUN cd /opt && \
    git clone --depth=1 --branch main \
        https://github.com/jamesawesome/rpi-rgb-led-matrix.git rgbmatrix-src && \
    cd rgbmatrix-src && \
    pip install .

# Layer 2: app dependencies (only rebuilds if pyproject.toml changes)
FROM rgbmatrix
WORKDIR /code
COPY pyproject.toml /code/
RUN pip install --no-cache-dir -e ".[dev]"

# Layer 3: app source (rebuilds on any code change — but fast, no pip)
COPY . /code/
RUN pip install --no-deps .

CMD ["led-ticker", "--config", "/code/config/config.toml"]
