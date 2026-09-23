from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Header, HTTPException, Request

from backend.app.http_utils import json_safe
from backend.app.services.archive_authority import update_ravan_archive_match
from backend.app.services.source_preview import preview_source_file
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
from utils.permissions import get_user_permissions, has_permission

router = APIRouter(prefix="/api/modules", tags=["modules"])


@router.get("")
async def get_modules(x_user: Optional[str] = Header("admin")):
    perms = get_user_permissions(x_user)
    manifests = module_registry.list_manifests(user_permissions=perms)
    return [manifest.model_dump() for manifest in manifests]


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
