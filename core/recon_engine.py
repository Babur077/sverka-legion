import functools

import polars as pl
import pandas as pd
import numpy as np
from core.parsers import clean_amount_polars, clean_date_polars, clean_rrn_polars
from utils.db_manager import get_epos_registry

def apply_reversals(df: pl.DataFrame, status_col: str, action: str, amt_col: str, rev_words: list) -> pl.DataFrame:
    if not status_col or status_col not in df.columns or not rev_words:
        return df

    status_norm = pl.col(status_col).cast(pl.Utf8).str.to_lowercase().str.strip_chars()

    # ВАЖНО: маркеры возврата матчатся по ВХОЖДЕНИЮ подстроки (а не по точному
    # совпадению всей строки статуса), как и подсказывает UI ("Маркеры возврата
    # ... через запятую"). Раньше здесь стояло is_in(rev_words), из-за чего статус
    # вида "REFUND - client request" не распознавался как возврат, хотя
    # find_offsetting_rrns_by_status() на странице сверки уже искал именно по
    # вхождению — из-за расхождения возвраты могли не гаситься в расчёте сумм.
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
        return df.with_columns(
            pl.when(rev_mask).then(-pl.col(amt_col).abs()).otherwise(pl.col(amt_col)).alias(amt_col)
        )
    return df

def date_summary(dfo, dfb):
    if "net_amount_our" not in dfo.columns:
        dfo = dfo.assign(net_amount_our=0.0)
    if "net_amount_bank" not in dfb.columns:
        dfb = dfb.assign(net_amount_bank=0.0)
    so = dfo.groupby("date", as_index=False).agg(Кол_во_у_нас=("RRN","count"), Сумма_у_нас=("net_amount_our","sum")) if not dfo.empty else pd.DataFrame(columns=["date", "Кол_во_у_нас", "Сумма_у_нас"])
    sb = dfb.groupby("date", as_index=False).agg(Кол_во_в_банке=("RRN","count"), Сумма_в_банке=("net_amount_bank","sum")) if not dfb.empty else pd.DataFrame(columns=["date", "Кол_во_в_банке", "Сумма_в_банке"])
    s = pd.merge(so, sb, on="date", how="outer").fillna(0)
    for col in ["Сумма_в_банке", "Сумма_у_нас"]:
        if col not in s.columns: s[col] = 0.0
    for col in ["Кол_во_в_банке", "Кол_во_у_нас"]:
        if col not in s.columns: s[col] = 0
    s["Δ суммы"] = s["Сумма_в_банке"] - s["Сумма_у_нас"]
    s["Δ кол-во"] = s["Кол_во_в_банке"] - s["Кол_во_у_нас"]
    return s.sort_values("date", ascending=False).reset_index(drop=True)

def run_rrn_reconciliation(pl_our_raw: pl.DataFrame, pl_bank_raw: pl.DataFrame, cfg: dict) -> dict:
    # 1. Выбор колонок
    our_cols = list(dict.fromkeys([c for c in [cfg["our_date"], cfg["our_rrn"], cfg["our_amt"], cfg["our_status"]] if c]))
    bank_cols = list(dict.fromkeys([c for c in [cfg["bank_date"], cfg["bank_rrn"], cfg["bank_amt"], cfg["bank_tid"], cfg["bank_status"]] if c]))
    
    pl_our = pl_our_raw.select(our_cols).rename({cfg["our_date"]: "date", cfg["our_rrn"]: "RRN"})
    pl_bank = pl_bank_raw.select(bank_cols).rename({cfg["bank_date"]: "date", cfg["bank_rrn"]: "RRN"})
    
    if cfg["our_amt"]: pl_our = pl_our.rename({cfg["our_amt"]: "amount"})
    if cfg["our_status"]: pl_our = pl_our.rename({cfg["our_status"]: "status_our"})
    if cfg["bank_amt"]: pl_bank = pl_bank.rename({cfg["bank_amt"]: "amount"})
    if cfg["bank_status"]: pl_bank = pl_bank.rename({cfg["bank_status"]: "status_bank"})
    
    # 2. Очистка
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
    
    # 3. Интеграция с EPOS
    if cfg["bank_tid"]:
        df_epos = get_epos_registry()
        pl_epos = pl.from_pandas(df_epos).select(["terminal_id", "legal_entity", "commission_pct"])
        if cfg["bank_tid"] != "terminal_id":
            pl_bank = pl_bank.rename({cfg["bank_tid"]: "terminal_id"})
        pl_bank = pl_bank.with_columns(pl.col("terminal_id").cast(pl.Utf8))
        pl_epos = pl_epos.with_columns([pl.col("terminal_id").cast(pl.Utf8), pl.col("commission_pct").cast(pl.Float64)])
        pl_bank = pl_bank.join(pl_epos, on="terminal_id", how="left")
        pl_bank = pl_bank.with_columns(pl.col("commission_pct").fill_null(0.0))
    
    # 4. Возвраты
    pl_our = apply_reversals(pl_our, "status_our" if cfg["our_status"] else None, cfg["our_rev"], "net_amount_our", cfg["rev_words"])
    pl_bank = apply_reversals(pl_bank, "status_bank" if cfg["bank_status"] else None, cfg["bank_rev"], "raw_amount", cfg["rev_words"])
    
    if "commission_pct" in pl_bank.columns:
        pl_bank = pl_bank.with_columns((pl.col("raw_amount") - (pl.col("raw_amount") * (pl.col("commission_pct") / 100.0))).alias("net_amount_bank"))
    else:
        pl_bank = pl_bank.with_columns(pl.col("raw_amount").alias("net_amount_bank"))

    # 5. Дубликаты
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

    # 6. Слияние
    merged_pl = pl_our.join(pl_bank, on="RRN", how="full", coalesce=True, suffix="_bank")
    merged_pl = merged_pl.with_columns(pl.coalesce(["date", "date_bank"]).alias("date_unified"))
    merged_pl = merged_pl.with_columns(
        pl.when(pl.col("date").is_not_null() & pl.col("date_bank").is_null()).then(pl.lit("left_only"))
        .when(pl.col("date").is_null() & pl.col("date_bank").is_not_null()).then(pl.lit("right_only"))
        .otherwise(pl.lit("both")).alias("_merge")
    )

    tolerance = cfg["tolerance"]
    amt_mismatches_pl = merged_pl.filter((pl.col("_merge") == "both") & ((pl.col("net_amount_bank").fill_null(0.0) - pl.col("net_amount_our").fill_null(0.0)).abs() > tolerance))
    
    only_our = merged_pl.filter(pl.col("_merge") == "left_only").to_pandas()
    only_bank = merged_pl.filter(pl.col("_merge") == "right_only").to_pandas()
    amt_mismatches = amt_mismatches_pl.to_pandas()
    merged = merged_pl.to_pandas()
    
    if not amt_mismatches.empty:
        amt_mismatches["Δ сумма"] = amt_mismatches["net_amount_bank"].fillna(0.0) - amt_mismatches["net_amount_our"].fillna(0.0)

    # 7. Разрыв связей
    unbound_count = 0
    if cfg["unbind_mismatches"] and not amt_mismatches.empty:
        mismatched_rrns_set = set(amt_mismatches['RRN'].dropna().unique())
        unbound_count = len(mismatched_rrns_set)
        
        our_part = amt_mismatches.copy()
        for col in our_part.columns:
            if col not in {'date', 'net_amount_our', 'status_our', 'RRN', 'date_unified'}: our_part[col] = np.nan
        our_part['_merge'] = 'left_only'
        
        bank_part = amt_mismatches.copy()
        for col in bank_part.columns:
            if col not in {'date_bank', 'net_amount_bank', 'status_bank', 'RRN', 'date_unified'}: bank_part[col] = np.nan
        bank_part['date_unified'] = bank_part['date_bank']
        bank_part['_merge'] = 'right_only'
        
        merged = merged[~((merged['_merge'] == 'both') & (merged['RRN'].isin(mismatched_rrns_set)))]
        merged = pd.concat([merged, our_part, bank_part], ignore_index=True)
        only_our = pd.concat([only_our, our_part], ignore_index=True)
        only_bank = pd.concat([only_bank, bank_part], ignore_index=True)
        amt_mismatches = pd.DataFrame(columns=amt_mismatches.columns)

    only_our["date_str"] = pd.to_datetime(only_our["date_unified"], errors="coerce").dt.strftime("%d.%m.%Y").fillna("")
    only_bank["date_str"] = pd.to_datetime(only_bank["date_unified"], errors="coerce").dt.strftime("%d.%m.%Y").fillna("")

    only_our.insert(0, "✅", True)
    only_bank.insert(0, "✅", True)
    only_our["📝 Причина"] = ""
    only_bank["📝 Причина"] = ""

    summary = date_summary(pl_our.to_pandas(), pl_bank.to_pandas())
    tot_our_raw = float(summary["Сумма_у_нас"].sum())
    tot_bank_raw = float(summary["Сумма_в_банке"].sum())
    summary["date"] = summary["date"].apply(lambda x: x.strftime("%d.%m.%Y") if pd.notnull(x) and x else "")
    
    total_row = pd.DataFrame([{
        "date": "📊 ИТОГО (исходно)",
        "Кол_во_у_нас": summary["Кол_во_у_нас"].sum(),
        "Кол_во_в_банке": summary["Кол_во_в_банке"].sum(),
        "Δ кол-во": summary["Δ кол-во"].sum(),
        "Сумма_у_нас": tot_our_raw,
        "Сумма_в_банке": tot_bank_raw,
        "Δ суммы": tot_bank_raw - tot_our_raw,
    }])
    summary = pd.concat([summary, total_row], ignore_index=True)

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
        "merged": merged,
        "dup_action": cfg["dup_action"],
    }
