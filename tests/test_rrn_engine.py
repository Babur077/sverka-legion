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
