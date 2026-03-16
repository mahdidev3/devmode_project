\
import json
import os
import signal
import time
from pathlib import Path
from typing import Any, Dict, Optional


def is_pid_running(pid: int) -> bool:
    stat_path = Path(f"/proc/{pid}/stat")
    if stat_path.exists():
        try:
            parts = stat_path.read_text(encoding="utf-8").split()
            if len(parts) >= 3 and parts[2] == "Z":
                return False
        except Exception:
            pass
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def remove_state_files(*paths: Path) -> None:
    for path in paths:
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def write_info_file(info_file: Path, payload: Dict[str, Any]) -> None:
    info_file.parent.mkdir(parents=True, exist_ok=True)
    info_file.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def read_json_file(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def stop_pid(pid: int, timeout: float = 8.0) -> bool:
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return True

    deadline = time.time() + timeout
    while time.time() < deadline:
        if not is_pid_running(pid):
            return True
        time.sleep(0.2)

    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        return True

    time.sleep(0.5)
    return not is_pid_running(pid)
