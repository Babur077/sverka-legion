from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Request

from backend.app.models import EposItem
from utils.db_manager import (
    add_epos_terminal,
    delete_epos_terminal,
    get_epos_registry,
    update_epos_terminal,
)
from utils.permissions import get_user_permissions, has_permission, record_audit_event

router = APIRouter(prefix="/api", tags=["epos"])


@router.get("/epos")
async def fetch_epos(x_user: Optional[str] = Header("admin")):
    perms = get_user_permissions(x_user)
    if (
        not has_permission(perms, "epos.view")
        and not has_permission(perms, "epos.manage")
        and "*" not in perms
    ):
        raise HTTPException(status_code=403, detail="Нет прав на просмотр реестра EPOS")
    df = get_epos_registry()
    return df.to_dict(orient="records") if hasattr(df, "to_dict") else []


@router.post("/epos")
async def create_epos(
    item: EposItem,
    request: Request,
    x_user: Optional[str] = Header("admin"),
):
    perms = get_user_permissions(x_user)
    if not has_permission(perms, "epos.manage") and "*" not in perms:
        raise HTTPException(status_code=403, detail="Нет прав на изменение реестра EPOS")

    tid = item.terminal_id.strip()
    if not tid:
        raise HTTPException(status_code=400, detail="TID обязателен")

    ok, message = add_epos_terminal(
        tid,
        item.merchant_id or "",
        item.bank_acquirer.strip(),
        item.legal_entity or "",
        float(item.commission_pct),
    )
    if not ok:
        raise HTTPException(status_code=400, detail=message)

    record_audit_event(
        user_id=x_user,
        action="CREATE_EPOS",
        module_id="epos",
        object_type="EposTerminal",
        object_id=tid,
        status="SUCCESS",
        ip_address=request.client.host if request.client else "127.0.0.1",
        details=message,
    )
    return {"success": True, "message": message}


@router.put("/epos/{terminal_id}")
async def update_epos(
    terminal_id: str,
    item: EposItem,
    request: Request,
    x_user: Optional[str] = Header("admin"),
):
    perms = get_user_permissions(x_user)
    if not has_permission(perms, "epos.manage") and "*" not in perms:
        raise HTTPException(status_code=403, detail="Нет прав на изменение реестра EPOS")
    if terminal_id.strip() != item.terminal_id.strip():
        raise HTTPException(status_code=400, detail="TID в пути и теле запроса не совпадают")

    ok, message = update_epos_terminal(
        terminal_id.strip(),
        item.bank_acquirer.strip(),
        item.merchant_id or "",
        float(item.commission_pct),
        bool(item.is_active),
    )
    if not ok:
        raise HTTPException(status_code=400, detail=message)

    record_audit_event(
        user_id=x_user,
        action="UPDATE_EPOS",
        module_id="epos",
        object_type="EposTerminal",
        object_id=terminal_id,
        status="SUCCESS",
        ip_address=request.client.host if request.client else "127.0.0.1",
        details=message,
    )
    return {"success": True, "message": message}


@router.delete("/epos/{terminal_id}")
async def remove_epos(
    terminal_id: str,
    request: Request,
    x_user: Optional[str] = Header("admin"),
):
    perms = get_user_permissions(x_user)
    if not has_permission(perms, "epos.manage") and "*" not in perms:
        raise HTTPException(status_code=403, detail="Нет прав на изменение реестра EPOS")

    ok, message = delete_epos_terminal(terminal_id.strip())
    if not ok:
        raise HTTPException(status_code=400, detail=message)

    record_audit_event(
        user_id=x_user,
        action="DELETE_EPOS",
        module_id="epos",
        object_type="EposTerminal",
        object_id=terminal_id,
        status="SUCCESS",
        ip_address=request.client.host if request.client else "127.0.0.1",
        details=message,
    )
    return {"success": True, "message": message}


@router.get("/banks")
async def get_banks():
    df = get_epos_registry()
    if hasattr(df, "empty") and not df.empty and "bank_acquirer" in df.columns:
        banks = sorted(list(set(df["bank_acquirer"].dropna().unique())))
        if banks:
            return banks
    return [
        "Aloqa Bank",
        "Kapitalbank",
        "Ipak Yuli",
        "NBU",
        "TBC Bank",
        "Agrobank",
        "Humo",
        "Uzcard",
    ]
