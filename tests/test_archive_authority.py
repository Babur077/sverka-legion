from __future__ import annotations

import pytest
from fastapi import HTTPException

import utils.db_manager as db
from backend.app.repositories.run_results import cache_run_result
from backend.app.services.archive_authority import (
    prepare_authoritative_archive_payload,
    update_ravan_archive_match,
)


def _init(tmp_path, monkeypatch):
    db_path = tmp_path / "authoritative_archive.db"
    monkeypatch.setattr(db, "DB_PATH", str(db_path))
    db.init_db()
    return db_path


def test_bank_archive_ignores_client_financial_totals_and_recalculates_reviews(
    tmp_path,
    monkeypatch,
):
    _init(tmp_path, monkeypatch)

    canonical = {
        "run_id": "bank-run-1",
        "module_id": "bank_rrn",
        "status": "WARNING",
        "summary": {
            "total_records_a": 2,
            "total_records_b": 2,
            "total_sum_a": 300,
            "total_sum_b": 310,
            "matched_count": 1,
            "discrepancy_count": 2,
            "diff_sum": 10,
            "match_percentage": 33.33,
            "execution_time_ms": 5,
        },
        "by_date": [
            {
                "date": "01.09.2026",
                "Кол_во_у_нас": 2,
                "Кол_во_в_банке": 2,
                "Δ кол-во": 0,
                "Сумма_у_нас": 300,
                "Сумма_в_банке": 310,
                "Δ суммы": 10,
            },
            {
                "date": "📊 ИТОГО (исходно)",
                "Кол_во_у_нас": 2,
                "Кол_во_в_банке": 2,
                "Δ кол-во": 0,
                "Сумма_у_нас": 300,
                "Сумма_в_банке": 310,
                "Δ суммы": 10,
            },
        ],
        "custom_metrics": {
            "rrn": {
                "only_our": [
                    {
                        "date_str": "01.09.2026",
                        "RRN": "OUR-1",
                        "amount": 100,
                        "checked": True,
                    }
                ],
                "only_bank": [
                    {
                        "date_str": "01.09.2026",
                        "RRN": "BANK-1",
                        "amount": 110,
                        "checked": True,
                        "terminal_id": "T1",
                        "raw": {
                            "raw_amount": 110,
                            "commission_pct": 1,
                            "commission_amount": 1.1,
                        },
                    }
                ],
                "matched_count": 1,
                "mismatch_count": 0,
                "terminal_summary": [
                    {
                        "terminal_id": "T1",
                        "tx_count": 2,
                        "total_volume": 310,
                        "commission_pct": 1,
                        "commission_amount": 3.1,
                        "net_volume": 306.9,
                    }
                ],
                "total_commission": 3.1,
                "detected_months": ["2026-09"],
                "data_quality": {
                    "our": {"missing_date": 1},
                    "bank": {},
                },
            }
        },
    }
    cache_run_result(
        "bank_rrn",
        "bank-run-1",
        "alice",
        canonical,
        params={
            "our_date_col": "Date",
            "our_rrn_col": "RRN",
            "bank_date_col": "Date",
            "bank_rrn_col": "RRN",
            "tolerance": "0.01",
            "dup_action": "Ничего не делать",
        },
        source_files=["our.xlsx", "bank.xlsx"],
    )

    prepared = prepare_authoritative_archive_payload(
        "bank_rrn",
        "alice",
        {
            "run_id": "bank-run-1",
            "bank_name": "Test Bank",
            "period_month": "2026-09",
            "assigned_terminal_id": "T1",
            # These forged values must never become authoritative.
            "total_our": 999999999,
            "total_bank": -123,
            "difference": 777,
            "matched_count": 999,
            "summary": {"total_sum_a": 999999999},
            "review": {
                "excluded_our_indices": [0],
                "excluded_bank_indices": [0],
                "reasons_our": {"0": "Технический возврат"},
                "reasons_bank": {"0": "Технический возврат"},
            },
        },
    )

    assert prepared["total_our"] == 200
    assert prepared["total_bank"] == 200
    assert prepared["difference"] == 0
    assert prepared["only_our_count"] == 0
    assert prepared["only_bank_count"] == 0
    assert prepared["matched_count"] == 1
    assert prepared["source_our_name"] == "our.xlsx"
    assert prepared["source_bank_name"] == "bank.xlsx"
    assert prepared["summary"]["total_sum_a"] == 200
    assert prepared["summary"]["total_sum_b"] == 200
    assert prepared["result_snapshot"]["custom_metrics"]["rrn"]["only_our"][0]["checked"] is False
    assert prepared["terminals_summary"][0]["tx_count"] == 1
    assert prepared["terminals_summary"][0]["total_volume"] == 200
    assert prepared["archive_schema_version"] == 3
    assert prepared["status"] == "WARNING"


def test_direct_archive_requires_a_server_owned_run(tmp_path, monkeypatch):
    _init(tmp_path, monkeypatch)

    with pytest.raises(HTTPException) as exc:
        prepare_authoritative_archive_payload(
            "bank_rrn",
            "alice",
            {"run_id": "invented-client-run", "total_our": 999},
        )

    assert exc.value.status_code == 404


def _ravan_snapshot():
    row = {
        "Row_ID": "ravan-run-1-1",
        "Match_Type": "fuzzy",
        "Name_Similarity": 94.5,
        "Needs_Review": True,
        "Match_Confirmed": False,
        "Partner_Ravan": "ABDIMUMIN BEKPOLAT",
        "NDS": 0,
        "Kolvo_Ravan": 2,
        "Summ_Ravan": 200,
        "Summ_Corrected": 200,
        "Partner_C": "ABDIMUNIN BEKPOLAT",
        "Kolvo_C": 2,
        "Summ_C": 200,
        "Kolvo_Difference": 0,
        "Summ_Difference": 0,
        "Status": "OK",
    }
    return {
        "run_id": "ravan-run-1",
        "module_id": "ravan_1c",
        "status": "COMPLETED",
        "summary": {
            "total_records_a": 1,
            "total_records_b": 1,
            "total_sum_a": 200,
            "total_sum_b": 200,
            "matched_count": 1,
            "discrepancy_count": 0,
            "diff_sum": 0,
            "match_percentage": 100,
            "execution_time_ms": 3,
        },
        "by_category": [{"status": "OK", "count": 1}],
        "discrepancies": [],
        "custom_metrics": {
            "ravan_1c": {
                "rows": [row],
                "status_counts": {"OK": 1},
                "fuzzy_review_count": 1,
                "sum_tolerance": 1,
            }
        },
    }


def test_ravan_review_is_recalculated_on_server_and_owner_checked(tmp_path, monkeypatch):
    _init(tmp_path, monkeypatch)
    snapshot = _ravan_snapshot()

    ok, _, _ = db.save_reconciliation_run(
        "ravan_1c",
        "alice",
        {
            "run_id": "ravan-run-1",
            "status": "COMPLETED",
            "summary": snapshot["summary"],
            "result_snapshot": snapshot,
            "archive_schema_version": 3,
        },
    )
    assert ok

    with pytest.raises(HTTPException) as exc:
        update_ravan_archive_match(
            "bob",
            "ravan-run-1",
            "ravan-run-1-1",
            "confirm",
        )
    assert exc.value.status_code == 404

    confirmed = update_ravan_archive_match(
        "alice",
        "ravan-run-1",
        "ravan-run-1-1",
        "confirm",
    )["result_snapshot"]
    confirmed_row = confirmed["custom_metrics"]["ravan_1c"]["rows"][0]
    assert confirmed_row["Needs_Review"] is False
    assert confirmed_row["Match_Confirmed"] is True

    unlinked = update_ravan_archive_match(
        "alice",
        "ravan-run-1",
        "ravan-run-1-1",
        "unlink",
    )["result_snapshot"]
    rows = unlinked["custom_metrics"]["ravan_1c"]["rows"]
    assert len(rows) == 2
    assert {row["Status"] for row in rows} == {"Нет в !C", "Нет в Ravan"}
    assert unlinked["summary"]["matched_count"] == 0
    assert unlinked["summary"]["discrepancy_count"] == 2

    stored = db.get_reconciliation_runs("ravan_1c")[0]
    assert stored["created_by"] == "alice"
    assert len(stored["result_snapshot"]["custom_metrics"]["ravan_1c"]["rows"]) == 2
