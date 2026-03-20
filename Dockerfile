FROM python:3.13-bullseye AS rgbmatrix

ENV DEBIAN_FRONTEND=noninteractive

RUN mkdir /code
WORKDIR /code

RUN apt-get update && \
    apt-get install -y build-essential git python3-dev cmake && \
    rm -rf /var/lib/apt/lists/*

RUN cd /opt && \
    git clone --depth=1 https://github.com/jamesawesome/rpi-rgb-led-matrix.git && \
    cd rpi-rgb-led-matrix && \
    pip install .

FROM rgbmatrix

COPY . /code/
RUN pip install .

CMD ["led-ticker", "--config", "/code/config/config.toml"]
