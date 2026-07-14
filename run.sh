#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

PORT="${HOOK_UI_PORT:-8765}"
HOST="127.0.0.1"

if command -v uv >/dev/null 2>&1; then
  echo "Using uv"
  if [[ ! -d .venv ]]; then
    uv venv
  fi
  uv pip install -r requirements.txt
  exec uv run uvicorn server.app:app --host "$HOST" --port "$PORT" --reload
fi

echo "uv not found, falling back to python venv"
if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate
pip install -r requirements.txt
exec uvicorn server.app:app --host "$HOST" --port "$PORT" --reload
