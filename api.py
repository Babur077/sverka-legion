"""ReconcileHub FastAPI entrypoint.

The entrypoint only assembles the application. HTTP routes live in
backend/app/routers, reconciliation orchestration in services, persistence access
behind repositories/utils, and database schema evolution in versioned migrations.
"""
from __future__ import annotations

import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.app.http_utils import extract_bearer_token
from backend.app.routers import admin, audit, auth, epos, health, modules, settings
from utils.auth_sessions import get_session_user
from utils.db_manager import init_db


# One startup path owns the database schema. init_db() applies only pending,
# versioned migrations and then bootstraps reference data.
init_db()

app = FastAPI(
    title="ReconcileHub Platform API",
    description="Модульная платформа финансовых и банковских сверок",
    version="2.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def authenticate_api_request(request: Request, call_next):
    """Resolve bearer session to X-User before RBAC checks run."""
    path = request.url.path
    if (
        request.method == "OPTIONS"
        or not path.startswith("/api/")
        or path in {"/api/health", "/api/auth/login"}
    ):
        return await call_next(request)

    token = extract_bearer_token(request.headers.get("authorization"))
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


# API composition. Routers stay independent, which keeps future modules from
# expanding this entrypoint again.
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(modules.router)
app.include_router(epos.router)
app.include_router(settings.router)
app.include_router(admin.router)
app.include_router(audit.router)


# Compiled React frontend.
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
        return JSONResponse(
            {"message": "React index.html not found"},
            status_code=404,
        )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
