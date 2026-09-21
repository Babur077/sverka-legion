from __future__ import annotations

import json
from typing import Any, Optional

from fastapi import APIRouter, Header, HTTPException, Request

from backend.app.repositories import jobs
from backend.app.services.job_worker import (
    cleanup_job_files,
    persist_uploaded_files,
    wake_job_worker,
)
from backend.app.services.reconciliation import require_module
from utils.permissions import get_user_permissions, has_permission, record_audit_event

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


def _require_run_permission(module_id: str, username: str) -> None:
    perms = get_user_permissions(username)
    if not has_permission(perms, f"{module_id}.run") and "*" not in perms:
        raise HTTPException(
            status_code=403,
            detail=f"Нет прав на запуск модуля '{module_id}'",
        )
    require_module(module_id)


def _public_job(job: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in job.items()
        if key not in {"request", "files"}
    }


@router.post("/{module_id}")
async def enqueue_job(
    module_id: str,
    request: Request,
    x_user: Optional[str] = Header("admin"),
):
    username = x_user or ""
    _require_run_permission(module_id, username)

    form = await request.form()
    raw_archive_payload = form.get("archive_payload")
    archive_payload: dict[str, Any] = {}
    if raw_archive_payload:
        try:
            parsed = json.loads(str(raw_archive_payload))
            if isinstance(parsed, dict):
                archive_payload = parsed
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="archive_payload должен быть JSON-объектом")

    job_id = jobs.create_job(
        module_id,
        username,
        {"params": {}, "archive_payload": archive_payload},
    )

    try:
        _, params = await persist_uploaded_files(job_id, list(form.multi_items()))
        params.pop("archive_payload", None)

        with __import__("sqlite3").connect(__import__("utils.db_manager", fromlist=["DB_PATH"]).DB_PATH) as conn:
            conn.execute(
                "UPDATE reconciliation_jobs SET request_json = ? WHERE id = ?",
                (
                    json.dumps(
                        {"params": params, "archive_payload": archive_payload},
                        ensure_ascii=False,
                        default=str,
                    ),
                    job_id,
                ),
            )
            conn.commit()

        record_audit_event(
            user_id=username,
            action="RECONCILIATION_JOB_QUEUED",
            module_id=module_id,
            object_type="ReconciliationJob",
            object_id=str(job_id),
            status="SUCCESS",
            details="Задача поставлена в очередь",
        )
        wake_job_worker()
        job = jobs.get_job(job_id)
        return _public_job(job or {"id": job_id, "status": "QUEUED"})
    except Exception:
        job = jobs.get_job(job_id)
        cleanup_job_files(job)
        jobs.fail_job(job_id, "Не удалось сохранить входные файлы задачи")
        raise


@router.get("")
async def fetch_jobs(
    module_id: Optional[str] = None,
    limit: int = 20,
    x_user: Optional[str] = Header("admin"),
):
    return [
        _public_job(job)
        for job in jobs.list_jobs(x_user or "", module_id=module_id, limit=limit)
    ]


@router.get("/{job_id}")
async def fetch_job(
    job_id: int,
    x_user: Optional[str] = Header("admin"),
):
    job = jobs.get_job(job_id)
    if not job or str(job.get("created_by")) != str(x_user or ""):
        raise HTTPException(status_code=404, detail="Задача не найдена")
    return _public_job(job)


@router.post("/{job_id}/cancel")
async def cancel_job(
    job_id: int,
    x_user: Optional[str] = Header("admin"),
):
    username = x_user or ""
    before = jobs.get_job(job_id)
    ok, message = jobs.request_cancel(job_id, username)
    if not ok:
        raise HTTPException(status_code=400, detail=message)

    after = jobs.get_job(job_id)
    if after and after.get("status") == "CANCELLED":
        cleanup_job_files(before)

    record_audit_event(
        user_id=username,
        action="RECONCILIATION_JOB_CANCEL",
        module_id=str((after or before or {}).get("module_id") or ""),
        object_type="ReconciliationJob",
        object_id=str(job_id),
        status="SUCCESS",
        details=message,
    )
    return _public_job(after or {"id": job_id, "status": "CANCELLED"})
