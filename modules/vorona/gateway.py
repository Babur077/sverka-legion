from __future__ import annotations

import logging
from http.cookies import SimpleCookie
from threading import Lock
from typing import Callable, Iterable

from utils.auth_sessions import get_session_user
from utils.permissions import get_user_permissions

logger = logging.getLogger(__name__)

VORONA_SESSION_COOKIE = "reconcile_vorona_session"

_MANAGE_PATHS = {
    "/db/update",
    "/db/insert",
    "/db/delete",
    "/db/upload_excel",
    "/db/upload_saldo_initial",
    "/db/upload_balance_1c",
}


def _plain_response(start_response: Callable, status: str, message: str) -> Iterable[bytes]:
    payload = message.encode("utf-8")
    start_response(
        status,
        [
            ("Content-Type", "text/plain; charset=utf-8"),
            ("Content-Length", str(len(payload))),
            ("Cache-Control", "no-store"),
        ],
    )
    return [payload]


def _cookie_token(environ: dict) -> str:
    raw = str(environ.get("HTTP_COOKIE") or "")
    if not raw:
        return ""
    cookie = SimpleCookie()
    try:
        cookie.load(raw)
    except Exception:
        return ""
    morsel = cookie.get(VORONA_SESSION_COOKIE)
    return morsel.value if morsel else ""


def _allowed(username: str, path: str) -> bool:
    permissions = get_user_permissions(username)
    if "*" in permissions:
        return True

    if path in _MANAGE_PATHS:
        return "vorona.manage" in permissions

    return any(
        permission in permissions
        for permission in ("vorona.view", "vorona.run", "vorona.manage")
    )


class LazyVoronaGateway:
    """Authenticate ReconcileHub users, then delegate to the unchanged Flask app.

    Import is lazy so ReconcileHub can still start when PostgreSQL VORONA is
    temporarily unavailable. The original Flask application is loaded only when
    a user actually opens this module.
    """

    def __init__(self) -> None:
        self._app = None
        self._lock = Lock()

    def _load_app(self):
        if self._app is not None:
            return self._app
        with self._lock:
            if self._app is None:
                from VORONA_upload.app import app as legacy_app

                self._app = legacy_app
        return self._app

    def __call__(self, environ: dict, start_response: Callable):
        token = _cookie_token(environ)
        username = get_session_user(token)
        if not username:
            return _plain_response(
                start_response,
                "401 Unauthorized",
                "Сессия ReconcileHub недействительна. Вернитесь в ReconcileHub и откройте модуль заново.",
            )

        path = str(environ.get("PATH_INFO") or "/")
        if not _allowed(username, path):
            return _plain_response(
                start_response,
                "403 Forbidden",
                "Недостаточно прав для этого действия в модуле Сверка Vorona.",
            )

        environ["HTTP_X_USER"] = username
        try:
            app = self._load_app()
        except Exception as exc:
            logger.exception("Vorona legacy application could not be loaded")
            return _plain_response(
                start_response,
                "503 Service Unavailable",
                "Vorona временно недоступна. Проверьте подключение к PostgreSQL VORONA и настройки .env.",
            )

        return app(environ, start_response)


vorona_wsgi_app = LazyVoronaGateway()
