from __future__ import annotations

from typing import Any

from utils.db_manager import (
    delete_reconciliation_run,
    get_reconciliation_runs,
    save_reconciliation_run,
)


def save_run(module_id: str, username: str, payload: dict[str, Any]):
    return save_reconciliation_run(module_id, username, payload)


def list_runs(module_id: str) -> list[dict]:
    return get_reconciliation_runs(module_id)


def delete_run(module_id: str, record_id: int) -> bool:
    return delete_reconciliation_run(module_id, record_id)
