from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Header, HTTPException, Request

from backend.app.http_utils import json_safe
from backend.app.services.archive_authority import update_ravan_archive_match
from backend.app.services.source_preview import preview_source_file
from backend.app.services.test_vorona_storage import (
    SOURCE_TYPES as TEST_VORONA_SOURCE_TYPES,
    import_test_vorona_file,
)
from backend.app.services.reconciliation import (
    execute_module,
    get_module_run,
    get_module_run_reviews,
    list_module_runs,
    remove_module_run,
    save_module_run_review,
    require_module,
    save_module_run,
)
from modules.registry import module_registry
from utils.permissions import get_user_permissions, has_permission, record_audit_event

router = APIRouter(prefix="/api/modules", tags=["modules"])


@router.get("")
async def get_modules(x_user: Optional[str] = Header("admin")):
    perms = get_user_permissions(x_user)
    manifests = module_registry.list_manifests(user_permissions=perms)
    return [manifest.model_dump() for manifest in manifests]


@router.get("/test_vorona/imports")
async def get_test_vorona_imports(
    year: Optional[int] = None,
    month: Optional[int] = None,
    include_replaced: bool = True,
    x_user: Optional[str] = Header("admin"),
):
    perms = get_user_permissions(x_user)
    if (
        not has_permission(perms, "test_vorona.view")
        and not has_permission(perms, "test_vorona.run")
        and "*" not in perms
    ):
        raise HTTPException(status_code=403, detail="Нет прав на просмотр базы Тестовой вороны")

    require_module("test_vorona")
    return json_safe(list_test_vorona_import_batches(
        year=year,
        month=month,
        include_replaced=include_replaced,
    ))


@router.post("/test_vorona/imports/{source_type}")
async def upload_test_vorona_import(
    source_type: str,
    request: Request,
    x_user: Optional[str] = Header("admin"),
):
    perms = get_user_permissions(x_user)
    if not has_permission(perms, "test_vorona.run") and "*" not in perms:
        raise HTTPException(status_code=403, detail="Нет прав на загрузку данных Тестовой вороны")

    require_module("test_vorona")
    normalized_source = str(source_type or "").strip()
    if normalized_source not in TEST_VORONA_SOURCE_TYPES:
        raise HTTPException(status_code=404, detail="Неизвестный источник Тестовой вороны")

    form = await request.form()
    upload = form.get("file")
    if upload is None or not hasattr(upload, "read"):
        raise HTTPException(status_code=400, detail="Файл не передан")

    max_bytes = 200 * 1024 * 1024
    content = await upload.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise HTTPException(status_code=413, detail="Файл слишком большой. Максимум 200 МБ.")

    def optional_int(name: str) -> int | None:
        raw = str(form.get(name) or "").strip()
        if not raw:
            return None
        try:
            return int(raw)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"Некорректное поле {name}") from exc

    year = optional_int("year")
    month = optional_int("month")
    replace_existing = str(form.get("replace_existing") or "").strip().lower() in {
        "1", "true", "yes", "on",
    }

    if month is not None and not 1 <= month <= 12:
        raise HTTPException(status_code=400, detail="Месяц должен быть от 1 до 12")

    try:
        result = import_test_vorona_file(
            source_type=normalized_source,
            content=content,
            filename=getattr(upload, "filename", "") or "source.xlsx",
            year=year,
            month=month,
            username=x_user or "",
            replace_existing=replace_existing,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if result.get("state") == "conflict":
        raise HTTPException(status_code=409, detail=result)

    record_audit_event(
        user_id=x_user or "",
        action="TEST_VORONA_IMPORT",
        module_id="test_vorona",
        object_type="ImportBatch",
        object_id=str((result.get("batch") or {}).get("id") or ""),
        status="SUCCESS",
        details=(
            f"source={normalized_source}; state={result.get('state')}; "
            f"period={(result.get('batch') or {}).get('period_key')}"
        ),
    )
    return json_safe(result)


@router.get("/test_vorona/data/{source_type}")
async def get_test_vorona_data(
    source_type: str,
    year: int,
    through_month: Optional[int] = None,
    vid: Optional[str] = None,
    x_user: Optional[str] = Header("admin"),
):
    perms = get_user_permissions(x_user)
    if (
        not has_permission(perms, "test_vorona.view")
        and not has_permission(perms, "test_vorona.run")
        and "*" not in perms
    ):
        raise HTTPException(status_code=403, detail="Нет прав на просмотр базы Тестовой вороны")

    if source_type not in TEST_VORONA_SOURCE_TYPES:
        raise HTTPException(status_code=404, detail="Неизвестный источник Тестовой вороны")

    require_module("test_vorona")
    return json_safe(load_test_vorona_active_records(
        year=year,
        through_month=through_month,
        source_type=source_type,
        vid=vid,
    ))


@router.post("/test_vorona/run-stored")
async def run_test_vorona_from_database(
    payload: Dict[str, Any],
    x_user: Optional[str] = Header("admin"),
):
    perms = get_user_permissions(x_user)
    if not has_permission(perms, "test_vorona.run") and "*" not in perms:
        raise HTTPException(status_code=403, detail="Нет прав на запуск Тестовой вороны")

    try:
        year = int(payload.get("year"))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Укажите год сверки") from exc

    through_month_raw = payload.get("through_month")
    through_month = None
    if through_month_raw not in (None, ""):
        try:
            through_month = int(through_month_raw)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail="Некорректный месяц") from exc
        if not 1 <= through_month <= 12:
            raise HTTPException(status_code=400, detail="Месяц должен быть от 1 до 12")

    module = require_module("test_vorona")
    runner = getattr(module, "run_from_records", None)
    if not callable(runner):
        raise HTTPException(status_code=500, detail="Модуль не поддерживает запуск из базы")

    datasets = load_test_vorona_active_datasets(
        year=year,
        through_month=through_month,
    )
    if not any(datasets.get(key) for key in ("sales", "bank", "faktura", "one_c")):
        raise HTTPException(
            status_code=400,
            detail="В базе нет помесячных данных для выбранного периода.",
        )

    try:
        result = runner(
            datasets,
            year=year,
            through_month=through_month,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Ошибка расчёта Тестовой вороны: {exc}") from exc

    result_payload = result.model_dump()
    cache_run_result(
        "test_vorona",
        result.run_id,
        x_user or "",
        result_payload,
        params={
            "year": year,
            "through_month": through_month,
            "storage_mode": "persistent",
        },
        source_files=[
            str(batch.get("filename") or "")
            for batch in list_test_vorona_import_batches(
                year=year,
                include_replaced=False,
            )
            if batch.get("filename")
        ],
    )

    record_audit_event(
        user_id=x_user or "",
        action="RECONCILIATION_RUN",
        module_id="test_vorona",
        object_type="RunResult",
        object_id=result.run_id,
        status="SUCCESS",
        duration_ms=result.summary.execution_time_ms,
        details=(
            f"Persistent DB; year={year}; through_month={through_month}; "
            f"partners={result.summary.total_records_a}; "
            f"differences={result.summary.discrepancy_count}"
        ),
    )
    return json_safe(result_payload)


@router.post("/{module_id}/source-preview")
async def preview_module_source(
    module_id: str,
    request: Request,
    x_user: Optional[str] = Header("admin"),
):
    perms = get_user_permissions(x_user)
    if (
        not has_permission(perms, f"{module_id}.view")
        and not has_permission(perms, f"{module_id}.run")
        and "*" not in perms
    ):
        raise HTTPException(
            status_code=403,
            detail=f"У вас нет прав на просмотр источников модуля '{module_id}'",
        )

    require_module(module_id)
    form = await request.form()
    upload = form.get("file")
    if upload is None or not hasattr(upload, "read"):
        raise HTTPException(status_code=400, detail="Файл для preview не передан.")

    max_bytes = 200 * 1024 * 1024
    file_bytes = await upload.read(max_bytes + 1)
    if len(file_bytes) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail="Файл слишком большой. Максимальный размер preview — 200 МБ.",
        )

    requested_sheet = str(form.get("sheet_name") or "").strip() or None
    try:
        header_row = int(str(form.get("header_row") or "1"))
    except ValueError:
        header_row = 1

    return json_safe(preview_source_file(
        file_bytes,
        getattr(upload, "filename", "") or "source.xlsx",
        requested_sheet=requested_sheet,
        header_row=header_row,
    ))


@router.post("/{module_id}/run")
async def run_module_reconciliation(
    module_id: str,
    request: Request,
    x_user: Optional[str] = Header("admin"),
):
    perms = get_user_permissions(x_user)
    required_perm = f"{module_id}.run"
    if not has_permission(perms, required_perm) and "*" not in perms:
        raise HTTPException(
            status_code=403,
            detail=f"У вас нет прав на запуск модуля '{module_id}'",
        )
    return await execute_module(module_id, request, x_user or "")


@router.post("/{module_id}/archive")
async def save_module_archive(
    module_id: str,
    payload: Dict[str, Any],
    x_user: Optional[str] = Header("admin"),
):
    perms = get_user_permissions(x_user)
    if not has_permission(perms, f"{module_id}.run") and "*" not in perms:
        raise HTTPException(status_code=403, detail="Нет прав на сохранение результата сверки")
    return save_module_run(
        module_id,
        x_user or "",
        payload,
        allow_owner_override="*" in perms,
    )


@router.patch("/ravan_1c/archive/{run_id}/matches/{row_id}")
async def update_ravan_1c_archive_match(
    run_id: str,
    row_id: str,
    payload: Dict[str, Any],
    x_user: Optional[str] = Header("admin"),
):
    perms = get_user_permissions(x_user)
    if not has_permission(perms, "ravan_1c.run") and "*" not in perms:
        raise HTTPException(status_code=403, detail="Нет прав на изменение результата сверки")

    return json_safe(update_ravan_archive_match(
        x_user or "",
        run_id,
        row_id,
        str(payload.get("decision") or ""),
        allow_owner_override="*" in perms,
    ))


@router.get("/{module_id}/archive")
async def fetch_module_archive(
    module_id: str,
    summary_only: bool = False,
    x_user: Optional[str] = Header("admin"),
):
    perms = get_user_permissions(x_user)
    if (
        not has_permission(perms, f"{module_id}.view")
        and not has_permission(perms, "archive.view")
        and "*" not in perms
    ):
        raise HTTPException(status_code=403, detail="Доступ к архиву ограничен")
    return json_safe(list_module_runs(module_id, summary_only=summary_only))


@router.get("/{module_id}/archive/{record_id}")
async def fetch_module_archive_record(
    module_id: str,
    record_id: int,
    x_user: Optional[str] = Header("admin"),
):
    perms = get_user_permissions(x_user)
    if (
        not has_permission(perms, f"{module_id}.view")
        and not has_permission(perms, "archive.view")
        and "*" not in perms
    ):
        raise HTTPException(status_code=403, detail="Доступ к архиву ограничен")
    return json_safe(get_module_run(module_id, record_id))


@router.get("/{module_id}/reviews/{run_id}")
async def fetch_module_row_reviews(
    module_id: str,
    run_id: str,
    x_user: Optional[str] = Header("admin"),
):
    perms = get_user_permissions(x_user)
    if (
        not has_permission(perms, f"{module_id}.view")
        and not has_permission(perms, "archive.view")
        and "*" not in perms
    ):
        raise HTTPException(status_code=403, detail="Доступ к разбору сверки ограничен")
    return json_safe(get_module_run_reviews(module_id, run_id))


@router.put("/{module_id}/reviews/{run_id}")
async def update_module_row_review(
    module_id: str,
    run_id: str,
    payload: Dict[str, Any],
    x_user: Optional[str] = Header("admin"),
):
    perms = get_user_permissions(x_user)
    if not has_permission(perms, f"{module_id}.run") and "*" not in perms:
        raise HTTPException(status_code=403, detail="Нет прав на изменение разбора сверки")

    return json_safe(save_module_run_review(
        module_id,
        run_id,
        str(payload.get("row_key") or ""),
        str(payload.get("comment") or ""),
        bool(payload.get("reviewed", False)),
        x_user or "",
        smart_match_decision=payload.get("smart_match_decision"),
        smart_match_candidate=payload.get("smart_match_candidate"),
    ))


@router.delete("/{module_id}/archive/{record_id}")
async def remove_module_archive(
    module_id: str,
    record_id: int,
    x_user: Optional[str] = Header("admin"),
):
    perms = get_user_permissions(x_user)
    if not has_permission(perms, f"{module_id}.run") and "*" not in perms:
        raise HTTPException(status_code=403, detail="Нет прав на удаление записи архива")
    remove_module_run(
        module_id,
        record_id,
        x_user or "",
        allow_owner_override="*" in perms,
    )
    return {"success": True}


@router.get("/{module_id}/analytics")
async def get_module_analytics(
    module_id: str,
    x_user: Optional[str] = Header("admin"),
):
    perms = get_user_permissions(x_user)
    if (
        not has_permission(perms, f"{module_id}.view")
        and not has_permission(perms, "analytics.view_all")
        and "*" not in perms
    ):
        raise HTTPException(status_code=403, detail="Доступ к аналитике этого модуля ограничен")

    module = require_module(module_id)
    return module.get_analytics()
