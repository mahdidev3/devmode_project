import argparse
import getpass
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

from .config import AppConfig, load_config
from .runtime import is_pid_running, read_json_file, remove_state_files, stop_pid
from .userdb import UserDB


INSTANCES_FILE = "instances.json"
USER_PORTS_FILE = "user_ports.json"
REPLICA_PORTS_FILE = "replica_ports.json"


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


def _instances_file(app: AppConfig) -> Path:
    return app.state_dir / INSTANCES_FILE


def _user_ports_file(app: AppConfig) -> Path:
    return app.state_dir / USER_PORTS_FILE


def _replica_ports_file(app: AppConfig) -> Path:
    return app.state_dir / REPLICA_PORTS_FILE


def _load_json(path: Path, fallback):
    data = read_json_file(path)
    return fallback if data is None else data


def _write_json(path: Path, payload: Dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _load_instances(app: AppConfig) -> List[Dict]:
    payload = _load_json(_instances_file(app), {"instances": []})
    return payload.get("instances", [])


def _save_instances(app: AppConfig, instances: List[Dict]) -> None:
    _write_json(_instances_file(app), {"instances": instances})


def _load_user_ports(app: AppConfig) -> Dict[str, int]:
    payload = _load_json(_user_ports_file(app), {"user_ports": {}})
    ports = payload.get("user_ports", {})
    return {str(k): int(v) for k, v in ports.items()}


def _save_user_ports(app: AppConfig, ports: Dict[str, int]) -> None:
    _write_json(_user_ports_file(app), {"user_ports": ports})


def _load_replica_ports(app: AppConfig) -> Dict[str, int]:
    payload = _load_json(_replica_ports_file(app), {"replica_ports": {}})
    ports = payload.get("replica_ports", {})
    return {str(k): int(v) for k, v in ports.items()}


def _save_replica_ports(app: AppConfig, ports: Dict[str, int]) -> None:
    _write_json(_replica_ports_file(app), {"replica_ports": ports})


def _instance_id_for_user(username: str) -> str:
    return f"user:{username}"


def _instance_id_for_replica(idx: int) -> str:
    return f"replica:{idx}"


def _launch_instance(app: AppConfig, instance_id: str, host: str, port: int, allowed_user: Optional[str]) -> int:
    log_file = app.state_dir / f"{instance_id.replace(':', '_')}.log"
    info_file = app.state_dir / f"{instance_id.replace(':', '_')}.json"

    command = [
        sys.executable,
        "-m",
        "devmode_core.server_entry",
        "--app-key",
        app.app_key,
        "--root-dir",
        str(project_root_from_script(Path(__file__))),
    ]
    env = {
        **os.environ,
        f"{app.env_prefix}_HOST": host,
        f"{app.env_prefix}_PORT": str(port),
        f"{app.env_prefix}_ALLOWED_USER": allowed_user or "",
        "DEVMODE_INSTANCE_ID": instance_id,
        "DEVMODE_INSTANCE_INFO_FILE": str(info_file),
        "DEVMODE_INSTANCE_LOG_FILE": str(log_file),
    }
    with open(log_file, "ab") as logf:
        proc = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=logf,
            stderr=logf,
            start_new_session=True,
            close_fds=True,
            env=env,
        )

    deadline = time.time() + 10
    while time.time() < deadline:
        info = read_json_file(info_file)
        if info and is_pid_running(int(info.get("pid", 0))):
            return 0
        if proc.poll() is not None:
            break
        time.sleep(0.2)
    return 1


def _stop_instance_pid(instance: Dict, timeout: float = 8.0) -> bool:
    pid = int(instance.get("pid", 0))
    if pid <= 0:
        return True
    if not is_pid_running(pid):
        return True
    return stop_pid(pid, timeout=timeout)


def _desired_instances(app: AppConfig) -> List[Dict]:
    if app.auth_enabled:
        usernames = [app.allowed_user] if app.allowed_user else UserDB(app.users_file).list_users()
        user_ports = _load_user_ports(app)
        desired = []
        for username in usernames:
            desired.append(
                {
                    "instance_id": _instance_id_for_user(username),
                    "username": username,
                    "host": app.host,
                    "port": int(user_ports.get(username, 0)),
                }
            )
        return desired

    replica_ports = _load_replica_ports(app)
    desired = []
    for idx in range(1, app.replicas + 1):
        key = str(idx)
        desired.append(
            {
                "instance_id": _instance_id_for_replica(idx),
                "replica": idx,
                "host": app.host,
                "port": int(replica_ports.get(key, app.port if idx == 1 else 0)),
            }
        )
    return desired


def start_mode(config: AppConfig, host_override: Optional[str] = None, port_override: Optional[int] = None) -> int:
    if host_override:
        config.host = host_override
    if port_override is not None:
        config.port = port_override

    existing = {row["instance_id"]: row for row in _load_instances(config)}
    desired = _desired_instances(config)

    rc = 0
    alive_instances: List[Dict] = []

    for target in desired:
        instance_id = target["instance_id"]
        current = existing.get(instance_id)
        needs_restart = True
        if current and is_pid_running(int(current.get("pid", 0))):
            same_binding = current.get("host") == target["host"] and int(current.get("port", 0)) == int(target["port"])
            if same_binding:
                needs_restart = False
                alive_instances.append(current)

        if needs_restart and current:
            _stop_instance_pid(current)

        if needs_restart:
            if _launch_instance(config, instance_id, target["host"], target["port"], target.get("username")) != 0:
                print(f"Failed to start {config.app_name} instance {instance_id}", file=sys.stderr)
                rc = 1
                continue
            info = read_json_file(config.state_dir / f"{instance_id.replace(':', '_')}.json") or {}
            row = {
                "instance_id": instance_id,
                "pid": info.get("pid"),
                "host": info.get("host", target["host"]),
                "port": info.get("port", target["port"]),
                "username": target.get("username"),
                "replica": target.get("replica"),
                "info_file": str(config.state_dir / f"{instance_id.replace(':', '_')}.json"),
                "log_file": str(config.state_dir / f"{instance_id.replace(':', '_')}.log"),
            }
            alive_instances.append(row)
            print(
                f"STARTED APP={config.app_name} INSTANCE={instance_id} PID={row['pid']} HOST={row['host']} PORT={row['port']}"
            )

    desired_ids = {row["instance_id"] for row in desired}
    for instance_id, current in existing.items():
        if instance_id in desired_ids:
            continue
        _stop_instance_pid(current)
        info_file = Path(current.get("info_file", ""))
        log_file = Path(current.get("log_file", ""))
        remove_state_files(info_file)
        if log_file.exists() and log_file.stat().st_size == 0:
            remove_state_files(log_file)
        print(f"STOPPED APP={config.app_name} INSTANCE={instance_id}")

    alive_instances = [row for row in alive_instances if row.get("pid") and is_pid_running(int(row["pid"]))]
    _save_instances(config, alive_instances)
    return rc


def stop_mode(config: AppConfig, timeout: float = 8.0) -> int:
    instances = _load_instances(config)
    if not instances:
        print(f"{config.app_name} is not running.")
        return 0

    rc = 0
    for instance in instances:
        instance_id = instance.get("instance_id", "unknown")
        if _stop_instance_pid(instance, timeout=timeout):
            print(f"STOPPED APP={config.app_name} INSTANCE={instance_id} PID={instance.get('pid')}")
        else:
            print(f"Failed to stop APP={config.app_name} INSTANCE={instance_id} PID={instance.get('pid')}", file=sys.stderr)
            rc = 1
        remove_state_files(Path(instance.get("info_file", "")))

    remove_state_files(_instances_file(config), config.pid_file, config.port_file, config.info_file)
    return rc


def set_user_port(config: AppConfig, username: str, port: int, randomize: bool = False) -> None:
    if not config.auth_enabled:
        raise ValueError(f"{config.app_name} does not use user-based auth")
    userdb = UserDB(config.users_file)
    if username not in userdb.list_users():
        raise KeyError(f"user not found: {username}")
    ports = _load_user_ports(config)
    ports[username] = 0 if randomize else int(port)
    _save_user_ports(config, ports)


def set_replica_count(config: AppConfig, replicas: int) -> None:
    if config.auth_enabled:
        raise ValueError(f"{config.app_name} is auth-enabled and scales by users, not replicas")
    env_file = project_root_from_script(Path(__file__)) / ".env"
    key = f"{config.env_prefix}_REPLICAS"
    lines = env_file.read_text(encoding="utf-8").splitlines()
    replaced = False
    for idx, line in enumerate(lines):
        if line.strip().startswith(f"{key}="):
            lines[idx] = f"{key}={replicas}"
            replaced = True
            break
    if not replaced:
        lines.append(f"{key}={replicas}")
    env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")


def set_replica_port(config: AppConfig, replica: int, port: int, randomize: bool = False) -> None:
    ports = _load_replica_ports(config)
    ports[str(replica)] = 0 if randomize else int(port)
    _save_replica_ports(config, ports)


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
