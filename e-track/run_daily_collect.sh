#!/usr/bin/env bash
# Wrapper to run the e-track collector for the current month.
# Place this file in the e-track folder, make it executable: chmod +x run_daily_collect.sh

set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"

# load .env from repository root if present (do not override already exported vars)
REPO_ROOT="$(cd "$HERE/.." && pwd)"
if [ -f "$REPO_ROOT/.env" ]; then
  # shellcheck disable=SC1090
  set -o allexport
  . "$REPO_ROOT/.env"
  set +o allexport
fi

# activate venv if present
if [ -f .venv/bin/activate ]; then
  # shellcheck disable=SC1091
  . .venv/bin/activate
fi

# Run collector for the current month for all plates (idempotent)
python collector.py --fetch-current-month-all
