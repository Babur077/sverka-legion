from __future__ import annotations

import logging
import sqlite3
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

from backend.app.config import (
    BACKUP_DIR,
    BACKUP_ENABLED,
    BACKUP_INTERVAL_HOURS,
    BACKUP_RETENTION_DAYS,
)
import utils.db_manager as db


logger = logging.getLogger(__name__)

_thread: threading.Thread | None = None
_stop_event = threading.Event()
_lock = threading.Lock()


def create_backup(
    *,
    destination_dir: Path | None = None,
    now: datetime | None = None,
) -> Path:
    source_path = Path(db.DB_PATH)
    if not source_path.exists():
        raise FileNotFoundError(f"Database not found: {source_path}")

    target_dir = destination_dir or BACKUP_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    stamp = (now or datetime.now()).strftime("%Y%m%d_%H%M%S")
    target_path = target_dir / f"reconcile_hub_{stamp}.db"

    with sqlite3.connect(str(source_path), timeout=30) as source:
        with sqlite3.connect(str(target_path), timeout=30) as target:
            source.backup(target)

    logger.info("SQLite backup created path=%s", target_path)
    return target_path


def cleanup_old_backups(
    *,
    destination_dir: Path | None = None,
    retention_days: int | None = None,
    now: datetime | None = None,
) -> int:
    target_dir = destination_dir or BACKUP_DIR
    if not target_dir.exists():
        return 0

    days = retention_days if retention_days is not None else BACKUP_RETENTION_DAYS
    cutoff = (now or datetime.now()) - timedelta(days=max(1, int(days)))
    removed = 0

    for path in target_dir.glob("reconcile_hub_*.db"):
        try:
            modified = datetime.fromtimestamp(path.stat().st_mtime)
            if modified < cutoff:
                path.unlink()
                removed += 1
        except OSError:
            logger.exception("Failed to inspect/remove old backup path=%s", path)

    if removed:
        logger.info("Removed %s expired SQLite backups", removed)
    return removed


def _backup_loop() -> None:
    interval_seconds = BACKUP_INTERVAL_HOURS * 3600
    while not _stop_event.wait(interval_seconds):
        try:
            create_backup()
            cleanup_old_backups()
        except Exception:
            logger.exception("Scheduled SQLite backup failed")


def start_backup_worker() -> None:
    global _thread
    if not BACKUP_ENABLED:
        logger.info("SQLite automatic backups are disabled")
        return

    with _lock:
        if _thread and _thread.is_alive():
            return

        try:
            create_backup()
            cleanup_old_backups()
        except Exception:
            logger.exception("Startup SQLite backup failed")

        _stop_event.clear()
        _thread = threading.Thread(
            target=_backup_loop,
            name="reconcilehub-backup-worker",
            daemon=True,
        )
        _thread.start()


def stop_backup_worker() -> None:
    _stop_event.set()
