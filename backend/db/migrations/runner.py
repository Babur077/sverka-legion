from __future__ import annotations

import importlib
import pkgutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

VERSIONS_PACKAGE = "backend.db.migrations.versions"


def _ensure_migrations_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at TEXT NOT NULL
        )
        """
    )
    conn.commit()


def _discover_migrations() -> list[tuple[int, str, Callable[[sqlite3.Connection], None]]]:
    package = importlib.import_module(VERSIONS_PACKAGE)
    package_path = Path(package.__file__).parent
    migrations: list[tuple[int, str, Callable[[sqlite3.Connection], None]]] = []

    for module_info in pkgutil.iter_modules([str(package_path)]):
        if not module_info.name.startswith("v"):
            continue
        module = importlib.import_module(f"{VERSIONS_PACKAGE}.{module_info.name}")
        version = int(getattr(module, "VERSION"))
        name = str(getattr(module, "NAME"))
        upgrade = getattr(module, "upgrade")
        migrations.append((version, name, upgrade))

    return sorted(migrations, key=lambda item: item[0])


def run_migrations(db_path: str) -> list[int]:
    """Apply pending migrations in order and return applied version numbers."""
    with sqlite3.connect(db_path) as conn:
        _ensure_migrations_table(conn)
        applied = {
            int(row[0])
            for row in conn.execute("SELECT version FROM schema_migrations").fetchall()
        }

        newly_applied: list[int] = []
        for version, name, upgrade in _discover_migrations():
            if version in applied:
                continue

            try:
                conn.execute("BEGIN")
                upgrade(conn)
                conn.execute(
                    "INSERT INTO schema_migrations (version, name, applied_at) VALUES (?, ?, ?)",
                    (
                        version,
                        name,
                        datetime.now(timezone.utc).isoformat(),
                    ),
                )
                conn.commit()
                newly_applied.append(version)
            except Exception:
                conn.rollback()
                raise

        return newly_applied


def get_applied_migrations(db_path: str) -> list[dict]:
    with sqlite3.connect(db_path) as conn:
        _ensure_migrations_table(conn)
        rows = conn.execute(
            "SELECT version, name, applied_at FROM schema_migrations ORDER BY version"
        ).fetchall()
    return [
        {"version": int(version), "name": str(name), "applied_at": str(applied_at)}
        for version, name, applied_at in rows
    ]
