\
import argparse
from pathlib import Path

from .config import load_config
from .proxy_server import run_server


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app-key", required=True)
    parser.add_argument("--root-dir", required=True)
    args = parser.parse_args()

    root_dir = Path(args.root_dir).resolve()
    config = load_config(root_dir).app(args.app_key)
    run_server(config)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
