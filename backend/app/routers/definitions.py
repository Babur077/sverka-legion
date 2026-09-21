from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Header, HTTPException, Request

from backend.app.repositories.definitions import (
    deactivate_definition,
    get_definition,
    get_definition_version,
    list_definition_versions,
    list_definitions,
    restore_definition_version,
    save_definition,
)
from utils.permissions import get_user_permissions, has_permission, record_audit_event

router = APIRouter(prefix="/api/reconciliation-definitions", tags=["reconciliation-definitions"])


def _can_view(perms: list[str]) -> bool:
    return (
        "*" in perms
        or has_permission(perms, "reconciliation_builder.view")
        or has_permission(perms, "reconciliation_builder.run")
        or has_permission(perms, "reconciliation_builder.manage")
    )


@router.get("")
async def fetch_definitions(x_user: Optional[str] = Header("admin")):
    perms = get_user_permissions(x_user)
    if not _can_view(perms):
        raise HTTPException(status_code=403, detail="Нет прав на просмотр шаблонов сверки")
    return list_definitions(active_only=True)


@router.get("/{definition_id}")
async def fetch_definition(
    definition_id: int,
    x_user: Optional[str] = Header("admin"),
):
    perms = get_user_permissions(x_user)
    if not _can_view(perms):
        raise HTTPException(status_code=403, detail="Нет прав на просмотр шаблонов сверки")
    item = get_definition(definition_id)
    if not item or not item.get("is_active"):
        raise HTTPException(status_code=404, detail="Шаблон не найден")
    return item


@router.post("")
async def create_definition(
    payload: Dict[str, Any],
    request: Request,
    x_user: Optional[str] = Header("admin"),
):
    perms = get_user_permissions(x_user)
    if not has_permission(perms, "reconciliation_builder.manage") and "*" not in perms:
        raise HTTPException(status_code=403, detail="Нет прав на сохранение шаблонов")

    config = payload.get("config")
    if not isinstance(config, dict):
        raise HTTPException(status_code=400, detail="config должен быть объектом")

    ok, message, record_id = save_definition(
        name=str(payload.get("name") or ""),
        description=str(payload.get("description") or ""),
        config=config,
        username=x_user or "",
        change_note=str(payload.get("change_note") or ""),
    )
    if not ok:
        raise HTTPException(status_code=400, detail=message)

    record_audit_event(
        user_id=x_user or "",
        action="CREATE_RECON_DEFINITION",
        module_id="reconciliation_builder",
        object_type="ReconciliationDefinition",
        object_id=str(record_id),
        ip_address=request.client.host if request.client else "127.0.0.1",
        details=message,
    )
    item = get_definition(int(record_id)) if record_id is not None else None
    return {
        "success": True,
        "message": message,
        "id": record_id,
        "version_id": item.get("active_version_id") if item else None,
        "version_number": item.get("current_version_number") if item else None,
    }


@router.put("/{definition_id}")
async def update_definition(
    definition_id: int,
    payload: Dict[str, Any],
    request: Request,
    x_user: Optional[str] = Header("admin"),
):
    perms = get_user_permissions(x_user)
    if not has_permission(perms, "reconciliation_builder.manage") and "*" not in perms:
        raise HTTPException(status_code=403, detail="Нет прав на изменение шаблонов")

    config = payload.get("config")
    if not isinstance(config, dict):
        raise HTTPException(status_code=400, detail="config должен быть объектом")

    ok, message, record_id = save_definition(
        definition_id=definition_id,
        name=str(payload.get("name") or ""),
        description=str(payload.get("description") or ""),
        config=config,
        username=x_user or "",
        change_note=str(payload.get("change_note") or ""),
    )
    if not ok:
        raise HTTPException(status_code=400, detail=message)

    record_audit_event(
        user_id=x_user or "",
        action="UPDATE_RECON_DEFINITION",
        module_id="reconciliation_builder",
        object_type="ReconciliationDefinition",
        object_id=str(record_id),
        ip_address=request.client.host if request.client else "127.0.0.1",
        details=message,
    )
    item = get_definition(definition_id)
    return {
        "success": True,
        "message": message,
        "id": record_id,
        "version_id": item.get("active_version_id") if item else None,
        "version_number": item.get("current_version_number") if item else None,
    }


@router.get("/{definition_id}/versions")
async def fetch_definition_versions(
    definition_id: int,
    x_user: Optional[str] = Header("admin"),
):
    perms = get_user_permissions(x_user)
    if not _can_view(perms):
        raise HTTPException(status_code=403, detail="Нет прав на просмотр версий шаблона")
    item = get_definition(definition_id)
    if not item:
        raise HTTPException(status_code=404, detail="Шаблон не найден")
    return list_definition_versions(definition_id)


@router.get("/{definition_id}/versions/{version_id}")
async def fetch_definition_version(
    definition_id: int,
    version_id: int,
    x_user: Optional[str] = Header("admin"),
):
    perms = get_user_permissions(x_user)
    if not _can_view(perms):
        raise HTTPException(status_code=403, detail="Нет прав на просмотр версий шаблона")
    item = get_definition_version(definition_id, version_id)
    if not item:
        raise HTTPException(status_code=404, detail="Версия шаблона не найдена")
    return item


@router.post("/{definition_id}/versions/{version_id}/restore")
async def restore_definition_version_route(
    definition_id: int,
    version_id: int,
    payload: Dict[str, Any],
    request: Request,
    x_user: Optional[str] = Header("admin"),
):
    perms = get_user_permissions(x_user)
    if not has_permission(perms, "reconciliation_builder.manage") and "*" not in perms:
        raise HTTPException(status_code=403, detail="Нет прав на восстановление версий")

    ok, message, item = restore_definition_version(
        definition_id=definition_id,
        version_id=version_id,
        username=x_user or "",
        change_note=str(payload.get("change_note") or ""),
    )
    if not ok or not item:
        raise HTTPException(status_code=400, detail=message)

    record_audit_event(
        user_id=x_user or "",
        action="RESTORE_RECON_DEFINITION_VERSION",
        module_id="reconciliation_builder",
        object_type="ReconciliationDefinition",
        object_id=str(definition_id),
        ip_address=request.client.host if request.client else "127.0.0.1",
        details=message,
    )
    return {
        "success": True,
        "message": message,
        "definition": item,
    }


@router.delete("/{definition_id}")
async def delete_definition(
    definition_id: int,
    request: Request,
    x_user: Optional[str] = Header("admin"),
):
    perms = get_user_permissions(x_user)
    if not has_permission(perms, "reconciliation_builder.manage") and "*" not in perms:
        raise HTTPException(status_code=403, detail="Нет прав на удаление шаблонов")

    if not deactivate_definition(definition_id):
        raise HTTPException(status_code=404, detail="Шаблон не найден")

    record_audit_event(
        user_id=x_user or "",
        action="DELETE_RECON_DEFINITION",
        module_id="reconciliation_builder",
        object_type="ReconciliationDefinition",
        object_id=str(definition_id),
        ip_address=request.client.host if request.client else "127.0.0.1",
        details=f"Шаблон #{definition_id} деактивирован",
    )
    return {"success": True}
