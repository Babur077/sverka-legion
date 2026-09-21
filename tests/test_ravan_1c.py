from __future__ import annotations

import io

import pandas as pd

from modules.ravan_1c.engine import Ravan1CModule, clean_company_name


def _excel_bytes(frame: pd.DataFrame, *, header: bool = True) -> bytes:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        frame.to_excel(writer, index=False, header=header)
    return buffer.getvalue()


def test_company_name_cleanup_matches_original_workflow():
    assert clean_company_name('«ABC» MCHJ') == "abc"
    assert clean_company_name("OOO Test-Company") == "test company"
    assert clean_company_name("YATT   Alfa") == "alfa"


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
