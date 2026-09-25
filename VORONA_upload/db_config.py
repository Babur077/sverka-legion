from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import quote_plus

try:
    from dotenv import load_dotenv
except ImportError:  # Standalone legacy launch still gives a clear DB error later.
    load_dotenv = None

if load_dotenv is not None:
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")


def get_database_url() -> str:
    explicit = os.getenv("VORONA_DATABASE_URL", "").strip()
    if explicit:
        return explicit

    user = os.getenv("VORONA_DB_USER", "postgres").strip() or "postgres"
    password = os.getenv("VORONA_DB_PASSWORD", "")
    host = os.getenv("VORONA_DB_HOST", "localhost").strip() or "localhost"
    port = os.getenv("VORONA_DB_PORT", "5432").strip() or "5432"
    database = os.getenv("VORONA_DB_NAME", "VORONA").strip() or "VORONA"

    auth = quote_plus(user)
    if password:
        auth += ":" + quote_plus(password)
    return f"postgresql+psycopg2://{auth}@{host}:{port}/{quote_plus(database)}"


DATABASE_URL = get_database_url()
