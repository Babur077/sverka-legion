from __future__ import annotations

import sqlite3

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from modules.registry import module_registry
import utils.db_manager as db

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
async def health():
    return {
        "status": "healthy",
        "platform": "ReconcileHub Modular Monolith",
        "active_modules_count": len(module_registry.list_manifests()),
        "version": "2.2.0",
    }


@router.get("/ready")
async def readiness():
    checks: dict[str, object] = {
        "database": False,
        "modules": False,
    }

    try:
        with sqlite3.connect(db.DB_PATH, timeout=3) as conn:
            conn.execute("SELECT 1").fetchone()
            conn.execute("SELECT version FROM schema_migrations ORDER BY version DESC LIMIT 1").fetchone()
        checks["database"] = True
    except Exception as exc:
        checks["database_error"] = type(exc).__name__

    try:
        manifests = module_registry.list_manifests()
        checks["modules"] = len(manifests) > 0
        checks["active_modules_count"] = len(manifests)
    except Exception as exc:
        checks["modules_error"] = type(exc).__name__

    ready = bool(checks["database"] and checks["modules"])
    payload = {
        "status": "ready" if ready else "not_ready",
        "checks": checks,
    }
    if ready:
        return payload
    return JSONResponse(payload, status_code=503)
