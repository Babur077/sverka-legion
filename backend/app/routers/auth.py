from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Request

from backend.app.http_utils import extract_bearer_token
from backend.app.models import LoginRequest
from utils.auth_sessions import create_session, revoke_session
from utils.db_manager import authenticate_user, get_user_id
from utils.permissions import get_user_access, get_user_permissions, record_audit_event

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login")
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


@router.post("/logout")
async def logout(request: Request, x_user: Optional[str] = Header(None)):
    token = extract_bearer_token(request.headers.get("authorization"))
    revoke_session(token)
    if x_user:
        record_audit_event(
            user_id=x_user,
            action="LOGOUT",
            status="SUCCESS",
            ip_address=request.client.host if request.client else "127.0.0.1",
        )
    return {"success": True}


@router.get("/me")
async def current_user(x_user: Optional[str] = Header(None)):
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
