from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Header, HTTPException, Request

from backend.app.http_utils import json_safe
from backend.app.services.archive_authority import update_ravan_archive_match
from backend.app.services.reconciliation import (
    execute_module,
    list_module_runs,
    remove_module_run,
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
    x_user: Optional[str] = Header("admin"),
):
    perms = get_user_permissions(x_user)
    if (
        not has_permission(perms, f"{module_id}.view")
        and not has_permission(perms, "archive.view")
        and "*" not in perms
    ):
        raise HTTPException(status_code=403, detail="Доступ к архиву ограничен")
    return json_safe(list_module_runs(module_id))


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
