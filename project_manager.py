#!/usr/bin/env python3
"""High-level project manager for the Devmode project.

This script wraps the lower-level devmode CLI and adds project lifecycle tasks:
- bootstrap / install
- update from git and reinstall requirements
- uninstall / remove runtime state
- env helpers
- per-mode start/stop/restart/status
- user management

The goal is to make the project easy to clone on a fresh machine and easy to extend
with new Devmodes later.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable, Sequence

from devmode_core import cli as core_cli
from devmode_core.config import load_config


ROOT = Path(__file__).resolve().parent
ENV_FILE = ROOT / ".env"
ENV_EXAMPLE = ROOT / ".env.example"
VENV_DIR = ROOT / ".venv"


class ProjectError(RuntimeError):
    pass


def run(cmd: Sequence[str], *, check: bool = True, cwd: Path | None = None) -> int:
    print("+", " ".join(cmd))
    result = subprocess.run(list(cmd), cwd=str(cwd or ROOT))
    if check and result.returncode != 0:
        raise ProjectError(f"command failed with exit code {result.returncode}: {' '.join(cmd)}")
    return result.returncode


def exists_cmd(name: str) -> bool:
    return shutil.which(name) is not None


def ensure_env(copy_if_missing: bool = True) -> None:
    if ENV_FILE.exists():
        return
    if copy_if_missing and ENV_EXAMPLE.exists():
        shutil.copy2(ENV_EXAMPLE, ENV_FILE)
        print(f"Created {ENV_FILE.name} from {ENV_EXAMPLE.name}. Please review it.")
        return
    raise ProjectError("Missing .env file. Create it from .env.example")


def maybe_python() -> str:
    python_bin = VENV_DIR / "bin" / "python3"
    if python_bin.exists():
        return str(python_bin)
    return sys.executable or "python3"


def install_python_requirements() -> None:
    python_bin = maybe_python()
    req_files = [ROOT / "requirements.txt"] + sorted(ROOT.glob("Devmode*/requirements.txt"))
    for req_file in req_files:
        if not req_file.exists():
            continue
        text = req_file.read_text(encoding="utf-8").strip()
        if not text or text.startswith("# No external"):
            print(f"Skipping empty requirements: {req_file.relative_to(ROOT)}")
            continue
        run([python_bin, "-m", "pip", "install", "-r", str(req_file)])


def cmd_bootstrap(args) -> int:
    if args.create_venv:
        if not exists_cmd("python3"):
            raise ProjectError("python3 is required to create a virtual environment")
        if not VENV_DIR.exists():
            run(["python3", "-m", "venv", str(VENV_DIR)])
        else:
            print(f"Virtual environment already exists: {VENV_DIR}")
        run([maybe_python(), "-m", "pip", "install", "--upgrade", "pip"])

    ensure_env(copy_if_missing=not args.no_copy_env)
    install_python_requirements()

    if args.setup:
        return core_cli.main(["setup"])
    return 0


def cmd_setup(args) -> int:
    ensure_env(copy_if_missing=False)
    return core_cli.main(["setup"])


def cmd_update(args) -> int:
    ensure_env(copy_if_missing=False)
    if not (ROOT / ".git").exists():
        raise ProjectError("This folder is not a git repository")
    run(["git", "pull", "--ff-only"])
    install_python_requirements()
    if args.with_bootstrap:
        cmd_bootstrap(argparse.Namespace(create_venv=False, no_copy_env=True, setup=False))
    if args.restart:
        return core_cli.main(["restart", "all"])
    if args.setup:
        return core_cli.main(["setup"])
    return 0


def cmd_remove(args) -> int:
    ensure_env(copy_if_missing=False)
    target = args.target or "all"
    rc = core_cli.main(["remove", target] + (["--purge-state"] if args.purge_state else []))

    if args.remove_venv and VENV_DIR.exists():
        shutil.rmtree(VENV_DIR, ignore_errors=True)
        print(f"Removed virtual environment: {VENV_DIR}")

    if args.delete_root:
        root = ROOT.resolve()
        parent = root.parent
        os.chdir(parent)
        shutil.rmtree(root, ignore_errors=True)
        print(f"Deleted project directory: {root}")
    return rc


def forward_to_core(argv: Iterable[str]) -> int:
    ensure_env(copy_if_missing=False)
    return core_cli.main(list(argv))


def cmd_install_system(args) -> int:
    """Print or install a small launcher into ~/.local/bin."""
    launcher_dir = Path.home() / ".local" / "bin"
    launcher_dir.mkdir(parents=True, exist_ok=True)
    launcher = launcher_dir / "devmode-project"
    launcher.write_text(
        "#!/usr/bin/env bash\n"
        f'exec "{maybe_python()}" "{ROOT / "project_manager.py"}" "$@"\n',
        encoding="utf-8",
    )
    launcher.chmod(0o755)
    print(f"Installed launcher: {launcher}")
    print("Make sure ~/.local/bin is in your PATH.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="High-level project manager for Devmode")
    sub = parser.add_subparsers(dest="command", required=True)

    bootstrap = sub.add_parser("bootstrap", help="Prepare .env, optional venv, and install requirements")
    bootstrap.add_argument("--create-venv", action="store_true", help="Create .venv and use it for installs")
    bootstrap.add_argument("--no-copy-env", action="store_true", help="Fail instead of creating .env from .env.example")
    bootstrap.add_argument("--setup", action="store_true", help="Run project setup after bootstrap")
    bootstrap.set_defaults(func=cmd_bootstrap)

    setup = sub.add_parser("setup", help="Run application setup")
    setup.set_defaults(func=cmd_setup)

    update = sub.add_parser("update", help="Pull from git and reinstall requirements")
    update.add_argument("--with-bootstrap", action="store_true", help="Also rerun bootstrap steps")
    update.add_argument("--setup", action="store_true", help="Run setup after update")
    update.add_argument("--restart", action="store_true", help="Restart all enabled apps after update")
    update.set_defaults(func=cmd_update)

    remove = sub.add_parser("remove", help="Stop apps and remove runtime state")
    remove.add_argument("target", nargs="?", default="all")
    remove.add_argument("--purge-state", action="store_true", help="Delete runtime state directories")
    remove.add_argument("--remove-venv", action="store_true", help="Delete the local .venv directory")
    remove.add_argument("--delete-root", action="store_true", help="Delete the project directory itself")
    remove.set_defaults(func=cmd_remove)

    install_system = sub.add_parser("install-launcher", help="Install a launcher into ~/.local/bin")
    install_system.set_defaults(func=cmd_install_system)

    for name in ("start", "stop", "restart"):
        p = sub.add_parser(name, help=f"{name.title()} one Devmode or all enabled modes")
        p.add_argument("target", nargs="?", default="all")
        p.set_defaults(func=lambda args, _name=name: forward_to_core([_name, args.target]))

    status = sub.add_parser("status", help="Show mode status")
    status.add_argument("--json", action="store_true")
    status.set_defaults(func=lambda args: forward_to_core(["status"] + (["--json"] if args.json else [])))

    add_user = sub.add_parser("add-user", help="Add user to auth-enabled modes")
    add_user.add_argument("target")
    add_user.add_argument("username")
    add_user.add_argument("--password", required=True)
    add_user.set_defaults(func=lambda args: forward_to_core(["add-user", args.target, args.username, "--password", args.password]))

    remove_user = sub.add_parser("remove-user", help="Remove user from auth-enabled modes")
    remove_user.add_argument("target")
    remove_user.add_argument("username")
    remove_user.set_defaults(func=lambda args: forward_to_core(["remove-user", args.target, args.username]))

    passwd = sub.add_parser("passwd", help="Change a user's password")
    passwd.add_argument("target")
    passwd.add_argument("username")
    passwd.add_argument("--password", required=True)
    passwd.set_defaults(func=lambda args: forward_to_core(["passwd", args.target, args.username, "--password", args.password]))

    list_users = sub.add_parser("list-users", help="List users from auth-enabled modes")
    list_users.add_argument("target", nargs="?", default="all")
    list_users.set_defaults(func=lambda args: forward_to_core(["list-users", args.target]))

    edit_env = sub.add_parser("edit-env", help="Open the project .env in your editor")
    edit_env.set_defaults(func=lambda args: forward_to_core(["edit-env"]))

    load_env = sub.add_parser("load-env", help="Print shell export commands for .env")
    load_env.set_defaults(func=lambda args: forward_to_core(["load-env"]))

    doctor = sub.add_parser("doctor", help="Validate common project requirements")
    doctor.set_defaults(func=cmd_doctor)

    return parser


def cmd_doctor(args) -> int:
    ok = True
    print(f"Project root: {ROOT}")
    print(f"Python: {maybe_python()}")
    print(f"Git available: {exists_cmd('git')}")
    print(f"OpenSSL available: {exists_cmd('openssl')}")
    print(f"Curl available: {exists_cmd('curl')}")
    print(f".env exists: {ENV_FILE.exists()}")
    if ENV_FILE.exists():
        try:
            config = load_config(ROOT)
            print(f"Enabled apps: {', '.join(app.app_name for app in config.enabled_apps()) or '(none)'}")
        except Exception as exc:  # pragma: no cover - defensive diagnostics
            ok = False
            print(f"Config load error: {exc}")
    else:
        ok = False
    return 0 if ok else 1


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except ProjectError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
