#!/usr/bin/env bash
set -e
# Start Postgres container
docker-compose up -d db
# Wait for Postgres to accept connections
echo "Aguardando Postgres subir..."
for i in {1..20}; do
  if docker exec $(docker-compose ps -q db) pg_isready -U auvo >/dev/null 2>&1; then
    echo "Postgres pronto"
    exit 0
  fi
  sleep 1
done
echo "Timeout esperando Postgres"
exit 1
