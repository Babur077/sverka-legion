import json
from pathlib import Path

import utils.db_manager as db
from backend.app.repositories import jobs
from backend.app.services import job_worker


def _prepare_db(tmp_path, monkeypatch):
    db_path = tmp_path / "reconcile_hub.db"
    monkeypatch.setattr(db, "DB_PATH", str(db_path))
    db.init_db()
    return db_path


def test_job_queue_claims_only_one_running_job(tmp_path, monkeypatch):
    _prepare_db(tmp_path, monkeypatch)

    first_id = jobs.create_job("reconciliation_builder", "tester", {"params": {}})
    second_id = jobs.create_job("reconciliation_builder", "tester", {"params": {}})

    first = jobs.claim_next_job()
    assert first is not None
    assert first["id"] == first_id
    assert first["status"] == "RUNNING"

    assert jobs.claim_next_job() is None

    jobs.complete_job(first_id, "run-1")
    second = jobs.claim_next_job()
    assert second is not None
    assert second["id"] == second_id
    assert second["status"] == "RUNNING"


def test_queued_job_can_be_cancelled(tmp_path, monkeypatch):
    _prepare_db(tmp_path, monkeypatch)

    job_id = jobs.create_job("reconciliation_builder", "tester", {"params": {}})
    ok, message = jobs.request_cancel(job_id, "tester")

    assert ok is True
    assert "отменена" in message
    job = jobs.get_job(job_id)
    assert job["status"] == "CANCELLED"
    assert job["cancel_requested"] is True
    assert jobs.claim_next_job() is None


def test_background_worker_completes_builder_job_and_archives_run(tmp_path, monkeypatch):
    db_path = _prepare_db(tmp_path, monkeypatch)

    job_id = jobs.create_job(
        "reconciliation_builder",
        "tester",
        {
            "params": {},
            "archive_payload": {
                "period_month": "2026-09",
                "definition_name": "Background test",
                "config_snapshot": {
                    "key_pairs": [
                        {"left": "ID", "right": "ID", "mode": "text"},
                    ],
                    "amount_tolerance": 0,
                    "date_tolerance_days": 0,
                    "ignore_empty_keys": True,
                    "dayfirst": True,
                },
            },
        },
    )

    root = Path(db_path).parent / "job_files" / str(job_id)
    root.mkdir(parents=True)
    source_a = root / "01_source_a.bin"
    source_b = root / "02_source_b.bin"
    source_a.write_bytes(b"ID;Amount\nA;100\n")
    source_b.write_bytes(b"ID;Amount\nA;100\n")

    jobs.set_job_files(
        job_id,
        {
            "source_a": {"path": str(source_a), "filename": "a.csv"},
            "source_b": {"path": str(source_b), "filename": "b.csv"},
        },
    )
    jobs.set_job_request(
        job_id,
        {
            "params": {
                "source_a_filename": "a.csv",
                "source_b_filename": "b.csv",
                "key_pairs": json.dumps([
                    {"left": "ID", "right": "ID", "mode": "text"},
                ]),
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
            },
            "archive_payload": {
                "period_month": "2026-09",
                "definition_name": "Background test",
                "config_snapshot": {
                    "key_pairs": [
                        {"left": "ID", "right": "ID", "mode": "text"},
                    ],
                    "amount_tolerance": 0,
                    "date_tolerance_days": 0,
                    "ignore_empty_keys": True,
                    "dayfirst": True,
                },
            },
        },
    )

    claimed = jobs.claim_next_job()
    assert claimed is not None
    job_worker._process_job(claimed)

    completed = jobs.get_job(job_id)
    assert completed["status"] == "COMPLETED"
    assert completed["progress"] == 100
    assert completed["run_id"]

    archived = db.get_reconciliation_runs("reconciliation_builder")
    assert len(archived) == 1
    assert archived[0]["run_id"] == completed["run_id"]
    assert archived[0]["result_snapshot"]["summary"]["matched_count"] == 1
    assert archived[0]["result_snapshot"]["summary"]["discrepancy_count"] == 0
    assert not root.exists()
