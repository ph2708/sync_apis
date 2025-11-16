#!/usr/bin/env bash
set -euo pipefail

# Entrypoint: run migration then sleep for 24h and repeat.
# Uses environment variables: PGHOST, PGPORT, PGUSER, PGPASSWORD, PGDATABASE

SCRIPT_DIR="/app"
MIGRATE_CMD=("/usr/local/bin/python" "$SCRIPT_DIR/run_migration.py")

echo "Starting migration-cron container. Will run migration once and then every 24h."

while true; do
  echo "[$(date --iso-8601=seconds)] Running migration..."
  if "${MIGRATE_CMD[@]}"; then
    echo "[$(date --iso-8601=seconds)] Migration completed successfully."
  else
    echo "[$(date --iso-8601=seconds)] Migration failed (exit code). Check logs." >&2
  fi

  # Sleep 24 hours (86400 seconds). This is simple and avoids cron complexity inside container.
  sleep 86400
done
