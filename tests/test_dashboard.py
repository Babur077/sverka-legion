import sqlite3
from datetime import datetime

import utils.db_manager as db
from backend.app.repositories import dashboard, jobs


def test_dashboard_aggregates_generic_and_bank_runs(tmp_path, monkeypatch):
    db_path = tmp_path / "dashboard.db"
    monkeypatch.setattr(db, "DB_PATH", str(db_path))
    monkeypatch.setattr(dashboard.db, "DB_PATH", str(db_path))
    monkeypatch.setattr(jobs.db, "DB_PATH", str(db_path))
    db.init_db()

    month = datetime.now().strftime("%Y-%m")

    ok, _, _ = db.save_reconciliation_run(
        "reconciliation_builder",
        "alice",
        {
            "run_id": "builder-1",
            "period_month": month,
            "status": "WARNING",
            "definition_name": "1C ↔ Bank",
            "summary": {
                "matched_count": 90,
                "discrepancy_count": 10,
                "match_percentage": 90,
            },
        },
    )
    assert ok

    ok, _, _ = db.save_reconciliation_run(
        "bank_rrn",
        "bob",
        {
            "run_id": "bank-1",
            "period_month": month,
            "status": "COMPLETED",
            "bank_name": "Test Bank",
            "summary": {
                "matched_count": 98,
                "mismatch_count": 1,
                "only_our_count": 1,
                "only_bank_count": 0,
            },
        },
    )
    assert ok

    job_id = jobs.create_job(
        "reconciliation_builder",
        "alice",
        {"params": {}},
    )
    assert job_id

    data = dashboard.get_dashboard_data(
        allowed_modules={
            "bank_rrn": "Bank RRN",
            "reconciliation_builder": "Constructor",
        },
        username="alice",
        months=1,
        include_all_jobs=False,
    )

    assert data["summary"]["runs"] == 2
    assert data["summary"]["problem_runs"] == 2
    assert data["summary"]["discrepancies"] == 12
    assert round(data["summary"]["average_match_percentage"], 2) == 94.0
    assert data["summary"]["queued_jobs"] == 1
    assert len(data["recent_runs"]) == 2

    by_module = {item["module_id"]: item for item in data["modules"]}
    assert by_module["reconciliation_builder"]["average_match_percentage"] == 90
    assert by_module["bank_rrn"]["average_match_percentage"] == 98
    assert data["trend"][0]["runs"] == 2


def test_dashboard_respects_module_filter_and_job_scope(tmp_path, monkeypatch):
    db_path = tmp_path / "dashboard_scope.db"
    monkeypatch.setattr(db, "DB_PATH", str(db_path))
    monkeypatch.setattr(dashboard.db, "DB_PATH", str(db_path))
    monkeypatch.setattr(jobs.db, "DB_PATH", str(db_path))
    db.init_db()

    month = datetime.now().strftime("%Y-%m")
    for module_id, user, run_id in [
        ("bank_rrn", "alice", "bank-a"),
        ("reconciliation_builder", "alice", "builder-a"),
    ]:
        ok, _, _ = db.save_reconciliation_run(
            module_id,
            user,
            {
                "run_id": run_id,
                "period_month": month,
                "summary": {
                    "matched_count": 1,
                    "discrepancy_count": 0,
                    "match_percentage": 100,
                },
            },
        )
        assert ok

    jobs.create_job("reconciliation_builder", "alice", {"params": {}})
    jobs.create_job("reconciliation_builder", "bob", {"params": {}})

    own = dashboard.get_dashboard_data(
        allowed_modules={
            "bank_rrn": "Bank RRN",
            "reconciliation_builder": "Constructor",
        },
        username="alice",
        months=1,
        module_id="reconciliation_builder",
        include_all_jobs=False,
    )
    assert own["summary"]["runs"] == 1
    assert own["recent_runs"][0]["module_id"] == "reconciliation_builder"
    assert len(own["jobs"]) == 1
    assert own["jobs"][0]["created_by"] == "alice"

    manager = dashboard.get_dashboard_data(
        allowed_modules={"reconciliation_builder": "Constructor"},
        username="alice",
        months=1,
        include_all_jobs=True,
    )
    assert len(manager["jobs"]) == 2


def test_dashboard_does_not_require_full_archive_payload_json(tmp_path, monkeypatch):
    db_path = tmp_path / "dashboard_light_payload.db"
    monkeypatch.setattr(db, "DB_PATH", str(db_path))
    monkeypatch.setattr(dashboard.db, "DB_PATH", str(db_path))
    db.init_db()

    month = datetime.now().strftime("%Y-%m")
    ok, _, record_id = db.save_reconciliation_run(
        "bank_rrn",
        "alice",
        {
            "run_id": "large-run",
            "period_month": month,
            "bank_name": "Large Legacy Bank",
            "summary": {
                "matched_count": 10,
                "discrepancy_count": 1,
                "match_percentage": 90.91,
            },
        },
    )
    assert ok
    assert record_id is not None

    # A full json.loads() of payload_json would fail here. Dashboard must work
    # from summary_json + a tiny bounded prefix only.
    malformed_large_payload = (
        '{"bank_name":"Large Legacy Bank","result_snapshot":"'
        + ("x" * 200_000)
    )
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE reconciliation_runs SET payload_json = ? WHERE id = ?",
            (malformed_large_payload, record_id),
        )
        conn.commit()

    data = dashboard.get_dashboard_data(
        allowed_modules={"bank_rrn": "Bank RRN"},
        username="alice",
        months=1,
    )

    assert data["summary"]["runs"] == 1
    assert data["recent_runs"][0]["bank_name"] == "Large Legacy Bank"
    assert data["recent_runs"][0]["matched_count"] == 10

