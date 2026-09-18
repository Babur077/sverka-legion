import functools

import polars as pl
import pandas as pd
import numpy as np
from core.parsers import clean_amount_polars, parse_amount_polars, clean_date_polars, clean_rrn_polars


def _reversal_action_kind(action: str) -> str:
    """Normalize UI and legacy reversal action labels to engine operations."""
    normalized = str(action or "").strip().lower()
    if "💥" in normalized or "rrn полностью" in normalized:
        return "drop_rrn"
    if "🗑" in normalized or "удалить строк" in normalized or "удалить возврат" in normalized:
        return "drop_row"
    if "➖" in normalized or "минусовать" in normalized or "изменить знак" in normalized:
        return "negate"
    return "none"


def apply_reversals(df: pl.DataFrame, status_col: str, action: str, amt_col: str, rev_words: list) -> pl.DataFrame:
    if not status_col or status_col not in df.columns or not rev_words:
        return df

    words = [str(word).strip().lower() for word in rev_words if str(word).strip()]
    if not words:
        return df

    status_norm = (
        pl.col(status_col)
        .cast(pl.Utf8, strict=False)
        .fill_null("")
        .str.to_lowercase()
        .str.strip_chars()
    )
    rev_mask = functools.reduce(
        lambda acc, word: acc | status_norm.str.contains(word, literal=True),
        words[1:],
        status_norm.str.contains(words[0], literal=True),
    ).fill_null(False)

    action_kind = _reversal_action_kind(action)
    if action_kind == "drop_rrn":
        bad_rrns = df.filter(rev_mask).select("RRN").unique()
        return df.join(bad_rrns, on="RRN", how="anti")
    if action_kind == "drop_row":
        return df.filter(~rev_mask)
    if action_kind == "negate":
        return df.with_columns(
            pl.when(rev_mask)
            .then(-pl.col(amt_col).abs())
            .otherwise(pl.col(amt_col))
            .alias(amt_col)
        )
    return df


def date_summary(pl_our: pl.DataFrame, pl_bank: pl.DataFrame) -> pd.DataFrame:
    so = (
        pl_our.group_by("date").agg([pl.len().alias("Кол_во_у_нас"), pl.col("net_amount_our").sum().alias("Сумма_у_нас")])
        if pl_our.height > 0
        else pl.DataFrame(schema={"date": pl.Date, "Кол_во_у_нас": pl.UInt32, "Сумма_у_нас": pl.Float64})
    )
    sb = (
        pl_bank.group_by("date").agg([pl.len().alias("Кол_во_в_банке"), pl.col("net_amount_bank").sum().alias("Сумма_в_банке")])
        if pl_bank.height > 0
        else pl.DataFrame(schema={"date": pl.Date, "Кол_во_в_банке": pl.UInt32, "Сумма_в_банке": pl.Float64})
    )
    s = so.join(sb, on="date", how="full", coalesce=True)
    s = s.with_columns([
        pl.col("Кол_во_у_нас").fill_null(0), pl.col("Сумма_у_нас").fill_null(0.0),
        pl.col("Кол_во_в_банке").fill_null(0), pl.col("Сумма_в_банке").fill_null(0.0),
    ])
    s = s.with_columns([
        (pl.col("Сумма_в_банке") - pl.col("Сумма_у_нас")).alias("Δ суммы"),
        (pl.col("Кол_во_в_банке") - pl.col("Кол_во_у_нас")).alias("Δ кол-во"),
    ])
    return s.sort("date", descending=True).to_pandas()


def _source_quality(df: pl.DataFrame, date_col: str, rrn_col: str, amount_col: str | None = None) -> dict:
    """Count source values that require review before period close."""
    empty = {
        "missing_date": 0,
        "invalid_date": 0,
        "empty_rrn": 0,
        "missing_amount": 0,
        "invalid_amount": 0,
    }
    if df is None or df.height == 0:
        return empty

    raw_date = pl.col(date_col).cast(pl.Utf8, strict=False).fill_null("").str.strip_chars()
    raw_rrn = pl.col(rrn_col).cast(pl.Utf8, strict=False).fill_null("").str.strip_chars().str.to_uppercase()
    parsed_date = clean_date_polars(date_col)

    exprs = [
        (raw_date == "").sum().alias("missing_date"),
        ((raw_date != "") & parsed_date.is_null()).sum().alias("invalid_date"),
        raw_rrn.is_in(["", "NAN", "NONE", "NAT"]).sum().alias("empty_rrn"),
    ]

    if amount_col and amount_col in df.columns:
        raw_amount = pl.col(amount_col).cast(pl.Utf8, strict=False).fill_null("").str.strip_chars()
        parsed_amount = parse_amount_polars(amount_col)
        exprs.extend([
            (raw_amount == "").sum().alias("missing_amount"),
            ((raw_amount != "") & parsed_amount.is_null()).sum().alias("invalid_amount"),
        ])
    else:
        exprs.extend([
            pl.lit(0).alias("missing_amount"),
            pl.lit(0).alias("invalid_amount"),
        ])

    row = df.select(exprs).to_dicts()[0]
    return {key: int(value or 0) for key, value in row.items()}


def _assign_duplicate_index(df: pl.DataFrame, amount_col: str, source_index_col: str) -> pl.DataFrame:
    """Pair repeated RRN deterministically by date, amount and original order.

    Sorting both sources by the same business keys prevents reordered duplicate
    rows from creating false amount mismatches. Original row order is only the
    final tie-breaker for truly identical duplicates.
    """
    sort_cols = ["RRN", "date", amount_col, source_index_col]
    return (
        df.sort(sort_cols, nulls_last=True)
        .with_columns(pl.col("RRN").cum_count().over("RRN").alias("_dup_idx"))
    )


def terminal_summary(pl_bank: pl.DataFrame, tid_col: str = "terminal_id") -> pd.DataFrame:
    if pl_bank is None or getattr(pl_bank, "height", 0) == 0:
        return pd.DataFrame(columns=["terminal_id", "tx_count", "total_volume", "commission_pct", "commission_amount", "net_volume", "legal_entity"])
    col_name = tid_col if (tid_col and tid_col in pl_bank.columns) else ("terminal_id" if "terminal_id" in pl_bank.columns else None)
    if not col_name:
        return pd.DataFrame()
    amt_col = "raw_amount" if "raw_amount" in pl_bank.columns else ("net_amount_bank" if "net_amount_bank" in pl_bank.columns else ("amount" if "amount" in pl_bank.columns else None))
    if not amt_col:
        return pd.DataFrame()
    has_legal = "legal_entity" in pl_bank.columns
    has_merchant = "merchant_id" in pl_bank.columns
    has_bank_name = "bank_acquirer" in pl_bank.columns
    has_comm = "commission_pct" in pl_bank.columns
    agg_exprs = [pl.len().alias("tx_count"), pl.col(amt_col).sum().alias("total_volume")]
    if has_comm:
        agg_exprs.append(pl.col("commission_pct").first().alias("commission_pct"))
        if "commission_amount" in pl_bank.columns:
            agg_exprs.append(pl.col("commission_amount").sum().alias("commission_amount"))
    if has_legal:
        agg_exprs.append(pl.col("legal_entity").first().alias("legal_entity"))
    if has_merchant:
        agg_exprs.append(pl.col("merchant_id").first().alias("merchant_id"))
    if has_bank_name:
        agg_exprs.append(pl.col("bank_acquirer").first().alias("bank_acquirer"))
    t_df = pl_bank.group_by(col_name).agg(agg_exprs).to_pandas()
    if col_name != "terminal_id" and "terminal_id" not in t_df.columns:
        t_df["terminal_id"] = t_df[col_name]
    if "commission_pct" not in t_df.columns:
        t_df["commission_pct"] = 0.0
    if "commission_amount" not in t_df.columns:
        t_df["commission_amount"] = t_df["total_volume"] * (t_df["commission_pct"] / 100.0)
    t_df["net_volume"] = t_df["total_volume"] - t_df["commission_amount"]
    if "legal_entity" not in t_df.columns:
        t_df["legal_entity"] = ""
    return t_df


def run_rrn_reconciliation(pl_our_raw: pl.DataFrame, pl_bank_raw: pl.DataFrame, cfg: dict, epos_registry: pd.DataFrame | None = None) -> dict:
    """Run RRN reconciliation using supplied data/configuration.

    ``epos_registry`` is the preferred dependency-injection path. During the
    Streamlit migration, omitting it temporarily falls back to the legacy DB
    provider so the current UI keeps working. The fallback is intentionally
    isolated here and will be removed once the page is moved to the API layer.
    """
    if epos_registry is None:
        from utils.db_manager import get_epos_registry
        epos_registry = get_epos_registry()

    our_cols = list(dict.fromkeys([c for c in [cfg["our_date"], cfg["our_rrn"], cfg["our_amt"], cfg["our_status"]] if c]))
    bank_cols = list(dict.fromkeys([c for c in [cfg["bank_date"], cfg["bank_rrn"], cfg["bank_amt"], cfg["bank_tid"], cfg["bank_status"]] if c]))
    data_quality = {
        "our": _source_quality(pl_our_raw, cfg["our_date"], cfg["our_rrn"], cfg.get("our_amt")),
        "bank": _source_quality(pl_bank_raw, cfg["bank_date"], cfg["bank_rrn"], cfg.get("bank_amt")),
    }

    pl_our = (
        pl_our_raw.select(our_cols)
        .with_row_index("_our_source_idx")
        .rename({cfg["our_date"]: "date", cfg["our_rrn"]: "RRN"})
        .with_columns(pl.lit(True).alias("_our_present"))
    )
    pl_bank = (
        pl_bank_raw.select(bank_cols)
        .with_row_index("_bank_source_idx")
        .rename({cfg["bank_date"]: "date", cfg["bank_rrn"]: "RRN"})
        .with_columns(pl.lit(True).alias("_bank_present"))
    )
    if cfg["our_amt"]: pl_our = pl_our.rename({cfg["our_amt"]: "amount"})
    if cfg["our_status"]: pl_our = pl_our.rename({cfg["our_status"]: "status_our"})
    if cfg["bank_amt"]: pl_bank = pl_bank.rename({cfg["bank_amt"]: "amount"})
    if cfg["bank_status"]: pl_bank = pl_bank.rename({cfg["bank_status"]: "status_bank"})

    our_amount_expr = parse_amount_polars("amount") if cfg["our_amt"] else pl.lit(0.0)
    bank_amount_expr = parse_amount_polars("amount") if cfg["bank_amt"] else pl.lit(0.0)

    pl_our = pl_our.with_columns([
        clean_date_polars("date").alias("date"),
        our_amount_expr.alias("net_amount_our"),
        our_amount_expr.is_not_null().alias("_our_amount_valid"),
        clean_rrn_polars("RRN", "our").alias("RRN"),
    ])
    pl_bank = pl_bank.with_columns([
        clean_date_polars("date").alias("date"),
        bank_amount_expr.alias("raw_amount"),
        bank_amount_expr.is_not_null().alias("_bank_amount_valid"),
        clean_rrn_polars("RRN", "bank").alias("RRN"),
    ])

    if cfg["bank_tid"]:
        if cfg["bank_tid"] != "terminal_id":
            pl_bank = pl_bank.rename({cfg["bank_tid"]: "terminal_id"})
        pl_bank = pl_bank.with_columns(pl.col("terminal_id").cast(pl.Utf8, strict=False))

        epos_source = epos_registry.copy() if epos_registry is not None else None
        if epos_source is not None and not epos_source.empty and "is_active" in epos_source.columns:
            active_mask = epos_source["is_active"].map(
                lambda value: value in (True, 1, "1", "true", "True", "yes", "Yes", "да", "Да")
            )
            epos_source = epos_source[active_mask]

        if epos_source is not None and not epos_source.empty:
            required_epos = {"terminal_id", "legal_entity", "commission_pct"}
            missing_epos = required_epos.difference(epos_source.columns)
            if missing_epos:
                raise ValueError(f"EPOS registry is missing columns: {sorted(missing_epos)}")
            epos_columns = ["terminal_id", "legal_entity", "commission_pct"]
            for optional_col in ("merchant_id", "bank_acquirer"):
                if optional_col in epos_source.columns:
                    epos_columns.append(optional_col)
            pl_epos = pl.from_pandas(epos_source[epos_columns])
            pl_epos = pl_epos.with_columns([
                pl.col("terminal_id").cast(pl.Utf8, strict=False),
                pl.col("commission_pct").cast(pl.Float64, strict=False).fill_null(0.0),
            ])
            pl_bank = pl_bank.join(pl_epos, on="terminal_id", how="left")
            pl_bank = pl_bank.with_columns([
                pl.col("commission_pct").fill_null(0.0),
                pl.col("legal_entity").fill_null(""),
            ])
        else:
            pl_bank = pl_bank.with_columns([
                pl.lit(0.0).alias("commission_pct"),
                pl.lit("").alias("legal_entity"),
            ])

    pl_our = apply_reversals(pl_our, "status_our" if cfg["our_status"] else None, cfg["our_rev"], "net_amount_our", cfg["rev_words"])
    pl_bank = apply_reversals(pl_bank, "status_bank" if cfg["bank_status"] else None, cfg["bank_rev"], "raw_amount", cfg["rev_words"])

    deduct_comm = bool(cfg.get("deduct_commission", False))
    if "commission_pct" in pl_bank.columns:
        pl_bank = pl_bank.with_columns((pl.col("raw_amount") * (pl.col("commission_pct") / 100.0)).alias("commission_amount"))
        if deduct_comm:
            pl_bank = pl_bank.with_columns((pl.col("raw_amount") - pl.col("commission_amount")).alias("net_amount_bank"))
        else:
            pl_bank = pl_bank.with_columns(pl.col("raw_amount").alias("net_amount_bank"))
    else:
        pl_bank = pl_bank.with_columns([pl.lit(0.0).alias("commission_pct"), pl.lit(0.0).alias("commission_amount"), pl.col("raw_amount").alias("net_amount_bank")])

    dups_our_pl = pl_our.filter(pl.col("RRN").is_duplicated())
    dups_bank_pl = pl_bank.filter(pl.col("RRN").is_duplicated())
    if "первую" in cfg["dup_action"]:
        pl_our = pl_our.unique(subset=["RRN"], keep="first", maintain_order=True)
        pl_bank = pl_bank.unique(subset=["RRN"], keep="first", maintain_order=True)
    elif "последнюю" in cfg["dup_action"]:
        pl_our = pl_our.unique(subset=["RRN"], keep="last", maintain_order=True)
        pl_bank = pl_bank.unique(subset=["RRN"], keep="last", maintain_order=True)
    elif "Удалить все" in cfg["dup_action"]:
        pl_our = pl_our.filter(~pl.col("RRN").is_in(dups_our_pl["RRN"]))
        pl_bank = pl_bank.filter(~pl.col("RRN").is_in(dups_bank_pl["RRN"]))
    else:
        pl_our = _assign_duplicate_index(pl_our, "net_amount_our", "_our_source_idx")
        pl_bank = _assign_duplicate_index(pl_bank, "net_amount_bank", "_bank_source_idx")

    if "_dup_idx" in pl_our.columns:
        merged_pl = pl_our.join(pl_bank, on=["RRN", "_dup_idx"], how="full", coalesce=True, suffix="_bank")
    else:
        merged_pl = pl_our.join(pl_bank, on="RRN", how="full", coalesce=True, suffix="_bank")
    merged_pl = merged_pl.with_columns(pl.coalesce(["date", "date_bank"]).alias("date_unified"))
    merged_pl = merged_pl.with_columns([
        pl.col("date_unified").dt.strftime("%d.%m.%Y").fill_null("").alias("date_str"),
        pl.when(pl.col("_our_present").fill_null(False) & ~pl.col("_bank_present").fill_null(False)).then(pl.lit("left_only"))
        .when(~pl.col("_our_present").fill_null(False) & pl.col("_bank_present").fill_null(False)).then(pl.lit("right_only"))
        .otherwise(pl.lit("both")).alias("_merge")
    ]).with_row_index("_match_row_id")

    tolerance = max(0.0, float(cfg["tolerance"]))
    both_sides = pl.col("_merge") == "both"
    valid_amounts = (
        pl.col("_our_amount_valid").fill_null(False)
        & pl.col("_bank_amount_valid").fill_null(False)
    )
    amount_delta = pl.col("net_amount_bank") - pl.col("net_amount_our")
    amt_mismatches_pl = merged_pl.filter(
        both_sides
        & (
            ~valid_amounts
            | (valid_amounts & (amount_delta.abs() > tolerance))
        )
    )
    only_our = merged_pl.filter(pl.col("_merge") == "left_only").to_pandas()
    only_bank = merged_pl.filter(pl.col("_merge") == "right_only").to_pandas()
    amt_mismatches = amt_mismatches_pl.to_pandas()
    merged = merged_pl.to_pandas()

    comm_only_diff_count = 0
    if not amt_mismatches.empty:
        our_valid = amt_mismatches["_our_amount_valid"].fillna(False).astype(bool)
        bank_valid = amt_mismatches["_bank_amount_valid"].fillna(False).astype(bool)
        both_valid = our_valid & bank_valid

        amt_mismatches["Δ сумма"] = np.where(
            both_valid,
            amt_mismatches["net_amount_bank"] - amt_mismatches["net_amount_our"],
            np.nan,
        )
        amt_mismatches["amount_issue"] = np.select(
            [
                ~our_valid & ~bank_valid,
                ~our_valid,
                ~bank_valid,
            ],
            [
                "Невалидная сумма с обеих сторон",
                "Невалидная сумма у нас",
                "Невалидная сумма в банке",
            ],
            default="Расхождение суммы",
        )

        if "raw_amount" in amt_mismatches.columns:
            amt_mismatches["raw_delta"] = np.where(
                both_valid,
                amt_mismatches["raw_amount"] - amt_mismatches["net_amount_our"],
                np.nan,
            )
            comm_only_diff_count = int((
                both_valid
                & (amt_mismatches["raw_delta"].abs() <= tolerance)
                & (amt_mismatches["Δ сумма"].abs() > tolerance)
            ).sum())

    unbound_count = 0
    if cfg["unbind_mismatches"] and not amt_mismatches.empty:
        # Unbind exactly the mismatching joined rows, not every row sharing the
        # same RRN. This matters when the same RRN occurs more than once.
        mismatched_row_ids = set(amt_mismatches["_match_row_id"].dropna().astype(int).tolist())
        unbound_count = len(mismatched_row_ids)

        our_part = amt_mismatches.copy()
        for col in ["date_bank", "net_amount_bank", "raw_amount", "status_bank", "terminal_id", "commission_pct", "commission_amount", "legal_entity"]:
            if col in our_part.columns:
                our_part[col] = np.nan
        our_part["_merge"] = "left_only"

        bank_part = amt_mismatches.copy()
        for col in ["date", "net_amount_our", "status_our"]:
            if col in bank_part.columns:
                bank_part[col] = np.nan
        bank_part["date_unified"] = bank_part["date_bank"]
        bank_part["_merge"] = "right_only"

        merged = merged[~merged["_match_row_id"].isin(mismatched_row_ids)]
        merged = pd.concat([merged, our_part, bank_part], ignore_index=True)
        only_our = pd.concat([only_our, our_part], ignore_index=True)
        only_bank = pd.concat([only_bank, bank_part], ignore_index=True)
        amt_mismatches = pd.DataFrame(columns=amt_mismatches.columns)

    if "date_str" not in only_our.columns:
        only_our["date_str"] = pd.to_datetime(only_our["date_unified"], errors="coerce").dt.strftime("%d.%m.%Y").fillna("")
    if "date_str" not in only_bank.columns:
        only_bank["date_str"] = pd.to_datetime(only_bank["date_unified"], errors="coerce").dt.strftime("%d.%m.%Y").fillna("")
    only_our.insert(0, "✅", True)
    only_bank.insert(0, "✅", True)
    only_our["📝 Причина"] = ""
    only_bank["📝 Причина"] = ""

    # Empty RRN values use an internal non-matching sentinel during the join.
    # Never expose that implementation detail to users.
    for frame in (only_our, only_bank):
        if "RRN" in frame.columns:
            empty_rrn_mask = frame["RRN"].astype(str).str.startswith("_EMPTY_")
            frame.loc[empty_rrn_mask, "RRN"] = ""
            frame.loc[empty_rrn_mask, "📝 Причина"] = "Пустой RRN"

    summary = date_summary(pl_our, pl_bank)
    tot_our_raw = float(summary["Сумма_у_нас"].sum())
    tot_bank_raw = float(summary["Сумма_в_банке"].sum())
    summary["date"] = summary["date"].apply(
        lambda x: x.strftime("%d.%m.%Y")
        if hasattr(x, "strftime") and pd.notnull(x)
        else (str(x) if pd.notnull(x) and x else "Дата не распознана")
    )
    total_row = pd.DataFrame([{
        "date": "📊 ИТОГО (исходно)", "Кол_во_у_нас": summary["Кол_во_у_нас"].sum(), "Кол_во_в_банке": summary["Кол_во_в_банке"].sum(),
        "Δ кол-во": summary["Δ кол-во"].sum(), "Сумма_у_нас": tot_our_raw, "Сумма_в_банке": tot_bank_raw, "Δ суммы": tot_bank_raw - tot_our_raw,
    }])
    summary = pd.concat([summary, total_row], ignore_index=True)

    terminal_summary_list = []
    total_commission = 0.0
    effective_commission_rate = 0.0
    detected_months = []
    if "date" in pl_bank.columns:
        dates_series = pl_bank.select(pl.col("date").dt.strftime("%Y-%m").drop_nulls()).to_series().to_list()
        detected_months = sorted(list(set(dates_series)), reverse=True)
    if "terminal_id" in pl_bank.columns:
        t_df = terminal_summary(pl_bank, "terminal_id")
        if not t_df.empty:
            total_commission = float(t_df["commission_amount"].sum())
            total_volume = float(t_df["total_volume"].sum())
            effective_commission_rate = (total_commission / total_volume * 100.0) if total_volume else 0.0
            terminal_summary_list = t_df.to_dict(orient="records")

    return {
        "summary": summary,
        "only_our": only_our,
        "only_bank": only_bank,
        "amt_mismatches": amt_mismatches,
        "dups_our": dups_our_pl.to_pandas(),
        "dups_bank": dups_bank_pl.to_pandas(),
        "dup_our_c": dups_our_pl.height,
        "dup_bank_c": dups_bank_pl.height,
        "matched_count": merged_pl.filter(pl.col("_merge") == "both").height - unbound_count,
        "mismatch_count": 0 if cfg["unbind_mismatches"] else amt_mismatches_pl.height,
        "comm_only_diff_count": comm_only_diff_count,
        "deduct_commission": deduct_comm,
        "terminal_summary": terminal_summary_list,
        "total_commission": total_commission,
        "effective_commission_rate": effective_commission_rate,
        "data_quality": data_quality,
        "detected_months": detected_months,
        "merged": merged,
        "dup_action": cfg["dup_action"],
    }
