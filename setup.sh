#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="${ENV_FILE:-$ROOT_DIR/.env}"

if [ ! -f "$ENV_FILE" ]; then
  echo "Missing .env file."
  echo "Run: cp .env.example .env"
  exit 1
fi

if [ -z "${DEVMODE_VENV_ACTIVATE:-}" ]; then
  if grep -q '^DEVMODE_VENV_ACTIVATE=' "$ENV_FILE"; then
    DEVMODE_VENV_ACTIVATE="$(grep '^DEVMODE_VENV_ACTIVATE=' "$ENV_FILE" | head -n1 | cut -d= -f2-)"
  fi
fi

if [ -n "${1:-}" ]; then
  DEVMODE_VENV_ACTIVATE="$1"
fi

if [ -n "${DEVMODE_VENV_ACTIVATE:-}" ] && [ -f "$DEVMODE_VENV_ACTIVATE" ]; then
  # shellcheck disable=SC1090
  source "$DEVMODE_VENV_ACTIVATE"
  echo "Using venv: $DEVMODE_VENV_ACTIVATE"
fi

exec python3 "$ROOT_DIR/project_manager.py" setup
