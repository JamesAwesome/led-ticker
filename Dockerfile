FROM balenalib/raspberry-pi-python:3.13-bullseye AS rgbmatrix

ENV DEBIAN_FRONTEND=noninteractive

RUN mkdir /code
WORKDIR /code

RUN apt-get update && \
    apt-get install -y build-essential git make python3-dev python3-pillow cmake && \
    rm -rf /var/lib/apt/lists/*

# Use fork with Python 3.9+ support (upstream requires 3.13+)
RUN cd /opt && \
    git clone --depth=1 https://github.com/jamesawesome/rpi-rgb-led-matrix.git && \
    cd rpi-rgb-led-matrix && \
    pip3 install .

FROM rgbmatrix

COPY . /code/
RUN pip3 install .

CMD ["led-ticker", "--config", "/code/config/config.toml"]
