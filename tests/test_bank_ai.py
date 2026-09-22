import json

from backend.app.services import bank_ai


def _payload():
    only_our = [
        {
            "checked": True,
            "date_str": "31.08.2026",
            "RRN": f"SECRET-RRN-{index}",
            "amount": 100_000 + index,
            "status": "SUCCESS",
        }
        for index in range(6)
    ]
    only_bank = [
        {
            "checked": True,
            "date_str": "01.09.2026",
            "RRN": "BANK-SECRET-1",
            "amount": 100_000,
            "status": "SETTLED",
        }
    ]

    return {
        "bank_name": "Test Bank",
        "currency": "UZS",
        "adjusted": {
            "total_our": 1_000_000,
            "total_bank": 900_000,
            "difference": -100_000,
            "active_only_our_count": 6,
            "active_only_bank_count": 1,
        },
        "result": {
            "summary": [
                {
                    "date": "31.08.2026",
                    "Кол_во_у_нас": 10,
                    "Кол_во_в_банке": 4,
                    "Δ кол-во": -6,
                    "Сумма_у_нас": 1_000_000,
                    "Сумма_в_банке": 400_000,
                    "Δ суммы": -600_000,
                },
                {
                    "date": "ИТОГО",
                    "Кол_во_у_нас": 10,
                    "Кол_во_в_банке": 4,
                    "Δ кол-во": -6,
                    "Сумма_у_нас": 1_000_000,
                    "Сумма_в_банке": 400_000,
                    "Δ суммы": -600_000,
                },
            ],
            "only_our": only_our,
            "only_bank": only_bank,
            "amt_mismatches": [],
            "dups_our": [],
            "dups_bank": [],
            "dup_our_c": 0,
            "dup_bank_c": 0,
            "matched_count": 20,
            "mismatch_count": 0,
            "comm_only_diff_count": 0,
            "effective_commission_rate": 1.2,
            "deduct_commission": False,
            "data_quality": {"our": {}, "bank": {}},
            "detected_months": ["2026-08", "2026-09"],
        },
    }


def test_month_end_hypothesis_detects_possible_next_period_shift(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    payload = _payload()
    result = bank_ai.analyze_bank_reconciliation(payload)

    assert result["provider"] == "local"
    assert "сверк" in result["executive_summary"].lower()

    month_end = next(
        item for item in result["insights"]
        if item["kind"] == "month_end_cutoff"
    )
    assert month_end["confidence"] == "high"
    assert "границу месяца" in month_end["title"].lower()
    assert "следующего периода" in month_end["explanation"].lower()
    assert any("6 операций у нас" in evidence for evidence in month_end["evidence"])


def test_ai_context_does_not_include_rrn_or_raw_rows():
    payload = _payload()

    context = bank_ai.build_bank_ai_context(payload)
    serialized = json.dumps(context, ensure_ascii=False)

    assert "SECRET-RRN" not in serialized
    assert "BANK-SECRET" not in serialized
    assert "raw" not in context
    assert context["unmatched"]["only_our"]["count"] == 6
    assert context["unmatched"]["only_bank"]["count"] == 1


def test_commission_and_data_quality_generate_separate_hypotheses(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    payload = _payload()
    payload["result"]["amt_mismatches"] = [
        {
            "RRN": "DO-NOT-LEAK",
            "date_our": "20.08.2026",
            "date_bank": "20.08.2026",
            "net_amount_our": 100_000,
            "net_amount_bank": 98_800,
            "Δ сумма": -1_200,
        },
        {
            "RRN": "DO-NOT-LEAK-2",
            "date_our": "20.08.2026",
            "date_bank": "20.08.2026",
            "net_amount_our": 200_000,
            "net_amount_bank": 197_600,
            "Δ сумма": -2_400,
        },
    ]
    payload["result"]["comm_only_diff_count"] = 2
    payload["result"]["data_quality"] = {
        "our": {"empty_rrn": 1},
        "bank": {"invalid_amount": 2},
    }

    result = bank_ai.analyze_bank_reconciliation(payload)
    kinds = {item["kind"] for item in result["insights"]}

    assert "commission" in kinds
    assert "data_quality" in kinds
    assert "DO-NOT-LEAK" not in json.dumps(result["context"], ensure_ascii=False)


def test_ai_summary_distinguishes_found_rrn_from_unbound_amount_mismatches(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    payload = _payload()
    payload["result"]["matched_count"] = 0
    payload["result"]["rrn_found_count"] = 10
    payload["result"]["amount_mismatch_count_before_unbind"] = 10
    payload["result"]["unbound_mismatch_count"] = 10

    result = bank_ai.analyze_bank_reconciliation(payload)

    assert result["context"]["rrn_presence"]["found_on_both_sides"] == 10
    assert result["context"]["rrn_presence"]["unbound_amount_mismatches"] == 10
    assert "RRN найдено с обеих сторон: 10" in result["executive_summary"]
    assert "10 пар развязано" in result["executive_summary"]

