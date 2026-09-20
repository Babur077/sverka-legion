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



def test_builder_filters_rows_before_matching():
    module = ReconciliationBuilderModule()

    result = module.run(
        {
            "source_a": _csv("ID;Amount;Status\n1;100;OK\n2;200;CANCELLED"),
            "source_b": _csv("ID;Amount;Status\n1;100;OK\n2;200;CANCELLED"),
        },
        {
            "source_a_filename": "a.csv",
            "source_b_filename": "b.csv",
            "key_pairs": json.dumps([
                {"left": "ID", "right": "ID", "mode": "numeric"},
            ]),
            "filters": json.dumps([
                {"side": "a", "column": "Status", "operator": "not_equals", "value": "CANCELLED"},
                {"side": "b", "column": "Status", "operator": "not_equals", "value": "CANCELLED"},
            ]),
            "amount_a_col": "Amount",
            "amount_b_col": "Amount",
        },
    )

    generic = result.custom_metrics["generic"]
    assert result.summary.total_records_a == 1
    assert result.summary.total_records_b == 1
    assert result.summary.matched_count == 1
    assert generic["filter_stats"] == {
        "source_a_before": 2,
        "source_a_after": 1,
        "source_b_before": 2,
        "source_b_after": 1,
    }


def test_builder_key_transform_removes_formatting_noise():
    module = ReconciliationBuilderModule()

    result = module.run(
        {
            "source_a": _csv("Ref;Amount\n00 123;500"),
            "source_b": _csv("Reference;Amount\n123;500"),
        },
        {
            "source_a_filename": "a.csv",
            "source_b_filename": "b.csv",
            "key_pairs": json.dumps([
                {
                    "left": "Ref",
                    "right": "Reference",
                    "mode": "numeric",
                    "left_transform": "remove_spaces",
                    "right_transform": "none",
                },
            ]),
            "amount_a_col": "Amount",
            "amount_b_col": "Amount",
        },
    )

    assert result.summary.matched_count == 1
    assert result.summary.discrepancy_count == 0


def test_builder_can_invert_amount_sign_on_one_source():
    module = ReconciliationBuilderModule()

    result = module.run(
        {
            "source_a": _csv("ID;Amount\nA;1000"),
            "source_b": _csv("ID;Amount\nA;-1000"),
        },
        {
            "source_a_filename": "a.csv",
            "source_b_filename": "b.csv",
            "key_pairs": json.dumps([
                {"left": "ID", "right": "ID", "mode": "text"},
            ]),
            "amount_a_col": "Amount",
            "amount_b_col": "Amount",
            "amount_b_transform": "invert",
            "amount_tolerance": "0",
        },
    )

    assert result.summary.matched_count == 1
    assert result.summary.total_sum_a == 1000
    assert result.summary.total_sum_b == 1000


def test_builder_matches_one_to_many_by_group_sum():
    module = ReconciliationBuilderModule()

    result = module.run(
        {
            "source_a": _csv("ID;Amount\nA;100"),
            "source_b": _csv("ID;Amount\nA;40\nA;60"),
        },
        {
            "source_a_filename": "a.csv",
            "source_b_filename": "b.csv",
            "key_pairs": json.dumps([
                {"left": "ID", "right": "ID", "mode": "text"},
            ]),
            "matching_mode": "one_to_many",
            "amount_a_col": "Amount",
            "amount_b_col": "Amount",
            "amount_tolerance": "0",
        },
    )

    generic = result.custom_metrics["generic"]
    assert result.summary.matched_count == 1
    assert result.summary.discrepancy_count == 0
    assert generic["matched"][0]["match_type"] == "1↔N"
    assert generic["matched"][0]["grouped_rows_a"] == [2]
    assert generic["matched"][0]["grouped_rows_b"] == [2, 3]
    assert generic["matched"][0]["amount_a"] == 100
    assert generic["matched"][0]["amount_b"] == 100


def test_builder_matches_many_to_one_by_group_sum():
    module = ReconciliationBuilderModule()

    result = module.run(
        {
            "source_a": _csv("ID;Amount\nA;25\nA;75"),
            "source_b": _csv("ID;Amount\nA;100"),
        },
        {
            "source_a_filename": "a.csv",
            "source_b_filename": "b.csv",
            "key_pairs": json.dumps([
                {"left": "ID", "right": "ID", "mode": "text"},
            ]),
            "matching_mode": "many_to_one",
            "amount_a_col": "Amount",
            "amount_b_col": "Amount",
            "amount_tolerance": "0",
        },
    )

    generic = result.custom_metrics["generic"]
    assert result.summary.matched_count == 1
    assert result.summary.discrepancy_count == 0
    assert generic["matched"][0]["match_type"] == "N↔1"
    assert generic["matched"][0]["grouped_rows_a"] == [2, 3]
    assert generic["matched"][0]["grouped_rows_b"] == [2]


def test_builder_group_mode_reports_group_amount_mismatch():
    module = ReconciliationBuilderModule()

    result = module.run(
        {
            "source_a": _csv("ID;Amount\nA;100"),
            "source_b": _csv("ID;Amount\nA;40\nA;70"),
        },
        {
            "source_a_filename": "a.csv",
            "source_b_filename": "b.csv",
            "key_pairs": json.dumps([
                {"left": "ID", "right": "ID", "mode": "text"},
            ]),
            "matching_mode": "one_to_many",
            "amount_a_col": "Amount",
            "amount_b_col": "Amount",
            "amount_tolerance": "0",
        },
    )

    generic = result.custom_metrics["generic"]
    assert result.summary.matched_count == 0
    assert result.summary.discrepancy_count == 1
    assert generic["mismatches"][0]["match_type"] == "1↔N"
    assert generic["mismatches"][0]["amount_delta"] == 10
    assert "Сумма группы вне допуска" in generic["mismatches"][0]["reason"]



def test_builder_computed_fields_can_chain_concat_and_replace():
    module = ReconciliationBuilderModule()

    result = module.run(
        {
            "source_a": _csv("Account;Document;Amount\n2020;001;500"),
            "source_b": _csv("Reference;Amount\n2020001;500"),
        },
        {
            "source_a_filename": "a.csv",
            "source_b_filename": "b.csv",
            "computed_fields": json.dumps([
                {
                    "side": "a",
                    "name": "Combined",
                    "operation": "concat",
                    "sources": ["Account", "Document"],
                    "separator": "-",
                },
                {
                    "side": "a",
                    "name": "MatchKey",
                    "operation": "replace",
                    "sources": ["Combined"],
                    "find": "-",
                    "replace_with": "",
                },
            ]),
            "key_pairs": json.dumps([
                {"left": "MatchKey", "right": "Reference", "mode": "numeric"},
            ]),
            "amount_a_col": "Amount",
            "amount_b_col": "Amount",
        },
    )

    generic = result.custom_metrics["generic"]
    assert result.summary.matched_count == 1
    assert result.summary.discrepancy_count == 0
    assert [field["name"] for field in generic["computed_fields"]] == [
        "Combined",
        "MatchKey",
    ]


def test_builder_computed_substring_can_be_used_as_key():
    module = ReconciliationBuilderModule()

    result = module.run(
        {
            "source_a": _csv("LongRef;Amount\nXX-ABC-999;100"),
            "source_b": _csv("Ref;Amount\nABC;100"),
        },
        {
            "source_a_filename": "a.csv",
            "source_b_filename": "b.csv",
            "computed_fields": json.dumps([
                {
                    "side": "a",
                    "name": "ShortRef",
                    "operation": "substring",
                    "sources": ["LongRef"],
                    "start": 3,
                    "length": 3,
                },
            ]),
            "key_pairs": json.dumps([
                {"left": "ShortRef", "right": "Ref", "mode": "exact"},
            ]),
            "amount_a_col": "Amount",
            "amount_b_col": "Amount",
        },
    )

    assert result.summary.matched_count == 1


def test_builder_computed_normalized_date_can_be_used_as_key():
    module = ReconciliationBuilderModule()

    result = module.run(
        {
            "source_a": _csv("Date;Amount\n01.09.2026;100"),
            "source_b": _csv("DateKey;Amount\n20260901;100"),
        },
        {
            "source_a_filename": "a.csv",
            "source_b_filename": "b.csv",
            "computed_fields": json.dumps([
                {
                    "side": "a",
                    "name": "DateKey",
                    "operation": "normalize_date",
                    "sources": ["Date"],
                    "date_format": "compact",
                },
            ]),
            "key_pairs": json.dumps([
                {"left": "DateKey", "right": "DateKey", "mode": "exact"},
            ]),
            "amount_a_col": "Amount",
            "amount_b_col": "Amount",
            "dayfirst": "true",
        },
    )

    assert result.summary.matched_count == 1


def test_builder_computed_field_rejects_forward_reference():
    module = ReconciliationBuilderModule()

    try:
        module.run(
            {
                "source_a": _csv("A;Amount\n1;100"),
                "source_b": _csv("Key;Amount\n1;100"),
            },
            {
                "source_a_filename": "a.csv",
                "source_b_filename": "b.csv",
                "computed_fields": json.dumps([
                    {
                        "side": "a",
                        "name": "First",
                        "operation": "normalize_text",
                        "sources": ["Later"],
                        "text_mode": "trim",
                    },
                    {
                        "side": "a",
                        "name": "Later",
                        "operation": "normalize_text",
                        "sources": ["A"],
                        "text_mode": "trim",
                    },
                ]),
                "key_pairs": json.dumps([
                    {"left": "First", "right": "Key", "mode": "exact"},
                ]),
            },
        )
        assert False, "forward reference must fail"
    except ValueError as exc:
        assert "не найдены колонки Later" in str(exc)
