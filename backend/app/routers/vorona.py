from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from backend.app.config import IS_PRODUCTION
from backend.app.http_utils import extract_bearer_token
from modules.vorona.gateway import VORONA_SESSION_COOKIE
from utils.permissions import get_user_permissions, record_audit_event

router = APIRouter(prefix="/api/vorona", tags=["vorona"])


@router.post("/session")
async def create_vorona_session(
    request: Request,
    x_user: Optional[str] = Header(None),
):
    username = str(x_user or "").strip()
    permissions = get_user_permissions(username) if username else []
    if "*" not in permissions and not any(
        permission in permissions
        for permission in ("vorona.view", "vorona.run", "vorona.manage")
    ):
        raise HTTPException(status_code=403, detail="Нет доступа к модулю Сверка Vorona")

    token = extract_bearer_token(request.headers.get("authorization"))
    if not token:
        raise HTTPException(status_code=401, detail="Сессия ReconcileHub не найдена")

    response = JSONResponse({"url": "/vorona/"})
    response.set_cookie(
        key=VORONA_SESSION_COOKIE,
        value=token,
        httponly=True,
        secure=IS_PRODUCTION,
        samesite="lax",
        path="/vorona",
    )

    record_audit_event(
        user_id=username,
        action="VORONA_OPEN",
        module_id="vorona",
        object_type="Workspace",
        object_id="vorona",
        status="SUCCESS",
        ip_address=request.client.host if request.client else "127.0.0.1",
    )
    return response
