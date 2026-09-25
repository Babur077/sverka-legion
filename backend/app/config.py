from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

if load_dotenv is not None:
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


ENVIRONMENT = _env("RECONCILEHUB_ENV", "development").lower()
IS_PRODUCTION = ENVIRONMENT in {"prod", "production"}
HOST = _env("RECONCILEHUB_HOST", "0.0.0.0")
try:
    PORT = max(1, min(65535, int(_env("RECONCILEHUB_PORT", "8000"))))
except ValueError:
    PORT = 8000

_raw_origins = _env("RECONCILEHUB_ALLOWED_ORIGINS")
if _raw_origins:
    ALLOWED_ORIGINS = [
        item.strip()
        for item in _raw_origins.split(",")
        if item.strip()
    ]
else:
    # In production the React app is normally served by the same FastAPI origin,
    # so no cross-origin access is required by default.
    ALLOWED_ORIGINS = [] if IS_PRODUCTION else ["*"]

LOG_LEVEL = _env("RECONCILEHUB_LOG_LEVEL", "INFO").upper()
LOG_DIR = Path(_env("RECONCILEHUB_LOG_DIR", "logs"))

BACKUP_ENABLED = _env(
    "RECONCILEHUB_BACKUP_ENABLED",
    "true" if IS_PRODUCTION else "false",
).lower() in {"1", "true", "yes", "on"}
BACKUP_DIR = Path(_env("RECONCILEHUB_BACKUP_DIR", "backups"))
try:
    BACKUP_INTERVAL_HOURS = max(
        1.0,
        float(_env("RECONCILEHUB_BACKUP_INTERVAL_HOURS", "24")),
    )
except ValueError:
    BACKUP_INTERVAL_HOURS = 24.0
try:
    BACKUP_RETENTION_DAYS = max(
        1,
        int(_env("RECONCILEHUB_BACKUP_RETENTION_DAYS", "14")),
    )
except ValueError:
    BACKUP_RETENTION_DAYS = 14
