#!/usr/bin/env bash
# Démarre le démon Docker dans WSL et vérifie qu'il répond.
set -e

if docker info >/dev/null 2>&1; then
  echo "dockerd already running"
  docker --version
  exit 0
fi

nohup dockerd >/tmp/dockerd.log 2>&1 &
for i in $(seq 1 30); do
  if docker info >/dev/null 2>&1; then
    echo "dockerd ready after ${i}s"
    docker --version
    exit 0
  fi
  sleep 1
done

echo "dockerd FAILED to start"
tail -30 /tmp/dockerd.log
exit 1
