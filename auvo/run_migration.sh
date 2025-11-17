#!/usr/bin/env bash
# Wrapper to run run_migration.py using environment variables.
set -euo pipefail

# Example usage:
# Example usage:
# PGHOST=db PGPORT=5432 PGUSER=auvo PGPASSWORD=auvo_pass PGDATABASE=auvo ./run_migration.sh

PYTHON=${PYTHON:-python3}
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
:
# Default to the consolidated database name if PGDATABASE is not set
: ${PGDATABASE:=sync_apis}

"$PYTHON" "$SCRIPT_DIR/run_migration.py"
