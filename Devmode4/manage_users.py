#!/usr/bin/env python3
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from devmode_core.manage_mode import manage_users_main

if __name__ == "__main__":
    raise SystemExit(manage_users_main(Path(__file__), "Devmode4"))
