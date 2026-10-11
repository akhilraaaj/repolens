"""Load apps/api/.env into the process without overriding variables already set."""

import os
from pathlib import Path

_ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


def load_local_env() -> None:
    if not _ENV_FILE.is_file():
        return
    for raw in _ENV_FILE.read_text().splitlines():
        line = raw.strip()
        if line == "" or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key == "" or key in os.environ:
            continue
        os.environ[key] = value.strip().strip('"').strip("'")
