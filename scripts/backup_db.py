from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.logging_config import configure_logging  # noqa: E402
from backend.app.services.backups import cleanup_old_backups, create_backup  # noqa: E402
from utils.db_manager import init_db  # noqa: E402


if __name__ == "__main__":
    configure_logging()
    init_db()
    path = create_backup()
    removed = cleanup_old_backups()
    print(f"Backup created: {path}")
    if removed:
        print(f"Expired backups removed: {removed}")
