#!/usr/bin/env python3
"""Compatibility wrapper.

Older docs/scripts may call ``devmodectl.py`` directly using legacy option-style
arguments (for example ``add-user --mode Devmode1 --username alice``). Keep those
calls working by translating them into the new project-manager positional syntax.
"""
from __future__ import annotations

from typing import Sequence

from project_manager import main


def _extract_legacy_value(argv: list[str], flag: str) -> str | None:
    if flag not in argv:
        return None
    idx = argv.index(flag)
    if idx + 1 >= len(argv):
        return None
    value = argv[idx + 1]
    del argv[idx: idx + 2]
    return value


def _translate_legacy_args(argv: Sequence[str]) -> list[str]:
    """Convert old flag-style user-management commands into current syntax."""
    if not argv:
        return list(argv)

    args = list(argv)
    command = args[0]

    if command in {"add-user", "remove-user", "passwd", "list-users"}:
        mode = _extract_legacy_value(args, "--mode")
        username = _extract_legacy_value(args, "--username")

        if mode:
            args.insert(1, mode)

        if username and command in {"add-user", "remove-user", "passwd"}:
            insert_at = 2 if mode else 1
            args.insert(insert_at, username)

    return args


if __name__ == "__main__":
    import sys

    raise SystemExit(main(_translate_legacy_args(sys.argv[1:])))
