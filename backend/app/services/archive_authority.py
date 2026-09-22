from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any

from fastapi import HTTPException

from backend.app.repositories.run_results import get_run_result
from backend.app.repositories.runs import list_runs, save_run
from utils.permissions import record_audit_event


def _text(value: Any, limit: int = 300) -> str:
    return str(value or "").strip()[:limit]


def _number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _indices(value: Any, size: int) -> set[int]:
    if not isinstance(value, list):
        return set()
    result: set[int] = set()
    for raw in value:
        try:
            index = int(raw)
        except (TypeError, ValueError):
            continue
        if 0 <= index < size:
            result.add(index)
    return result


def _reason_map(value: Any, size: int) -> dict[int, str]:
    if not isinstance(value, dict):
        return {}
    result: dict[int, str] = {}
    for raw_index, raw_reason in value.items():
        try:
            index = int(raw_index)
        except (TypeError, ValueError):
            continue
        if 0 <= index < size:
            result[index] = _text(raw_reason, 300)
    return result


def _bank_config(params: dict[str, Any]) -> dict[str, Any]:
    return {
        "our_date_col": params.get("our_date_col"),
        "our_rrn_col": params.get("our_rrn_col"),
        "our_amt_col": params.get("our_amt_col"),
        "our_status_col": params.get("our_status_col"),
        "bank_date_col": params.get("bank_date_col"),
        "bank_rrn_col": params.get("bank_rrn_col"),
        "bank_amt_col": params.get("bank_amt_col"),
        "bank_status_col": params.get("bank_status_col"),
        "bank_tid_col": params.get("bank_tid_col"),
        "rev_words": [
            item.strip()
            for item in str(params.get("rev_words") or "").split(",")
            if item.strip()
        ],
        "our_rev_action": params.get("our_rev_action"),
        "bank_rev_action": params.get("bank_rev_action"),
        "dup_action": params.get("dup_action"),
        "unbind_mismatches": str(params.get("unbind_mismatches") or "").lower() in {"1", "true", "yes", "on"},
        "tolerance": _number(params.get("tolerance")),
        "deduct_commission": str(params.get("deduct_commission") or "").lower() in {"1", "true", "yes", "on"},
        "source_options": {
            "our": {
                "sheetName": params.get("our_sheet_name") or "",
                "headerRow": int(_number(params.get("our_header_row")) or 1),
            },
            "bank": {
                "sheetName": params.get("bank_sheet_name") or "",
                "headerRow": int(_number(params.get("bank_header_row")) or 1),
            },
        },
    }


def _bank_authoritative_payload(
    cached: dict[str, Any],
    client_payload: dict[str, Any],
) -> dict[str, Any]:
    result = deepcopy(cached.get("result") or {})
    rrn = deepcopy(((result.get("custom_metrics") or {}).get("rrn") or {}))
    only_our = list(rrn.get("only_our") or [])
    only_bank = list(rrn.get("only_bank") or [])

    review = client_payload.get("review")
    if not isinstance(review, dict):
        review = {}

    excluded_our = _indices(review.get("excluded_our_indices"), len(only_our))
    excluded_bank = _indices(review.get("excluded_bank_indices"), len(only_bank))
    reasons_our = _reason_map(review.get("reasons_our"), len(only_our))
    reasons_bank = _reason_map(review.get("reasons_bank"), len(only_bank))

    for index, row in enumerate(only_our):
        if isinstance(row, dict):
            row["checked"] = index not in excluded_our
            if index in reasons_our:
                row["reason"] = reasons_our[index]
    for index, row in enumerate(only_bank):
        if isinstance(row, dict):
            row["checked"] = index not in excluded_bank
            if index in reasons_bank:
                row["reason"] = reasons_bank[index]

    excluded_our_by_date: dict[str, dict[str, float]] = {}
    for index in excluded_our:
        row = only_our[index]
        key = str(row.get("date_str") or "")
        current = excluded_our_by_date.setdefault(key, {"count": 0.0, "sum": 0.0})
        current["count"] += 1
        current["sum"] += _number(row.get("amount"))

    excluded_bank_by_date: dict[str, dict[str, float]] = {}
    for index in excluded_bank:
        row = only_bank[index]
        key = str(row.get("date_str") or "")
        current = excluded_bank_by_date.setdefault(key, {"count": 0.0, "sum": 0.0})
        current["count"] += 1
        current["sum"] += _number(row.get("amount"))

    adjusted_by_date: list[dict[str, Any]] = []
    for raw in result.get("by_date") or []:
        if not isinstance(raw, dict):
            continue
        date_value = str(raw.get("date") or "")
        if "ИТОГО" in date_value:
            continue
        ex_our = excluded_our_by_date.get(date_value, {"count": 0.0, "sum": 0.0})
        ex_bank = excluded_bank_by_date.get(date_value, {"count": 0.0, "sum": 0.0})
        our_count = int(_number(raw.get("Кол_во_у_нас")) - ex_our["count"])
        bank_count = int(_number(raw.get("Кол_во_в_банке")) - ex_bank["count"])
        our_sum = _number(raw.get("Сумма_у_нас")) - ex_our["sum"]
        bank_sum = _number(raw.get("Сумма_в_банке")) - ex_bank["sum"]
        adjusted_by_date.append({
            "date": date_value,
            "Кол_во_у_нас": our_count,
            "Кол_во_в_банке": bank_count,
            "Δ кол-во": bank_count - our_count,
            "Сумма_у_нас": round(our_sum, 2),
            "Сумма_в_банке": round(bank_sum, 2),
            "Δ суммы": round(bank_sum - our_sum, 2),
        })

    total_our = round(sum(_number(row.get("Сумма_у_нас")) for row in adjusted_by_date), 2)
    total_bank = round(sum(_number(row.get("Сумма_в_банке")) for row in adjusted_by_date), 2)
    total_our_count = sum(int(_number(row.get("Кол_во_у_нас"))) for row in adjusted_by_date)
    total_bank_count = sum(int(_number(row.get("Кол_во_в_банке"))) for row in adjusted_by_date)
    difference = round(total_bank - total_our, 2)

    adjusted_by_date.append({
        "date": "ИТОГО (с учётом исключений)",
        "Кол_во_у_нас": total_our_count,
        "Кол_во_в_банке": total_bank_count,
        "Δ кол-во": total_bank_count - total_our_count,
        "Сумма_у_нас": total_our,
        "Сумма_в_банке": total_bank,
        "Δ суммы": difference,
    })

    excluded_by_terminal: dict[str, dict[str, float]] = {}
    for index in excluded_bank:
        row = only_bank[index]
        raw = row.get("raw") if isinstance(row.get("raw"), dict) else {}
        terminal_id = _text(row.get("terminal_id") or raw.get("terminal_id"), 120)
        if not terminal_id:
            continue
        raw_amount = _number(raw.get("raw_amount") if raw else row.get("amount"))
        commission_pct = _number(raw.get("commission_pct") if raw else row.get("commission_pct"))
        commission = raw.get("commission_amount") if raw else None
        commission_amount = (
            _number(commission)
            if commission is not None
            else raw_amount * commission_pct / 100
        )
        current = excluded_by_terminal.setdefault(
            terminal_id,
            {"tx": 0.0, "volume": 0.0, "commission": 0.0},
        )
        current["tx"] += 1
        current["volume"] += raw_amount
        current["commission"] += commission_amount

    adjusted_terminals: list[dict[str, Any]] = []
    for terminal in rrn.get("terminal_summary") or []:
        if not isinstance(terminal, dict):
            continue
        item = deepcopy(terminal)
        terminal_id = _text(item.get("terminal_id"), 120)
        excluded = excluded_by_terminal.get(
            terminal_id,
            {"tx": 0.0, "volume": 0.0, "commission": 0.0},
        )
        tx_count = max(0, int(_number(item.get("tx_count")) - excluded["tx"]))
        total_volume = _number(item.get("total_volume")) - excluded["volume"]
        commission_amount = max(
            0.0,
            _number(item.get("commission_amount")) - excluded["commission"],
        )
        item["tx_count"] = tx_count
        item["total_volume"] = round(total_volume, 2)
        item["commission_amount"] = round(commission_amount, 2)
        item["net_volume"] = round(total_volume - commission_amount, 2)
        if tx_count > 0 or abs(total_volume) > 0.000001:
            adjusted_terminals.append(item)

    if adjusted_terminals:
        total_commission = round(
            sum(_number(item.get("commission_amount")) for item in adjusted_terminals),
            2,
        )
    else:
        excluded_commission = 0.0
        for index in excluded_bank:
            row = only_bank[index]
            raw = row.get("raw") if isinstance(row.get("raw"), dict) else {}
            direct = raw.get("commission_amount") if raw else None
            if direct is not None:
                excluded_commission += _number(direct)
            else:
                amount = _number(raw.get("raw_amount") if raw else row.get("amount"))
                pct = _number(raw.get("commission_pct") if raw else row.get("commission_pct"))
                excluded_commission += amount * pct / 100
        total_commission = round(
            max(0.0, _number(rrn.get("total_commission")) - excluded_commission),
            2,
        )

    matched_count = int(_number(rrn.get("matched_count")))
    mismatch_count = int(_number(rrn.get("mismatch_count")))
    active_only_our = len(only_our) - len(excluded_our)
    active_only_bank = len(only_bank) - len(excluded_bank)
    exact_matched = max(0, matched_count - mismatch_count)
    scope = matched_count + active_only_our + active_only_bank
    match_percentage = round((exact_matched / scope) * 100, 2) if scope else 0.0

    rrn["only_our"] = only_our
    rrn["only_bank"] = only_bank
    rrn["terminal_summary"] = adjusted_terminals
    rrn["total_commission"] = total_commission
    result["by_date"] = adjusted_by_date
    result["custom_metrics"] = {**(result.get("custom_metrics") or {}), "rrn": rrn}
    result["summary"] = {
        **(result.get("summary") or {}),
        "total_records_a": total_our_count,
        "total_records_b": total_bank_count,
        "total_sum_a": total_our,
        "total_sum_b": total_bank,
        "matched_count": matched_count,
        "discrepancy_count": mismatch_count + active_only_our + active_only_bank,
        "diff_sum": difference,
        "match_percentage": match_percentage,
    }
    data_quality = rrn.get("data_quality") or {}
    data_quality_issue_count = sum(
        int(value or 0)
        for side in ("our", "bank")
        for value in ((data_quality.get(side) or {}).values())
    )
    result["status"] = (
        "COMPLETED"
        if mismatch_count == 0
        and active_only_our == 0
        and active_only_bank == 0
        and data_quality_issue_count == 0
        else "WARNING"
    )

    params = cached.get("params") or {}
    source_files = list(cached.get("source_files") or [])
    period = _text(client_payload.get("period_month"), 7)
    if len(period) != 7 or period[4:5] != "-":
        detected = rrn.get("detected_months") or []
        period = str(detected[0]) if detected else datetime.now().strftime("%Y-%m")

    return {
        "run_id": cached["run_id"],
        "status": result["status"],
        "period_month": period,
        "bank_name": _text(client_payload.get("bank_name"), 200) or "Банк",
        "assigned_terminal_id": _text(client_payload.get("assigned_terminal_id"), 120) or None,
        "total_our": total_our,
        "total_bank": total_bank,
        "difference": difference,
        "matched_count": matched_count,
        "mismatch_count": mismatch_count,
        "only_our_count": active_only_our,
        "only_bank_count": active_only_bank,
        "total_commission": total_commission,
        "terminals_summary": adjusted_terminals,
        "source_our_name": source_files[0] if len(source_files) > 0 else "",
        "source_bank_name": source_files[1] if len(source_files) > 1 else "",
        "source_files": source_files,
        "config": _bank_config(params),
        "summary": result["summary"],
        "result_snapshot": result,
        "review": {
            "excluded_our_indices": sorted(excluded_our),
            "excluded_bank_indices": sorted(excluded_bank),
            "reasons_our": {str(k): v for k, v in reasons_our.items()},
            "reasons_bank": {str(k): v for k, v in reasons_bank.items()},
        },
        "archive_schema_version": 3,
    }


def _ravan_authoritative_payload(
    cached: dict[str, Any],
    client_payload: dict[str, Any],
) -> dict[str, Any]:
    result = deepcopy(cached.get("result") or {})
    metrics = ((result.get("custom_metrics") or {}).get("ravan_1c") or {})
    source_files = list(cached.get("source_files") or metrics.get("source_files") or [])
    return {
        "run_id": cached["run_id"],
        "status": result.get("status") or "COMPLETED",
        "period_month": _text(client_payload.get("period_month"), 7) or None,
        "source_files": source_files,
        "summary": deepcopy(result.get("summary") or {}),
        "producer": "Sayfulloh Abdusalomov",
        "sum_tolerance": _number(metrics.get("sum_tolerance") or 1),
        "result_snapshot": result,
        "archive_schema_version": 3,
    }


def prepare_authoritative_archive_payload(
    module_id: str,
    username: str,
    client_payload: dict[str, Any],
    *,
    allow_owner_override: bool = False,
) -> dict[str, Any]:
    run_id = _text((client_payload or {}).get("run_id"), 160)
    if not run_id:
        raise HTTPException(status_code=400, detail="run_id обязателен для сохранения архива")

    cached = get_run_result(
        module_id,
        run_id,
        username,
        allow_owner_override=allow_owner_override,
    )
    if not cached:
        raise HTTPException(
            status_code=404,
            detail="Серверный результат Run не найден или принадлежит другому пользователю",
        )

    if module_id == "bank_rrn":
        return _bank_authoritative_payload(cached, client_payload or {})
    if module_id == "ravan_1c":
        return _ravan_authoritative_payload(cached, client_payload or {})

    result = deepcopy(cached.get("result") or {})
    source_files = list(cached.get("source_files") or [])
    return {
        "run_id": cached["run_id"],
        "status": result.get("status") or "COMPLETED",
        "period_month": _text((client_payload or {}).get("period_month"), 7) or None,
        "source_files": source_files,
        "summary": deepcopy(result.get("summary") or {}),
        "result_snapshot": result,
        "archive_schema_version": 3,
    }


def _recalculate_ravan_snapshot(snapshot: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    snapshot = deepcopy(snapshot)
    status_counts: dict[str, int] = {}
    for row in rows:
        status = str(row.get("Status") or "Ошибка")
        status_counts[status] = status_counts.get(status, 0) + 1

    matched_count = sum(1 for row in rows if row.get("Status") == "OK")
    discrepancy_count = len(rows) - matched_count
    match_percentage = round(matched_count / len(rows) * 100, 2) if rows else 0.0

    metrics = deepcopy(((snapshot.get("custom_metrics") or {}).get("ravan_1c") or {}))
    metrics["rows"] = rows
    metrics["status_counts"] = status_counts
    metrics["fuzzy_review_count"] = sum(1 for row in rows if row.get("Needs_Review"))
    snapshot["custom_metrics"] = {
        **(snapshot.get("custom_metrics") or {}),
        "ravan_1c": metrics,
    }
    snapshot["summary"] = {
        **(snapshot.get("summary") or {}),
        "matched_count": matched_count,
        "discrepancy_count": discrepancy_count,
        "match_percentage": match_percentage,
    }
    order = [
        "OK",
        "Ошибка Kolvo",
        "Ошибка Summ",
        "Ошибка Kolvo + Summ",
        "Нет в !C",
        "Нет в Ravan",
        "Ошибка",
    ]
    snapshot["by_category"] = [
        {"status": status, "count": status_counts[status]}
        for status in order
        if status_counts.get(status)
    ] + [
        {"status": status, "count": count}
        for status, count in status_counts.items()
        if status not in order
    ]
    snapshot["discrepancies"] = [
        row for row in rows if row.get("Status") != "OK"
    ]
    snapshot["status"] = "COMPLETED" if discrepancy_count == 0 else "WARNING"
    return snapshot


def update_ravan_archive_match(
    username: str,
    run_id: str,
    row_id: str,
    decision: str,
    *,
    allow_owner_override: bool = False,
) -> dict[str, Any]:
    record = next(
        (
            item
            for item in list_runs("ravan_1c")
            if str(item.get("run_id") or "") == str(run_id)
            and (
                str(item.get("created_by") or "") == str(username)
                or allow_owner_override
            )
        ),
        None,
    )
    if not record:
        raise HTTPException(status_code=404, detail="Архивный Run не найден")

    snapshot = deepcopy(record.get("result_snapshot") or {})
    metrics = ((snapshot.get("custom_metrics") or {}).get("ravan_1c") or {})
    rows = [deepcopy(row) for row in (metrics.get("rows") or []) if isinstance(row, dict)]
    target_index = next(
        (index for index, row in enumerate(rows) if str(row.get("Row_ID") or "") == str(row_id)),
        None,
    )
    if target_index is None:
        raise HTTPException(status_code=404, detail="Строка сопоставления не найдена")

    target = rows[target_index]
    if target.get("Match_Type") != "fuzzy":
        raise HTTPException(status_code=409, detail="Эта строка не является fuzzy-сопоставлением")

    normalized_decision = str(decision or "").strip().lower()
    if normalized_decision == "confirm":
        target["Needs_Review"] = False
        target["Match_Confirmed"] = True
        rows[target_index] = target
    elif normalized_decision == "unlink":
        if not target.get("Partner_Ravan") or not target.get("Partner_C"):
            raise HTTPException(status_code=409, detail="Сопоставление уже разорвано")

        ravan_only = deepcopy(target)
        ravan_only.update({
            "Row_ID": f"{row_id}-r",
            "Match_Type": "manual_unlinked",
            "Name_Similarity": None,
            "Needs_Review": False,
            "Match_Confirmed": False,
            "Partner_C": None,
            "Kolvo_C": None,
            "Summ_C": None,
            "Kolvo_Difference": -_number(target.get("Kolvo_Ravan")),
            "Summ_Difference": -_number(target.get("Summ_Corrected")),
            "Status": "Нет в !C",
        })
        one_c_only = deepcopy(target)
        one_c_only.update({
            "Row_ID": f"{row_id}-c",
            "Match_Type": "manual_unlinked",
            "Name_Similarity": None,
            "Needs_Review": False,
            "Match_Confirmed": False,
            "Partner_Ravan": None,
            "NDS": None,
            "Kolvo_Ravan": None,
            "Summ_Ravan": None,
            "Summ_Corrected": None,
            "Kolvo_Difference": _number(target.get("Kolvo_C")),
            "Summ_Difference": _number(target.get("Summ_C")),
            "Status": "Нет в Ravan",
        })
        rows[target_index:target_index + 1] = [ravan_only, one_c_only]
    else:
        raise HTTPException(status_code=400, detail="decision должен быть confirm или unlink")

    updated_snapshot = _recalculate_ravan_snapshot(snapshot, rows)
    payload = {
        key: value
        for key, value in record.items()
        if key not in {
            "id", "module_id", "timestamp", "created_at", "updated_at",
            "username", "created_by", "review_status",
        }
    }
    payload["run_id"] = run_id
    payload["status"] = updated_snapshot.get("status")
    payload["summary"] = updated_snapshot.get("summary") or {}
    payload["result_snapshot"] = updated_snapshot
    payload["archive_schema_version"] = max(int(payload.get("archive_schema_version") or 0), 3)

    ok, message, record_id = save_run(
        "ravan_1c",
        username,
        payload,
        allow_owner_override=allow_owner_override,
    )
    if not ok:
        raise HTTPException(status_code=500, detail=message)

    record_audit_event(
        user_id=username,
        action="ARCHIVE_REVIEW",
        module_id="ravan_1c",
        object_type="ReconciliationRun",
        object_id=str(record_id or ""),
        status="SUCCESS",
        details=f"Run {run_id}: {normalized_decision} fuzzy match {row_id}",
    )

    return {
        "success": True,
        "message": message,
        "id": record_id,
        "result_snapshot": updated_snapshot,
    }
