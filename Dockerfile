FROM python:3.11-bookworm AS weather-station-base

RUN apt-get update
RUN apt-get install -y --no-install-recommends apt-utils build-essential git make

RUN apt-get install -y ca-certificates

RUN pip install requests psutil paho-mqtt==1.5 pillow

WORKDIR /build
RUN git clone https://github.com/hzeller/rpi-rgb-led-matrix.git
WORKDIR ./rpi-rgb-led-matrix

RUN apt-get install python3-dev cython3 --no-install-recommends -y
RUN make build-python PYTHON=$(which python3) CYTHON=$(which cython3) -j 8
RUN make install-python PYTHON=$(command -v python3)

FROM weather-station-base

COPY . /weather-station
WORKDIR /weather-station/led-clock

CMD ["python", "-B", "-u", "led-clock.py", "--light-adjust=0"]
