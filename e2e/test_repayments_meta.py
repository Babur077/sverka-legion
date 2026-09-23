"""Exercise the 1C ↔ Meta repayment module through the real API and archive."""

import pytest


pytestmark = pytest.mark.e2e


def test_repayments_run_and_archive_round_trip(api_client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    module_path = "/api/modules/repayments"

    manifests = api_client.get("/api/modules", headers=headers)
    assert manifests.status_code == 200, manifests.text
    manifest = next(row for row in manifests.json() if row["id"] == "repayments")
    assert manifest["name"] == "Сверка Погашений"
    assert manifest["workspace"] == "repayments"

    missing = api_client.post(module_path + "/run", headers=headers)
    assert missing.status_code == 400, missing.text

    response = api_client.post(
        module_path + "/run",
        headers=headers,
        files={
            "one_c_file": (
                "1C Погашение.csv",
                (
                    "Вх.номер,Дата,Сумма\n"
                    "12345,01.09.2026,1000\n"
                ).encode("utf-8-sig"),
                "text/csv",
            ),
            "meta_file": (
                "Meta Погашение.csv",
                (
                    "withdraw_unique_id,bank_date,bank_amount,our_system_date,"
                    "our_system_amount_success,contract_number\n"
                    "12345,01.09.2026,1000,02.09.2026,1000,C-1\n"
                ).encode("utf-8-sig"),
                "text/csv",
            ),
        },
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["status"] == "COMPLETED"
    assert result["summary"]["matched_count"] == 1
    assert result["summary"]["diff_sum"] == 0
    rows = result["custom_metrics"]["repayments"]["rows"]
    assert rows[0]["Комментарий"] == "Правильно"
    assert rows[0]["Номер договора опознание"] == "C-1"

    saved = api_client.post(
        module_path + "/archive",
        headers=headers,
        json={"run_id": result["run_id"]},
    )
    assert saved.status_code == 200, saved.text
    record_id = saved.json()["id"]

    try:
        archive = api_client.get(
            module_path + "/archive?summary_only=true",
            headers=headers,
        )
        assert archive.status_code == 200, archive.text
        summary_record = next(
            row for row in archive.json() if row["run_id"] == result["run_id"]
        )
        assert "result_snapshot" not in summary_record

        full = api_client.get(
            module_path + f"/archive/{record_id}",
            headers=headers,
        )
        assert full.status_code == 200, full.text
        assert full.json()["result_snapshot"]["run_id"] == result["run_id"]
    finally:
        removed = api_client.delete(
            module_path + f"/archive/{record_id}",
            headers=headers,
        )
        assert removed.status_code == 200, removed.text
