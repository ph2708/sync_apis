#!/usr/bin/env bash
set -e
# Stop Postgres container for e-track
cd "$(dirname "$0")"
docker-compose down
echo "e-track DB stopped (docker-compose down)"
