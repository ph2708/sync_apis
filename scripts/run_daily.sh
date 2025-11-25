#!/usr/bin/env bash
# Wrapper para iniciar o daily runner usando venv quando presente
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV="$ROOT_DIR/.venv"

if [ -x "$VENV/bin/python" ]; then
  echo "Usando venv: $VENV"
  exec "$VENV/bin/python" "$ROOT_DIR/scripts/daily_runner.py" "$@"
else
  echo "Aviso: venv não encontrado em $VENV — usando python do PATH"
  exec python3 "$ROOT_DIR/scripts/daily_runner.py" "$@"
fi
