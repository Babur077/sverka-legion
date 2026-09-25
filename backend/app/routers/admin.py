from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Header, HTTPException, Request

from modules.registry import module_registry
from utils.db_manager import add_user, delete_user, get_all_users
from utils.permissions import (
    DEFAULT_ROLE_PERMISSIONS,
    VALID_ROLES,
    get_user_access,
    get_user_permissions,
    record_audit_event,
    update_user_access,
)

router = APIRouter(prefix="/api/admin", tags=["admin"])

PLATFORM_PERMISSION_CATALOG = [
    {
        "id": "epos",
        "name": "Реестр EPOS",
        "permissions": [
            {"id": "epos.view", "label": "Просмотр реестра"},
            {"id": "epos.manage", "label": "Изменение реестра"},
        ],
    },
    {
        "id": "analytics",
        "name": "Аналитика",
        "permissions": [
            {"id": "analytics.view_all", "label": "Просмотр общей аналитики"},
        ],
    },
    {
        "id": "archive",
        "name": "Архив",
        "permissions": [
            {"id": "archive.view", "label": "Просмотр архива"},
        ],
    },
    {
        "id": "audit",
        "name": "Аудит",
        "permissions": [
            {"id": "audit.view", "label": "Просмотр журнала аудита"},
        ],
    },
]


def permission_catalog() -> Dict[str, Any]:
    groups = []
    for manifest in module_registry.list_manifests():
        declared = manifest.available_permissions or manifest.required_permissions
        seen = set()
        permissions = []
        labels = {
            "view": "Просмотр",
            "run": "Запуск сверки",
            "export": "Экспорт",
            "manage": "Управление данными",
        }
        for permission in declared:
            if permission in seen:
                continue
            seen.add(permission)
            suffix = permission.split(".", 1)[1] if "." in permission else permission
            permissions.append({
                "id": permission,
                "label": labels.get(suffix, permission),
            })
        groups.append({
            "id": f"module:{manifest.id}",
            "name": manifest.name,
            "type": "module",
            "module_id": manifest.id,
            "status": manifest.status,
            "permissions": permissions,
        })

    groups.extend([
        {**group, "type": "platform"}
        for group in PLATFORM_PERMISSION_CATALOG
    ])

    return {
        "roles": DEFAULT_ROLE_PERMISSIONS,
        "groups": groups,
    }


def known_assignable_permissions() -> set[str]:
    return {
        permission["id"]
        for group in permission_catalog()["groups"]
        for permission in group["permissions"]
    }


@router.get("/permissions")
async def fetch_permission_catalog(x_user: Optional[str] = Header("admin")):
    perms = get_user_permissions(x_user)
    if "*" not in perms:
        raise HTTPException(
            status_code=403,
            detail="Только администратор может управлять правами",
        )
    return permission_catalog()


@router.get("/users")
async def fetch_users(x_user: Optional[str] = Header("admin")):
    perms = get_user_permissions(x_user)
    if "*" not in perms:
        raise HTTPException(
            status_code=403,
            detail="Только администратор может управлять пользователями",
        )

    df = get_all_users()
    records = df.to_dict(orient="records") if hasattr(df, "to_dict") else []
    enriched = []
    for item in records:
        access = get_user_access(str(item.get("username") or ""))
        enriched.append(access if access else item)
    return enriched


@router.post("/users")
async def create_user(
    payload: Dict[str, Any],
    x_user: Optional[str] = Header("admin"),
):
    perms = get_user_permissions(x_user)
    if "*" not in perms:
        raise HTTPException(
            status_code=403,
            detail="Только администратор может управлять пользователями",
        )

    username = str(payload.get("username") or "").strip()
    password = str(payload.get("password") or "")
    role = str(payload.get("role") or "").strip()

    if not username or not password:
        raise HTTPException(status_code=400, detail="Логин и пароль обязательны")
    if role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail="Недопустимая роль пользователя")

    ok, message = add_user(username, password, role)
    if not ok:
        raise HTTPException(status_code=400, detail=message)

    record_audit_event(
        user_id=x_user,
        action="CREATE_USER",
        object_type="User",
        object_id=username,
        status="SUCCESS",
        details=f"Создан пользователь {username} ({role})",
    )
    return {"success": True, "message": message}


@router.put("/users/{user_id}/access")
async def update_user_permissions(
    user_id: int,
    payload: Dict[str, Any],
    request: Request,
    x_user: Optional[str] = Header("admin"),
):
    perms = get_user_permissions(x_user)
    if "*" not in perms:
        raise HTTPException(
            status_code=403,
            detail="Только администратор может управлять правами",
        )

    role = str(payload.get("role") or "").strip()
    allow = payload.get("allow") or []
    deny = payload.get("deny") or []

    if role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail="Недопустимая роль пользователя")
    if not isinstance(allow, list) or not isinstance(deny, list):
        raise HTTPException(status_code=400, detail="allow и deny должны быть списками")

    normalized_allow = [str(value).strip() for value in allow if str(value).strip()]
    normalized_deny = [str(value).strip() for value in deny if str(value).strip()]
    requested = set(normalized_allow) | set(normalized_deny)

    if "*" in requested:
        raise HTTPException(
            status_code=400,
            detail="Полный доступ задаётся только ролью admin",
        )

    unknown = sorted(requested.difference(known_assignable_permissions()))
    if unknown:
        raise HTTPException(
            status_code=400,
            detail="Неизвестные права: " + ", ".join(unknown),
        )

    ok, message, access = update_user_access(
        user_id=user_id,
        role=role,
        allow=normalized_allow,
        deny=normalized_deny,
    )
    if not ok:
        raise HTTPException(status_code=400, detail=message)

    record_audit_event(
        user_id=x_user,
        action="UPDATE_USER_ACCESS",
        object_type="User",
        object_id=str(user_id),
        status="SUCCESS",
        ip_address=request.client.host if request.client else "127.0.0.1",
        details=(
            f"{message}; роль={role}; "
            f"allow={','.join(normalized_allow) or '-'}; "
            f"deny={','.join(normalized_deny) or '-'}"
        ),
    )
    return access


@router.delete("/users/{user_id}")
async def remove_user(
    user_id: int,
    x_user: Optional[str] = Header("admin"),
):
    perms = get_user_permissions(x_user)
    if "*" not in perms:
        raise HTTPException(
            status_code=403,
            detail="Только администратор может управлять пользователями",
        )

    ok, message = delete_user(user_id)
    if not ok:
        raise HTTPException(status_code=400, detail=message)

    record_audit_event(
        user_id=x_user,
        action="DELETE_USER",
        object_type="User",
        object_id=str(user_id),
        status="SUCCESS",
        details=message,
    )
    return {"success": True, "message": message}
