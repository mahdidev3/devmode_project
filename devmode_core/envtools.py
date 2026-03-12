\
import os
import re
from pathlib import Path
from typing import Dict

_VAR_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def parse_dotenv(env_file: Path) -> Dict[str, str]:
    data: Dict[str, str] = {}
    if not env_file.exists():
        return data

    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if value and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        data[key] = value

    changed = True
    while changed:
        changed = False
        for key, value in list(data.items()):
            expanded = _VAR_RE.sub(lambda m: data.get(m.group(1), os.environ.get(m.group(1), "")), value)
            if expanded != value:
                data[key] = expanded
                changed = True
    return data


def apply_env(env_map: Dict[str, str], override: bool = False) -> None:
    for key, value in env_map.items():
        if override or key not in os.environ:
            os.environ[key] = value


def load_project_env(root_dir: Path, override: bool = False) -> Dict[str, str]:
    env_file = root_dir / ".env"
    env_map = parse_dotenv(env_file)
    apply_env(env_map, override=override)
    return env_map
