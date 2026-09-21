from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from backend.app.config import LOG_DIR, LOG_LEVEL


_CONFIGURED = False


def configure_logging() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return

    level = getattr(logging, LOG_LEVEL, logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s"
    )

    root = logging.getLogger()
    root.setLevel(level)

    if not any(getattr(handler, "_reconcilehub_console", False) for handler in root.handlers):
        console = logging.StreamHandler()
        console.setFormatter(formatter)
        console._reconcilehub_console = True  # type: ignore[attr-defined]
        root.addHandler(console)

    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        log_path = LOG_DIR / "reconcilehub.log"
        if not any(getattr(handler, "_reconcilehub_file", False) for handler in root.handlers):
            file_handler = RotatingFileHandler(
                log_path,
                maxBytes=10 * 1024 * 1024,
                backupCount=5,
                encoding="utf-8",
            )
            file_handler.setFormatter(formatter)
            file_handler._reconcilehub_file = True  # type: ignore[attr-defined]
            root.addHandler(file_handler)
    except OSError:
        root.warning("Could not initialize file logging in %s", LOG_DIR)

    _CONFIGURED = True
