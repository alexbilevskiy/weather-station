ARG DOCKER_REGISTRY
FROM ${DOCKER_REGISTRY}/weather-station-base:latest

COPY . /weather-station
WORKDIR /weather-station/led-clock

CMD ["python", "-B", "-u", "led-clock.py", "--light-adjust=0"]
