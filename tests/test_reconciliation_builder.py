import json

from modules.reconciliation_builder.engine import ReconciliationBuilderModule


def _csv(text: str) -> bytes:
    return text.strip().encode("utf-8")


def test_builder_matches_by_key_amount_and_date():
    module = ReconciliationBuilderModule()

    source_a = _csv(
        """
RRN;Amount;Date
ABC;1000;01.09.2026
DEF;2000;02.09.2026
GHI;3000;03.09.2026
"""
    )
    source_b = _csv(
        """
Reference;Sum;PostingDate
abc;1000;01.09.2026
def;2005;02.09.2026
XYZ;500;03.09.2026
"""
    )

    result = module.run(
        {"source_a": source_a, "source_b": source_b},
        {
            "source_a_filename": "a.csv",
            "source_b_filename": "b.csv",
            "key_pairs": json.dumps([
                {"left": "RRN", "right": "Reference", "mode": "text"},
            ]),
            "amount_a_col": "Amount",
            "amount_b_col": "Sum",
            "amount_tolerance": "10",
            "date_a_col": "Date",
            "date_b_col": "PostingDate",
            "date_tolerance_days": "0",
            "ignore_empty_keys": "true",
            "dayfirst": "true",
        },
    )

    generic = result.custom_metrics["generic"]

    assert result.summary.matched_count == 2
    assert result.summary.discrepancy_count == 2
    assert round(result.summary.match_percentage, 2) == 50.0
    assert len(generic["matched"]) == 2
    assert len(generic["only_a"]) == 1
    assert len(generic["only_b"]) == 1
    assert len(generic["mismatches"]) == 0


def test_builder_marks_same_key_outside_tolerance_as_mismatch():
    module = ReconciliationBuilderModule()

    result = module.run(
        {
            "source_a": _csv("ID;Amount\n1;1000"),
            "source_b": _csv("ID;Amount\n1;1200"),
        },
        {
            "source_a_filename": "a.csv",
            "source_b_filename": "b.csv",
            "key_pairs": json.dumps([
                {"left": "ID", "right": "ID", "mode": "numeric"},
            ]),
            "amount_a_col": "Amount",
            "amount_b_col": "Amount",
            "amount_tolerance": "10",
        },
    )

    generic = result.custom_metrics["generic"]

    assert result.summary.matched_count == 0
    assert result.summary.discrepancy_count == 1
    assert len(generic["mismatches"]) == 1
    assert generic["mismatches"][0]["amount_delta"] == 200
    assert "Сумма вне допуска" in generic["mismatches"][0]["reason"]


def test_builder_pairs_duplicate_keys_deterministically_by_best_amount():
    module = ReconciliationBuilderModule()

    result = module.run(
        {
            "source_a": _csv("ID;Amount\nA;100\nA;200"),
            "source_b": _csv("ID;Amount\nA;200\nA;100"),
        },
        {
            "source_a_filename": "a.csv",
            "source_b_filename": "b.csv",
            "key_pairs": json.dumps([
                {"left": "ID", "right": "ID", "mode": "text"},
            ]),
            "amount_a_col": "Amount",
            "amount_b_col": "Amount",
            "amount_tolerance": "0",
        },
    )

    generic = result.custom_metrics["generic"]
    assert result.summary.matched_count == 2
    assert [row["amount_delta"] for row in generic["matched"]] == [0, 0]
