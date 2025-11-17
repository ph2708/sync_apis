#!/usr/bin/env bash
set -euo pipefail
# Normalize line endings and set executable bits for project helper scripts
# Usage: from repo root: bash scripts/fix-line-endings.sh

# Ensure dos2unix is installed
if ! command -v dos2unix >/dev/null 2>&1; then
  echo "dos2unix not found. Installing (requires sudo)..."
  sudo apt-get update && sudo apt-get install -y dos2unix
fi

REPO_ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$REPO_ROOT"

FILES=(
  "auvo/run-sync.sh"
  "auvo/reset-db.sh"
  "e-track/run_daily_collect.sh"
  "e-track/manage_db.sh"
)

for f in "${FILES[@]}"; do
  if [ -f "$f" ]; then
    echo "Normalizing: $f"
    dos2unix "$f" || true
    chmod +x "$f" || true
  else
    echo "Aviso: arquivo não encontrado: $f"
  fi
done

echo "Feito. Agora execute (ex):"
echo "  cd auvo && ./run-sync.sh   # ou desde a raiz: python3 auvo/auvo_sync.py --db-wait 2"
