# Stage 1: Build rgbmatrix C extension
FROM balenalib/raspberry-pi-debian:bookworm-build AS builder

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    python3 python3-dev python3-pip python3-venv \
    build-essential git make \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Build rgbmatrix from source
RUN cd /opt && \
    git clone --depth=1 https://github.com/hzeller/rpi-rgb-led-matrix.git && \
    cd rpi-rgb-led-matrix && \
    make build-python PYTHON=/opt/venv/bin/python3 && \
    make install-python PYTHON=/opt/venv/bin/python3

# Install application
COPY pyproject.toml /code/pyproject.toml
COPY src/ /code/src/
WORKDIR /code
RUN pip install --no-cache-dir .

# Stage 2: Runtime (slim, no build tools)
FROM balenalib/raspberry-pi-debian:bookworm-run

RUN apt-get update && apt-get install -y \
    python3 libpython3.11 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app
COPY config.example.toml /app/config.example.toml

CMD ["led-ticker", "--config", "/app/config/config.toml"]
