from __future__ import annotations

from typing import Any

from utils.db_manager import (
    delete_reconciliation_run,
    get_reconciliation_run,
    get_reconciliation_run_reviews,
    get_reconciliation_run_summaries,
    get_reconciliation_runs,
    save_reconciliation_run,
    save_reconciliation_run_review,
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


def list_run_reviews(module_id: str, run_id: str) -> list[dict]:
    return get_reconciliation_run_reviews(module_id, run_id)


def save_run_review(
    module_id: str,
    run_id: str,
    row_key: str,
    comment: str,
    reviewed: bool,
    username: str,
) -> dict:
    return save_reconciliation_run_review(
        module_id,
        run_id,
        row_key,
        comment,
        reviewed,
        username,
    )


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
