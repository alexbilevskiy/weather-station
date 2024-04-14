FROM ubuntu:22.04
#FROM python:3.12-bookworm
RUN apt-get update
RUN apt-get install -y --no-install-recommends apt-utils build-essential sudo git make
RUN apt-get install -y python3-dev python3-pillow python3-pip

RUN apt-get install -y ca-certificates

RUN git clone https://github.com/hzeller/rpi-rgb-led-matrix.git

WORKDIR rpi-rgb-led-matrix/bindings/python

RUN /usr/bin/python3 -m pip install requests psutil paho-mqtt==1.5 pillow

RUN make build-python PYTHON=$(command -v python3)
RUN make install-python PYTHON=$(command -v python3)

COPY . /weather-station
WORKDIR /weather-station/led-clock

CMD ["/usr/bin/python3", "-B", "-u", "led-clock.py", "--light-adjust=0"]
