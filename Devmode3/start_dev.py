#!/usr/bin/env python3
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from devmode_core.manage_mode import app_config_from_script, start_mode

if __name__ == "__main__":
    host = None
    port = None
    if len(sys.argv) >= 2:
        host = sys.argv[1]
    if len(sys.argv) >= 3:
        port = int(sys.argv[2])
    config = app_config_from_script(Path(__file__), "Devmode3")
    raise SystemExit(start_mode(config, host_override=host, port_override=port))
