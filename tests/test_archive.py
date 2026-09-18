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
    )
    assert ok
    assert "обновлена" in message

    archive = db.get_archive_data()
    assert len(archive) == 1

    row = archive.iloc[0]
    assert row["run_id"] == "run-123"
    assert row["source_our_name"] == "our.xlsx"
    assert row["source_bank_name"] == "bank.xlsx"
    assert row["difference"] == -10
    assert row["only_bank_count"] == 1
    assert json.loads(row["config_json"])["deduct_commission"] is True
