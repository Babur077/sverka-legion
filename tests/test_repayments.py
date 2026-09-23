import io

import pandas as pd
import pytest

from modules.repayments.engine import RepaymentsModule, clean_payment_number


def _csv(text: str) -> bytes:
    return text.encode("utf-8-sig")


def _rows(result):
    return result.custom_metrics["repayments"]["rows"]


def _by_payment(result):
    return {row["Номер платежа"]: row for row in _rows(result)}


def test_clean_payment_number_does_not_round_long_identifiers():
    assert clean_payment_number("0012345678901234567890") == "12345678901234567890"
    assert clean_payment_number("12345678901234567890.0") == "12345678901234567890"
    assert clean_payment_number(12345678901234567890) == "12345678901234567890"
    assert clean_payment_number("ABC-001") == "ABC-001"


def test_repayments_status_priority_and_business_rules():
    one_c = _csv(
        "Вх.номер,Дата,Сумма\n"
        "100,01.09.2026,100\n"
        "200,02.09.2026,200\n"
        "300,03.09.2026,300\n"
        "400,04.09.2026,400\n"
        "500,05.09.2026,500\n"
        "600,06.09.2026,600\n"
        "800,02.09.2026,1000\n"
    )
    meta = _csv(
        "withdraw_unique_id,bank_date,bank_amount,our_system_date,our_system_amount_success,contract_number\n"
        "100,01.09.2026,100,01.09.2026,100,C-100\n"
        "200,02.09.2026,202,02.09.2026,202,C-200\n"
        "300,04.09.2026,300,03.09.2026,300,C-300\n"
        "400,05.09.2026,405,04.09.2026,405,C-400\n"
        "500,05.09.2026,500,05.09.2026,0,C-500\n"
        "700,07.09.2026,700,07.09.2026,700,C-700\n"
        "800,01.09.2026,600,01.09.2026,600,C-A\n"
        "800,02.09.2026,400,03.09.2026,400,C-B\n"
    )

    result = RepaymentsModule().run(
        {"one_c_file": one_c, "meta_file": meta},
        {
            "one_c_file_filename": "1c.csv",
            "meta_file_filename": "meta.csv",
            "one_c_header_row": "1",
            "meta_header_row": "1",
        },
    )
    rows = _by_payment(result)

    assert rows["100"]["Комментарий"] == "Правильно"
    assert rows["200"]["Комментарий"] == "Не верная сумма"
    assert rows["300"]["Комментарий"] == "Не верная дата"
    assert rows["400"]["Комментарий"] == "Не верно"
    assert rows["500"]["Комментарий"] == "Не опознано"
    assert rows["600"]["Комментарий"] == "Нет в системе"
    assert rows["700"]["Комментарий"] == "Нет в 1С"

    # When Meta has several bank dates, an exact 1C date match wins over max().
    assert rows["800"]["Комментарий"] == "Правильно"
    assert rows["800"]["Дата Meta"] == "02.09.2026"
    assert rows["800"]["Сумма Meta"] == 1000
    assert rows["800"]["Сумма опознание"] == 1000
    assert rows["800"]["Дата в системе"] == "03.09.2026"
    assert rows["800"]["Номер договора опознание"] == "C-A, C-B"

    assert result.summary.matched_count == 2
    assert result.summary.discrepancy_count == 6
    assert result.status == "WARNING"


def test_payment_purpose_is_collected_from_1c_without_affecting_reconciliation():
    one_c = _csv(
        "Вх.номер,Дата,Сумма,Назначение платежа\n"
        "100,01.09.2026,600,Оплата по договору №1\n"
        "100,01.09.2026,400,Комиссия по договору №1\n"
    )
    meta = _csv(
        "withdraw_unique_id,bank_date,bank_amount,our_system_date,our_system_amount_success,contract_number\n"
        "100,01.09.2026,1000,01.09.2026,1000,C-100\n"
    )

    result = RepaymentsModule().run(
        {"one_c_file": one_c, "meta_file": meta},
        {
            "one_c_file_filename": "1c.csv",
            "meta_file_filename": "meta.csv",
        },
    )

    row = _rows(result)[0]
    assert row["Комментарий"] == "Правильно"
    assert row["Назначение платежа"] == (
        "Оплата по договору №1\nКомиссия по договору №1"
    )
    assert result.custom_metrics["repayments"]["payment_purpose_source"] == (
        "1C:Назначение платежа"
    )


def test_payment_purpose_supports_1c_alias_and_meta_fallback():
    one_c_alias = _csv(
        "Вх.номер,Дата,Сумма,Детали платежа\n"
        "200,02.09.2026,200,Погашение задолженности\n"
    )
    meta_plain = _csv(
        "withdraw_unique_id,bank_date,bank_amount,our_system_date,our_system_amount_success,contract_number\n"
        "200,02.09.2026,200,02.09.2026,200,C-200\n"
    )
    alias_result = RepaymentsModule().run(
        {"one_c_file": one_c_alias, "meta_file": meta_plain},
        {
            "one_c_file_filename": "1c.csv",
            "meta_file_filename": "meta.csv",
        },
    )
    assert _rows(alias_result)[0]["Назначение платежа"] == "Погашение задолженности"

    one_c_plain = _csv(
        "Вх.номер,Дата,Сумма\n"
        "300,03.09.2026,300\n"
    )
    meta_with_purpose = _csv(
        "withdraw_unique_id,bank_date,bank_amount,our_system_date,our_system_amount_success,contract_number,payment_purpose\n"
        "300,03.09.2026,300,03.09.2026,300,C-300,Meta purpose text\n"
    )
    fallback_result = RepaymentsModule().run(
        {"one_c_file": one_c_plain, "meta_file": meta_with_purpose},
        {
            "one_c_file_filename": "1c.csv",
            "meta_file_filename": "meta.csv",
        },
    )
    assert _rows(fallback_result)[0]["Назначение платежа"] == "Meta purpose text"
    assert fallback_result.custom_metrics["repayments"]["payment_purpose_source"] == (
        "Meta:payment_purpose"
    )


def test_amount_tolerance_is_fixed_at_one():
    one_c = _csv(
        "Вх.номер,Дата,Сумма\n"
        "1,01.09.2026,100\n"
        "2,01.09.2026,100\n"
    )
    meta = _csv(
        "withdraw_unique_id,bank_date,bank_amount,our_system_date,our_system_amount_success,contract_number\n"
        "1,01.09.2026,101,01.09.2026,101,C1\n"
        "2,01.09.2026,101.01,01.09.2026,101.01,C2\n"
    )

    result = RepaymentsModule().run(
        {"one_c_file": one_c, "meta_file": meta},
        {
            "one_c_file_filename": "1c.csv",
            "meta_file_filename": "meta.csv",
        },
    )
    rows = _by_payment(result)

    assert rows["1"]["Комментарий"] == "Правильно"
    assert rows["2"]["Комментарий"] == "Не верная сумма"


def test_second_header_row_is_supported():
    one_c = _csv(
        "Служебная строка,,\n"
        "Вх.номер,Дата,Сумма\n"
        "900,01.09.2026,100\n"
    )
    meta = _csv(
        "Служебная строка,,,,,\n"
        "withdraw_unique_id,bank_date,bank_amount,our_system_date,our_system_amount_success,contract_number\n"
        "900,01.09.2026,100,01.09.2026,100,C900\n"
    )

    result = RepaymentsModule().run(
        {"one_c_file": one_c, "meta_file": meta},
        {
            "one_c_file_filename": "1c.csv",
            "meta_file_filename": "meta.csv",
            "one_c_header_row": "2",
            "meta_header_row": "2",
        },
    )

    assert result.summary.matched_count == 1
    assert _rows(result)[0]["Комментарий"] == "Правильно"


def test_missing_required_columns_are_reported():
    with pytest.raises(ValueError, match="1C.*Вх.номер"):
        RepaymentsModule().run(
            {
                "one_c_file": _csv("Дата,Сумма\n01.09.2026,100\n"),
                "meta_file": _csv(
                    "withdraw_unique_id,bank_date,bank_amount,our_system_date,our_system_amount_success,contract_number\n"
                    "1,01.09.2026,100,01.09.2026,100,C1\n"
                ),
            },
            {
                "one_c_file_filename": "1c.csv",
                "meta_file_filename": "meta.csv",
            },
        )
