from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Header, Query

from backend.app.repositories.dashboard import get_dashboard_data
from modules.registry import module_registry
from utils.permissions import get_user_permissions, has_permission

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("")
async def dashboard(
    months: int = Query(6, ge=1, le=24),
    module_id: Optional[str] = None,
    x_user: Optional[str] = Header("admin"),
):
    username = x_user or ""
    permissions = get_user_permissions(username)
    manifests = module_registry.list_manifests(user_permissions=permissions)
    allowed_modules = {
        manifest.id: manifest.name
        for manifest in manifests
        if manifest.status == "active"
    }

    return get_dashboard_data(
        allowed_modules=allowed_modules,
        username=username,
        months=months,
        module_id=module_id,
        include_all_jobs=(
            "*" in permissions
            or has_permission(permissions, "analytics.view_all")
        ),
    )
