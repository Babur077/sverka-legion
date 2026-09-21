from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Header, HTTPException

from backend.app.http_utils import json_safe
from backend.app.services.audit_ai import analyze_audit_event
from utils.permissions import (
    get_audit_event,
    get_audit_filter_options,
    get_user_permissions,
    has_permission,
    query_audit_events,
)

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("/filters")
async def fetch_audit_filters(x_user: Optional[str] = Header("admin")):
    perms = get_user_permissions(x_user)
    if not has_permission(perms, "audit.view") and "*" not in perms:
        raise HTTPException(
            status_code=403,
            detail="Нет прав на просмотр журнала аудита",
        )
    return get_audit_filter_options()


@router.post("/{event_id}/ai")
async def analyze_audit_log(
    event_id: int,
    x_user: Optional[str] = Header("admin"),
):
    perms = get_user_permissions(x_user)
    if not has_permission(perms, "audit.view") and "*" not in perms:
        raise HTTPException(
            status_code=403,
            detail="Нет прав на AI-анализ журнала аудита",
        )

    event = get_audit_event(event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Событие аудита не найдено")

    return json_safe(analyze_audit_event(event))


@router.get("")
async def fetch_audit_trail(
    limit: int = 100,
    offset: int = 0,
    user: Optional[str] = None,
    action: Optional[str] = None,
    module_id: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    x_user: Optional[str] = Header("admin"),
):
    perms = get_user_permissions(x_user)
    if not has_permission(perms, "audit.view") and "*" not in perms:
        raise HTTPException(
            status_code=403,
            detail="Нет прав на просмотр журнала аудита",
        )

    normalized_date_from = None
    normalized_date_to = None
    try:
        if date_from:
            normalized_date_from = datetime.strptime(
                date_from,
                "%Y-%m-%d",
            ).isoformat()
        if date_to:
            normalized_date_to = (
                datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)
            ).isoformat()
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Дата фильтра должна быть в формате YYYY-MM-DD",
        )

    return query_audit_events(
        limit=limit,
        offset=offset,
        user=user,
        action=action,
        module_id=module_id,
        status=status,
        search=search,
        date_from=normalized_date_from,
        date_to=normalized_date_to,
    )
