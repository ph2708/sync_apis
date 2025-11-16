#!/usr/bin/env bash
set -e
# Activate virtualenv if exists
if [ -f .venv/bin/activate ]; then
  source .venv/bin/activate
fi
# Install dependencies
pip install -r requirements.txt
# Optionally load .env
if [ -f .env ]; then
  export $(grep -v '^#' .env | xargs)
fi
# Run sync (you can pass --pg-dsn or rely on env vars)
python3 auvo_sync.py --db-wait 2
