"""
ReconcileHub - FastAPI Backend (Modular Monolith)
Интегрирует централизованный реестр модулей (BaseReconciliationModule), RBAC и аудит.
"""
import os
import sys
import json
import time
import socket
import subprocess
from typing import Optional, List, Dict, Any
from datetime import datetime

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
    get_audit_logs,
    get_epos_registry,
    add_epos_terminal,
    update_epos_terminal,
    delete_epos_terminal,
    save_reconciliation,
    get_archive_data,
    delete_archive_record,
    add_user,
    delete_user,
)
from utils.permissions import (
    init_permissions_db,
    get_user_permissions,
    has_permission,
    record_audit_event,
)
from modules.registry import module_registry

# Инициализация схемы БД
init_db()
init_permissions_db()

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

# ─── Pydantic Модели ──────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str

class EposItem(BaseModel):
    terminal_id: str
    merchant_name: str
    bank_acquirer: str
    commission_pct: float
    account_number: Optional[str] = ""
    is_active: bool = True

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
    Универсальный эндпоинт запуска ЛЮБОГО модуля сверки (RRN, Paynet, EPOS и т.д.).
    Платформа проверяет права доступа, вызывает контракт модуля и фиксирует аудит-трейл.
    """
    perms = get_user_permissions(x_user)
    required_perm = f"{module_id}.run"

    if not has_permission(perms, required_perm) and "*" not in perms:
        raise HTTPException(status_code=403, detail=f"У вас нет прав на запуск модуля '{module_id}'")

    module = module_registry.get_module(module_id)
    if not module:
        raise HTTPException(status_code=404, detail=f"Модуль сверки '{module_id}' не найден")

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
        return result.model_dump()

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
    """Сохраняет метаданные результата сверки в серверный архив."""
    perms = get_user_permissions(x_user)
    if not has_permission(perms, f"{module_id}.run") and "*" not in perms:
        raise HTTPException(status_code=403, detail="Нет прав на сохранение результата сверки")
    if module_id != "bank_rrn":
        raise HTTPException(status_code=404, detail="Серверный архив для этого модуля пока не реализован")

    try:
        ok, message = save_reconciliation(
            user=x_user,
            bank_name=str(payload.get("bank_name") or "Не указан"),
            tot_our=float(payload.get("total_our") or 0),
            tot_bank=float(payload.get("total_bank") or 0),
            diff=float(payload.get("difference") or 0),
            matched_c=int(payload.get("matched_count") or 0),
            mismatch_c=int(payload.get("mismatch_count") or 0),
            only_our_c=int(payload.get("only_our_count") or 0),
            only_bank_c=int(payload.get("only_bank_count") or 0),
            period_month=payload.get("period_month"),
            total_commission=float(payload.get("total_commission") or 0),
            terminals_data=payload.get("terminals_summary") or [],
        )
        if not ok:
            raise HTTPException(status_code=500, detail=message)

        record_audit_event(
            user_id=x_user,
            action="ARCHIVE_SAVE",
            module_id=module_id,
            object_type="ReconciliationArchive",
            status="SUCCESS",
            details=message,
        )
        return {"success": True, "message": message}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка сохранения архива: {e}")

@app.get("/api/modules/{module_id}/archive")
async def fetch_module_archive(
    module_id: str,
    x_user: Optional[str] = Header("admin"),
):
    """Возвращает серверный архив конкретного модуля."""
    perms = get_user_permissions(x_user)
    if not has_permission(perms, f"{module_id}.view") and not has_permission(perms, "analytics.view_all") and "*" not in perms:
        raise HTTPException(status_code=403, detail="Доступ к архиву ограничен")
    if module_id != "bank_rrn":
        raise HTTPException(status_code=404, detail="Серверный архив для этого модуля пока не реализован")

    df = get_archive_data()
    records = df.to_dict(orient="records") if hasattr(df, "to_dict") else []
    for item in records:
        try:
            item["terminals_summary"] = json.loads(item.get("terminals_json") or "[]")
        except (TypeError, json.JSONDecodeError):
            item["terminals_summary"] = []
        item.pop("terminals_json", None)
    return records

@app.delete("/api/modules/{module_id}/archive/{record_id}")
async def remove_module_archive(
    module_id: str,
    record_id: int,
    x_user: Optional[str] = Header("admin"),
):
    """Удаляет запись из серверного архива."""
    perms = get_user_permissions(x_user)
    if not has_permission(perms, f"{module_id}.run") and "*" not in perms:
        raise HTTPException(status_code=403, detail="Нет прав на удаление записи архива")
    if module_id != "bank_rrn":
        raise HTTPException(status_code=404, detail="Серверный архив для этого модуля пока не реализован")
    delete_archive_record(record_id)
    record_audit_event(
        user_id=x_user,
        action="ARCHIVE_DELETE",
        module_id=module_id,
        object_type="ReconciliationArchive",
        object_id=str(record_id),
        status="SUCCESS",
        details=f"Удалена запись архива #{record_id}",
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
async def fetch_epos():
    df = get_epos_registry()
    return df.to_dict(orient="records") if hasattr(df, "to_dict") else []

@app.get("/api/banks")
async def get_banks():
    df = get_epos_registry()
    if hasattr(df, "empty") and not df.empty and "bank_acquirer" in df.columns:
        banks = sorted(list(set(df["bank_acquirer"].dropna().unique())))
        if banks:
            return banks
    return ["Aloqa Bank", "Kapitalbank", "Ipak Yuli", "NBU", "TBC Bank", "Agrobank", "Humo", "Uzcard"]

# ─── Аудит и Пользователи ─────────────────────────────────────

@app.get("/api/admin/users")
async def fetch_users(x_user: Optional[str] = Header("admin")):
    """Возвращает учётные записи без паролей. Только администратору."""
    perms = get_user_permissions(x_user)
    if "*" not in perms:
        raise HTTPException(status_code=403, detail="Только администратор может управлять пользователями")
    df = get_all_users()
    return df.to_dict(orient="records") if hasattr(df, "to_dict") else []


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
    if role not in {"admin", "accountant", "auditor"}:
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


@app.get("/api/audit")
async def fetch_audit_trail(limit: int = 100, x_user: Optional[str] = Header("admin")):
    import sqlite3
    from utils.db_manager import DB_PATH
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT * FROM audit_events ORDER BY id DESC LIMIT ?", (limit,))
        rows = cur.fetchall()
        return [dict(r) for r in rows]

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
