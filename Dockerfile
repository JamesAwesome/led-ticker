FROM balenalib/raspberry-pi-python:3.9-bullseye AS rgbmatrix

ENV DEBIAN_FRONTEND=noninteractive

RUN mkdir /code
WORKDIR /code

RUN apt-get update && \
    apt-get install -y build-essential git make python3-dev python3-pillow cython3 && \
    rm -rf /var/lib/apt/lists/*

# Pin to last release before Python 3.13 requirement
# Pin to commit before old Python build system was removed
RUN cd /opt && \
    git clone https://github.com/hzeller/rpi-rgb-led-matrix.git && \
    cd rpi-rgb-led-matrix && \
    git checkout 076c54b2207ca04ca42f24fa4ffc696507dbaa3f && \
    make build-python PYTHON=$(which python3) && \
    make install-python PYTHON=$(which python3)

FROM rgbmatrix

COPY . /code/
RUN pip3 install .

CMD ["led-ticker", "--config", "/code/config/config.toml"]
