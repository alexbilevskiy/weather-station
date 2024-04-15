#!/usr/bin/env bash
set -x
#docker buildx create --name weather-station-builder --use --config ./buildkit.toml
docker buildx use weather-station-builder
docker buildx build --platform=linux/arm/v7 --progress=plain -t bee:5001/weather-station:latest --push .
docker buildx use default
