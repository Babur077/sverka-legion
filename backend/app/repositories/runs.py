from __future__ import annotations

from typing import Any

from utils.db_manager import (
    delete_reconciliation_run,
    get_reconciliation_run,
    get_reconciliation_run_summaries,
    get_reconciliation_runs,
    save_reconciliation_run,
)


def save_run(
    module_id: str,
    username: str,
    payload: dict[str, Any],
    *,
    allow_owner_override: bool = False,
):
    return save_reconciliation_run(
        module_id,
        username,
        payload,
        allow_owner_override=allow_owner_override,
    )


def list_runs(module_id: str) -> list[dict]:
    return get_reconciliation_runs(module_id)


def list_run_summaries(module_id: str) -> list[dict]:
    return get_reconciliation_run_summaries(module_id)


def get_run(module_id: str, record_id: int) -> dict | None:
    return get_reconciliation_run(module_id, record_id)


def delete_run(
    module_id: str,
    record_id: int,
    username: str,
    *,
    allow_owner_override: bool = False,
) -> bool:
    return delete_reconciliation_run(
        module_id,
        record_id,
        username,
        allow_owner_override=allow_owner_override,
    )
