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


def test_numeric_rrn_matches_when_bank_has_leading_zero_padding():
    our = frame([
        {
            "date": "2026-09-01",
            "rrn": "30793201824",
            "amount": "1000",
            "status": "OK",
        },
    ])
    bank = frame([
        {
            "date": "2026-09-01",
            "rrn": "030793201824",
            "amount": "1000",
            "status": "OK",
        },
    ])

    result = run_rrn_reconciliation(our, bank, base_cfg())

    assert result["rrn_found_count"] == 1
    assert result["matched_count"] == 1
    assert result["mismatch_count"] == 0
    assert result["only_our"].empty
    assert result["only_bank"].empty


def test_alphanumeric_rrn_keeps_leading_zero_semantics():
    our = frame([
        {"date": "2026-09-01", "rrn": "0A123", "amount": "1000", "status": "OK"},
    ])
    bank = frame([
        {"date": "2026-09-01", "rrn": "A123", "amount": "1000", "status": "OK"},
    ])

    result = run_rrn_reconciliation(our, bank, base_cfg())

    assert result["rrn_found_count"] == 0
    assert len(result["only_our"]) == 1
    assert len(result["only_bank"]) == 1


def test_api_mode_skips_full_merged_materialization_and_keeps_unbind_results():
    our = frame([
        {"date": "2026-09-01", "rrn": "A100", "amount": "100", "status": "OK"},
        {"date": "2026-09-01", "rrn": "A200", "amount": "200", "status": "OK"},
    ])
    bank = frame([
        {"date": "2026-09-01", "rrn": "A100", "amount": "101", "status": "OK"},
        {"date": "2026-09-01", "rrn": "A200", "amount": "200", "status": "OK"},
    ])

    result = run_rrn_reconciliation(
        our,
        bank,
        base_cfg(include_merged=False, unbind_mismatches=True),
    )

    assert result["merged"] is None
    assert result["rrn_found_count"] == 2
    assert result["unbound_mismatch_count"] == 1
    assert len(result["only_our"]) == 1
    assert len(result["only_bank"]) == 1


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


def test_amount_mismatch_totals_show_full_compensation():
    our = frame([
        {"date": "2026-09-01", "rrn": "A1", "amount": "100", "status": "OK"},
        {"date": "2026-09-01", "rrn": "A2", "amount": "200", "status": "OK"},
    ])
    bank = frame([
        {"date": "2026-09-01", "rrn": "A1", "amount": "110", "status": "OK"},
        {"date": "2026-09-01", "rrn": "A2", "amount": "190", "status": "OK"},
    ])

    result = run_rrn_reconciliation(our, bank, base_cfg())

    assert result["mismatch_count"] == 2
    assert result["amount_mismatch_net_delta"] == pytest.approx(0)
    assert result["amount_mismatch_abs_delta"] == pytest.approx(20)
    assert result["amount_mismatch_positive_delta"] == pytest.approx(10)
    assert result["amount_mismatch_negative_delta"] == pytest.approx(-10)
    assert result["amount_mismatch_invalid_delta_count"] == 0


@pytest.mark.parametrize(
    ("dup_action", "expected_removed"),
    [
        ("Ничего не делать (оставить все)", 0),
        ("Оставить первую строку", 2),
        ("Оставить последнюю строку", 2),
        ("Удалить все дубли (и оригинал)", 3),
    ],
)
def test_duplicate_processing_reports_removed_rows(dup_action, expected_removed):
    rows = [
        {"date": "2026-09-01", "rrn": "DUP-1", "amount": "100", "status": "OK"},
        {"date": "2026-09-02", "rrn": "DUP-1", "amount": "100", "status": "OK"},
        {"date": "2026-09-03", "rrn": "DUP-1", "amount": "100", "status": "OK"},
    ]

    result = run_rrn_reconciliation(
        frame(rows),
        frame(rows),
        base_cfg(dup_action=dup_action),
    )

    assert result["dup_our_c"] == 3
    assert result["dup_bank_c"] == 3
    assert result["dup_our_rrn_c"] == 1
    assert result["dup_bank_rrn_c"] == 1
    assert result["dup_removed_our_c"] == expected_removed
    assert result["dup_removed_bank_c"] == expected_removed


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



def test_delete_approved_keeps_reversal_and_unrelated_rows():
    our = frame([
        {"date": "2026-09-01", "rrn": "R100", "amount": "500", "status": "APPROVED"},
        {"date": "2026-09-01", "rrn": "R100", "amount": "-500", "status": "REFUND"},
        {"date": "2026-09-01", "rrn": "R101", "amount": "700", "status": None},
    ])
    bank = frame([
        {"date": "2026-09-01", "rrn": "R100", "amount": "500", "status": "approved"},
        {"date": "2026-09-01", "rrn": "R100", "amount": "-500", "status": "refund"},
        {"date": "2026-09-01", "rrn": "R101", "amount": "700", "status": None},
    ])

    result = run_rrn_reconciliation(
        our,
        bank,
        base_cfg(
            our_rev="Удалить approved",
            bank_rev="Удалить approved",
            rev_words=["Refund"],
        ),
    )

    assert result["matched_count"] == 2
    assert result["mismatch_count"] == 0
    assert result["summary"].iloc[-1]["Кол_во_у_нас"] == 2
    assert result["summary"].iloc[-1]["Кол_во_в_банке"] == 2
    assert result["summary"].iloc[-1]["Сумма_у_нас"] == 200
    assert result["summary"].iloc[-1]["Сумма_в_банке"] == 200


def test_delete_reversed_keeps_approved_and_unrelated_rows():
    our = frame([
        {"date": "2026-09-01", "rrn": "R100", "amount": "500", "status": "APPROVED"},
        {"date": "2026-09-01", "rrn": "R100", "amount": "-500", "status": "REFUND"},
        {"date": "2026-09-01", "rrn": "R101", "amount": "700", "status": "APPROVED"},
    ])
    bank = frame([
        {"date": "2026-09-01", "rrn": "R100", "amount": "500", "status": "APPROVED"},
        {"date": "2026-09-01", "rrn": "R100", "amount": "-500", "status": "refund"},
        {"date": "2026-09-01", "rrn": "R101", "amount": "700", "status": "APPROVED"},
    ])

    result = run_rrn_reconciliation(
        our,
        bank,
        base_cfg(
            our_rev="Удалить reversed",
            bank_rev="Удалить reversed",
            rev_words=["Refund"],
        ),
    )

    assert result["matched_count"] == 2
    assert result["mismatch_count"] == 0
    assert result["summary"].iloc[-1]["Кол_во_у_нас"] == 2
    assert result["summary"].iloc[-1]["Кол_во_в_банке"] == 2
    assert result["summary"].iloc[-1]["Сумма_у_нас"] == 1200
    assert result["summary"].iloc[-1]["Сумма_в_банке"] == 1200


def test_delete_approved_and_reversed_removes_entire_reversal_rrn():
    our = frame([
        {"date": "2026-09-01", "rrn": "R100", "amount": "500", "status": "APPROVED"},
        {"date": "2026-09-01", "rrn": "R100", "amount": "-500", "status": "REFUND"},
        {"date": "2026-09-01", "rrn": "R101", "amount": "700", "status": "APPROVED"},
    ])
    bank = frame([
        {"date": "2026-09-01", "rrn": "R100", "amount": "500", "status": "APPROVED"},
        {"date": "2026-09-01", "rrn": "R100", "amount": "-500", "status": "REFUND"},
        {"date": "2026-09-01", "rrn": "R101", "amount": "700", "status": "APPROVED"},
    ])

    result = run_rrn_reconciliation(
        our,
        bank,
        base_cfg(
            our_rev="Удалить approved и reversed",
            bank_rev="Удалить approved и reversed",
            rev_words=["refund"],
        ),
    )

    assert result["matched_count"] == 1
    assert result["summary"].iloc[-1]["Кол_во_у_нас"] == 1
    assert result["summary"].iloc[-1]["Кол_во_в_банке"] == 1
    assert result["summary"].iloc[-1]["Сумма_у_нас"] == 700
    assert result["summary"].iloc[-1]["Сумма_в_банке"] == 700


def test_legacy_delete_row_label_maps_to_delete_approved_semantics():
    our = frame([
        {"date": "2026-09-01", "rrn": "R100", "amount": "100", "status": "APPROVED"},
        {"date": "2026-09-01", "rrn": "R100", "amount": "-100", "status": "REFUND"},
    ])
    bank = frame([
        {"date": "2026-09-01", "rrn": "R100", "amount": "100", "status": "APPROVED"},
        {"date": "2026-09-01", "rrn": "R100", "amount": "-100", "status": "REFUND"},
    ])

    result = run_rrn_reconciliation(
        our,
        bank,
        base_cfg(our_rev="Удалить строку", bank_rev="Удалить строку"),
    )

    assert result["matched_count"] == 1
    assert result["summary"].iloc[-1]["Сумма_у_нас"] == -100
    assert result["summary"].iloc[-1]["Сумма_в_банке"] == -100


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
    assert result["rrn_found_count"] == 2
    assert result["amount_mismatch_count_before_unbind"] == 1
    assert result["only_our_count_before_unbind"] == 0
    assert result["only_bank_count_before_unbind"] == 0
    assert result["unbound_mismatch_count"] == 1
    assert len(result["only_our"]) == 1
    assert len(result["only_bank"]) == 1
    assert result["only_our"].iloc[0]["status_our"] == "OK"
    assert result["only_bank"].iloc[0]["status_bank"] == "OK"
    assert int((result["merged"]["_merge"] == "both").sum()) == 1




def test_all_amount_mismatches_still_report_rrn_found_before_unbind():
    our = frame([
        {"date": "2026-09-01", "rrn": "A100", "amount": "100", "status": "OK"},
        {"date": "2026-09-01", "rrn": "A200", "amount": "200", "status": "OK"},
    ])
    bank = frame([
        {"date": "2026-09-01", "rrn": "A100", "amount": "101", "status": "OK"},
        {"date": "2026-09-01", "rrn": "A200", "amount": "202", "status": "OK"},
    ])

    result = run_rrn_reconciliation(
        our,
        bank,
        base_cfg(unbind_mismatches=True),
    )

    # Post-unbind there are no active joined rows, but both RRNs were found
    # on both sides before amount mismatches were intentionally split.
    assert result["matched_count"] == 0
    assert result["mismatch_count"] == 0
    assert result["rrn_found_count"] == 2
    assert result["amount_mismatch_count_before_unbind"] == 2
    assert result["only_our_count_before_unbind"] == 0
    assert result["only_bank_count_before_unbind"] == 0
    assert result["unbound_mismatch_count"] == 2
    assert len(result["only_our"]) == 2
    assert len(result["only_bank"]) == 2


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

