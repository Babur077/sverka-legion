import functools

import polars as pl
import pandas as pd
import numpy as np
from core.parsers import clean_amount_polars, clean_date_polars, clean_rrn_polars


def apply_reversals(df: pl.DataFrame, status_col: str, action: str, amt_col: str, rev_words: list) -> pl.DataFrame:
    if not status_col or status_col not in df.columns or not rev_words:
        return df
    status_norm = pl.col(status_col).cast(pl.Utf8).str.to_lowercase().str.strip_chars()
    rev_mask = functools.reduce(
        lambda acc, w: acc | status_norm.str.contains(w, literal=True),
        rev_words[1:],
        status_norm.str.contains(rev_words[0], literal=True),
    )
    if "💥" in action:
        bad_rrns = df.filter(rev_mask).select("RRN").unique()
        return df.join(bad_rrns, on="RRN", how="anti")
    elif "🗑" in action:
        return df.filter(~rev_mask)
    elif "➖" in action:
        return df.with_columns(pl.when(rev_mask).then(-pl.col(amt_col).abs()).otherwise(pl.col(amt_col)).alias(amt_col))
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
    has_comm = "commission_pct" in pl_bank.columns
    agg_exprs = [pl.len().alias("tx_count"), pl.col(amt_col).sum().alias("total_volume")]
    if has_comm:
        agg_exprs.append(pl.col("commission_pct").first().alias("commission_pct"))
        if "commission_amount" in pl_bank.columns:
            agg_exprs.append(pl.col("commission_amount").sum().alias("commission_amount"))
    if has_legal:
        agg_exprs.append(pl.col("legal_entity").first().alias("legal_entity"))
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
    pl_our = pl_our_raw.select(our_cols).rename({cfg["our_date"]: "date", cfg["our_rrn"]: "RRN"})
    pl_bank = pl_bank_raw.select(bank_cols).rename({cfg["bank_date"]: "date", cfg["bank_rrn"]: "RRN"})
    if cfg["our_amt"]: pl_our = pl_our.rename({cfg["our_amt"]: "amount"})
    if cfg["our_status"]: pl_our = pl_our.rename({cfg["our_status"]: "status_our"})
    if cfg["bank_amt"]: pl_bank = pl_bank.rename({cfg["bank_amt"]: "amount"})
    if cfg["bank_status"]: pl_bank = pl_bank.rename({cfg["bank_status"]: "status_bank"})

    pl_our = pl_our.with_columns([
        clean_date_polars("date").alias("date"),
        (clean_amount_polars("amount") if cfg["our_amt"] else pl.lit(0.0)).alias("net_amount_our"),
        clean_rrn_polars("RRN", "our").alias("RRN")
    ])
    pl_bank = pl_bank.with_columns([
        clean_date_polars("date").alias("date"),
        (clean_amount_polars("amount").alias("raw_amount") if cfg["bank_amt"] else pl.lit(0.0).alias("raw_amount")),
        clean_rrn_polars("RRN", "bank").alias("RRN")
    ])

    if cfg["bank_tid"]:
        if epos_registry is not None and not epos_registry.empty:
            required_epos = {"terminal_id", "legal_entity", "commission_pct"}
            missing_epos = required_epos.difference(epos_registry.columns)
            if missing_epos:
                raise ValueError(f"EPOS registry is missing columns: {sorted(missing_epos)}")
            pl_epos = pl.from_pandas(epos_registry[["terminal_id", "legal_entity", "commission_pct"]])
            if cfg["bank_tid"] != "terminal_id": pl_bank = pl_bank.rename({cfg["bank_tid"]: "terminal_id"})
            pl_bank = pl_bank.with_columns(pl.col("terminal_id").cast(pl.Utf8))
            pl_epos = pl_epos.with_columns([pl.col("terminal_id").cast(pl.Utf8), pl.col("commission_pct").cast(pl.Float64)])
            pl_bank = pl_bank.join(pl_epos, on="terminal_id", how="left")
            pl_bank = pl_bank.with_columns(pl.col("commission_pct").fill_null(0.0))
        else:
            if cfg["bank_tid"] != "terminal_id": pl_bank = pl_bank.rename({cfg["bank_tid"]: "terminal_id"})
            pl_bank = pl_bank.with_columns([pl.col("terminal_id").cast(pl.Utf8), pl.lit(0.0).alias("commission_pct"), pl.lit("").alias("legal_entity")])

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
        pl_our = pl_our.unique(subset=["RRN"], keep="first")
        pl_bank = pl_bank.unique(subset=["RRN"], keep="first")
    elif "последнюю" in cfg["dup_action"]:
        pl_our = pl_our.unique(subset=["RRN"], keep="last")
        pl_bank = pl_bank.unique(subset=["RRN"], keep="last")
    elif "Удалить все" in cfg["dup_action"]:
        pl_our = pl_our.filter(~pl.col("RRN").is_in(dups_our_pl["RRN"]))
        pl_bank = pl_bank.filter(~pl.col("RRN").is_in(dups_bank_pl["RRN"]))
    else:
        pl_our = pl_our.with_columns(pl.col("RRN").cum_count().over("RRN").alias("_dup_idx"))
        pl_bank = pl_bank.with_columns(pl.col("RRN").cum_count().over("RRN").alias("_dup_idx"))

    if "_dup_idx" in pl_our.columns:
        merged_pl = pl_our.join(pl_bank, on=["RRN", "_dup_idx"], how="full", coalesce=True, suffix="_bank")
    else:
        merged_pl = pl_our.join(pl_bank, on="RRN", how="full", coalesce=True, suffix="_bank")
    merged_pl = merged_pl.with_columns(pl.coalesce(["date", "date_bank"]).alias("date_unified"))
    merged_pl = merged_pl.with_columns([
        pl.col("date_unified").dt.strftime("%d.%m.%Y").fill_null("").alias("date_str"),
        pl.when(pl.col("date").is_not_null() & pl.col("date_bank").is_null()).then(pl.lit("left_only"))
        .when(pl.col("date").is_null() & pl.col("date_bank").is_not_null()).then(pl.lit("right_only"))
        .otherwise(pl.lit("both")).alias("_merge")
    ])

    tolerance = cfg["tolerance"]
    amt_mismatches_pl = merged_pl.filter((pl.col("_merge") == "both") & ((pl.col("net_amount_bank").fill_null(0.0) - pl.col("net_amount_our").fill_null(0.0)).abs() > tolerance))
    only_our = merged_pl.filter(pl.col("_merge") == "left_only").to_pandas()
    only_bank = merged_pl.filter(pl.col("_merge") == "right_only").to_pandas()
    amt_mismatches = amt_mismatches_pl.to_pandas()
    merged = merged_pl.to_pandas()

    comm_only_diff_count = 0
    if not amt_mismatches.empty:
        amt_mismatches["Δ сумма"] = amt_mismatches["net_amount_bank"].fillna(0.0) - amt_mismatches["net_amount_our"].fillna(0.0)
        if "raw_amount" in amt_mismatches.columns:
            amt_mismatches["raw_delta"] = amt_mismatches["raw_amount"].fillna(0.0) - amt_mismatches["net_amount_our"].fillna(0.0)
            comm_only_diff_count = int(((amt_mismatches["raw_delta"].abs() <= tolerance) & (amt_mismatches["Δ сумма"].abs() > tolerance)).sum())

    unbound_count = 0
    if cfg["unbind_mismatches"] and not amt_mismatches.empty:
        mismatched_rrns_set = set(amt_mismatches['RRN'].dropna().unique())
        unbound_count = len(mismatched_rrns_set)
        our_part = amt_mismatches.copy()
        for col in our_part.columns:
            if col not in {'date', 'net_amount_our', 'status_our', 'RRN', 'date_unified', 'date_str'}: our_part[col] = np.nan
        our_part['_merge'] = 'left_only'
        bank_part = amt_mismatches.copy()
        for col in bank_part.columns:
            if col not in {'date_bank', 'net_amount_bank', 'status_bank', 'RRN', 'date_unified', 'date_str'}: bank_part[col] = np.nan
        bank_part['date_unified'] = bank_part['date_bank']
        bank_part['_merge'] = 'right_only'
        merged = merged[~((merged['_merge'] == 'both') & (merged['RRN'].isin(mismatched_rrns_set)))]
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

    summary = date_summary(pl_our, pl_bank)
    tot_our_raw = float(summary["Сумма_у_нас"].sum())
    tot_bank_raw = float(summary["Сумма_в_банке"].sum())
    summary["date"] = summary["date"].apply(lambda x: x.strftime("%d.%m.%Y") if hasattr(x, "strftime") and pd.notnull(x) else (str(x) if pd.notnull(x) and x else ""))
    total_row = pd.DataFrame([{
        "date": "📊 ИТОГО (исходно)", "Кол_во_у_нас": summary["Кол_во_у_нас"].sum(), "Кол_во_в_банке": summary["Кол_во_в_банке"].sum(),
        "Δ кол-во": summary["Δ кол-во"].sum(), "Сумма_у_нас": tot_our_raw, "Сумма_в_банке": tot_bank_raw, "Δ суммы": tot_bank_raw - tot_our_raw,
    }])
    summary = pd.concat([summary, total_row], ignore_index=True)

    terminal_summary_list = []
    total_commission = 0.0
    detected_months = []
    if "date" in pl_bank.columns:
        dates_series = pl_bank.select(pl.col("date").dt.strftime("%Y-%m").drop_nulls()).to_series().to_list()
        detected_months = sorted(list(set(dates_series)), reverse=True)
    if "terminal_id" in pl_bank.columns:
        t_df = terminal_summary(pl_bank, "terminal_id")
        if not t_df.empty:
            total_commission = float(t_df["commission_amount"].sum())
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
        "detected_months": detected_months,
        "merged": merged,
        "dup_action": cfg["dup_action"],
    }
