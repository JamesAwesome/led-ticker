FROM python:3.13-bullseye AS rgbmatrix

ENV DEBIAN_FRONTEND=noninteractive

WORKDIR /code

RUN apt-get update && \
    apt-get install -y build-essential git python3-dev cmake && \
    rm -rf /var/lib/apt/lists/*

# Layer 1: rgbmatrix (only rebuilds if the fork changes)
RUN cd /opt && \
    git clone --depth=1 https://github.com/jamesawesome/rpi-rgb-led-matrix.git && \
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
