# Stage 1: Build rgbmatrix + install app
FROM balenalib/raspberry-pi-python:3.11 AS builder

ENV DEBIAN_FRONTEND=noninteractive

RUN mkdir /code
WORKDIR /code

RUN apt-get update && \
    apt-get install -y build-essential git make python3-dev python3-pillow && \
    rm -rf /var/lib/apt/lists/*

RUN cd /opt && \
    git clone --depth=1 https://github.com/hzeller/rpi-rgb-led-matrix.git && \
    cd rpi-rgb-led-matrix && \
    make -C lib && \
    cd bindings/python && \
    pip3 install .

# Stage 2: Install app on top
FROM builder

COPY . /code/
RUN pip3 install .

CMD ["led-ticker", "--config", "/code/config/config.toml"]
