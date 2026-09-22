import pandas as pd
import polars as pl
import pytest

from core.recon_engine import run_rrn_reconciliation
from modules.bank_rrn.engine import BankRrnModule


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
    assert result["amt_mismatches"].iloc[0]["status_our"] == "OK"
    assert result["amt_mismatches"].iloc[0]["status_bank"] == "OK"


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


@pytest.mark.parametrize(
    ("commission_pct", "expected_commission", "expected_net"),
    [
        (0.36, 360.0, 99640.0),
        (0.363, 363.0, 99637.0),
    ],
)
def test_fractional_epos_commission_keeps_precision_in_reconciliation(
    commission_pct,
    expected_commission,
    expected_net,
):
    epos_registry = pd.DataFrame([
        {
            "terminal_id": "T-PRECISE",
            "legal_entity": "LLC Precision",
            "commission_pct": commission_pct,
            "is_active": 1,
        },
    ])
    our = frame([
        {
            "date": "2026-09-01",
            "rrn": "P100",
            "amount": str(expected_net),
            "status": "OK",
        },
    ])
    bank = frame([
        {
            "date": "2026-09-01",
            "rrn": "P100",
            "amount": "100000",
            "terminal": "T-PRECISE",
            "status": "OK",
        },
    ])

    result = run_rrn_reconciliation(
        our,
        bank,
        base_cfg(bank_tid="terminal", deduct_commission=True),
        epos_registry=epos_registry,
    )

    assert result["matched_count"] == 1
    assert result["mismatch_count"] == 0
    assert result["total_commission"] == pytest.approx(expected_commission)
    terminal = result["terminal_summary"][0]
    assert terminal["commission_pct"] == pytest.approx(commission_pct)
    assert terminal["commission_amount"] == pytest.approx(expected_commission)
    assert terminal["net_volume"] == pytest.approx(expected_net)


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
    assert result["only_our"].iloc[0]["status_our"] == "OK"
    assert result["only_bank"].iloc[0]["status_bank"] == "OK"
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



def test_invalid_amount_is_not_silently_treated_as_zero():
    our = frame([
        {"date": "2026-09-01", "rrn": "A200", "amount": "not-a-number", "status": "OK"},
    ])
    bank = frame([
        {"date": "2026-09-01", "rrn": "A200", "amount": "0", "status": "OK"},
    ])

    result = run_rrn_reconciliation(our, bank, base_cfg())

    assert result["matched_count"] == 1
    assert result["mismatch_count"] == 1
    assert result["data_quality"]["our"]["invalid_amount"] == 1
    assert result["data_quality"]["our"]["missing_amount"] == 0

    mismatch = result["amt_mismatches"].iloc[0]
    assert pd.isna(mismatch["net_amount_our"])
    assert mismatch["net_amount_bank"] == 0.0
    assert pd.isna(mismatch["Δ сумма"])
    assert mismatch["amount_issue"] == "Невалидная сумма у нас"


def test_missing_amount_is_reported_separately_from_invalid_amount():
    our = frame([
        {"date": "2026-09-01", "rrn": "A201", "amount": "", "status": "OK"},
    ])
    bank = frame([
        {"date": "2026-09-01", "rrn": "A201", "amount": "100", "status": "OK"},
    ])

    result = run_rrn_reconciliation(our, bank, base_cfg())

    assert result["mismatch_count"] == 1
    assert result["data_quality"]["our"]["missing_amount"] == 1
    assert result["data_quality"]["our"]["invalid_amount"] == 0
    assert result["amt_mismatches"].iloc[0]["amount_issue"] == "Невалидная сумма у нас"


def test_reordered_duplicate_rrn_pairs_by_date_and_amount_not_input_order():
    our = frame([
        {"date": "2026-09-01", "rrn": "D200", "amount": "100", "status": "OK"},
        {"date": "2026-09-01", "rrn": "D200", "amount": "250", "status": "OK"},
        {"date": "2026-09-02", "rrn": "D200", "amount": "400", "status": "OK"},
    ])
    bank = frame([
        {"date": "2026-09-02", "rrn": "D200", "amount": "400", "status": "OK"},
        {"date": "2026-09-01", "rrn": "D200", "amount": "250", "status": "OK"},
        {"date": "2026-09-01", "rrn": "D200", "amount": "100", "status": "OK"},
    ])

    result = run_rrn_reconciliation(our, bank, base_cfg())

    assert result["matched_count"] == 3
    assert result["mismatch_count"] == 0
    assert result["only_our"].empty
    assert result["only_bank"].empty


def test_duplicate_pairing_keeps_real_difference_visible_after_reordering():
    our = frame([
        {"date": "2026-09-01", "rrn": "D201", "amount": "100", "status": "OK"},
        {"date": "2026-09-01", "rrn": "D201", "amount": "250", "status": "OK"},
    ])
    bank = frame([
        {"date": "2026-09-01", "rrn": "D201", "amount": "251", "status": "OK"},
        {"date": "2026-09-01", "rrn": "D201", "amount": "100", "status": "OK"},
    ])

    result = run_rrn_reconciliation(our, bank, base_cfg())

    assert result["matched_count"] == 2
    assert result["mismatch_count"] == 1
    mismatch = result["amt_mismatches"].iloc[0]
    assert mismatch["net_amount_our"] == 250.0
    assert mismatch["net_amount_bank"] == 251.0
    assert mismatch["Δ сумма"] == 1.0



def test_duplicate_rows_keep_transaction_statuses():
    our = frame([
        {"date": "2026-09-01", "rrn": "D300", "amount": "100", "status": "SUCCESS"},
        {"date": "2026-09-02", "rrn": "D300", "amount": "200", "status": "DECLINED"},
    ])
    bank = frame([
        {"date": "2026-09-01", "rrn": "B300", "amount": "100", "status": "SETTLED"},
        {"date": "2026-09-02", "rrn": "B300", "amount": "200", "status": "REVERSED"},
    ])

    result = run_rrn_reconciliation(
        our,
        bank,
        base_cfg(rev_words=[]),
    )

    assert set(result["dups_our"]["status_our"].tolist()) == {"SUCCESS", "DECLINED"}
    assert set(result["dups_bank"]["status_bank"].tolist()) == {"SETTLED", "REVERSED"}


def test_bank_rrn_module_trims_selected_column_names(monkeypatch):
    our = frame([
        {"Date": "2026-09-01", "RRN": "W100", "Summa": "1000", "Status": "OK"},
    ])
    bank = frame([
        {"Date": "2026-09-01", "RRN": "W100", "Summa": "1000", "Status": "OK"},
    ])

    def fake_loader(_file_bytes, file_name, **_kwargs):
        return our if str(file_name).startswith("our") else bank

    monkeypatch.setattr("modules.bank_rrn.engine.load_file_polars", fake_loader)
    monkeypatch.setattr(
        "modules.bank_rrn.engine.get_epos_registry",
        lambda: pd.DataFrame(),
    )

    result = BankRrnModule().run(
        {"our_file": b"our", "bank_file": b"bank"},
        {
            "our_filename": "our.xlsx",
            "bank_filename": "bank.xlsx",
            "our_date_col": "  Date  ",
            "our_rrn_col": " RRN ",
            "our_amt_col": " Summa ",
            "our_status_col": " Status ",
            "bank_date_col": " Date ",
            "bank_rrn_col": "  RRN  ",
            "bank_amt_col": " Summa ",
            "bank_status_col": " Status ",
            "bank_tid_col": "   ",
            "rev_words": "",
            "our_rev_action": "Ничего не делать",
            "bank_rev_action": "Ничего не делать",
            "dup_action": "Ничего не делать (оставить все)",
            "unbind_mismatches": False,
            "tolerance": 0.01,
            "deduct_commission": False,
        },
    )

    assert result.summary.matched_count == 1
    assert result.summary.discrepancy_count == 0

