#!/usr/bin/env python3
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from devmode_core.manage_mode import app_config_from_script, stop_mode

if __name__ == "__main__":
    config = app_config_from_script(Path(__file__), "Devmode4")
    raise SystemExit(stop_mode(config))
