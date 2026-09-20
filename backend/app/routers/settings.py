from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Header, HTTPException, Request

from utils.db_manager import get_settings, save_settings
from utils.permissions import get_user_permissions, record_audit_event

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("")
async def fetch_settings(x_user: Optional[str] = Header("admin")):
    perms = get_user_permissions(x_user)
    if not perms:
        raise HTTPException(status_code=403, detail="Пользователь не найден")
    return get_settings()


@router.put("")
async def update_settings(
    payload: Dict[str, Any],
    request: Request,
    x_user: Optional[str] = Header("admin"),
):
    perms = get_user_permissions(x_user)
    if "*" not in perms:
        raise HTTPException(
            status_code=403,
            detail="Только администратор может изменять системные настройки",
        )

    try:
        amount_tolerance = float(payload.get("amount_tolerance", 0.01))
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=400,
            detail="Допустимая погрешность должна быть числом",
        )

    if amount_tolerance < 0:
        raise HTTPException(
            status_code=400,
            detail="Допустимая погрешность не может быть отрицательной",
        )

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
