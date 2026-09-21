from __future__ import annotations

import os

import httpx
import pytest


BASE_URL = os.getenv("RECONCILEHUB_E2E_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
ADMIN_PASSWORD = os.getenv("RECONCILEHUB_ADMIN_PASSWORD", "e2e-admin")


@pytest.fixture(scope="session")
def base_url() -> str:
    return BASE_URL


@pytest.fixture()
def api_client(base_url: str):
    with httpx.Client(base_url=base_url, timeout=10.0) as client:
        yield client


def login(client: httpx.Client, username: str, password: str) -> str:
    response = client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200, response.text
    token = response.json().get("session_token")
    assert token
    return str(token)


@pytest.fixture()
def admin_token(api_client: httpx.Client) -> str:
    return login(api_client, "admin", ADMIN_PASSWORD)
