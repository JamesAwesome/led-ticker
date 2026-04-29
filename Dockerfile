FROM python:3.13-bullseye AS rgbmatrix

# Pin the rpi-rgb-led-matrix fork/branch. Default targets the Pi 4 sign;
# override with `--build-arg RGBMATRIX_REPO=... --build-arg RGBMATRIX_REF=...`
# for the Pi 5 image (see Makefile build-docker-pi5).
ARG RGBMATRIX_REPO=https://github.com/jamesawesome/rpi-rgb-led-matrix.git
ARG RGBMATRIX_REF=main

ENV DEBIAN_FRONTEND=noninteractive

WORKDIR /code

RUN apt-get update && \
    apt-get install -y build-essential git python3-dev cmake && \
    rm -rf /var/lib/apt/lists/*

# Layer 1: rgbmatrix (only rebuilds if the fork ref changes)
RUN cd /opt && \
    git clone --depth=1 --branch ${RGBMATRIX_REF} ${RGBMATRIX_REPO} && \
    cd rpi-rgb-led-matrix && \
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
