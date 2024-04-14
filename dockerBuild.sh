#!/usr/bin/env bash
set -x
#docker buildx create --use --config ./buildkit.toml
docker buildx build --platform=linux/arm --progress=plain -t bee:5001/weather-station:latest --push .