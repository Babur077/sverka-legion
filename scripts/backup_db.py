from __future__ import annotations

from backend.app.logging_config import configure_logging
from backend.app.services.backups import cleanup_old_backups, create_backup
from utils.db_manager import init_db


if __name__ == "__main__":
    configure_logging()
    init_db()
    path = create_backup()
    removed = cleanup_old_backups()
    print(f"Backup created: {path}")
    if removed:
        print(f"Expired backups removed: {removed}")
