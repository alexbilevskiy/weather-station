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

if [[ "$1" == "--base" ]];
  then
    echo "building base image..."
    docker buildx build --platform=linux/arm/v7 --progress=plain -f Dockerfile.base -t ${DOCKER_REGISTRY}/weather-station-base:latest --push .
  else
    docker buildx build --platform=linux/arm/v7 --progress=plain --build-arg DOCKER_REGISTRY=${DOCKER_REGISTRY} -t ${DOCKER_REGISTRY}/weather-station:latest --push .
fi

docker buildx use default
docker buildx stop ${BUILDX_NAME}
