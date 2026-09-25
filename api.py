"""ReconcileHub FastAPI entrypoint.

The entrypoint only assembles the application. HTTP routes live in
backend/app/routers, reconciliation orchestration in services, persistence access
behind repositories/utils, and database schema evolution in versioned migrations.
"""
from __future__ import annotations

import logging
import os
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.wsgi import WSGIMiddleware

from backend.app.config import ALLOWED_ORIGINS, HOST, IS_PRODUCTION, PORT
from backend.app.http_utils import extract_bearer_token
from backend.app.routers import admin, audit, auth, bank_ai, dashboard, definitions, epos, health, jobs, modules, settings, vorona
from backend.app.logging_config import configure_logging
from backend.app.services.backups import start_backup_worker, stop_backup_worker
from backend.app.services.job_worker import start_job_worker, stop_job_worker
from utils.auth_sessions import get_session_user
from utils.db_manager import init_db
from modules.vorona.gateway import vorona_wsgi_app


configure_logging()
logger = logging.getLogger("reconcilehub.api")

# One startup path owns the database schema. init_db() applies only pending,
# versioned migrations and then bootstraps reference data.
init_db()

@asynccontextmanager
async def lifespan(_app: FastAPI):
    start_job_worker()
    start_backup_worker()
    try:
        yield
    finally:
        stop_job_worker()
        stop_backup_worker()


app = FastAPI(
    title="ReconcileHub Platform API",
    description="Модульная платформа финансовых и банковских сверок",
    version="2.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=bool(ALLOWED_ORIGINS and "*" not in ALLOWED_ORIGINS),
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
        or path in {"/api/health", "/api/ready", "/api/auth/login"}
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


@app.middleware("http")
async def request_observability(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
    started = time.perf_counter()
    response = None
    try:
        response = await call_next(request)
        return response
    except Exception as exc:
        logger.exception(
            "request_failed request_id=%s method=%s path=%s error=%s",
            request_id,
            request.method,
            request.url.path,
            type(exc).__name__,
        )
        if IS_PRODUCTION:
            response = JSONResponse(
                {
                    "detail": "Внутренняя ошибка сервера.",
                    "request_id": request_id,
                },
                status_code=500,
            )
            return response
        raise
    finally:
        duration_ms = (time.perf_counter() - started) * 1000
        status_code = getattr(response, "status_code", 500)
        if request.url.path.startswith("/api/"):
            logger.info(
                "request request_id=%s method=%s path=%s status=%s duration_ms=%.1f",
                request_id,
                request.method,
                request.url.path,
                status_code,
                duration_ms,
            )
        if response is not None:
            response.headers["X-Request-ID"] = request_id


# API composition. Routers stay independent, which keeps future modules from
# expanding this entrypoint again.
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(definitions.router)
app.include_router(bank_ai.router)
app.include_router(dashboard.router)
app.include_router(jobs.router)
app.include_router(modules.router)
app.include_router(epos.router)
app.include_router(settings.router)
app.include_router(admin.router)
app.include_router(audit.router)
app.include_router(vorona.router)

# Legacy Vorona runs behind ReconcileHub auth/RBAC while keeping its original
# reconciliation and PostgreSQL logic intact.
app.mount("/vorona", WSGIMiddleware(vorona_wsgi_app), name="vorona")


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

    uvicorn.run(app, host=HOST, port=PORT)
