#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/.."
# Stop the centralized DB compose
docker-compose -f db/docker-compose.yml down
echo "Centralized DB stopped (db/docker-compose.yml down)"
