"""
ReconcileHub - FastAPI Backend (Modular Monolith)
Интегрирует централизованный реестр модулей (BaseReconciliationModule), RBAC и аудит.
"""
import os
import json
import math
import time
from typing import Optional, Dict, Any
from datetime import datetime, timedelta

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from utils.db_manager import (
    init_db,
    authenticate_user,
    get_user_id,
    get_all_users,
    get_epos_registry,
    add_epos_terminal,
    update_epos_terminal,
    delete_epos_terminal,
    save_reconciliation_run,
    get_reconciliation_runs,
    delete_reconciliation_run,
    add_user,
    delete_user,
    get_settings,
    save_settings,
)
from utils.permissions import (
    DEFAULT_ROLE_PERMISSIONS,
    VALID_ROLES,
    init_permissions_db,
    get_user_permissions,
    get_user_access,
    update_user_access,
    has_permission,
    record_audit_event,
    query_audit_events,
    get_audit_filter_options,
)
from modules.registry import module_registry
from utils.auth_sessions import (
    init_auth_sessions_db,
    create_session,
    get_session_user,
    revoke_session,
)

# Инициализация схемы БД
init_db()
init_permissions_db()
init_auth_sessions_db()

app = FastAPI(
    title="ReconcileHub Platform API",
    description="Модульная платформа финансовых и банковских сверок",
    version="2.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _extract_bearer_token(authorization: Optional[str]) -> str:
    value = str(authorization or "").strip()
    if not value.lower().startswith("bearer "):
        return ""
    return value[7:].strip()


@app.middleware("http")
async def authenticate_api_request(request: Request, call_next):
    """Resolve bearer session to X-User before existing RBAC checks run."""
    path = request.url.path
    if (
        request.method == "OPTIONS"
        or not path.startswith("/api/")
        or path in {"/api/health", "/api/auth/login"}
    ):
        return await call_next(request)

    token = _extract_bearer_token(request.headers.get("authorization"))
    username = get_session_user(token)
    if not username:
        return JSONResponse(
            {"detail": "Сессия недействительна или истекла. Войдите снова."},
            status_code=401,
        )

    headers = [
        (key, value)
        for key, value in request.scope.get("headers", [])
        if key.lower() != b"x-user"
    ]
    headers.append((b"x-user", username.encode("utf-8")))
    request.scope["headers"] = headers
    return await call_next(request)

# ─── Pydantic Модели ──────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str

class EposItem(BaseModel):
    terminal_id: str
    merchant_id: Optional[str] = ""
    bank_acquirer: str
    legal_entity: Optional[str] = ""
    commission_pct: float
    is_active: bool = True


def _json_safe(value: Any) -> Any:
    """Recursively replace values that Starlette cannot encode as strict JSON."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return None if not math.isfinite(value) else value
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "item"):
        try:
            return _json_safe(value.item())
        except (TypeError, ValueError):
            pass
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except (TypeError, ValueError):
            pass
    return str(value)

# ─── Базовые эндпоинты платформы ─────────────────────────────

@app.get("/api/health")
async def health():
    return {
        "status": "healthy",
        "platform": "ReconcileHub Modular Monolith",
        "active_modules_count": len(module_registry.list_manifests()),
        "version": "2.1.0"
    }

@app.post("/api/auth/login")
async def login(req: LoginRequest, request: Request):
    success, role = authenticate_user(req.username, req.password)
    if not success or not role:
        record_audit_event(
            user_id=req.username,
            action="LOGIN_FAILED",
            status="FAILED",
            ip_address=request.client.host if request.client else "127.0.0.1",
            details="Неверный логин или пароль",
        )
        raise HTTPException(status_code=401, detail="Неверный логин или пароль")

    perms = get_user_permissions(req.username)
    session_token, expires_at = create_session(req.username)
    record_audit_event(
        user_id=req.username,
        action="LOGIN_SUCCESS",
        status="SUCCESS",
        ip_address=request.client.host if request.client else "127.0.0.1",
        details=f"Роль: {role}, прав: {len(perms)}",
    )

    return {
        "id": get_user_id(req.username),
        "username": req.username,
        "role": role,
        "permissions": perms,
        "session_token": session_token,
        "expires_at": expires_at,
    }


@app.post("/api/auth/logout")
async def logout(request: Request, x_user: Optional[str] = Header(None)):
    token = _extract_bearer_token(request.headers.get("authorization"))
    revoke_session(token)
    if x_user:
        record_audit_event(
            user_id=x_user,
            action="LOGOUT",
            status="SUCCESS",
            ip_address=request.client.host if request.client else "127.0.0.1",
        )
    return {"success": True}


@app.get("/api/auth/me")
async def current_user(x_user: Optional[str] = Header(None)):
    """Refresh role and effective permissions for the current browser session."""
    if not x_user:
        raise HTTPException(status_code=401, detail="Пользователь не указан")
    access = get_user_access(x_user)
    if not access:
        raise HTTPException(status_code=401, detail="Пользователь не найден")
    return {
        "id": access["id"],
        "username": access["username"],
        "role": access["role"],
        "permissions": access["permissions"],
    }


# ─── Модульный API (Модули сверок) ────────────────────────────

@app.get("/api/modules")
async def get_modules(x_user: Optional[str] = Header("admin")):
    """
    Возвращает список доступных модулей сверок для конкретного пользователя.
    Бухгалтер увидит только свой модуль, а аудитор — все доступные для анализа.
    """
    perms = get_user_permissions(x_user)
    manifests = module_registry.list_manifests(user_permissions=perms)
    return [m.model_dump() for m in manifests]

@app.post("/api/modules/{module_id}/run")
async def run_module_reconciliation(
    module_id: str,
    request: Request,
    x_user: Optional[str] = Header("admin"),
):
    """
    Универсальный эндпоинт запуска зарегистрированного модуля сверки.
    Платформа проверяет права доступа, вызывает контракт модуля и фиксирует аудит-трейл.
    """
    perms = get_user_permissions(x_user)
    required_perm = f"{module_id}.run"

    if not has_permission(perms, required_perm) and "*" not in perms:
        raise HTTPException(status_code=403, detail=f"У вас нет прав на запуск модуля '{module_id}'")

    module = module_registry.get_module(module_id)
    if not module:
        raise HTTPException(status_code=404, detail=f"Модуль сверки '{module_id}' не найден")
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

    t_start = time.time()
    try:
        val_res = module.validate_inputs(files_dict, params_dict)
        if not val_res.is_valid:
            raise HTTPException(status_code=400, detail={"errors": val_res.errors})

        result = module.run(files_dict, params_dict)

        duration = (time.time() - t_start) * 1000
        record_audit_event(
            user_id=x_user,
            action="RECONCILIATION_RUN",
            module_id=module_id,
            object_type="RunResult",
            object_id=result.run_id,
            status="SUCCESS",
            duration_ms=duration,
            details=f"Записей А: {result.summary.total_records_a}, Записей B: {result.summary.total_records_b}, Сходимость: {result.summary.match_percentage}%",
        )
        return _json_safe(result.model_dump())

    except HTTPException:
        raise
    except Exception as e:
        duration = (time.time() - t_start) * 1000
        record_audit_event(
            user_id=x_user,
            action="RECONCILIATION_RUN_FAILED",
            module_id=module_id,
            status="FAILED",
            duration_ms=duration,
            details=str(e),
        )
        raise HTTPException(status_code=500, detail=f"Ошибка выполнения модуля: {str(e)}")

@app.post("/api/modules/{module_id}/archive")
async def save_module_archive(
    module_id: str,
    payload: Dict[str, Any],
    x_user: Optional[str] = Header("admin"),
):
    """Save one module result into the shared reconciliation journal."""
    perms = get_user_permissions(x_user)
    if not has_permission(perms, f"{module_id}.run") and "*" not in perms:
        raise HTTPException(status_code=403, detail="Нет прав на сохранение результата сверки")

    module = module_registry.get_module(module_id)
    if not module:
        raise HTTPException(status_code=404, detail=f"Модуль сверки '{module_id}' не найден")

    try:
        normalized_payload = dict(payload or {})
        if not normalized_payload.get("period_month"):
            normalized_payload["period_month"] = datetime.now().strftime("%Y-%m")

        ok, message, record_id = save_reconciliation_run(
            module_id=module_id,
            user=x_user or "",
            payload=normalized_payload,
        )
        if not ok:
            raise HTTPException(status_code=500, detail=message)

        record_audit_event(
            user_id=x_user,
            action="ARCHIVE_SAVE",
            module_id=module_id,
            object_type="ReconciliationRun",
            object_id=str(record_id or ""),
            status="SUCCESS",
            details=message,
        )
        return {"success": True, "message": message, "id": record_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка сохранения архива: {e}")


@app.get("/api/modules/{module_id}/archive")
async def fetch_module_archive(
    module_id: str,
    x_user: Optional[str] = Header("admin"),
):
    """Return only runs that belong to the requested reconciliation module."""
    perms = get_user_permissions(x_user)
    if not has_permission(perms, f"{module_id}.view") and not has_permission(perms, "archive.view") and "*" not in perms:
        raise HTTPException(status_code=403, detail="Доступ к архиву ограничен")

    module = module_registry.get_module(module_id)
    if not module:
        raise HTTPException(status_code=404, detail=f"Модуль сверки '{module_id}' не найден")

    return _json_safe(get_reconciliation_runs(module_id))


@app.delete("/api/modules/{module_id}/archive/{record_id}")
async def remove_module_archive(
    module_id: str,
    record_id: int,
    x_user: Optional[str] = Header("admin"),
):
    """Delete one record only from the requested module archive."""
    perms = get_user_permissions(x_user)
    if not has_permission(perms, f"{module_id}.run") and "*" not in perms:
        raise HTTPException(status_code=403, detail="Нет прав на удаление записи архива")

    module = module_registry.get_module(module_id)
    if not module:
        raise HTTPException(status_code=404, detail=f"Модуль сверки '{module_id}' не найден")

    deleted = delete_reconciliation_run(module_id, record_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Запись архива не найдена")

    record_audit_event(
        user_id=x_user,
        action="ARCHIVE_DELETE",
        module_id=module_id,
        object_type="ReconciliationRun",
        object_id=str(record_id),
        status="SUCCESS",
        details=f"Удалена запись журнала #{record_id}",
    )
    return {"success": True}


@app.get("/api/modules/{module_id}/analytics")
async def get_module_analytics(module_id: str, x_user: Optional[str] = Header("admin")):
    """Возвращает уникальную аналитику конкретного модуля."""
    perms = get_user_permissions(x_user)
    if not has_permission(perms, f"{module_id}.view") and not has_permission(perms, "analytics.view_all") and "*" not in perms:
        raise HTTPException(status_code=403, detail="Доступ к аналитике этого модуля ограничен")

    module = module_registry.get_module(module_id)
    if not module:
        raise HTTPException(status_code=404, detail="Модуль не найден")

    return module.get_analytics()

# ─── EPOS Справочник ──────────────────────────────────────────

@app.get("/api/epos")
async def fetch_epos(x_user: Optional[str] = Header("admin")):
    perms = get_user_permissions(x_user)
    if not has_permission(perms, "epos.view") and not has_permission(perms, "epos.manage") and "*" not in perms:
        raise HTTPException(status_code=403, detail="Нет прав на просмотр реестра EPOS")
    df = get_epos_registry()
    return df.to_dict(orient="records") if hasattr(df, "to_dict") else []

@app.post("/api/epos")
async def create_epos(item: EposItem, request: Request, x_user: Optional[str] = Header("admin")):
    perms = get_user_permissions(x_user)
    if not has_permission(perms, "epos.manage") and "*" not in perms:
        raise HTTPException(status_code=403, detail="Нет прав на изменение реестра EPOS")
    tid = item.terminal_id.strip()
    if not tid:
        raise HTTPException(status_code=400, detail="TID обязателен")
    ok, message = add_epos_terminal(tid, item.merchant_id or "", item.bank_acquirer.strip(), item.legal_entity or "", float(item.commission_pct))
    if not ok:
        raise HTTPException(status_code=400, detail=message)
    record_audit_event(user_id=x_user, action="CREATE_EPOS", module_id="epos", object_type="EposTerminal", object_id=tid, status="SUCCESS", ip_address=request.client.host if request.client else "127.0.0.1", details=message)
    return {"success": True, "message": message}

@app.put("/api/epos/{terminal_id}")
async def update_epos(terminal_id: str, item: EposItem, request: Request, x_user: Optional[str] = Header("admin")):
    perms = get_user_permissions(x_user)
    if not has_permission(perms, "epos.manage") and "*" not in perms:
        raise HTTPException(status_code=403, detail="Нет прав на изменение реестра EPOS")
    if terminal_id.strip() != item.terminal_id.strip():
        raise HTTPException(status_code=400, detail="TID в пути и теле запроса не совпадают")
    ok, message = update_epos_terminal(terminal_id.strip(), item.bank_acquirer.strip(), item.merchant_id or "", float(item.commission_pct), bool(item.is_active))
    if not ok:
        raise HTTPException(status_code=400, detail=message)
    record_audit_event(user_id=x_user, action="UPDATE_EPOS", module_id="epos", object_type="EposTerminal", object_id=terminal_id, status="SUCCESS", ip_address=request.client.host if request.client else "127.0.0.1", details=message)
    return {"success": True, "message": message}

@app.delete("/api/epos/{terminal_id}")
async def remove_epos(terminal_id: str, request: Request, x_user: Optional[str] = Header("admin")):
    perms = get_user_permissions(x_user)
    if not has_permission(perms, "epos.manage") and "*" not in perms:
        raise HTTPException(status_code=403, detail="Нет прав на изменение реестра EPOS")
    ok, message = delete_epos_terminal(terminal_id.strip())
    if not ok:
        raise HTTPException(status_code=400, detail=message)
    record_audit_event(user_id=x_user, action="DELETE_EPOS", module_id="epos", object_type="EposTerminal", object_id=terminal_id, status="SUCCESS", ip_address=request.client.host if request.client else "127.0.0.1", details=message)
    return {"success": True, "message": message}

@app.get("/api/banks")
async def get_banks():
    df = get_epos_registry()
    if hasattr(df, "empty") and not df.empty and "bank_acquirer" in df.columns:
        banks = sorted(list(set(df["bank_acquirer"].dropna().unique())))
        if banks:
            return banks
    return ["Aloqa Bank", "Kapitalbank", "Ipak Yuli", "NBU", "TBC Bank", "Agrobank", "Humo", "Uzcard"]

# ─── Общесистемные настройки ─────────────────────────────────

@app.get("/api/settings")
async def fetch_settings(x_user: Optional[str] = Header("admin")):
    """Возвращает общесистемные параметры сверки."""
    perms = get_user_permissions(x_user)
    if not perms:
        raise HTTPException(status_code=403, detail="Пользователь не найден")
    return get_settings()


@app.put("/api/settings")
async def update_settings(payload: Dict[str, Any], request: Request, x_user: Optional[str] = Header("admin")):
    """Сохраняет общесистемные параметры сверки."""
    perms = get_user_permissions(x_user)
    if "*" not in perms:
        raise HTTPException(status_code=403, detail="Только администратор может изменять системные настройки")

    try:
        amount_tolerance = float(payload.get("amount_tolerance", 0.01))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Допустимая погрешность должна быть числом")

    if amount_tolerance < 0:
        raise HTTPException(status_code=400, detail="Допустимая погрешность не может быть отрицательной")

    currency = str(payload.get("currency") or "UZS").strip().upper()
    if currency not in {"UZS", "USD", "RUB", "EUR"}:
        raise HTTPException(status_code=400, detail="Недопустимая валюта")

    dayfirst = bool(payload.get("dayfirst", True))
    new_settings = {
        "amount_tolerance": amount_tolerance,
        "currency": currency,
        "dayfirst": dayfirst,
    }
    save_settings(new_settings)
    record_audit_event(
        user_id=x_user,
        action="UPDATE_SETTINGS",
        object_type="SystemSettings",
        status="SUCCESS",
        ip_address=request.client.host if request.client else "127.0.0.1",
        details=f"Допуск: {amount_tolerance}, Валюта: {currency}, dayfirst: {dayfirst}",
    )
    return new_settings


# ─── Аудит и Пользователи ─────────────────────────────────────

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


def _permission_catalog() -> Dict[str, Any]:
    groups = []
    for manifest in module_registry.list_manifests():
        declared = manifest.available_permissions or manifest.required_permissions
        seen = set()
        permissions = []
        labels = {
            "view": "Просмотр",
            "run": "Запуск сверки",
            "export": "Экспорт",
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


def _known_assignable_permissions() -> set[str]:
    return {
        permission["id"]
        for group in _permission_catalog()["groups"]
        for permission in group["permissions"]
    }


@app.get("/api/admin/permissions")
async def fetch_permission_catalog(x_user: Optional[str] = Header("admin")):
    """Permission catalog for the generic administration UI."""
    perms = get_user_permissions(x_user)
    if "*" not in perms:
        raise HTTPException(status_code=403, detail="Только администратор может управлять правами")
    return _permission_catalog()


@app.get("/api/admin/users")
async def fetch_users(x_user: Optional[str] = Header("admin")):
    """Возвращает учётные записи без паролей. Только администратору."""
    perms = get_user_permissions(x_user)
    if "*" not in perms:
        raise HTTPException(status_code=403, detail="Только администратор может управлять пользователями")
    df = get_all_users()
    records = df.to_dict(orient="records") if hasattr(df, "to_dict") else []
    enriched = []
    for item in records:
        access = get_user_access(str(item.get("username") or ""))
        if access:
            enriched.append(access)
        else:
            enriched.append(item)
    return enriched


@app.post("/api/admin/users")
async def create_user(payload: Dict[str, Any], x_user: Optional[str] = Header("admin")):
    """Создаёт пользователя через серверную БД."""
    perms = get_user_permissions(x_user)
    if "*" not in perms:
        raise HTTPException(status_code=403, detail="Только администратор может управлять пользователями")

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


@app.put("/api/admin/users/{user_id}/access")
async def update_user_permissions(
    user_id: int,
    payload: Dict[str, Any],
    request: Request,
    x_user: Optional[str] = Header("admin"),
):
    """Update role template and individual permission overrides."""
    perms = get_user_permissions(x_user)
    if "*" not in perms:
        raise HTTPException(status_code=403, detail="Только администратор может управлять правами")

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
        raise HTTPException(status_code=400, detail="Полный доступ задаётся только ролью admin")

    unknown = sorted(requested.difference(_known_assignable_permissions()))
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


@app.delete("/api/admin/users/{user_id}")
async def remove_user(user_id: int, x_user: Optional[str] = Header("admin")):
    """Удаляет пользователя через серверную БД."""
    perms = get_user_permissions(x_user)
    if "*" not in perms:
        raise HTTPException(status_code=403, detail="Только администратор может управлять пользователями")

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


@app.get("/api/audit/filters")
async def fetch_audit_filters(x_user: Optional[str] = Header("admin")):
    """Return complete filter values for the audit workspace."""
    perms = get_user_permissions(x_user)
    if not has_permission(perms, "audit.view") and "*" not in perms:
        raise HTTPException(status_code=403, detail="Нет прав на просмотр журнала аудита")
    return get_audit_filter_options()


@app.get("/api/audit")
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
    """Return the immutable server audit trail with filters and pagination."""
    perms = get_user_permissions(x_user)
    if not has_permission(perms, "audit.view") and "*" not in perms:
        raise HTTPException(status_code=403, detail="Нет прав на просмотр журнала аудита")

    normalized_date_from = None
    normalized_date_to = None
    try:
        if date_from:
            normalized_date_from = datetime.strptime(date_from, "%Y-%m-%d").isoformat()
        if date_to:
            normalized_date_to = (
                datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)
            ).isoformat()
    except ValueError:
        raise HTTPException(status_code=400, detail="Дата фильтра должна быть в формате YYYY-MM-DD")

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

# ─── Раздача скомпилированного React Frontend ──────────────────

DIST_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dist")

if os.path.exists(DIST_DIR):
    assets_dir = os.path.join(DIST_DIR, "assets")
    if os.path.exists(assets_dir):
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/{full_path:path}")
    async def serve_react_spa(full_path: str):
        target_file = os.path.join(DIST_DIR, full_path)
        if full_path and os.path.isfile(target_file):
            return FileResponse(target_file)
        index_file = os.path.join(DIST_DIR, "index.html")
        if os.path.exists(index_file):
            return FileResponse(index_file)
        return JSONResponse({"message": "React index.html not found"}, status_code=404)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
