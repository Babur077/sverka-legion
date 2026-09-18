import pandas as pd
import polars as pl

from core.recon_engine import run_rrn_reconciliation


def base_cfg(**overrides):
    cfg = {
        "our_date": "date",
        "our_rrn": "rrn",
        "our_amt": "amount",
        "our_status": "status",
        "our_rev": "Удалить возвраты 🗑",
        "bank_date": "date",
        "bank_rrn": "rrn",
        "bank_amt": "amount",
        "bank_tid": None,
        "bank_status": "status",
        "bank_rev": "Удалить возвраты 🗑",
        "rev_words": ["refund", "возврат"],
        "deduct_commission": False,
        "dup_action": "Оставить все дубликаты",
        "tolerance": 0.01,
        "unbind_mismatches": False,
    }
    cfg.update(overrides)
    return cfg


def frame(rows):
    return pl.DataFrame(rows)


def test_exact_rrn_match_and_normalization():
    our = frame([
        {"date": "2026-09-01", "rrn": "00123.0", "amount": "1000", "status": "OK"},
    ])
    bank = frame([
        {"date": "2026-09-01", "rrn": "00123", "amount": "1000.00", "status": "OK"},
    ])

    result = run_rrn_reconciliation(our, bank, base_cfg())

    assert result["matched_count"] == 1
    assert result["mismatch_count"] == 0
    assert result["only_our"].empty
    assert result["only_bank"].empty


def test_amount_mismatch_is_reported():
    our = frame([
        {"date": "2026-09-01", "rrn": "A100", "amount": "1000", "status": "OK"},
    ])
    bank = frame([
        {"date": "2026-09-01", "rrn": "A100", "amount": "1001", "status": "OK"},
    ])

    result = run_rrn_reconciliation(our, bank, base_cfg())

    assert result["matched_count"] == 1
    assert result["mismatch_count"] == 1
    assert result["amt_mismatches"].iloc[0]["Δ сумма"] == 1.0


def test_reversal_status_can_zero_out_transaction():
    our = frame([
        {"date": "2026-09-01", "rrn": "R100", "amount": "500", "status": "REFUND - client request"},
        {"date": "2026-09-01", "rrn": "R101", "amount": "500", "status": "OK"},
    ])
    bank = frame([
        {"date": "2026-09-01", "rrn": "R100", "amount": "500", "status": "REFUND - client request"},
        {"date": "2026-09-01", "rrn": "R101", "amount": "500", "status": "OK"},
    ])

    result = run_rrn_reconciliation(
        our,
        bank,
        base_cfg(
            our_rev="Изменить знак ➖",
            bank_rev="Изменить знак ➖",
        ),
    )

    assert result["matched_count"] == 2
    assert result["mismatch_count"] == 0


def test_epos_commission_is_joined_and_can_be_deducted():
    epos_registry = pd.DataFrame([
        {"terminal_id": "T1", "legal_entity": "LLC Test", "commission_pct": 2.0},
    ])

    our = frame([
        {"date": "2026-09-01", "rrn": "C100", "amount": "980", "status": "OK"},
    ])
    bank = frame([
        {"date": "2026-09-01", "rrn": "C100", "amount": "1000", "terminal": "T1", "status": "OK"},
    ])

    result = run_rrn_reconciliation(
        our,
        bank,
        base_cfg(bank_tid="terminal", deduct_commission=True),
        epos_registry=epos_registry,
    )

    assert result["matched_count"] == 1
    assert result["mismatch_count"] == 0
    assert result["total_commission"] == 20.0



def test_ui_reversal_labels_are_applied_case_insensitively_and_keep_null_status_rows():
    our = frame([
        {"date": "2026-09-01", "rrn": "R100", "amount": "500", "status": "REFUND"},
        {"date": "2026-09-01", "rrn": "R101", "amount": "700", "status": None},
    ])
    bank = frame([
        {"date": "2026-09-01", "rrn": "R100", "amount": "500", "status": "refund"},
        {"date": "2026-09-01", "rrn": "R101", "amount": "700", "status": None},
    ])

    result = run_rrn_reconciliation(
        our,
        bank,
        base_cfg(
            our_rev="Удалить строку",
            bank_rev="Удалить строку",
            rev_words=["Refund"],
        ),
    )

    assert result["matched_count"] == 1
    assert result["mismatch_count"] == 0
    assert result["summary"].iloc[-1]["Кол_во_у_нас"] == 1
    assert result["summary"].iloc[-1]["Кол_во_в_банке"] == 1


def test_unbind_mismatch_only_splits_the_mismatching_duplicate_row():
    our = frame([
        {"date": "2026-09-01", "rrn": "D100", "amount": "100", "status": "OK"},
        {"date": "2026-09-02", "rrn": "D100", "amount": "200", "status": "OK"},
    ])
    bank = frame([
        {"date": "2026-09-01", "rrn": "D100", "amount": "100", "status": "OK"},
        {"date": "2026-09-02", "rrn": "D100", "amount": "250", "status": "OK"},
    ])

    result = run_rrn_reconciliation(
        our,
        bank,
        base_cfg(unbind_mismatches=True),
    )

    assert result["matched_count"] == 1
    assert result["mismatch_count"] == 0
    assert len(result["only_our"]) == 1
    assert len(result["only_bank"]) == 1
    assert int((result["merged"]["_merge"] == "both").sum()) == 1


def test_inactive_epos_terminal_does_not_apply_commission():
    epos_registry = pd.DataFrame([
        {
            "terminal_id": "T1",
            "merchant_id": "MID1",
            "bank_acquirer": "Test Bank",
            "legal_entity": "LLC Test",
            "commission_pct": 2.0,
            "is_active": 0,
        },
    ])
    our = frame([
        {"date": "2026-09-01", "rrn": "C200", "amount": "1000", "status": "OK"},
    ])
    bank = frame([
        {"date": "2026-09-01", "rrn": "C200", "amount": "1000", "terminal": "T1", "status": "OK"},
    ])

    result = run_rrn_reconciliation(
        our,
        bank,
        base_cfg(bank_tid="terminal", deduct_commission=True),
        epos_registry=epos_registry,
    )

    assert result["matched_count"] == 1
    assert result["mismatch_count"] == 0
    assert result["total_commission"] == 0.0


def test_effective_commission_rate_and_epos_metadata_are_returned():
    epos_registry = pd.DataFrame([
        {
            "terminal_id": "T1",
            "merchant_id": "MID1",
            "bank_acquirer": "Test Bank",
            "legal_entity": "LLC Test",
            "commission_pct": 2.0,
            "is_active": 1,
        },
    ])
    our = frame([
        {"date": "2026-09-01", "rrn": "C300", "amount": "1000", "status": "OK"},
    ])
    bank = frame([
        {"date": "2026-09-01", "rrn": "C300", "amount": "1000", "terminal": "T1", "status": "OK"},
    ])

    result = run_rrn_reconciliation(
        our,
        bank,
        base_cfg(bank_tid="terminal"),
        epos_registry=epos_registry,
    )

    terminal = result["terminal_summary"][0]
    assert result["total_commission"] == 20.0
    assert result["effective_commission_rate"] == 2.0
    assert terminal["merchant_id"] == "MID1"
    assert terminal["bank_acquirer"] == "Test Bank"


def test_empty_rrn_is_unmatched_without_exposing_internal_sentinel():
    our = frame([
        {"date": "2026-09-01", "rrn": "", "amount": "100", "status": "OK"},
    ])
    bank = frame([
        {"date": "2026-09-01", "rrn": "", "amount": "100", "status": "OK"},
    ])

    result = run_rrn_reconciliation(our, bank, base_cfg())

    assert result["matched_count"] == 0
    assert result["only_our"].iloc[0]["RRN"] == ""
    assert result["only_bank"].iloc[0]["RRN"] == ""
    assert result["only_our"].iloc[0]["📝 Причина"] == "Пустой RRN"
    assert result["only_bank"].iloc[0]["📝 Причина"] == "Пустой RRN"



def test_invalid_date_does_not_change_rrn_presence_classification():
    our = frame([
        {"date": "not-a-date", "rrn": "Q100", "amount": "1000", "status": "OK"},
    ])
    bank = frame([
        {"date": "2026-09-01", "rrn": "Q100", "amount": "1000", "status": "OK"},
    ])

    result = run_rrn_reconciliation(our, bank, base_cfg())

    assert result["matched_count"] == 1
    assert result["mismatch_count"] == 0
    assert result["only_our"].empty
    assert result["only_bank"].empty
    assert result["data_quality"]["our"]["invalid_date"] == 1
    assert result["data_quality"]["bank"]["invalid_date"] == 0


def test_missing_date_is_reported_but_same_rrn_can_still_match():
    our = frame([
        {"date": "", "rrn": "Q200", "amount": "500", "status": "OK"},
    ])
    bank = frame([
        {"date": "", "rrn": "Q200", "amount": "500", "status": "OK"},
    ])

    result = run_rrn_reconciliation(our, bank, base_cfg())

    assert result["matched_count"] == 1
    assert result["only_our"].empty
    assert result["only_bank"].empty
    assert result["data_quality"]["our"]["missing_date"] == 1
    assert result["data_quality"]["bank"]["missing_date"] == 1
    assert "Дата не распознана" in result["summary"]["date"].tolist()
