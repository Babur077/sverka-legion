from __future__ import annotations

import json
import time
from datetime import datetime

import httpx
import pytest

from conftest import login


pytestmark = pytest.mark.e2e


def auth(token: str, **extra: str) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    headers.update(extra)
    return headers


def poll_job(
    client: httpx.Client,
    token: str,
    job_id: int,
    timeout_seconds: float = 15.0,
) -> dict:
    deadline = time.monotonic() + timeout_seconds
    last = None
    while time.monotonic() < deadline:
        response = client.get(f"/api/jobs/{job_id}", headers=auth(token))
        assert response.status_code == 200, response.text
        last = response.json()
        if last["status"] in {"COMPLETED", "FAILED", "CANCELLED"}:
            return last
        time.sleep(0.2)
    pytest.fail(f"Job #{job_id} did not finish in time. Last state: {last}")


def test_login_template_version_job_archive_restore_dashboard_flow(
    api_client: httpx.Client,
    admin_token: str,
):
    token = admin_token
    headers = auth(token)

    me = api_client.get("/api/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["username"] == "admin"

    v1_config = {
        "key_pairs": [
            {
                "left": "ID",
                "right": "ID",
                "mode": "text",
                "left_transform": "none",
                "right_transform": "none",
            }
        ],
        "matching_mode": "one_to_one",
        "filters": [],
        "computed_fields": [],
        "result_columns_a": ["Amount"],
        "result_columns_b": ["Amount"],
        "amount_a_col": "Amount",
        "amount_b_col": "Amount",
        "amount_tolerance": 100,
        "amount_a_transform": "as_is",
        "amount_b_transform": "as_is",
        "date_a_col": "",
        "date_b_col": "",
        "date_tolerance_days": 0,
        "ignore_empty_keys": True,
        "dayfirst": True,
    }

    created = api_client.post(
        "/api/reconciliation-definitions",
        headers=headers,
        json={
            "name": "E2E 1C ↔ Bank",
            "description": "Critical workflow test",
            "config": v1_config,
            "change_note": "v1 for E2E",
        },
    )
    assert created.status_code == 200, created.text
    definition_id = int(created.json()["id"])
    assert created.json()["version_number"] == 1

    v2_config = dict(v1_config)
    v2_config["amount_tolerance"] = 0

    updated = api_client.put(
        f"/api/reconciliation-definitions/{definition_id}",
        headers=headers,
        json={
            "name": "E2E 1C ↔ Bank",
            "description": "Critical workflow test",
            "config": v2_config,
            "change_note": "Tighten amount tolerance",
        },
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["version_number"] == 2
    v2_id = int(updated.json()["version_id"])

    versions = api_client.get(
        f"/api/reconciliation-definitions/{definition_id}/versions",
        headers=headers,
    )
    assert versions.status_code == 200, versions.text
    version_rows = versions.json()
    assert [row["version_number"] for row in version_rows[:2]] == [2, 1]
    v1_id = next(row["id"] for row in version_rows if row["version_number"] == 1)

    month = datetime.now().strftime("%Y-%m")
    archive_payload = {
        "period_month": month,
        "definition_id": definition_id,
        "definition_name": "E2E 1C ↔ Bank",
        "definition_version_id": v2_id,
        "definition_version_number": 2,
        "source_a_name": "a.csv",
        "source_b_name": "b.csv",
        "source_files": ["a.csv", "b.csv"],
        "config": v2_config,
        "config_snapshot": v2_config,
        "archive_schema_version": 1,
    }

    form_data = {
        "source_a_filename": "a.csv",
        "source_b_filename": "b.csv",
        "key_pairs": json.dumps(v2_config["key_pairs"]),
        "filters": "[]",
        "computed_fields": "[]",
        "matching_mode": "one_to_one",
        "amount_a_col": "Amount",
        "amount_b_col": "Amount",
        "amount_tolerance": "0",
        "amount_a_transform": "as_is",
        "amount_b_transform": "as_is",
        "date_a_col": "",
        "date_b_col": "",
        "date_tolerance_days": "0",
        "ignore_empty_keys": "true",
        "dayfirst": "true",
        "definition_id": str(definition_id),
        "definition_name": "E2E 1C ↔ Bank",
        "archive_payload": json.dumps(archive_payload),
    }
    files = {
        "source_a": ("a.csv", b"ID;Amount\nA;100\n", "text/csv"),
        "source_b": ("b.csv", b"ID;Amount\nA;150\n", "text/csv"),
    }

    queued = api_client.post(
        "/api/jobs/reconciliation_builder",
        headers=headers,
        data=form_data,
        files=files,
    )
    assert queued.status_code == 200, queued.text
    job_id = int(queued.json()["id"])
    assert queued.json()["status"] in {"QUEUED", "RUNNING"}

    completed = poll_job(api_client, token, job_id)
    assert completed["status"] == "COMPLETED", completed.get("error")
    assert completed["progress"] == 100
    assert completed["run_id"]

    archive = api_client.get(
        "/api/modules/reconciliation_builder/archive",
        headers=headers,
    )
    assert archive.status_code == 200, archive.text
    runs = archive.json()
    run = next(item for item in runs if item.get("run_id") == completed["run_id"])

    assert run["definition_id"] == definition_id
    assert run["definition_version_id"] == v2_id
    assert run["definition_version_number"] == 2
    assert run["config_snapshot"]["amount_tolerance"] == 0
    assert run["result_snapshot"]["summary"]["discrepancy_count"] == 1
    assert len(run["result_snapshot"]["custom_metrics"]["generic"]["mismatches"]) == 1

    restored = api_client.post(
        f"/api/reconciliation-definitions/{definition_id}/versions/{v1_id}/restore",
        headers=headers,
        json={"change_note": "E2E rollback to v1"},
    )
    assert restored.status_code == 200, restored.text
    assert restored.json()["definition"]["current_version_number"] == 3
    assert restored.json()["definition"]["config"]["amount_tolerance"] == 100

    versions_after = api_client.get(
        f"/api/reconciliation-definitions/{definition_id}/versions",
        headers=headers,
    ).json()
    assert [row["version_number"] for row in versions_after[:3]] == [3, 2, 1]

    archive_after_restore = api_client.get(
        "/api/modules/reconciliation_builder/archive",
        headers=headers,
    ).json()
    historical_run = next(
        item for item in archive_after_restore
        if item.get("run_id") == completed["run_id"]
    )
    assert historical_run["definition_version_number"] == 2
    assert historical_run["config_snapshot"]["amount_tolerance"] == 0
    assert historical_run["result_snapshot"]["summary"]["discrepancy_count"] == 1

    dashboard = api_client.get(
        "/api/dashboard",
        headers=headers,
        params={"months": 1, "module_id": "reconciliation_builder"},
    )
    assert dashboard.status_code == 200, dashboard.text
    dashboard_data = dashboard.json()
    assert dashboard_data["summary"]["runs"] >= 1
    assert any(
        item.get("run_id") == completed["run_id"]
        and item.get("definition_version_number") == 2
        for item in dashboard_data["recent_runs"]
    )


def test_bearer_session_rbac_and_x_user_spoofing_are_enforced(
    api_client: httpx.Client,
    admin_token: str,
):
    admin_headers = auth(admin_token)
    username = f"e2e_auditor_{int(time.time() * 1000)}"

    created = api_client.post(
        "/api/admin/users",
        headers=admin_headers,
        json={
            "username": username,
            "password": "auditor-pass",
            "role": "auditor",
        },
    )
    assert created.status_code == 200, created.text

    auditor_token = login(api_client, username, "auditor-pass")
    auditor_headers = auth(auditor_token)

    definitions = api_client.get(
        "/api/reconciliation-definitions",
        headers=auditor_headers,
    )
    assert definitions.status_code == 200

    forbidden_create = api_client.post(
        "/api/reconciliation-definitions",
        headers=auditor_headers,
        json={
            "name": "Should fail",
            "description": "",
            "config": {"key_pairs": []},
        },
    )
    assert forbidden_create.status_code == 403

    forbidden_job = api_client.post(
        "/api/jobs/reconciliation_builder",
        headers=auditor_headers,
        data={},
    )
    assert forbidden_job.status_code == 403

    spoofed = api_client.get(
        "/api/admin/users",
        headers=auth(auditor_token, **{"X-User": "admin"}),
    )
    assert spoofed.status_code == 403

    logout = api_client.post("/api/auth/logout", headers=auditor_headers)
    assert logout.status_code == 200

    invalid_after_logout = api_client.get("/api/auth/me", headers=auditor_headers)
    assert invalid_after_logout.status_code == 401
