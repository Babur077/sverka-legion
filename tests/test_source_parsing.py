from __future__ import annotations

import io

from openpyxl import Workbook

from core.parsers import load_file_polars


def _xlsx_with_custom_sheet_and_header() -> bytes:
    workbook = Workbook()
    cover = workbook.active
    cover.title = "Cover"
    cover.append(["Отчёт за период"])
    cover.append(["Это не таблица"])

    data = workbook.create_sheet("Transactions")
    data.append(["ООО Example"])
    data.append(["Сверка за август"])
    data.append(["Дата", "RRN", "Сумма"])
    data.append(["31.08.2026", "00123", 100000])
    data.append(["01.09.2026", "00124", 200000])

    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def test_excel_named_sheet_and_header_row_are_applied():
    frame = load_file_polars(
        _xlsx_with_custom_sheet_and_header(),
        "sample.xlsx",
        sheet_name="Transactions",
        header_row=3,
    )

    assert frame.columns == ["Дата", "RRN", "Сумма"]
    assert frame.height == 2
    assert str(frame["RRN"][0]) == "00123"
    assert frame["Сумма"][1] == 200000


def test_csv_header_row_is_applied_before_delimiter_detection():
    content = (
        "Отчёт эквайринга\n"
        "Период;Август 2026\n"
        "Дата;RRN;Сумма\n"
        "31.08.2026;0001;100\n"
        "01.09.2026;0002;200\n"
    ).encode("utf-8")

    frame = load_file_polars(
        content,
        "sample.csv",
        header_row=3,
    )

    assert frame.columns == ["Дата", "RRN", "Сумма"]
    assert frame.height == 2
    assert frame["Дата"][0] == "31.08.2026"
