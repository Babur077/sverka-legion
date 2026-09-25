import sqlite3

import utils.db_manager as db
from backend.app.repositories.test_vorona import (
    list_import_batches,
    load_active_datasets,
    save_import_batch,
)
from modules.test_vorona.engine import TestVoronaModule


def _record(**overrides):
    row = {
        "row_index": 2,
        "date": "2026-09-01",
        "year": 2026,
        "month": 9,
        "inn": "307128450",
        "vid": "V112",
        "partner": "IMAN HALAL",
        "amount": 1000.0,
        "commission": 0.0,
        "status": "",
        "service": "",
        "side": "",
        "raw": {},
        "row_hash": "row-hash",
    }
    row.update(overrides)
    return row


def test_persistent_import_rejects_duplicate_and_can_replace_period(tmp_path, monkeypatch):
    db_path = tmp_path / "vorona.db"
    monkeypatch.setattr(db, "DB_PATH", str(db_path))
    db.init_db()

    first = save_import_batch(
        source_type="bank",
        year=2026,
        month=9,
        filename="bank-sep.xlsx",
        file_hash="file-a",
        records=[_record(amount=1000)],
        username="tester",
        replace_existing=False,
    )
    assert first["state"] == "saved"

    duplicate = save_import_batch(
        source_type="bank",
        year=2026,
        month=9,
        filename="bank-sep-copy.xlsx",
        file_hash="file-a",
        records=[_record(amount=1000)],
        username="tester",
        replace_existing=False,
    )
    assert duplicate["state"] == "duplicate"

    conflict = save_import_batch(
        source_type="bank",
        year=2026,
        month=9,
        filename="bank-sep-fixed.xlsx",
        file_hash="file-b",
        records=[_record(amount=1200)],
        username="tester",
        replace_existing=False,
    )
    assert conflict["state"] == "conflict"

    replaced = save_import_batch(
        source_type="bank",
        year=2026,
        month=9,
        filename="bank-sep-fixed.xlsx",
        file_hash="file-b",
        records=[_record(amount=1200)],
        username="tester",
        replace_existing=True,
    )
    assert replaced["state"] == "saved"
    assert replaced["replaced_batch_id"] == first["batch"]["id"]

    batches = list_import_batches(year=2026, month=9)
    assert len(batches) == 2
    assert sum(bool(item["is_active"]) for item in batches) == 1
    assert next(item for item in batches if item["is_active"])["filename"] == "bank-sep-fixed.xlsx"


def test_active_datasets_only_use_current_period_version(tmp_path, monkeypatch):
    db_path = tmp_path / "vorona-active.db"
    monkeypatch.setattr(db, "DB_PATH", str(db_path))
    db.init_db()

    save_import_batch(
        source_type="bank",
        year=2026,
        month=9,
        filename="old.xlsx",
        file_hash="old",
        records=[_record(amount=1000)],
        username="tester",
        replace_existing=False,
    )
    save_import_batch(
        source_type="bank",
        year=2026,
        month=9,
        filename="new.xlsx",
        file_hash="new",
        records=[_record(amount=1750, row_hash="row-new")],
        username="tester",
        replace_existing=True,
    )

    datasets = load_active_datasets(year=2026, through_month=9)
    assert len(datasets["bank"]) == 1
    assert datasets["bank"][0]["amount"] == 1750
    assert datasets["bank"][0]["source_file"] == "new.xlsx"


def test_test_vorona_can_run_from_persistent_datasets():
    module = TestVoronaModule()
    datasets = {
        "partners": [
            {"vid": "V112", "inn": "307128450", "partner": "IMAN HALAL"},
        ],
        "sales": [
            {
                "vid": "V112",
                "inn": "307128450",
                "partner": "IMAN HALAL",
                "amount": 10_000,
                "commission": 500,
                "Status": "SUCCESS",
            },
        ],
        "bank": [
            {"vid": "V112", "amount": 8_000},
        ],
        "faktura": [
            {"vid": "V112", "amount": 500},
        ],
        "opening_balances": [
            {"vid": "V112", "amount": 0},
        ],
        "one_c": [
            {"vid": "V112", "amount": 1_500, "side": "6990 / 6310"},
        ],
    }

    result = module.run_from_records(datasets, year=2026, through_month=9)

    row = result.custom_metrics["test_vorona"]["rows"][0]
    assert row["payment"] == 10_000
    assert row["bank"] == 8_000
    assert row["faktura"] == 500
    assert row["komissiya"] == 500
    assert row["saldo"] == 1_500
    assert row["one_c"] == 1_500
    assert row["difference"] == 0
    assert row["difference_1c"] == 0
    assert row["status"] == "Без расхождений"


def test_migration_creates_test_vorona_tables(tmp_path, monkeypatch):
    db_path = tmp_path / "vorona-schema.db"
    monkeypatch.setattr(db, "DB_PATH", str(db_path))
    db.init_db()

    with sqlite3.connect(db_path) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }

    assert "test_vorona_import_batches" in tables
    assert "test_vorona_records" in tables
