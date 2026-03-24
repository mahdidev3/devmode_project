import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List

from .config import AppConfig, load_config
from .manage_mode import (
    _load_instances,
    resolve_app_name,
    set_replica_count,
    set_replica_port,
    set_user_port,
    start_mode,
    stop_mode,
)
from .runtime import is_pid_running
from .userdb import UserDB


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def selected_apps(config, target: str) -> List[AppConfig]:
    if target.lower() == "all":
        return config.enabled_apps()
    return [config.app(resolve_app_name(target))]


def ensure_certs(config, app: AppConfig) -> None:
    if not app.tls_enabled:
        return
    if app.tls_cert and app.tls_key and app.tls_cert.exists() and app.tls_key.exists():
        return
    if not config.auto_generate_certs:
        raise SystemExit(f"TLS cert/key missing for {app.app_name} and auto generation is disabled")
    if not shutil.which("openssl"):
        raise SystemExit(f"TLS cert/key missing for {app.app_name} and openssl is not available")

    app.tls_cert.parent.mkdir(parents=True, exist_ok=True)
    app.tls_key.parent.mkdir(parents=True, exist_ok=True)
    subject = (
        f"/C={config.env.get('DEVMODE_CERT_COUNTRY', 'US')}"
        f"/ST={config.env.get('DEVMODE_CERT_STATE', 'Dev')}"
        f"/L={config.env.get('DEVMODE_CERT_LOCALITY', 'Dev')}"
        f"/O={config.env.get('DEVMODE_CERT_ORG', 'Devmode')}"
        f"/OU={config.env.get('DEVMODE_CERT_ORG_UNIT', 'Engineering')}"
        f"/CN={config.env.get('DEVMODE_CERT_COMMON_NAME', 'localhost')}"
    )
    subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-nodes",
            "-newkey",
            "rsa:2048",
            "-days",
            str(config.cert_days),
            "-subj",
            subject,
            "-keyout",
            str(app.tls_key),
            "-out",
            str(app.tls_cert),
        ],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    print(f"Generated self-signed cert for {app.app_name}: {app.tls_cert}")


def cmd_setup(args) -> int:
    config = load_config(project_root())
    for app in config.enabled_apps():
        app.state_dir.mkdir(parents=True, exist_ok=True)
        if app.auth_enabled and config.setup_create_default_users:
            userdb = UserDB(app.users_file)
            if config.default_admin_user not in userdb.list_users():
                userdb.add_user(config.default_admin_user, config.default_admin_password)
                print(f"Created default admin user for {app.app_name}: {config.default_admin_user}")
        ensure_certs(config, app)
        start_mode(app)
    print("Setup finished")
    return 0


def cmd_start(args) -> int:
    config = load_config(project_root())
    rc = 0
    for app in selected_apps(config, args.target):
        if not app.enabled and args.target.lower() == "all":
            continue
        if app.tls_enabled:
            ensure_certs(config, app)
        rc |= start_mode(app)
    return rc


def cmd_stop(args) -> int:
    config = load_config(project_root())
    rc = 0
    for app in selected_apps(config, args.target):
        rc |= stop_mode(app)
    return rc


def cmd_restart(args) -> int:
    config = load_config(project_root())
    rc = 0
    for app in selected_apps(config, args.target):
        rc |= stop_mode(app)
        if app.enabled or args.target.lower() != "all":
            if app.tls_enabled:
                ensure_certs(config, app)
            rc |= start_mode(app)
    return rc


def cmd_status(args) -> int:
    config = load_config(project_root())
    rows = []
    for app in config.all_apps():
        instances = _load_instances(app)
        active = [row for row in instances if row.get("pid") and is_pid_running(int(row["pid"]))]
        rows.append(
            {
                "app": app.app_name,
                "enabled": app.enabled,
                "running": bool(active),
                "scheme": app.listen_scheme,
                "auth_enabled": app.auth_enabled,
                "mode_kind": app.mode_kind,
                "replicas": app.replicas,
                "instances": active,
                "upstream_url": app.upstream_url,
            }
        )
    if args.json:
        print(json.dumps(rows, indent=2))
        return 0
    for row in rows:
        print(
            f"{row['app']}: enabled={row['enabled']} running={row['running']} "
            f"scheme={row['scheme']} auth={row['auth_enabled']} replicas={row['replicas']} "
            f"mode={row['mode_kind']} upstream={row['upstream_url']}"
        )
        for instance in row["instances"]:
            extra = f" user={instance.get('username')}" if instance.get("username") else f" replica={instance.get('replica')}"
            print(
                f"  - instance={instance.get('instance_id')} host={instance.get('host')} "
                f"port={instance.get('port')} pid={instance.get('pid')}{extra}"
            )
    return 0


def _user_apps(config, target: str) -> List[AppConfig]:
    apps = selected_apps(config, target)
    return [app for app in apps if app.auth_enabled]


def _has_running_instances(app: AppConfig) -> bool:
    for row in _load_instances(app):
        pid = int(row.get("pid", 0) or 0)
        if pid > 0 and is_pid_running(pid):
            return True
    return False


def cmd_add_user(args) -> int:
    config = load_config(project_root())
    rc = 0
    for app in _user_apps(config, args.target):
        userdb = UserDB(app.users_file)
        userdb.add_user(args.username, args.password)
        print(f"saved user in {app.app_name}: {args.username}")
        set_user_port(app, args.username, 0, randomize=True)
        print(f"assigned random port for {app.app_name} user={args.username}")

        if _has_running_instances(app):
            rc |= start_mode(app)
    return rc


def cmd_remove_user(args) -> int:
    config = load_config(project_root())
    for app in _user_apps(config, args.target):
        userdb = UserDB(app.users_file)
        try:
            userdb.remove_user(args.username)
            print(f"removed user from {app.app_name}: {args.username}")
        except KeyError as exc:
            print(f"{app.app_name}: {exc}", file=sys.stderr)
    return 0


def cmd_passwd(args) -> int:
    config = load_config(project_root())
    for app in _user_apps(config, args.target):
        userdb = UserDB(app.users_file)
        try:
            userdb.change_password(args.username, args.password)
            print(f"updated password for user in {app.app_name}: {args.username}")
        except KeyError as exc:
            print(f"{app.app_name}: {exc}", file=sys.stderr)
    return 0


def cmd_list_users(args) -> int:
    config = load_config(project_root())
    for app in _user_apps(config, args.target):
        print(f"[{app.app_name}]")
        for username in UserDB(app.users_file).list_users():
            print(username)
    return 0


def cmd_set_user_port(args) -> int:
    config = load_config(project_root())
    app = config.app(resolve_app_name(args.target))
    set_user_port(app, args.username, args.port, randomize=False)
    print(f"Set {app.app_name} user={args.username} port={args.port}")
    if args.restart or _has_running_instances(app):
        return start_mode(app)
    return 0


def cmd_random_user_port(args) -> int:
    config = load_config(project_root())
    app = config.app(resolve_app_name(args.target))
    set_user_port(app, args.username, 0, randomize=True)
    print(f"Set {app.app_name} user={args.username} port=random")
    if args.restart or _has_running_instances(app):
        return start_mode(app)
    return 0


def cmd_set_replicas(args) -> int:
    config = load_config(project_root())
    app = config.app(resolve_app_name(args.target))
    set_replica_count(app, args.replicas)
    print(f"Set {app.app_name} replicas={args.replicas}")
    if args.restart:
        app = load_config(project_root()).app(app.app_key)
        return start_mode(app)
    return 0


def cmd_set_replica_port(args) -> int:
    config = load_config(project_root())
    app = config.app(resolve_app_name(args.target))
    set_replica_port(app, args.replica, args.port)
    print(f"Set {app.app_name} replica={args.replica} port={args.port}")
    if args.restart:
        return start_mode(app)
    return 0


def cmd_random_replica_port(args) -> int:
    config = load_config(project_root())
    app = config.app(resolve_app_name(args.target))
    set_replica_port(app, args.replica, 0, randomize=True)
    print(f"Set {app.app_name} replica={args.replica} port=random")
    if args.restart:
        return start_mode(app)
    return 0


def cmd_edit_env(args) -> int:
    root = project_root()
    env_file = root / ".env"
    editor = os.environ.get("EDITOR") or shutil.which("nano") or shutil.which("vi")
    if not editor:
        raise SystemExit("No editor found. Set $EDITOR.")
    return subprocess.call([editor, str(env_file)])


def cmd_load_env(args) -> int:
    config = load_config(project_root())
    for key, value in sorted(config.env.items()):
        print(f"export {key}={json.dumps(value)}")
    return 0


def cmd_update(args) -> int:
    root = project_root()
    if not (root / ".git").exists():
        raise SystemExit("This folder is not a git repository")
    subprocess.run(["git", "-C", str(root), "pull", "--ff-only"], check=True)
    print("Git update completed")
    if args.with_setup:
        return cmd_setup(args)
    return 0


def cmd_remove(args) -> int:
    config = load_config(project_root())
    apps = selected_apps(config, args.target)
    for app in apps:
        stop_mode(app)
        if args.purge_state and app.state_dir.exists():
            shutil.rmtree(app.state_dir, ignore_errors=True)
            print(f"Removed state dir: {app.state_dir}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage the Devmode project")
    sub = parser.add_subparsers(dest="command", required=True)

    setup = sub.add_parser("setup")
    setup.set_defaults(func=cmd_setup)

    start = sub.add_parser("start")
    start.add_argument("target", nargs="?", default="all")
    start.set_defaults(func=cmd_start)

    stop = sub.add_parser("stop")
    stop.add_argument("target", nargs="?", default="all")
    stop.set_defaults(func=cmd_stop)

    restart = sub.add_parser("restart")
    restart.add_argument("target", nargs="?", default="all")
    restart.set_defaults(func=cmd_restart)

    status = sub.add_parser("status")
    status.add_argument("--json", action="store_true")
    status.set_defaults(func=cmd_status)

    add_user = sub.add_parser("add-user")
    add_user.add_argument("target")
    add_user.add_argument("username")
    add_user.add_argument("--password", required=True)
    add_user.set_defaults(func=cmd_add_user)

    remove_user = sub.add_parser("remove-user")
    remove_user.add_argument("target")
    remove_user.add_argument("username")
    remove_user.set_defaults(func=cmd_remove_user)

    passwd = sub.add_parser("passwd")
    passwd.add_argument("target")
    passwd.add_argument("username")
    passwd.add_argument("--password", required=True)
    passwd.set_defaults(func=cmd_passwd)

    list_users = sub.add_parser("list-users")
    list_users.add_argument("target", nargs="?", default="all")
    list_users.set_defaults(func=cmd_list_users)

    set_user_port_cmd = sub.add_parser("set-user-port")
    set_user_port_cmd.add_argument("target")
    set_user_port_cmd.add_argument("username")
    set_user_port_cmd.add_argument("port", type=int)
    set_user_port_cmd.add_argument("--restart", action="store_true")
    set_user_port_cmd.set_defaults(func=cmd_set_user_port)

    random_user_port_cmd = sub.add_parser("random-user-port")
    random_user_port_cmd.add_argument("target")
    random_user_port_cmd.add_argument("username")
    random_user_port_cmd.add_argument("--restart", action="store_true")
    random_user_port_cmd.set_defaults(func=cmd_random_user_port)

    set_replicas_cmd = sub.add_parser("set-replicas")
    set_replicas_cmd.add_argument("target")
    set_replicas_cmd.add_argument("replicas", type=int)
    set_replicas_cmd.add_argument("--restart", action="store_true")
    set_replicas_cmd.set_defaults(func=cmd_set_replicas)

    set_replica_port_cmd = sub.add_parser("set-replica-port")
    set_replica_port_cmd.add_argument("target")
    set_replica_port_cmd.add_argument("replica", type=int)
    set_replica_port_cmd.add_argument("port", type=int)
    set_replica_port_cmd.add_argument("--restart", action="store_true")
    set_replica_port_cmd.set_defaults(func=cmd_set_replica_port)

    random_replica_port_cmd = sub.add_parser("random-replica-port")
    random_replica_port_cmd.add_argument("target")
    random_replica_port_cmd.add_argument("replica", type=int)
    random_replica_port_cmd.add_argument("--restart", action="store_true")
    random_replica_port_cmd.set_defaults(func=cmd_random_replica_port)

    edit_env = sub.add_parser("edit-env")
    edit_env.set_defaults(func=cmd_edit_env)

    load_env = sub.add_parser("load-env")
    load_env.set_defaults(func=cmd_load_env)

    update = sub.add_parser("update")
    update.add_argument("--with-setup", action="store_true")
    update.set_defaults(func=cmd_update)

    remove = sub.add_parser("remove")
    remove.add_argument("target", nargs="?", default="all")
    remove.add_argument("--purge-state", action="store_true")
    remove.set_defaults(func=cmd_remove)

    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)
