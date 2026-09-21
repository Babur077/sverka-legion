from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Header, HTTPException

from backend.app.services.bank_ai import analyze_bank_reconciliation
from utils.permissions import get_user_permissions, has_permission

router = APIRouter(prefix="/api/modules/bank_rrn/ai", tags=["bank-ai"])


@router.post("/summary")
async def bank_ai_summary(
    payload: Dict[str, Any],
    x_user: Optional[str] = Header("admin"),
):
    perms = get_user_permissions(x_user)
    if (
        not has_permission(perms, "bank_rrn.view")
        and not has_permission(perms, "bank_rrn.run")
        and "*" not in perms
    ):
        raise HTTPException(status_code=403, detail="Нет прав на AI-анализ банковской сверки")

    result = payload.get("result")
    if not isinstance(result, dict):
        raise HTTPException(status_code=400, detail="Не передан результат банковской сверки")

    return analyze_bank_reconciliation(payload)
