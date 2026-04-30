FROM python:3.13-bullseye AS rgbmatrix

# rpi-rgb-led-matrix: jamesawesome/pi5_support — based on kingdo9's pi5_support
# (upstream PR hzeller#1886) with our build patch (named the unused PIO param in
# pio_rp1.c so it builds under bullseye GCC 10). Validated 2026-04-29 to run on
# both the Pi 4 sign and the Pi 5 bigsign — runtime detects the SoC and selects
# the BCM2711 GPIO path or the RP1 PIO path. Once #1886 merges, switch to
# hzeller/master.

ENV DEBIAN_FRONTEND=noninteractive

WORKDIR /code

RUN apt-get update && \
    apt-get install -y build-essential git python3-dev cmake && \
    rm -rf /var/lib/apt/lists/*

# Layer 1: rgbmatrix (only rebuilds if the pinned ref changes)
RUN cd /opt && \
    git clone --depth=1 --branch pi5_support \
        https://github.com/jamesawesome/rpi-rgb-led-matrix.git rgbmatrix-src && \
    cd rgbmatrix-src && \
    pip install .

# Layer 2: app dependencies (only rebuilds if pyproject.toml changes)
FROM rgbmatrix
WORKDIR /code
COPY pyproject.toml /code/
RUN pip install --no-cache-dir -e ".[dev]" 2>/dev/null || true

# Layer 3: app source (rebuilds on any code change — but fast, no pip)
COPY . /code/
RUN pip install --no-deps .

CMD ["led-ticker", "--config", "/code/config/config.toml"]
