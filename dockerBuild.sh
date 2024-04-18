#!/usr/bin/env bash
if [[ $DOCKER_REGISTRY == "" ]];
  then
    echo "specifiy DOCKER_REGISTRY env"
    exit
  else
    echo "using registry ${DOCKER_REGISTRY}"
fi

TAG=`git rev-parse HEAD`
DATE=`date +%s`

set -x
#docker buildx create --name weather-station-builder --use --config ./buildkit.toml
docker buildx use weather-station-builder
docker buildx build --platform=linux/arm/v7 --progress=plain -t ${DOCKER_REGISTRY}/weather-station:latest -t ${DOCKER_REGISTRY}/weather-station:${DATE}_${TAG} --push .
docker buildx use default
