from __future__ import annotations

import io

import pandas as pd
import pytest

from modules.ravan_1c.engine import (
    Ravan1CModule,
    clean_company_name,
    company_name_similarity,
)


def _excel_bytes(frame: pd.DataFrame, *, header: bool = True) -> bytes:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        frame.to_excel(writer, index=False, header=header)
    return buffer.getvalue()


def test_company_name_cleanup_matches_original_workflow():
    assert clean_company_name('«ABC» MCHJ') == "abc"
    assert clean_company_name("OOO Test-Company") == "test company"
    assert clean_company_name("YATT   Alfa") == "alfa"
    assert clean_company_name('"AXE TECHNOLOGY" xususiy korxona') == "axe technology"


def test_company_name_similarity_handles_single_letter_typos():
    assert company_name_similarity("ABDIMUMIN BEKPO'LAT", '"Abdimunin Bekpo`lat" XK') >= 0.90
    assert company_name_similarity(
        "ABDURAKHMONOV AKBAR SHOH",
        "ABDURAXMONOV AKBAR SHOH",
    ) >= 0.90


def test_ravan_1c_module_preserves_formula_and_status_logic():
    ravan = pd.DataFrame(
        [
            {"Partner": "ABC MCHJ", "NDS": 12, "Kolvo": 5, "Summ": 1120},
            {"Partner": "XYZ LLC", "NDS": 0, "Kolvo": 3, "Summ": 300},
            {"Partner": "Solo Ravan", "NDS": 0, "Kolvo": 1, "Summ": 50},
        ]
    )
    one_c = pd.DataFrame(
        [
            ["ABC", 5, 1000],
            ["XYZ", 2, 300],
            ["Only 1C", 1, 70],
        ]
    )

    module = Ravan1CModule()
    result = module.run(
        {
            "ravan_file": _excel_bytes(ravan),
            "c_file": _excel_bytes(one_c, header=False),
        },
        {
            "ravan_file_filename": "Ravan.xlsx",
            "c_file_filename": "1C 2910.xlsx",
            "sum_tolerance": "1",
        },
    )

    rows = result.custom_metrics["ravan_1c"]["rows"]
    by_ravan = {
        row.get("Partner_Ravan"): row
        for row in rows
        if row.get("Partner_Ravan")
    }

    assert by_ravan["ABC MCHJ"]["Summ_Corrected"] == 1000.0
    assert by_ravan["ABC MCHJ"]["Status"] == "OK"
    assert by_ravan["XYZ LLC"]["Status"] == "Ошибка Kolvo"
    assert by_ravan["Solo Ravan"]["Status"] == "Нет в !C"
    assert any(
        row.get("Partner_C") == "Only 1C" and row["Status"] == "Нет в Ravan"
        for row in rows
    )

    assert result.summary.total_records_a == 3
    assert result.summary.total_records_b == 3
    assert result.summary.matched_count == 1
    assert result.summary.discrepancy_count == 3
    assert result.summary.match_percentage == 25.0
    assert result.status == "WARNING"
    assert result.custom_metrics["ravan_1c"]["producer"] == "Sayfulloh Abdusalomov"


@pytest.mark.parametrize("separator", [",", ";", "\t"])
@pytest.mark.parametrize("encoding", ["utf-8-sig", "cp1251"])
def test_csv_sources_support_delimiters_quotes_and_encodings(separator, encoding):
    partner = 'ООО Альфа, "Бета"; Гамма'
    ravan = pd.DataFrame([{"Partner": partner, "NDS": 12, "Kolvo": 5, "Summ": 1120}])
    one_c = pd.DataFrame([[partner, 5, 1000]])
    result = Ravan1CModule().run(
        {
            "ravan_file": ravan.to_csv(index=False, sep=separator).encode(encoding),
            "c_file": one_c.to_csv(index=False, header=False, sep=separator).encode(encoding),
        },
        {"ravan_file_filename": "Ravan.csv", "c_file_filename": "1C.csv"},
    )
    assert result.summary.matched_count == 1
    assert result.summary.total_sum_a == 1000
    assert result.custom_metrics["ravan_1c"]["rows"][0]["Partner_C"] == partner


def test_duplicate_company_rows_do_not_inflate_source_totals():
    ravan = pd.DataFrame([
        {"Partner": "Alpha MCHJ", "NDS": 12, "Kolvo": 1, "Summ": 112},
        {"Partner": "Alpha LLC", "NDS": 12, "Kolvo": 2, "Summ": 224},
    ])
    one_c = pd.DataFrame([["Alpha", 1, 100], ["Alpha", 2, 210]])
    result = Ravan1CModule().run(
        {"ravan_file": _excel_bytes(ravan), "c_file": _excel_bytes(one_c, header=False)},
        {},
    )
    # Keep the original comparison rows, but count each source amount once.
    assert len(result.custom_metrics["ravan_1c"]["rows"]) == 4
    assert result.summary.total_sum_a == 300
    assert result.summary.total_sum_b == 310
    assert result.summary.diff_sum == 10


@pytest.mark.parametrize(
    "quantity,amount,status",
    [(5, 1000, "OK"), (5, 1001, "OK"), (5, 1001.01, "Ошибка Summ"),
     (4, 1000, "Ошибка Kolvo"), (4, 1002, "Ошибка Kolvo + Summ")],
)
def test_statuses_and_inclusive_tolerance_boundary(quantity, amount, status):
    ravan = pd.DataFrame([{"Partner": "Alpha", "NDS": 12, "Kolvo": 5, "Summ": 1120}])
    one_c = pd.DataFrame([["Alpha", quantity, amount]])
    result = Ravan1CModule().run(
        {"ravan_file": _excel_bytes(ravan), "c_file": _excel_bytes(one_c, header=False)},
        {},
    )
    assert result.custom_metrics["ravan_1c"]["rows"][0]["Status"] == status


def test_ravan_1c_sum_tolerance_matches_original_default_rule():
    ravan = pd.DataFrame(
        [{"Partner": "Tolerance MCHJ", "NDS": 0, "Kolvo": 1, "Summ": 100}]
    )
    one_c = pd.DataFrame([["Tolerance", 1, 100.75]])

    result = Ravan1CModule().run(
        {
            "ravan_file": _excel_bytes(ravan),
            "c_file": _excel_bytes(one_c, header=False),
        },
        {
            "ravan_file_filename": "Ravan.xlsx",
            "c_file_filename": "1C.xlsx",
            "sum_tolerance": "1",
        },
    )

    row = result.custom_metrics["ravan_1c"]["rows"][0]
    assert row["Status"] == "OK"
    assert result.summary.matched_count == 1

def test_fuzzy_counterparty_match_is_paired_and_put_first_for_review():
    ravan = pd.DataFrame([
        {"Partner": "EXACT COMPANY MCHJ", "NDS": 0, "Kolvo": 1, "Summ": 100},
        {"Partner": "ABDIMUMIN BEKPO'LAT", "NDS": 0, "Kolvo": 2, "Summ": 200},
    ])
    one_c = pd.DataFrame([
        ["EXACT COMPANY", 1, 100],
        ['"Abdimunin Bekpo`lat" XK', 2, 200],
    ])

    result = Ravan1CModule().run(
        {"ravan_file": _excel_bytes(ravan), "c_file": _excel_bytes(one_c, header=False)},
        {"ravan_file_filename": "Ravan.xlsx", "c_file_filename": "1C.xlsx"},
    )

    rows = result.custom_metrics["ravan_1c"]["rows"]
    assert len(rows) == 2
    assert rows[0]["Match_Type"] == "fuzzy"
    assert rows[0]["Needs_Review"] is True
    assert rows[0]["Match_Confirmed"] is False
    assert rows[0]["Name_Similarity"] >= 90
    assert rows[0]["Partner_Ravan"] == "ABDIMUMIN BEKPO'LAT"
    assert rows[0]["Partner_C"] == '"Abdimunin Bekpo`lat" XK'
    assert result.custom_metrics["ravan_1c"]["fuzzy_review_count"] == 1
    assert result.custom_metrics["ravan_1c"]["source_files"] == ["Ravan.xlsx", "1C.xlsx"]


def test_dissimilar_unmatched_counterparties_are_not_force_paired():
    ravan = pd.DataFrame([
        {"Partner": "ALPHA SERVICE", "NDS": 0, "Kolvo": 1, "Summ": 100},
    ])
    one_c = pd.DataFrame([["COMPLETELY DIFFERENT", 1, 100]])

    result = Ravan1CModule().run(
        {"ravan_file": _excel_bytes(ravan), "c_file": _excel_bytes(one_c, header=False)},
        {},
    )

    rows = result.custom_metrics["ravan_1c"]["rows"]
    assert len(rows) == 2
    assert {row["Status"] for row in rows} == {"Нет в !C", "Нет в Ravan"}
    assert not any(row.get("Needs_Review") for row in rows)

