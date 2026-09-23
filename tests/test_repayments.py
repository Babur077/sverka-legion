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


def test_payment_purposes_are_collected_from_both_sources_separately():
    one_c = _csv(
        "Вх.номер,Дата,Сумма,Назначение платежа\n"
        "100,01.09.2026,600,Оплата по договору №1\n"
        "100,01.09.2026,400,Комиссия по договору №1\n"
    )
    meta = _csv(
        "withdraw_unique_id,bank_date,bank_amount,our_system_date,"
        "our_system_amount_success,contract_number,bank_purpose_of_payment\n"
        "100,01.09.2026,600,01.09.2026,600,C-100,Meta назначение A\n"
        "100,01.09.2026,400,01.09.2026,400,C-100,Meta назначение B\n"
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
    assert row["Назначения 1С"] == [
        "Оплата по договору №1",
        "Комиссия по договору №1",
    ]
    assert row["Назначения Meta"] == [
        "Meta назначение A",
        "Meta назначение B",
    ]
    assert row["Количество назначений 1С"] == 2
    assert row["Количество назначений Meta"] == 2
    assert row["Назначение платежа"] == (
        "Оплата по договору №1\n"
        "Комиссия по договору №1\n"
        "Meta назначение A\n"
        "Meta назначение B"
    )
    assert result.custom_metrics["repayments"]["payment_purpose_source"] == (
        "1C:Назначение платежа | Meta:bank_purpose_of_payment"
    )
    assert result.custom_metrics["repayments"]["payment_purpose_sources"] == {
        "one_c": "Назначение платежа",
        "meta": "bank_purpose_of_payment",
    }


def test_payment_purpose_supports_1c_alias_and_meta_bank_field():
    one_c = _csv(
        "Вх.номер,Дата,Сумма,Детали платежа\n"
        "200,02.09.2026,200,Погашение задолженности\n"
    )
    meta = _csv(
        "withdraw_unique_id,bank_date,bank_amount,our_system_date,"
        "our_system_amount_success,contract_number,bank_purpose_of_payment\n"
        "200,02.09.2026,200,02.09.2026,200,C-200,Meta погашение\n"
    )
    result = RepaymentsModule().run(
        {"one_c_file": one_c, "meta_file": meta},
        {
            "one_c_file_filename": "1c.csv",
            "meta_file_filename": "meta.csv",
        },
    )

    row = _rows(result)[0]
    assert row["Назначения 1С"] == ["Погашение задолженности"]
    assert row["Назначения Meta"] == ["Meta погашение"]
    assert result.custom_metrics["repayments"]["payment_purpose_source"] == (
        "1C:Детали платежа | Meta:bank_purpose_of_payment"
    )


def test_meta_purposes_are_visible_when_payment_is_missing_in_1c():
    one_c = _csv(
        "Вх.номер,Дата,Сумма\n"
        "100,01.09.2026,100\n"
    )
    meta = _csv(
        "withdraw_unique_id,bank_date,bank_amount,our_system_date,"
        "our_system_amount_success,contract_number,bank_purpose_of_payment\n"
        "700,07.09.2026,400,07.09.2026,400,C-700,Первое назначение Meta\n"
        "700,07.09.2026,300,07.09.2026,300,C-700,Второе назначение Meta\n"
    )

    result = RepaymentsModule().run(
        {"one_c_file": one_c, "meta_file": meta},
        {
            "one_c_file_filename": "1c.csv",
            "meta_file_filename": "meta.csv",
        },
    )
    row = _by_payment(result)["700"]

    assert row["Комментарий"] == "Нет в 1С"
    assert row["Назначения 1С"] == []
    assert row["Назначения Meta"] == [
        "Первое назначение Meta",
        "Второе назначение Meta",
    ]
    assert row["Количество назначений Meta"] == 2


def test_smart_match_suggests_conservative_pair_for_missing_ids():
    one_c = _csv(
        "Вх.номер,Дата,Сумма,Назначение платежа\n"
        "A100,01.09.2026,1000,Погашение договора 77\n"
    )
    meta = _csv(
        "withdraw_unique_id,bank_date,bank_amount,our_system_date,"
        "our_system_amount_success,contract_number,bank_purpose_of_payment\n"
        "B100,02.09.2026,1000,02.09.2026,1000,C-77,Погашение договора 77\n"
    )

    result = RepaymentsModule().run(
        {"one_c_file": one_c, "meta_file": meta},
        {
            "one_c_file_filename": "1c.csv",
            "meta_file_filename": "meta.csv",
        },
    )
    rows = _by_payment(result)

    assert rows["A100"]["Комментарий"] == "Нет в системе"
    assert rows["B100"]["Комментарий"] == "Нет в 1С"
    assert rows["A100"]["Smart Match кандидат"] == "B100"
    assert rows["B100"]["Smart Match кандидат"] == "A100"
    assert rows["A100"]["Smart Match уверенность"] >= 70
    assert "сумма совпадает" in rows["A100"]["Smart Match причина"]
    assert result.custom_metrics["repayments"]["smart_match_pair_count"] == 1


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
