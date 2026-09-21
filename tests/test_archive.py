import json

import utils.db_manager as db


def test_archive_upserts_same_run_id_and_preserves_context(tmp_path, monkeypatch):
    db_path = tmp_path / "reconcile_hub.db"
    monkeypatch.setattr(db, "DB_PATH", str(db_path))
    db.init_db()

    ok, _ = db.save_reconciliation(
        user="tester",
        bank_name="Test Bank",
        tot_our=1000,
        tot_bank=1000,
        diff=0,
        matched_c=1,
        mismatch_c=0,
        only_our_c=0,
        only_bank_c=0,
        period_month="2026-09",
        total_commission=10,
        terminals_data=[],
        run_id="run-123",
        source_our_name="our.xlsx",
        source_bank_name="bank.xlsx",
        config_data={"tolerance": 0.01, "dup_action": "Оставить все дубликаты"},
        assigned_terminal_id="TID-OLD-001",
    )
    assert ok

    ok, message = db.save_reconciliation(
        user="tester",
        bank_name="Test Bank",
        tot_our=1000,
        tot_bank=990,
        diff=-10,
        matched_c=1,
        mismatch_c=0,
        only_our_c=0,
        only_bank_c=1,
        period_month="2026-09",
        total_commission=9,
        terminals_data=[],
        run_id="run-123",
        source_our_name="our.xlsx",
        source_bank_name="bank.xlsx",
        config_data={"tolerance": 0.01, "deduct_commission": True},
        assigned_terminal_id="TID-OLD-001",
    )
    assert ok
    assert "обновлена" in message

    archive = db.get_archive_data()
    assert len(archive) == 1

    row = archive.iloc[0]
    assert row["run_id"] == "run-123"
    assert row["source_our_name"] == "our.xlsx"
    assert row["source_bank_name"] == "bank.xlsx"
    assert row["assigned_terminal_id"] == "TID-OLD-001"
    assert row["difference"] == -10
    assert row["only_bank_count"] == 1
    assert json.loads(row["config_json"])["deduct_commission"] is True



def test_init_db_migrates_archive_with_assigned_terminal_column(tmp_path, monkeypatch):
    import sqlite3

    db_path = tmp_path / "legacy_archive.db"
    monkeypatch.setattr(db, "DB_PATH", str(db_path))

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE reconciliation_archive (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                username TEXT,
                bank_name TEXT,
                total_our REAL,
                total_bank REAL,
                difference REAL,
                matched_count INTEGER,
                mismatch_count INTEGER,
                only_our_count INTEGER,
                only_bank_count INTEGER
            )
            """
        )
        conn.commit()

    db.init_db()

    with sqlite3.connect(db_path) as conn:
        columns = {
            row[1]
            for row in conn.execute("PRAGMA table_info(reconciliation_archive)").fetchall()
        }

    assert "assigned_terminal_id" in columns



def test_generic_run_store_isolated_by_module(tmp_path, monkeypatch):
    db_path = tmp_path / "generic_runs.db"
    monkeypatch.setattr(db, "DB_PATH", str(db_path))
    db.init_db()

    ok, _, bank_id = db.save_reconciliation_run(
        "bank_rrn",
        "tester",
        {
            "run_id": "same-run",
            "period_month": "2026-09",
            "bank_name": "Test Bank",
            "total_bank": 100,
        },
    )
    assert ok

    ok, _, one_c_id = db.save_reconciliation_run(
        "bank_1c",
        "tester",
        {
            "run_id": "same-run",
            "period_month": "2026-09",
            "account": "20208000",
            "difference": 5,
        },
    )
    assert ok
    assert bank_id != one_c_id

    bank_runs = db.get_reconciliation_runs("bank_rrn")
    one_c_runs = db.get_reconciliation_runs("bank_1c")

    assert len(bank_runs) == 1
    assert bank_runs[0]["module_id"] == "bank_rrn"
    assert bank_runs[0]["bank_name"] == "Test Bank"

    assert len(one_c_runs) == 1
    assert one_c_runs[0]["module_id"] == "bank_1c"
    assert one_c_runs[0]["account"] == "20208000"

    assert db.delete_reconciliation_run("bank_rrn", bank_id) is True
    assert db.get_reconciliation_runs("bank_rrn") == []
    assert len(db.get_reconciliation_runs("bank_1c")) == 1


def test_generic_run_upserts_only_inside_same_module(tmp_path, monkeypatch):
    db_path = tmp_path / "generic_upsert.db"
    monkeypatch.setattr(db, "DB_PATH", str(db_path))
    db.init_db()

    ok, _, first_id = db.save_reconciliation_run(
        "bank_rrn",
        "tester",
        {"run_id": "run-1", "period_month": "2026-08", "total_bank": 100},
    )
    assert ok

    ok, message, second_id = db.save_reconciliation_run(
        "bank_rrn",
        "tester",
        {"run_id": "run-1", "period_month": "2026-08", "total_bank": 150},
    )
    assert ok
    assert "обновлена" in message
    assert first_id == second_id

    runs = db.get_reconciliation_runs("bank_rrn")
    assert len(runs) == 1
    assert runs[0]["total_bank"] == 150


def test_legacy_archive_is_copied_to_generic_bank_rrn_runs(tmp_path, monkeypatch):
    import sqlite3

    db_path = tmp_path / "legacy_migration.db"
    monkeypatch.setattr(db, "DB_PATH", str(db_path))

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE reconciliation_archive (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                username TEXT,
                bank_name TEXT,
                total_our REAL,
                total_bank REAL,
                difference REAL,
                matched_count INTEGER,
                mismatch_count INTEGER,
                only_our_count INTEGER,
                only_bank_count INTEGER,
                period_month TEXT,
                total_commission REAL,
                terminals_json TEXT,
                run_id TEXT,
                source_our_name TEXT,
                source_bank_name TEXT,
                config_json TEXT,
                assigned_terminal_id TEXT
            )
            """
        )
        conn.execute(
            """
            INSERT INTO reconciliation_archive (
                timestamp, username, bank_name, total_our, total_bank, difference,
                matched_count, mismatch_count, only_our_count, only_bank_count,
                period_month, total_commission, terminals_json, run_id,
                source_our_name, source_bank_name, config_json, assigned_terminal_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2026-09-20T10:00:00",
                "tester",
                "Legacy Bank",
                100,
                100,
                0,
                1,
                0,
                0,
                0,
                "2026-08",
                1,
                "[]",
                "legacy-run",
                "our.xlsx",
                "bank.xlsx",
                "{}",
                "TID-LEGACY",
            ),
        )
        conn.commit()

    db.init_db()

    runs = db.get_reconciliation_runs("bank_rrn")
    assert len(runs) == 1
    assert runs[0]["run_id"] == "legacy-run"
    assert runs[0]["bank_name"] == "Legacy Bank"
    assert runs[0]["assigned_terminal_id"] == "TID-LEGACY"

    # init_db is idempotent; migration must not duplicate old rows.
    db.init_db()
    assert len(db.get_reconciliation_runs("bank_rrn")) == 1



def test_generic_run_preserves_full_result_snapshot(tmp_path, monkeypatch):
    db_path = tmp_path / "builder_snapshot.db"
    monkeypatch.setattr(db, "DB_PATH", str(db_path))
    db.init_db()

    snapshot = {
        "run_id": "builder-run-1",
        "module_id": "reconciliation_builder",
        "status": "WARNING",
        "summary": {
            "total_records_a": 2,
            "total_records_b": 2,
            "matched_count": 1,
            "discrepancy_count": 1,
        },
        "custom_metrics": {
            "generic": {
                "matched": [
                    {
                        "key": "A-1",
                        "source_a": {"Amount": 100, "Status": "OK"},
                        "source_b": {"Sum": 100, "State": "SETTLED"},
                    }
                ],
                "mismatches": [
                    {
                        "key": "A-2",
                        "reason": "Сумма вне допуска",
                        "source_a": {"Amount": 200},
                        "source_b": {"Sum": 190},
                    }
                ],
                "only_a": [],
                "only_b": [],
            }
        },
    }

    ok, _, record_id = db.save_reconciliation_run(
        "reconciliation_builder",
        "tester",
        {
            "run_id": "builder-run-1",
            "period_month": "2026-09",
            "definition_name": "1C ↔ Bank",
            "summary": snapshot["summary"],
            "config_snapshot": {
                "key_pairs": [{"left": "Doc", "right": "Reference", "mode": "text"}],
                "amount_tolerance": 1,
            },
            "result_snapshot": snapshot,
            "archive_schema_version": 1,
        },
    )
    assert ok
    assert record_id is not None

    runs = db.get_reconciliation_runs("reconciliation_builder")
    assert len(runs) == 1
    assert runs[0]["result_snapshot"] == snapshot
    assert runs[0]["config_snapshot"]["amount_tolerance"] == 1
    assert runs[0]["archive_schema_version"] == 1
