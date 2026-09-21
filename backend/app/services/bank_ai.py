from __future__ import annotations

import calendar
import json
import os
from collections import Counter, defaultdict
from datetime import datetime
from typing import Any


AI_CONFIDENCE_LABELS = {
    "low": "Низкая",
    "medium": "Средняя",
    "high": "Высокая",
}


def _safe_float(value: Any) -> float:
    try:
        number = float(value)
        return number if number == number else 0.0
    except (TypeError, ValueError):
        return 0.0


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _active_rows(rows: Any) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        return []
    return [
        row
        for row in rows
        if isinstance(row, dict) and row.get("checked", True) is not False
    ]


def _parse_date(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None

    normalized = text[:19].replace("T", " ")
    formats = (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%d.%m.%Y %H:%M:%S",
        "%d.%m.%Y",
        "%d/%m/%Y",
        "%m/%d/%Y",
    )
    for fmt in formats:
        try:
            return datetime.strptime(normalized, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _aggregate_unmatched(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_date: dict[str, dict[str, float]] = defaultdict(
        lambda: {"count": 0.0, "amount": 0.0}
    )
    statuses: Counter[str] = Counter()

    for row in rows:
        date_text = str(row.get("date_str") or "").strip() or "Без даты"
        by_date[date_text]["count"] += 1
        by_date[date_text]["amount"] += _safe_float(row.get("amount"))

        status = str(row.get("status") or "").strip()
        if status:
            statuses[status] += 1

    top_dates = sorted(
        (
            {
                "date": date,
                "count": int(values["count"]),
                "amount": round(values["amount"], 2),
            }
            for date, values in by_date.items()
        ),
        key=lambda item: (item["count"], abs(item["amount"])),
        reverse=True,
    )[:8]

    return {
        "count": len(rows),
        "amount": round(sum(_safe_float(row.get("amount")) for row in rows), 2),
        "top_dates": top_dates,
        "top_statuses": [
            {"status": status, "count": count}
            for status, count in statuses.most_common(6)
        ],
    }


def _month_end_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for row in rows:
        parsed = _parse_date(row.get("date_str"))
        if not parsed:
            continue
        last_day = calendar.monthrange(parsed.year, parsed.month)[1]
        if parsed.day >= last_day - 2:
            result.append(row)
    return result


def _first_days_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for row in rows:
        parsed = _parse_date(row.get("date_str"))
        if parsed and parsed.day <= 3:
            result.append(row)
    return result


def _date_label(rows: list[dict[str, Any]]) -> str:
    values = []
    for row in rows:
        date_text = str(row.get("date_str") or "").strip()
        if date_text and date_text not in values:
            values.append(date_text)
    return ", ".join(values[:4]) or "конец периода"


def _hypothesis(
    *,
    kind: str,
    title: str,
    explanation: str,
    confidence: str,
    evidence: list[str],
) -> dict[str, Any]:
    return {
        "kind": kind,
        "title": title,
        "explanation": explanation,
        "confidence": confidence,
        "confidence_label": AI_CONFIDENCE_LABELS.get(confidence, confidence),
        "evidence": evidence,
    }


def build_bank_ai_context(payload: dict[str, Any]) -> dict[str, Any]:
    result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
    adjusted = payload.get("adjusted") if isinstance(payload.get("adjusted"), dict) else {}
    rrn = (
        result.get("custom_metrics", {}).get("rrn", {})
        if isinstance(result.get("custom_metrics"), dict)
        else {}
    )
    if not isinstance(rrn, dict):
        rrn = {}

    summary = result.get("summary") if isinstance(result.get("summary"), dict) else {}
    only_our = _active_rows(rrn.get("only_our") or result.get("only_our"))
    only_bank = _active_rows(rrn.get("only_bank") or result.get("only_bank"))
    mismatches = rrn.get("amt_mismatches") or result.get("amt_mismatches") or []
    mismatches = [row for row in mismatches if isinstance(row, dict)]

    unmatched_our = _aggregate_unmatched(only_our)
    unmatched_bank = _aggregate_unmatched(only_bank)

    mismatch_abs = sum(abs(_safe_float(row.get("Δ сумма"))) for row in mismatches)
    duplicate_our = _safe_int(rrn.get("dup_our_c") or result.get("dup_our_c"))
    duplicate_bank = _safe_int(rrn.get("dup_bank_c") or result.get("dup_bank_c"))
    commission_rate = _safe_float(
        rrn.get("effective_commission_rate")
        or result.get("effective_commission_rate")
    )
    commission_only = _safe_int(
        rrn.get("comm_only_diff_count")
        or result.get("comm_only_diff_count")
    )
    data_quality = rrn.get("data_quality") or result.get("data_quality") or {}
    if not isinstance(data_quality, dict):
        data_quality = {}

    total_our = _safe_float(adjusted.get("total_our"))
    total_bank = _safe_float(adjusted.get("total_bank"))
    total_diff = _safe_float(adjusted.get("difference"))
    if "total_our" not in adjusted:
        total_our = _safe_float(summary.get("total_sum_a"))
    if "total_bank" not in adjusted:
        total_bank = _safe_float(summary.get("total_sum_b"))
    if "difference" not in adjusted:
        total_diff = _safe_float(summary.get("diff_sum"))

    matched_count = _safe_int(
        summary.get("matched_count")
        if summary
        else rrn.get("matched_count") or result.get("matched_count")
    )
    mismatch_count = len(mismatches)
    discrepancy_count = _safe_int(summary.get("discrepancy_count")) if summary else (
        len(only_our) + len(only_bank) + mismatch_count
    )
    if summary and summary.get("match_percentage") is not None:
        match_percentage = _safe_float(summary.get("match_percentage"))
    else:
        exact_matched = max(0, matched_count - mismatch_count)
        scope = matched_count + len(only_our) + len(only_bank)
        match_percentage = (exact_matched / scope * 100) if scope else 0.0

    if isinstance(result.get("by_date"), list):
        date_rows = result.get("by_date") or []
    elif isinstance(result.get("summary"), list):
        # Frontend Bank RRN adapter exposes the date table as result.summary.
        date_rows = result.get("summary") or []
    else:
        date_rows = []
    daily = []
    for row in date_rows:
        if not isinstance(row, dict):
            continue
        date_value = str(row.get("date") or "").strip()
        if not date_value or "ИТОГО" in date_value.upper():
            continue
        daily.append({
            "date": date_value,
            "our_count": _safe_int(row.get("Кол_во_у_нас")),
            "bank_count": _safe_int(row.get("Кол_во_в_банке")),
            "count_delta": _safe_int(row.get("Δ кол-во")),
            "our_sum": round(_safe_float(row.get("Сумма_у_нас")), 2),
            "bank_sum": round(_safe_float(row.get("Сумма_в_банке")), 2),
            "sum_delta": round(_safe_float(row.get("Δ суммы")), 2),
        })

    daily = sorted(
        daily,
        key=lambda item: (abs(item["sum_delta"]), abs(item["count_delta"])),
        reverse=True,
    )[:10]

    context = {
        "bank_name": str(payload.get("bank_name") or "Банк"),
        "currency": str(payload.get("currency") or "UZS"),
        "summary": {
            "matched_count": matched_count,
            "discrepancy_count": discrepancy_count,
            "match_percentage": round(match_percentage, 2),
            "total_our": round(total_our, 2),
            "total_bank": round(total_bank, 2),
            "difference_bank_minus_our": round(total_diff, 2),
        },
        "unmatched": {
            "only_our": unmatched_our,
            "only_bank": unmatched_bank,
        },
        "amount_mismatches": {
            "count": len(mismatches),
            "absolute_delta_sum": round(mismatch_abs, 2),
            "commission_like_count": commission_only,
        },
        "duplicates": {
            "our": duplicate_our,
            "bank": duplicate_bank,
        },
        "commission": {
            "effective_rate_pct": round(commission_rate, 4),
            "deducted_in_matching": bool(
                rrn.get("deduct_commission")
                or result.get("deduct_commission")
            ),
        },
        "data_quality": data_quality,
        "detected_months": rrn.get("detected_months")
        or result.get("detected_months")
        or [],
        "largest_daily_differences": daily,
    }

    # Transaction identifiers and raw source rows are intentionally excluded.
    return context


def build_local_hypotheses(
    payload: dict[str, Any],
    context: dict[str, Any],
) -> list[dict[str, Any]]:
    result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
    rrn = (
        result.get("custom_metrics", {}).get("rrn", {})
        if isinstance(result.get("custom_metrics"), dict)
        else {}
    )
    if not isinstance(rrn, dict):
        rrn = {}

    only_our = _active_rows(rrn.get("only_our") or result.get("only_our"))
    only_bank = _active_rows(rrn.get("only_bank") or result.get("only_bank"))
    hypotheses: list[dict[str, Any]] = []

    end_our = _month_end_rows(only_our)
    end_bank = _month_end_rows(only_bank)
    first_our = _first_days_rows(only_our)
    first_bank = _first_days_rows(only_bank)

    if end_our or end_bank:
        our_count = len(end_our)
        bank_count = len(end_bank)
        dominant_side = "нашей системе" if our_count >= bank_count else "банке"
        dominant_rows = end_our if our_count >= bank_count else end_bank
        dominant_count = max(our_count, bank_count)
        total_unmatched = max(1, len(only_our) + len(only_bank))
        share = dominant_count / total_unmatched

        evidence = [
            (
                f"На последних 3 календарных днях месяца несопоставлено "
                f"{our_count} операций у нас и {bank_count} операций у банка."
            ),
            f"Даты концентрации: {_date_label(dominant_rows)}.",
        ]

        next_side_count = len(first_bank if our_count >= bank_count else first_our)
        if next_side_count:
            evidence.append(
                f"На первых 3 днях доступного периода у противоположной стороны есть "
                f"{next_side_count} несопоставленных операций."
            )

        confidence = "medium"
        if share >= 0.5 and dominant_count >= 3 and next_side_count:
            confidence = "high"

        direction = (
            "часть операций могла попасть в банковскую выписку уже следующего периода"
            if our_count >= bank_count
            else "часть банковских операций могла быть отражена в нашей системе уже следующим периодом"
        )

        hypotheses.append(_hypothesis(
            kind="month_end_cutoff",
            title="Возможен переход операций через границу месяца",
            explanation=(
                f"Расхождения концентрируются в конце месяца, причём операций больше в "
                f"{dominant_side}. Это совместимо с временным лагом проведения/settlement: "
                f"{direction}. Это гипотеза, а не подтверждённая причина — её лучше проверить "
                f"по выписке первых дней следующего месяца."
            ),
            confidence=confidence,
            evidence=evidence,
        ))

    amount_info = context["amount_mismatches"]
    mismatch_count = _safe_int(amount_info.get("count"))
    commission_like = _safe_int(amount_info.get("commission_like_count"))
    commission_rate = _safe_float(context["commission"].get("effective_rate_pct"))
    if mismatch_count > 0 and commission_like > 0:
        share = commission_like / max(1, mismatch_count)
        hypotheses.append(_hypothesis(
            kind="commission",
            title="Часть расхождений похожа на эффект комиссии",
            explanation=(
                "В движке уже найдены расхождения сумм, которые соответствуют ожидаемому "
                "размеру комиссии EPOS. Проверьте, сравнивается ли gross с gross или gross с net, "
                "и одинаково ли применяется режим вычета комиссии на обеих сторонах."
            ),
            confidence="high" if share >= 0.6 else "medium",
            evidence=[
                f"Commission-like расхождений: {commission_like} из {mismatch_count}.",
                f"Эффективная ставка по данным банка: {commission_rate:.2f}%.",
            ],
        ))

    dup_our = _safe_int(context["duplicates"].get("our"))
    dup_bank = _safe_int(context["duplicates"].get("bank"))
    if dup_our or dup_bank:
        hypotheses.append(_hypothesis(
            kind="duplicates",
            title="Дубликаты могут искажать количество и суммы",
            explanation=(
                "Повторяющиеся RRN способны создавать лишние строки или нарушать однозначное "
                "сопоставление. Перед закрытием периода стоит проверить, являются ли это реальные "
                "повторные операции, возвраты или технические дубли."
            ),
            confidence="medium",
            evidence=[
                f"Дубликатов у нас: {dup_our}.",
                f"Дубликатов у банка: {dup_bank}.",
            ],
        ))

    quality_issue_count = 0
    for side in ("our", "bank"):
        side_data = context.get("data_quality", {}).get(side, {})
        if isinstance(side_data, dict):
            quality_issue_count += sum(_safe_int(value) for value in side_data.values())
    if quality_issue_count:
        hypotheses.append(_hypothesis(
            kind="data_quality",
            title="Есть проблемы качества исходных данных",
            explanation=(
                "Часть расхождений может быть технической: пустые/невалидные даты, RRN или суммы "
                "снижают качество сопоставления. Сначала стоит очистить эти строки, а затем повторить сверку."
            ),
            confidence="high",
            evidence=[f"Зафиксировано проблем качества данных: {quality_issue_count}."],
        ))

    unmatched_total = (
        _safe_int(context["unmatched"]["only_our"].get("count"))
        + _safe_int(context["unmatched"]["only_bank"].get("count"))
    )
    top_dates = (
        context["unmatched"]["only_our"].get("top_dates", [])
        + context["unmatched"]["only_bank"].get("top_dates", [])
    )
    if unmatched_total >= 5 and top_dates:
        combined: dict[str, int] = defaultdict(int)
        for item in top_dates:
            combined[str(item.get("date") or "")] += _safe_int(item.get("count"))
        if combined:
            top_date, top_count = max(combined.items(), key=lambda pair: pair[1])
            share = top_count / max(1, unmatched_total)
            if share >= 0.4:
                hypotheses.append(_hypothesis(
                    kind="date_concentration",
                    title="Несопоставленные операции сосредоточены на одной дате",
                    explanation=(
                        "Большая доля unmatched приходится на один операционный день. "
                        "Это может указывать на локальную проблему загрузки, задержку выгрузки, "
                        "особенность банковского settlement или неполный дневной файл."
                    ),
                    confidence="medium",
                    evidence=[
                        f"{top_count} из {unmatched_total} несопоставленных операций приходятся на {top_date}.",
                        f"Доля концентрации: {share * 100:.1f}%.",
                    ],
                ))

    return hypotheses[:6]


def _local_summary(
    context: dict[str, Any],
    hypotheses: list[dict[str, Any]],
) -> str:
    summary = context["summary"]
    unmatched = context["unmatched"]
    problem_count = _safe_int(summary.get("discrepancy_count"))
    match_rate = _safe_float(summary.get("match_percentage"))
    diff = _safe_float(summary.get("difference_bank_minus_our"))
    currency = context.get("currency") or "UZS"

    parts = [
        (
            f"Сверка: точное совпадение {match_rate:.1f}%, "
            f"проблемных строк {problem_count}, финансовая разница "
            f"(банк − мы) {diff:,.2f} {currency}."
        ).replace(",", " ")
    ]

    our_count = _safe_int(unmatched["only_our"].get("count"))
    bank_count = _safe_int(unmatched["only_bank"].get("count"))
    if our_count or bank_count:
        parts.append(
            f"Несопоставлено: {our_count} только у нас и {bank_count} только у банка."
        )

    if hypotheses:
        parts.append(
            "Наиболее заметная гипотеза: " + hypotheses[0]["title"].lower() + "."
        )
    else:
        parts.append(
            "Явной системной закономерности по доступным агрегатам не обнаружено."
        )

    return " ".join(parts)


def _strip_json_fence(text: str) -> str:
    clean = text.strip()
    fence = chr(96) * 3
    if clean.startswith(fence):
        clean = clean.split("\n", 1)[1] if "\n" in clean else clean
        if clean.endswith(fence):
            clean = clean[:-3]
    if clean.startswith("json\n"):
        clean = clean[5:]
    return clean.strip()


def _openai_enrich(
    context: dict[str, Any],
    local_hypotheses: list[dict[str, Any]],
) -> dict[str, Any] | None:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return None

    try:
        from openai import OpenAI
    except ImportError:
        return None

    model = os.getenv("RECONCILEHUB_AI_MODEL", "gpt-6-astra").strip() or "gpt-6-astra"
    client = OpenAI(api_key=api_key)

    prompt_payload = {
        "aggregated_reconciliation": context,
        "rule_based_hypotheses": local_hypotheses,
    }
    instructions = (
        "Ты аналитик банковских сверок. Анализируй только переданные агрегированные факты. "
        "Не придумывай транзакции, RRN, даты или причины. Разделяй факт и гипотезу. "
        "Причины формулируй как возможные объяснения, а не как установленный факт. "
        "Особенно обращай внимание на конец месяца: если у одной стороны на 29-31 число "
        "больше unmatched, можно предположить cutoff/settlement lag и попадание операций "
        "в следующий период, но обязательно указать, что это нужно подтвердить выпиской "
        "первых дней следующего месяца. Не советуй бухгалтерские проводки. "
        "Ответь только JSON-объектом с полями executive_summary (строка) и insights "
        "(массив максимум 5 объектов: title, explanation, confidence=low|medium|high)."
    )

    response = client.responses.create(
        model=model,
        instructions=instructions,
        input=json.dumps(prompt_payload, ensure_ascii=False, default=str),
        store=False,
    )
    text = getattr(response, "output_text", "") or ""
    if not text:
        return None

    try:
        parsed = json.loads(_strip_json_fence(text))
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None

    summary = str(parsed.get("executive_summary") or "").strip()
    insights = parsed.get("insights")
    if not summary or not isinstance(insights, list):
        return None

    normalized_insights = []
    for item in insights[:5]:
        if not isinstance(item, dict):
            continue
        confidence = str(item.get("confidence") or "low").lower()
        if confidence not in AI_CONFIDENCE_LABELS:
            confidence = "low"
        normalized_insights.append({
            "kind": "ai_interpretation",
            "title": str(item.get("title") or "Наблюдение").strip(),
            "explanation": str(item.get("explanation") or "").strip(),
            "confidence": confidence,
            "confidence_label": AI_CONFIDENCE_LABELS[confidence],
            "evidence": [],
        })

    return {
        "executive_summary": summary,
        "insights": normalized_insights,
        "model": model,
    }


def analyze_bank_reconciliation(payload: dict[str, Any]) -> dict[str, Any]:
    context = build_bank_ai_context(payload)
    local_hypotheses = build_local_hypotheses(payload, context)
    local_summary = _local_summary(context, local_hypotheses)

    provider = "local"
    model = None
    executive_summary = local_summary
    insights = local_hypotheses
    warning = None

    if os.getenv("OPENAI_API_KEY", "").strip():
        try:
            enriched = _openai_enrich(context, local_hypotheses)
            if enriched:
                provider = "openai"
                model = enriched.get("model")
                executive_summary = enriched["executive_summary"]
                insights = (local_hypotheses + enriched["insights"])[:7]
            else:
                warning = (
                    "AI-провайдер не вернул структурированный ответ; показаны локальные "
                    "гипотезы на основе правил."
                )
        except Exception as exc:
            warning = (
                "AI-провайдер временно недоступен; показаны локальные гипотезы. "
                f"Техническая причина: {type(exc).__name__}."
            )

    return {
        "provider": provider,
        "model": model,
        "executive_summary": executive_summary,
        "insights": insights,
        "context": context,
        "warning": warning,
        "disclaimer": (
            "Это аналитические гипотезы. Они не изменяют результат сверки и не являются "
            "подтверждением причины расхождения. Проверяйте выводы по исходным документам "
            "и следующему/предыдущему периоду."
        ),
        "privacy": (
            "Во внешний AI передаются только агрегаты и диагностические признаки; "
            "RRN и raw-строки источников в AI-контекст не включаются."
        ),
    }
