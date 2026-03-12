#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="${ENV_FILE:-$ROOT_DIR/.env}"

if [ ! -f "$ENV_FILE" ]; then
  echo "Missing .env file."
  echo "Run: cp .env.example .env"
  exit 1
fi

if [ -n "${1:-}" ] && [ -f "$1" ]; then
  # shellcheck disable=SC1090
  source "$1"
  echo "Using venv: $1"
fi

python3 "$ROOT_DIR/project_manager.py" setup

python3 - <<'PY'
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path.cwd()
STATE_ROOT = Path.home() / ".local" / "run"

def bool_env(value: str) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on"}

def env_file():
    env = {}
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        env[key.strip()] = value.strip()
    return env

def test_one(mode_num: int, scheme: str, auth: bool):
    key = f"devmode{mode_num}"
    info_file = STATE_ROOT / key / "app.json"
    if not info_file.exists():
        print(f"[SKIP] {key}: not running")
        return
    info = json.loads(info_file.read_text(encoding="utf-8"))
    host = os.environ.get("DEVMODE_TEST_PROXY_HOST", "127.0.0.1")
    port = info["port"]
    username = os.environ.get("DEVMODE_DEFAULT_ADMIN_USER", "admin")
    password = os.environ.get("DEVMODE_DEFAULT_ADMIN_PASSWORD", "admin123")
    if scheme == "https":
        target = os.environ.get("DEVMODE_TEST_HTTPS_URL", "https://example.com/")
        base = ["curl", "-skS", "--proxy-insecure", "--proxy", f"https://{host}:{port}", target]
        if auth:
            base = ["curl", "-skS", "--proxy-insecure", "--proxy", f"https://{username}:{password}@{host}:{port}", target]
    else:
        target = os.environ.get("DEVMODE_TEST_HTTP_URL", "http://example.com/")
        base = ["curl", "-sS", "--proxy", f"http://{host}:{port}", target]
        if auth:
            base = ["curl", "-sS", "--proxy", f"http://{username}:{password}@{host}:{port}", target]
    print(f"\n[TEST] {info['app']} scheme={scheme} auth={auth} target={target}")
    result = subprocess.run(base, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    print(result.stdout[:1200])
    if result.returncode != 0:
        raise SystemExit(result.returncode)

env = env_file()
os.environ.update(env)

modes = [
    (1, "http", bool_env(env.get("DEVMODE1_AUTH_ENABLED", "true"))),
    (2, "https", bool_env(env.get("DEVMODE2_AUTH_ENABLED", "true"))),
    (3, "http", bool_env(env.get("DEVMODE3_AUTH_ENABLED", "false"))),
    (4, "https", bool_env(env.get("DEVMODE4_AUTH_ENABLED", "false"))),
    (5, "http", bool_env(env.get("DEVMODE5_AUTH_ENABLED", "false"))),
]
for num, scheme, auth in modes:
    if bool_env(env.get(f"DEVMODE{num}_ENABLED", "false")):
        test_one(num, scheme, auth)
PY

echo
echo "Setup + tests finished"
