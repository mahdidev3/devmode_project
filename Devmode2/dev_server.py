#!/usr/bin/env python3
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from devmode_core.config import load_config
from devmode_core.proxy_server import run_server

if __name__ == "__main__":
    config = load_config(ROOT).app("devmode2")
    run_server(config)
