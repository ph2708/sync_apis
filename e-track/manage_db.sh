#!/usr/bin/env bash
set -euo pipefail
# manage_db.sh - utilitário para controlar o DB do e-track e aplicar schema
# Uso: ./manage_db.sh <command>
# Commands: up | down | status | apply-schema | init | exec-psql

HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"

# carrega .env se existir
if [ -f .env ]; then
  # shellcheck disable=SC1091
  source .env
fi

# valores padrão (podem ser sobrescritos por .env ou ambiente)
: ${PGHOST:=127.0.0.1}
: ${PGPORT:=5433}
: ${PGDATABASE:=e_track}
: ${PGUSER:=etrack}
: ${PGPASSWORD:=etrack_pass}

function wait_ready() {
  echo "Aguardando Postgres estar pronto..."
  for i in {1..30}; do
    CONTAINER_ID=$(docker-compose ps -q db || true)
    if [ -n "$CONTAINER_ID" ] && docker exec "$CONTAINER_ID" pg_isready -U "$PGUSER" >/dev/null 2>&1; then
      echo "Postgres pronto"
      return 0
    fi
    sleep 1
  done
  echo "Timeout esperando Postgres"
  return 1
}

case ${1-} in
  up)
    docker-compose up -d db
    wait_ready
    ;;
  down)
    docker-compose down
    ;;
  status)
    docker ps --filter "name=e_track_db" --format "table {{.Names}}	{{.Status}}	{{.Ports}}"
    ;;
  apply-schema)
    # aplica schema.sql usando variáveis de ambiente para psql
    echo "Aplicando schema em postgresql://$PGUSER@$PGHOST:$PGPORT/$PGDATABASE"
    PGPASSWORD="$PGPASSWORD" psql "postgresql://$PGUSER:$PGHOST:$PGPORT/$PGDATABASE" -f schema.sql
    ;;
  init)
    docker-compose up -d db
    wait_ready
    echo "Aplicando schema..."
    PGPASSWORD="$PGPASSWORD" psql "postgresql://$PGUSER:$PGHOST:$PGPORT/$PGDATABASE" -f schema.sql
    echo "Init concluído"
    ;;
  exec-psql)
    # abre um psql interativo para o DB configurado
    PGPASSWORD="$PGPASSWORD" psql "postgresql://$PGUSER:$PGHOST:$PGPORT/$PGDATABASE"
    ;;
  *)
    echo "Uso: $0 {up|down|status|apply-schema|init|exec-psql}"
    exit 2
    ;;
esac
