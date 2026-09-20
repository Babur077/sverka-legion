from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


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
