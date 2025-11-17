#!/usr/bin/env bash
set -euo pipefail

# Wrapper to run the Auvo sync.
# - creates a virtualenv `.venv` and installs requirements once
# - use FORCE_REINSTALL=1 to force reinstall of requirements

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$HERE/.." && pwd)"

# load .env from repo root if present (do not override existing env vars)
if [ -f "$REPO_ROOT/.env" ]; then
  # shellcheck disable=SC1090
  set -o allexport
  . "$REPO_ROOT/.env"
  set +o allexport
fi

# create or activate virtualenv
if [ -f ".venv/bin/activate" ]; then
  # activate existing venv
  # shellcheck disable=SC1091
  source .venv/bin/activate
else
  echo "Creating virtualenv .venv and installing dependencies..."
  python3 -m venv .venv
  # shellcheck disable=SC1091
  source .venv/bin/activate
  pip install --upgrade pip
  pip install -r requirements.txt
  touch .venv/.requirements_installed
fi

# If requirements.txt changed since last install or FORCE_REINSTALL=1, reinstall
if [ -f ".venv/.requirements_installed" ]; then
  if [ "${FORCE_REINSTALL:-0}" = "1" ] || [ requirements.txt -nt .venv/.requirements_installed ]; then
    echo "Reinstalling requirements (FORCE_REINSTALL=${FORCE_REINSTALL:-0})..."
    pip install -r requirements.txt
    touch .venv/.requirements_installed
  fi
fi

# Run sync (you can pass --pg-dsn or rely on env vars)
python3 auvo_sync.py --db-wait 2

