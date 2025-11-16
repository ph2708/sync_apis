#!/usr/bin/env bash
set -e
# Load .env if present
if [ -f .env ]; then
  export $(grep -v '^#' .env | xargs)
fi

python3 reset_db.py "$@"
