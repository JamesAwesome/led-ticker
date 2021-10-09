FROM balenalib/raspberry-pi-python:3.7.9 as rgbmatrix

ENV DEBIAN_FRONTEND noninteractive

RUN mkdir /code

WORKDIR /code

RUN apt-get update && \
    apt-get install -y build-essential git make python3-dev python3-pillow && \
    rm -rf /var/lib/apt/lists/*

RUN cd /opt && \
    git clone https://github.com/hzeller/rpi-rgb-led-matrix.git && \
    cd rpi-rgb-led-matrix && \
    make build-python PYTHON=$(which python3) && \
    make install-python PYTHON=$(which python3)

# Next Stage
FROM rgbmatrix

COPY . /code/

RUN pip3 install -e .

CMD python3 main.py
