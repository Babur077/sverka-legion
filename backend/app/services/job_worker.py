from __future__ import annotations

import json
import shutil
import threading
import time
from pathlib import Path
from typing import Any

from backend.app.repositories import jobs
from backend.app.repositories.runs import save_run
from backend.app.services.reconciliation import require_module
from modules.registry import module_registry
from utils.permissions import record_audit_event
import utils.db_manager as db


_worker_thread: threading.Thread | None = None
_stop_event = threading.Event()
_worker_lock = threading.Lock()


def _job_root(job_id: int) -> Path:
    return Path(db.DB_PATH).parent / "job_files" / str(job_id)


def cleanup_job_files(job: dict[str, Any] | None) -> None:
    if not job:
        return
    shutil.rmtree(_job_root(int(job["id"])), ignore_errors=True)


async def persist_uploaded_files(
    job_id: int,
    form_items: list[tuple[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    root = _job_root(job_id)
    root.mkdir(parents=True, exist_ok=True)

    files_payload: dict[str, Any] = {}
    params: dict[str, Any] = {}

    for key, value in form_items:
        if hasattr(value, "read"):
            file_path = root / f"{len(files_payload) + 1:02d}_{key}.bin"
            with file_path.open("wb") as handle:
                while True:
                    chunk = await value.read(1024 * 1024)
                    if not chunk:
                        break
                    handle.write(chunk)

            files_payload[key] = {
                "path": str(file_path),
                "filename": str(getattr(value, "filename", "") or ""),
            }
            params[f"{key}_filename"] = str(getattr(value, "filename", "") or "")
        else:
            params[key] = str(value)

    jobs.set_job_files(job_id, files_payload)
    return files_payload, params


def _read_files(job: dict[str, Any]) -> dict[str, bytes]:
    result: dict[str, bytes] = {}
    for key, meta in (job.get("files") or {}).items():
        path = Path(str((meta or {}).get("path") or ""))
        if not path.exists():
            raise FileNotFoundError(f"Файл задачи не найден: {key}")
        result[key] = path.read_bytes()
    return result


def _archive_result(
    job: dict[str, Any],
    result_payload: dict[str, Any],
) -> None:
    request_payload = job.get("request") or {}
    archive_payload = dict(request_payload.get("archive_payload") or {})
    source_files = [
        str((meta or {}).get("filename") or "")
        for meta in (job.get("files") or {}).values()
        if str((meta or {}).get("filename") or "")
    ]

    archive_payload.update({
        "run_id": result_payload.get("run_id"),
        "status": result_payload.get("status", "COMPLETED"),
        "source_files": archive_payload.get("source_files") or source_files,
        "summary": result_payload.get("summary") or {},
        "result_snapshot": result_payload,
        "archive_schema_version": max(
            int(archive_payload.get("archive_schema_version") or 0),
            1,
        ),
    })

    ok, message, _ = save_run(
        str(job["module_id"]),
        str(job["created_by"]),
        archive_payload,
    )
    if not ok:
        raise RuntimeError(message)


def _process_job(job: dict[str, Any]) -> None:
    job_id = int(job["id"])
    started = time.time()
    try:
        if jobs.is_cancel_requested(job_id):
            jobs.cancel_running_job(job_id)
            return

        jobs.update_job_progress(job_id, 10, "Чтение файлов")
        files_dict = _read_files(job)

        if jobs.is_cancel_requested(job_id):
            jobs.cancel_running_job(job_id)
            return

        module_id = str(job["module_id"])
        module = require_module(module_id)
        if module.manifest.status != "active":
            raise RuntimeError(
                f"Модуль '{module_id}' имеет статус '{module.manifest.status}'"
            )

        params = dict((job.get("request") or {}).get("params") or {})
        jobs.update_job_progress(job_id, 20, "Проверка входных данных")
        validation = module.validate_inputs(files_dict, params)
        if not validation.is_valid:
            raise ValueError("; ".join(validation.errors))

        if jobs.is_cancel_requested(job_id):
            jobs.cancel_running_job(job_id)
            return

        jobs.update_job_progress(job_id, 40, "Выполнение сверки")
        result = module.run(files_dict, params)
        result_payload = result.model_dump()

        if jobs.is_cancel_requested(job_id):
            jobs.cancel_running_job(job_id)
            return

        jobs.update_job_progress(job_id, 90, "Сохранение результата")
        _archive_result(job, result_payload)

        duration = (time.time() - started) * 1000
        record_audit_event(
            user_id=str(job["created_by"]),
            action="RECONCILIATION_JOB_COMPLETED",
            module_id=module_id,
            object_type="ReconciliationJob",
            object_id=str(job_id),
            status="SUCCESS",
            duration_ms=duration,
            details=(
                f"Run {result.run_id}; "
                f"сходимость {result.summary.match_percentage}%"
            ),
        )
        jobs.complete_job(job_id, result.run_id)

    except Exception as exc:
        jobs.fail_job(job_id, str(exc))
        record_audit_event(
            user_id=str(job.get("created_by") or ""),
            action="RECONCILIATION_JOB_FAILED",
            module_id=str(job.get("module_id") or ""),
            object_type="ReconciliationJob",
            object_id=str(job_id),
            status="FAILED",
            duration_ms=(time.time() - started) * 1000,
            details=str(exc),
        )
    finally:
        cleanup_job_files(job)


def _worker_loop() -> None:
    jobs.recover_interrupted_jobs()
    while not _stop_event.is_set():
        job = jobs.claim_next_job()
        if job:
            _process_job(job)
            continue
        _stop_event.wait(0.75)


def start_job_worker() -> None:
    global _worker_thread
    with _worker_lock:
        if _worker_thread and _worker_thread.is_alive():
            return
        _stop_event.clear()
        _worker_thread = threading.Thread(
            target=_worker_loop,
            name="reconcilehub-job-worker",
            daemon=True,
        )
        _worker_thread.start()


def stop_job_worker() -> None:
    _stop_event.set()


def wake_job_worker() -> None:
    # The current MVP polls every 750ms, so no condition variable is required.
    # Keeping this function gives the router a stable hook for a future queue backend.
    return None
