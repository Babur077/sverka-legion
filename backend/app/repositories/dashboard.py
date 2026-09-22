from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from datetime import datetime
from typing import Any

import utils.db_manager as db


def _json_dict(raw: Any) -> dict[str, Any]:
    try:
        value = json.loads(raw or "{}")
        return value if isinstance(value, dict) else {}
    except (TypeError, json.JSONDecodeError):
        return {}


def _month_key(value: str | None) -> str:
    text = str(value or "").strip()
    if len(text) >= 7 and text[4] == "-":
        return text[:7]
    return datetime.now().strftime("%Y-%m")


def _shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    absolute = year * 12 + (month - 1) + delta
    return absolute // 12, absolute % 12 + 1


def _month_window(months: int) -> list[str]:
    now = datetime.now()
    count = max(1, min(int(months), 24))
    values = []
    for offset in range(-(count - 1), 1):
        year, month = _shift_month(now.year, now.month, offset)
        values.append(f"{year:04d}-{month:02d}")
    return values


def _metrics(summary: dict[str, Any]) -> tuple[int, int, float]:
    matched = int(summary.get("matched_count") or 0)
    discrepancy = summary.get("discrepancy_count")
    if discrepancy is None:
        discrepancy = (
            int(summary.get("mismatch_count") or 0)
            + int(summary.get("only_our_count") or 0)
            + int(summary.get("only_bank_count") or 0)
        )
    discrepancy = int(discrepancy or 0)

    raw_rate = summary.get("match_percentage")
    if raw_rate is not None:
        try:
            rate = float(raw_rate)
        except (TypeError, ValueError):
            rate = 0.0
    else:
        scope = matched + discrepancy
        rate = matched / scope * 100 if scope else 0.0
    return matched, discrepancy, rate


def get_dashboard_data(
    *,
    allowed_modules: dict[str, str],
    username: str,
    months: int = 6,
    module_id: str | None = None,
    include_all_jobs: bool = False,
) -> dict[str, Any]:
    month_keys = _month_window(months)
    allowed_ids = set(allowed_modules)
    if module_id and module_id not in allowed_ids:
        module_id = None

    run_conditions = []
    run_params: list[Any] = []
    if allowed_ids:
        placeholders = ",".join("?" for _ in allowed_ids)
        run_conditions.append(f"module_id IN ({placeholders})")
        run_params.extend(sorted(allowed_ids))
    else:
        run_conditions.append("1 = 0")
    if module_id:
        run_conditions.append("module_id = ?")
        run_params.append(module_id)

    where_runs = " AND ".join(run_conditions)

    with sqlite3.connect(db.DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        run_rows = conn.execute(
            f"""
            SELECT id, module_id, run_id, status, period_month, created_at,
                   updated_at, created_by, summary_json
            FROM reconciliation_runs
            WHERE {where_runs}
            ORDER BY updated_at DESC, id DESC
            """,
            run_params,
        ).fetchall()

        job_conditions = []
        job_params: list[Any] = []
        if allowed_ids:
            placeholders = ",".join("?" for _ in allowed_ids)
            job_conditions.append(f"module_id IN ({placeholders})")
            job_params.extend(sorted(allowed_ids))
        else:
            job_conditions.append("1 = 0")
        if module_id:
            job_conditions.append("module_id = ?")
            job_params.append(module_id)
        if not include_all_jobs:
            job_conditions.append("created_by = ?")
            job_params.append(username)

        job_rows = conn.execute(
            f"""
            SELECT id, module_id, status, progress, stage, created_by,
                   created_at, updated_at, started_at, finished_at, run_id, error
            FROM reconciliation_jobs
            WHERE {' AND '.join(job_conditions)}
            ORDER BY id DESC
            LIMIT 20
            """,
            job_params,
        ).fetchall()

    relevant_runs: list[dict[str, Any]] = []
    month_set = set(month_keys)
    for row in run_rows:
        raw = dict(row)
        summary = _json_dict(raw.get("summary_json"))
        period = _month_key(raw.get("period_month") or raw.get("created_at"))
        if period not in month_set:
            continue
        matched, discrepancy, rate = _metrics(summary)
        relevant_runs.append({
            "id": int(raw["id"]),
            "module_id": str(raw["module_id"]),
            "module_name": allowed_modules.get(str(raw["module_id"]), str(raw["module_id"])),
            "run_id": raw.get("run_id"),
            "status": str(raw.get("status") or ""),
            "period_month": period,
            "created_at": raw.get("created_at"),
            "updated_at": raw.get("updated_at"),
            "created_by": raw.get("created_by") or "",
            "matched_count": matched,
            "discrepancy_count": discrepancy,
            "match_percentage": round(rate, 2),
            "definition_name": summary.get("definition_name"),
            "definition_version_number": summary.get("definition_version_number"),
            "bank_name": summary.get("bank_name"),
        })

    total_runs = len(relevant_runs)
    completed_runs = sum(
        1 for run in relevant_runs
        if run["status"].upper() in {"COMPLETED", "WARNING"}
    )
    failed_runs = sum(1 for run in relevant_runs if run["status"].upper() == "FAILED")
    problem_runs = sum(
        1 for run in relevant_runs
        if run["discrepancy_count"] > 0
        or run["status"].upper() in {"WARNING", "FAILED"}
    )
    total_discrepancies = sum(run["discrepancy_count"] for run in relevant_runs)
    average_match = (
        sum(run["match_percentage"] for run in relevant_runs) / total_runs
        if total_runs
        else 0.0
    )

    trend_acc: dict[str, dict[str, float]] = {
        month: {"runs": 0.0, "rate_sum": 0.0, "discrepancies": 0.0}
        for month in month_keys
    }
    module_acc: dict[str, dict[str, float]] = defaultdict(
        lambda: {"runs": 0.0, "rate_sum": 0.0, "problems": 0.0, "discrepancies": 0.0}
    )

    for run in relevant_runs:
        trend = trend_acc[run["period_month"]]
        trend["runs"] += 1
        trend["rate_sum"] += run["match_percentage"]
        trend["discrepancies"] += run["discrepancy_count"]

        module = module_acc[run["module_id"]]
        module["runs"] += 1
        module["rate_sum"] += run["match_percentage"]
        module["discrepancies"] += run["discrepancy_count"]
        if run["discrepancy_count"] > 0 or run["status"].upper() in {"WARNING", "FAILED"}:
            module["problems"] += 1

    trend = []
    for month in month_keys:
        item = trend_acc[month]
        count = int(item["runs"])
        trend.append({
            "month": month,
            "runs": count,
            "average_match_percentage": round(item["rate_sum"] / count, 2) if count else 0.0,
            "discrepancies": int(item["discrepancies"]),
        })

    modules = []
    for current_id in sorted(allowed_ids):
        if module_id and current_id != module_id:
            continue
        item = module_acc[current_id]
        count = int(item["runs"])
        modules.append({
            "module_id": current_id,
            "module_name": allowed_modules.get(current_id, current_id),
            "runs": count,
            "average_match_percentage": round(item["rate_sum"] / count, 2) if count else 0.0,
            "problem_runs": int(item["problems"]),
            "discrepancies": int(item["discrepancies"]),
        })

    jobs = [dict(row) for row in job_rows]
    active_jobs = [job for job in jobs if str(job.get("status")) in {"QUEUED", "RUNNING"}]
    queued_jobs = sum(1 for job in active_jobs if str(job.get("status")) == "QUEUED")
    running_jobs = sum(1 for job in active_jobs if str(job.get("status")) == "RUNNING")
    failed_jobs = sum(1 for job in jobs if str(job.get("status")) == "FAILED")

    return {
        "period": {
            "months": len(month_keys),
            "from_month": month_keys[0],
            "to_month": month_keys[-1],
        },
        "filters": {
            "module_id": module_id,
            "available_modules": [
                {"id": key, "name": value}
                for key, value in sorted(allowed_modules.items(), key=lambda item: item[1])
            ],
        },
        "summary": {
            "runs": total_runs,
            "completed_runs": completed_runs,
            "failed_runs": failed_runs,
            "problem_runs": problem_runs,
            "average_match_percentage": round(average_match, 2),
            "discrepancies": total_discrepancies,
            "running_jobs": running_jobs,
            "queued_jobs": queued_jobs,
            "failed_jobs": failed_jobs,
        },
        "trend": trend,
        "modules": modules,
        "recent_runs": relevant_runs[:10],
        "jobs": jobs[:10],
    }
