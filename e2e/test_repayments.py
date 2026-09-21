"""Exercise the repayment module through the real API and archive."""
import pytest


pytestmark = pytest.mark.e2e


def test_repayment_run_and_archive_round_trip(api_client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    module_path = "/api/modules/ravan_1c"
    assert api_client.post(module_path + "/run").status_code == 401

    manifests = api_client.get("/api/modules", headers=headers)
    assert manifests.status_code == 200, manifests.text
    manifest = next(row for row in manifests.json() if row["id"] == "ravan_1c")
    assert manifest["name"] == "Сверка погашений"
    assert manifest["author"] == "Sayfulloh Abdusalomov"

    missing = api_client.post(module_path + "/run", headers=headers)
    assert missing.status_code == 400, missing.text

    response = api_client.post(
        module_path + "/run",
        headers=headers,
        files={
            "ravan_file": ("Ravan.csv", b"Partner,NDS,Kolvo,Summ\nAlpha MCHJ,12,5,1120\n", "text/csv"),
            "c_file": ("1C.csv", b"Alpha,5,1000\n", "text/csv"),
        },
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["status"] == "COMPLETED"
    assert result["summary"]["matched_count"] == 1
    assert result["summary"]["diff_sum"] == 0

    saved = api_client.post(
        module_path + "/archive",
        headers=headers,
        json={
            "run_id": result["run_id"],
            "status": result["status"],
            "summary": result["summary"],
            "result_snapshot": result,
            "source_files": ["Ravan.csv", "1C.csv"],
            "producer": "Sayfulloh Abdusalomov",
            "sum_tolerance": 1,
            "archive_schema_version": 1,
        },
    )
    assert saved.status_code == 200, saved.text
    record_id = saved.json()["id"]
    try:
        archive = api_client.get(module_path + "/archive", headers=headers)
        assert archive.status_code == 200, archive.text
        record = next(row for row in archive.json() if row["run_id"] == result["run_id"])
        assert record["result_snapshot"] == result
        assert record["source_files"] == ["Ravan.csv", "1C.csv"]
    finally:
        removed = api_client.delete(module_path + f"/archive/{record_id}", headers=headers)
        assert removed.status_code == 200, removed.text
