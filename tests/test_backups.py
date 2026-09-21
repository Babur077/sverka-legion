from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timedelta

import utils.db_manager as db
from backend.app.services import backups


def test_sqlite_backup_creates_consistent_copy(tmp_path, monkeypatch):
    source = tmp_path / "source.db"
    destination = tmp_path / "backups"
    monkeypatch.setattr(db, "DB_PATH", str(source))
    monkeypatch.setattr(backups.db, "DB_PATH", str(source))

    with sqlite3.connect(source) as conn:
        conn.execute("CREATE TABLE sample (id INTEGER PRIMARY KEY, value TEXT)")
        conn.execute("INSERT INTO sample (value) VALUES ('ok')")
        conn.commit()

    path = backups.create_backup(
        destination_dir=destination,
        now=datetime(2026, 9, 21, 12, 0, 0),
    )

    assert path.exists()
    assert path.name == "reconcile_hub_20260921_120000.db"

    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT value FROM sample").fetchone()[0] == "ok"


def test_backup_retention_removes_only_expired_files(tmp_path):
    destination = tmp_path / "backups"
    destination.mkdir()
    old_file = destination / "reconcile_hub_20260801_000000.db"
    fresh_file = destination / "reconcile_hub_20260920_000000.db"
    old_file.write_bytes(b"old")
    fresh_file.write_bytes(b"fresh")

    now = datetime(2026, 9, 21, 12, 0, 0)
    old_time = (now - timedelta(days=30)).timestamp()
    fresh_time = (now - timedelta(days=1)).timestamp()
    os.utime(old_file, (old_time, old_time))
    os.utime(fresh_file, (fresh_time, fresh_time))

    removed = backups.cleanup_old_backups(
        destination_dir=destination,
        retention_days=14,
        now=now,
    )

    assert removed == 1
    assert not old_file.exists()
    assert fresh_file.exists()
