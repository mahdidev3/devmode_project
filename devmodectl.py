#!/usr/bin/env python3
"""Compatibility wrapper.

Older docs/scripts may call devmodectl.py directly. Keep that path working by routing
through the new high-level project manager.
"""
from project_manager import main

if __name__ == "__main__":
    raise SystemExit(main())
