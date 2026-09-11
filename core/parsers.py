import io
import polars as pl
import pandas as pd

def load_file_polars(file_name: str, file_bytes: bytes, sheet_name=0) -> pl.DataFrame:
    if file_name.lower().endswith((".xlsx", ".xls")):
        return pl.read_excel(io.BytesIO(file_bytes), sheet_id=1 if sheet_name in (0, None) else sheet_name + 1, engine="calamine")
    else:
        try:
            return pl.read_csv(io.BytesIO(file_bytes), separator=";", ignore_errors=True)
        except:
            return pl.read_csv(io.BytesIO(file_bytes), separator=",", ignore_errors=True)

def clean_amount_polars(col_name: str) -> pl.Expr:
    c = pl.col(col_name).cast(pl.Utf8)
    c = c.str.replace_all(r"[^\d\.,\-]", "")
    c = pl.when(c.str.contains(",") & ~c.str.contains(r"\.")).then(c.str.replace(",", ".")).otherwise(c)
    c = pl.when(c.str.contains(",") & c.str.contains(r"\.")).then(c.str.replace_all(",", "")).otherwise(c)
    return c.cast(pl.Float64, strict=False).fill_null(0.0)

def clean_date_polars(col_name: str) -> pl.Expr:
    c = pl.col(col_name).cast(pl.Utf8).str.strip_chars()
    return pl.coalesce([
        c.str.strptime(pl.Datetime, "%Y-%m-%d %H:%M:%S%.f", strict=False).cast(pl.Date),
        c.str.strptime(pl.Datetime, "%Y-%m-%d %H:%M:%S", strict=False).cast(pl.Date),
        c.str.strptime(pl.Date, "%Y-%m-%d", strict=False),
        c.str.strptime(pl.Date, "%d.%m.%Y", strict=False),
        c.str.strptime(pl.Datetime, "%d.%m.%Y %H:%M:%S", strict=False).cast(pl.Date),
        c.str.strptime(pl.Date, "%d/%m/%Y", strict=False),
        c.str.strptime(pl.Date, "%d-%m-%Y", strict=False),
    ])

def clean_rrn_polars(col_name: str, prefix: str) -> pl.Expr:
    row_index_str = pl.int_range(0, pl.len()).cast(pl.Utf8)
    empty_filler = pl.lit(f"_EMPTY_{prefix.upper()}_") + row_index_str
    normalized = pl.col(col_name).cast(pl.Utf8).str.strip_chars().str.to_uppercase().str.replace(r"\.0$", "")
    return pl.when(normalized.is_in(["", "NAN", "NONE", "NAT"]) | normalized.is_null()).then(empty_filler).otherwise(normalized)

def guess_col(df, keywords: list):
    if df is None or getattr(df, "is_empty", lambda: getattr(df, "empty", True))(): return None
    for col in df.columns:
        if any(kw in str(col).lower().strip() for kw in keywords): return col
    return None