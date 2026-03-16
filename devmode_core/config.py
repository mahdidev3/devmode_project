\
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlparse

from .envtools import load_project_env
from .registry import MODE_SPECS, ORDERED_MODE_KEYS


def _bool(value: str, default: bool = False) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _expand_path(root_dir: Path, value: Optional[str]) -> Optional[Path]:
    if not value:
        return None
    candidate = Path(os.path.expanduser(value))
    if not candidate.is_absolute():
        candidate = root_dir / candidate
    return candidate.resolve()


@dataclass
class AppConfig:
    app_key: str
    app_name: str
    env_prefix: str
    enabled: bool
    mode_kind: str
    listen_scheme: str
    auth_enabled: bool
    host: str
    port: int
    replicas: int
    state_dir: Path
    pid_file: Path
    port_file: Path
    info_file: Path
    log_file: Path
    users_file: Path
    tls_cert: Optional[Path]
    tls_key: Optional[Path]
    upstream_url: Optional[str]
    upstream_scheme: Optional[str]
    upstream_host: Optional[str]
    upstream_port: Optional[int]
    upstream_username: Optional[str]
    upstream_password: Optional[str]
    allowed_user: Optional[str]

    @property
    def tls_enabled(self) -> bool:
        return self.listen_scheme == "https"

    @property
    def uses_users(self) -> bool:
        return self.auth_enabled


class ProjectConfig:
    def __init__(self, root_dir: Path, env: Dict[str, str]):
        self.root_dir = root_dir
        self.env = env
        self.state_root = Path(os.path.expanduser(env.get("DEVMODE_STATE_ROOT", "~/.local/run"))).resolve()
        self.default_admin_user = env.get("DEVMODE_DEFAULT_ADMIN_USER", "admin")
        self.default_admin_password = env.get("DEVMODE_DEFAULT_ADMIN_PASSWORD", "admin123")
        self.setup_create_default_users = _bool(env.get("DEVMODE_SETUP_CREATE_DEFAULT_USERS", "true"), True)
        self.auto_generate_certs = _bool(env.get("DEVMODE_AUTO_GENERATE_CERTS", "true"), True)
        self.cert_days = int(env.get("DEVMODE_CERT_DAYS", "3650"))

    def app(self, app_key: str) -> AppConfig:
        spec = MODE_SPECS[app_key]
        env_prefix = spec["env_prefix"]
        app_name = spec["app_name"]
        state_dir = self.state_root / app_key
        host = self.env.get(f"{env_prefix}_HOST", self.env.get("DEVMODE_BIND_HOST", "0.0.0.0"))
        port = int(self.env.get(f"{env_prefix}_PORT", "0"))
        replicas = int(self.env.get(f"{env_prefix}_REPLICAS", "1"))
        enabled = _bool(self.env.get(f"{env_prefix}_ENABLED", "true"), True)
        auth_enabled = _bool(self.env.get(f"{env_prefix}_AUTH_ENABLED", str(spec["auth_enabled"]).lower()), spec["auth_enabled"])
        listen_scheme = self.env.get(f"{env_prefix}_SCHEME", spec["listen_scheme"]).lower()
        mode_kind = self.env.get(f"{env_prefix}_MODE_KIND", spec["mode_kind"]).lower()

        tls_cert = _expand_path(self.root_dir, self.env.get(f"{env_prefix}_TLS_CERT"))
        tls_key = _expand_path(self.root_dir, self.env.get(f"{env_prefix}_TLS_KEY"))

        upstream_url = self.env.get(f"{env_prefix}_UPSTREAM_URL")
        upstream_scheme = upstream_host = upstream_port = None
        if upstream_url:
            parsed = urlparse(upstream_url)
            upstream_scheme = parsed.scheme or "http"
            upstream_host = parsed.hostname
            upstream_port = parsed.port or (443 if upstream_scheme == "https" else 80)

        return AppConfig(
            app_key=app_key,
            app_name=app_name,
            env_prefix=env_prefix,
            enabled=enabled,
            mode_kind=mode_kind,
            listen_scheme=listen_scheme,
            auth_enabled=auth_enabled,
            host=host,
            port=port,
            replicas=max(1, replicas),
            state_dir=state_dir,
            pid_file=state_dir / "app.pid",
            port_file=state_dir / "app.port",
            info_file=state_dir / "app.json",
            log_file=state_dir / "app.log",
            users_file=state_dir / "users.json",
            tls_cert=tls_cert,
            tls_key=tls_key,
            upstream_url=upstream_url,
            upstream_scheme=upstream_scheme,
            upstream_host=upstream_host,
            upstream_port=upstream_port,
            upstream_username=self.env.get(f"{env_prefix}_UPSTREAM_USERNAME"),
            upstream_password=self.env.get(f"{env_prefix}_UPSTREAM_PASSWORD"),
            allowed_user=self.env.get(f"{env_prefix}_ALLOWED_USER") or None,
        )

    def all_apps(self) -> List[AppConfig]:
        return [self.app(key) for key in ORDERED_MODE_KEYS]

    def enabled_apps(self) -> List[AppConfig]:
        return [app for app in self.all_apps() if app.enabled]


def load_config(root_dir: Path) -> ProjectConfig:
    env = load_project_env(root_dir, override=True)
    return ProjectConfig(root_dir=root_dir, env=env)
