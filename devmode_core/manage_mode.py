import os
\
import argparse
import getpass
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Iterable, List, Optional

from .config import AppConfig, load_config
from .runtime import is_pid_running, read_json_file, remove_state_files, stop_pid
from .userdb import UserDB


def project_root_from_script(script_path: Path) -> Path:
    current = script_path.resolve()
    for candidate in [current.parent] + list(current.parents):
        if (candidate / "devmode_core").is_dir() and (candidate / "devmodectl.py").exists():
            return candidate
    raise RuntimeError("Could not locate project root")


def resolve_app_name(name_or_key: str) -> str:
    raw = name_or_key.strip()
    if raw.lower().startswith("devmode"):
        num = raw[len("devmode"):]
        if num.isdigit():
            return f"devmode{int(num)}"
    return raw.lower()


def app_config_from_script(script_path: Path, mode_name: str) -> AppConfig:
    root = project_root_from_script(script_path)
    config = load_config(root)
    return config.app(resolve_app_name(mode_name))


def start_mode(config: AppConfig, host_override: Optional[str] = None, port_override: Optional[int] = None) -> int:
    running = read_json_file(config.info_file)
    if running and is_pid_running(int(running.get("pid", 0))):
        print(f"{config.app_name} already running: PID={running['pid']} PORT={running['port']} HOST={running['host']}")
        return 0

    if host_override:
        config.host = host_override
    if port_override is not None:
        config.port = port_override

    command = [
        sys.executable,
        "-m",
        "devmode_core.server_entry",
        "--app-key",
        config.app_key,
        "--root-dir",
        str(project_root_from_script(Path(__file__))),
    ]
    with open(config.log_file, "ab") as logf:
        proc = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=logf,
            stderr=logf,
            start_new_session=True,
            close_fds=True,
            env={**os.environ, f"{config.env_prefix}_HOST": config.host, f"{config.env_prefix}_PORT": str(config.port)},
        )
    deadline = time.time() + 10
    while time.time() < deadline:
        info = read_json_file(config.info_file)
        if info and is_pid_running(int(info["pid"])):
            print(f"STARTED APP={config.app_name} PID={info['pid']} HOST={info['host']} PORT={info['port']}")
            return 0
        if proc.poll() is not None:
            break
        time.sleep(0.2)
    print(f"Failed to start {config.app_name}. Check log: {config.log_file}", file=sys.stderr)
    return 1


def stop_mode(config: AppConfig, timeout: float = 8.0) -> int:
    if not config.pid_file.exists():
        print(f"{config.app_name} is not running.")
        remove_state_files(config.pid_file, config.port_file, config.info_file)
        return 0
    try:
        pid = int(config.pid_file.read_text(encoding="utf-8").strip())
    except Exception:
        print("Invalid PID file. Cleaning state.")
        remove_state_files(config.pid_file, config.port_file, config.info_file)
        return 1
    if not is_pid_running(pid):
        print("Process already stopped. Cleaning state.")
        remove_state_files(config.pid_file, config.port_file, config.info_file)
        return 0
    if stop_pid(pid, timeout=timeout):
        remove_state_files(config.pid_file, config.port_file, config.info_file)
        print(f"STOPPED APP={config.app_name} PID={pid}")
        return 0
    print(f"Failed to stop PID={pid}", file=sys.stderr)
    return 1


def manage_users_main(script_path: Path, mode_name: str, argv: Optional[List[str]] = None) -> int:
    app = app_config_from_script(script_path, mode_name)
    parser = argparse.ArgumentParser(description=f"Manage access users for {app.app_name}")
    sub = parser.add_subparsers(dest="command", required=True)

    add_parser = sub.add_parser("add")
    add_parser.add_argument("username")
    add_parser.add_argument("--password")

    rm_parser = sub.add_parser("remove")
    rm_parser.add_argument("username")

    passwd_parser = sub.add_parser("passwd")
    passwd_parser.add_argument("username")
    passwd_parser.add_argument("--password")

    sub.add_parser("list")

    args = parser.parse_args(argv)
    userdb = UserDB(app.users_file)

    if args.command == "add":
        password = args.password or getpass.getpass("Password: ")
        if not password:
            raise SystemExit("password can not be empty")
        userdb.add_user(args.username, password)
        print(f"saved user in {app.app_name}: {args.username}")
        return 0

    if args.command == "remove":
        try:
            userdb.remove_user(args.username)
        except KeyError as exc:
            raise SystemExit(str(exc))
        print(f"removed user from {app.app_name}: {args.username}")
        return 0

    if args.command == "passwd":
        password = args.password or getpass.getpass("New password: ")
        if not password:
            raise SystemExit("password can not be empty")
        try:
            userdb.change_password(args.username, password)
        except KeyError as exc:
            raise SystemExit(str(exc))
        print(f"updated password for user in {app.app_name}: {args.username}")
        return 0

    if args.command == "list":
        for username in userdb.list_users():
            print(username)
        return 0

    return 1
