from __future__ import annotations

import time
from datetime import datetime
from typing import Any, Dict

from fastapi import HTTPException, Request

from backend.app.http_utils import json_safe
from backend.app.repositories.run_results import cache_run_result
from backend.app.services.archive_authority import prepare_authoritative_archive_payload
from backend.app.repositories.runs import delete_run, list_runs, save_run
from modules.registry import module_registry
from utils.permissions import record_audit_event


def require_module(module_id: str):
    module = module_registry.get_module(module_id)
    if not module:
        raise HTTPException(status_code=404, detail=f"Модуль сверки '{module_id}' не найден")
    return module


async def execute_module(module_id: str, request: Request, username: str):
    module = require_module(module_id)
    if module.manifest.status != "active":
        raise HTTPException(
            status_code=409,
            detail=f"Модуль '{module_id}' имеет статус '{module.manifest.status}' и пока недоступен для запуска",
        )

    form = await request.form()
    files_dict: Dict[str, bytes] = {}
    params_dict: Dict[str, Any] = {}

    for key, value in form.items():
        if hasattr(value, "read"):
            files_dict[key] = await value.read()
            params_dict[f"{key}_filename"] = getattr(value, "filename", "")
        else:
            params_dict[key] = value

    started = time.time()
    try:
        validation = module.validate_inputs(files_dict, params_dict)
        if not validation.is_valid:
            raise HTTPException(status_code=400, detail={"errors": validation.errors})

        result = module.run(files_dict, params_dict)
        result_payload = result.model_dump()
        source_files = [
            str(value)
            for key, value in params_dict.items()
            if key.endswith("_filename") and str(value or "").strip()
        ]
        cache_run_result(
            module_id,
            result.run_id,
            username,
            result_payload,
            params=params_dict,
            source_files=source_files,
        )
        duration = (time.time() - started) * 1000
        record_audit_event(
            user_id=username,
            action="RECONCILIATION_RUN",
            module_id=module_id,
            object_type="RunResult",
            object_id=result.run_id,
            status="SUCCESS",
            duration_ms=duration,
            details=(
                f"Записей А: {result.summary.total_records_a}, "
                f"Записей B: {result.summary.total_records_b}, "
                f"Сходимость: {result.summary.match_percentage}%"
            ),
        )
        return json_safe(result_payload)
    except HTTPException:
        raise
    except Exception as exc:
        duration = (time.time() - started) * 1000
        record_audit_event(
            user_id=username,
            action="RECONCILIATION_RUN_FAILED",
            module_id=module_id,
            status="FAILED",
            duration_ms=duration,
            details=str(exc),
        )
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка выполнения модуля: {exc}",
        ) from exc


def save_module_run(
    module_id: str,
    username: str,
    payload: dict[str, Any],
    *,
    allow_owner_override: bool = False,
) -> dict:
    require_module(module_id)
    normalized = prepare_authoritative_archive_payload(
        module_id,
        username,
        dict(payload or {}),
        allow_owner_override=allow_owner_override,
    )
    if not normalized.get("period_month"):
        normalized["period_month"] = datetime.now().strftime("%Y-%m")

    ok, message, record_id = save_run(
        module_id,
        username,
        normalized,
        allow_owner_override=allow_owner_override,
    )
    if not ok:
        status_code = 403 if "Нет прав на изменение архивной записи" in message else 500
        raise HTTPException(status_code=status_code, detail=message)

    record_audit_event(
        user_id=username,
        action="ARCHIVE_SAVE",
        module_id=module_id,
        object_type="ReconciliationRun",
        object_id=str(record_id or ""),
        status="SUCCESS",
        details=message,
    )
    return {"success": True, "message": message, "id": record_id}


def list_module_runs(module_id: str) -> list[dict]:
    require_module(module_id)
    return list_runs(module_id)


def remove_module_run(
    module_id: str,
    record_id: int,
    username: str,
    *,
    allow_owner_override: bool = False,
) -> None:
    require_module(module_id)
    if not delete_run(
        module_id,
        record_id,
        username,
        allow_owner_override=allow_owner_override,
    ):
        raise HTTPException(status_code=404, detail="Запись архива не найдена")

    record_audit_event(
        user_id=username,
        action="ARCHIVE_DELETE",
        module_id=module_id,
        object_type="ReconciliationRun",
        object_id=str(record_id),
        status="SUCCESS",
        details=f"Удалена запись журнала #{record_id}",
    )
