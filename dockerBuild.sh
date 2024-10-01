#!/usr/bin/env bash
if [[ $DOCKER_REGISTRY == "" ]];
  then
    echo "specifiy DOCKER_REGISTRY env"
    exit
  else
    echo "using registry ${DOCKER_REGISTRY}"
fi

BUILDX_NAME=weather-station-builder

existingBuildx=`docker buildx ls --format "{{.Name}}" | grep ${BUILDX_NAME}`
set -x
if [[ existingBuildx == "" ]];
  then
    echo "no buildx"
    exit
    docker buildx create --name ${BUILDX_NAME} --use
  else
    docker buildx use ${BUILDX_NAME}
fi

docker buildx build --platform=linux/arm/v7 --progress=plain -t ${DOCKER_REGISTRY}/weather-station:latest --push .
docker buildx use default
docker buildx stop ${BUILDX_NAME}