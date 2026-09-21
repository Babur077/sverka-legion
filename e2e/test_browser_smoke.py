from __future__ import annotations

import os

import pytest
from playwright.sync_api import Page, expect


pytestmark = pytest.mark.e2e


def test_login_dashboard_and_constructor_navigation(page: Page, base_url: str):
    password = os.getenv("RECONCILEHUB_ADMIN_PASSWORD", "e2e-admin")

    page.goto(base_url)

    expect(page.get_by_role("heading", name="Вход в ReconcileHub")).to_be_visible()
    page.locator("#login-username").fill("admin")
    page.locator("#login-password").fill(password)
    page.locator("#login-submit-button").click()

    expect(page.get_by_role("heading", name="Dashboard", exact=True)).to_be_visible()
    expect(page.locator("#nav-item-dashboard")).to_be_visible()
    expect(page.get_by_text("Динамика сверок", exact=True)).to_be_visible()

    page.locator("#nav-item-constructor").click()
    expect(page.get_by_role("heading", name="Конструктор сверок", exact=True)).to_be_visible()
    expect(page.get_by_role("button", name="Запустить сверку", exact=True).first).to_be_visible()

    page.locator("#nav-item-dashboard").click()
    expect(page.get_by_role("heading", name="Dashboard", exact=True)).to_be_visible()
