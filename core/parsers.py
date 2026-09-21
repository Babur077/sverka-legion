import io
from typing import Union, Optional
import polars as pl
import pandas as pd

def load_file_polars(
    first_arg,
    second_arg=None,
    sheet_name=0,
    header_row: int = 1,
) -> pl.DataFrame:
    """
    Универсальный загрузчик файлов в Polars DataFrame.
    Поддерживает вызовы:
      load_file_polars(filename, file_bytes)
      load_file_polars(file_bytes, filename)
      load_file_polars(file_path_str)

    Дополнительно:
      sheet_name — индекс (0-based) или имя листа Excel;
      header_row — 1-based номер строки с заголовками.
    """
    if isinstance(first_arg, (bytes, bytearray)):
        file_bytes = bytes(first_arg)
        file_name = str(second_arg or "data.xlsx")
    elif isinstance(second_arg, (bytes, bytearray)):
        file_name = str(first_arg or "data.xlsx")
        file_bytes = bytes(second_arg)
    elif isinstance(first_arg, str) and second_arg is None:
        file_name = first_arg
        with open(first_arg, "rb") as f:
            file_bytes = f.read()
    else:
        file_name = str(first_arg or "data.xlsx")
        file_bytes = bytes(second_arg or b"")

    try:
        header_row = max(1, min(int(header_row or 1), 200))
    except (TypeError, ValueError):
        header_row = 1

    if file_name.lower().endswith((".xlsx", ".xls")):
        # For non-default source options pandas gives the most predictable
        # behavior across engines (named sheet + arbitrary header row).
        if header_row != 1 or sheet_name not in (0, None, "", "0"):
            pdf = pd.read_excel(
                io.BytesIO(file_bytes),
                sheet_name=sheet_name if sheet_name not in (None, "") else 0,
                header=header_row - 1,
            )
            if isinstance(pdf, dict):
                # Defensive fallback if a caller accidentally requested all sheets.
                pdf = next(iter(pdf.values()), pd.DataFrame())
            return pl.from_pandas(pdf)

        sheet_id = 1
        try:
            return pl.read_excel(io.BytesIO(file_bytes), sheet_id=sheet_id, engine="calamine")
        except Exception:
            try:
                return pl.read_excel(io.BytesIO(file_bytes), sheet_id=sheet_id, engine="fastexcel")
            except Exception:
                try:
                    return pl.read_excel(io.BytesIO(file_bytes), sheet_id=sheet_id)
                except Exception:
                    pdf = pd.read_excel(
                        io.BytesIO(file_bytes),
                        sheet_name=0,
                        header=0,
                    )
                    return pl.from_pandas(pdf)

    # CSV exports in finance commonly arrive with semicolon, comma or tab
    # delimiters. A wrong delimiter often parses "successfully" as one huge
    # column, so choose the successful parse with the most columns.
    candidates = []
    skip_rows = header_row - 1
    for separator in (";", ",", "\t"):
        try:
            frame = pl.read_csv(
                io.BytesIO(file_bytes),
                separator=separator,
                ignore_errors=True,
                skip_rows=skip_rows,
            )
            candidates.append(frame)
        except Exception:
            continue
    if not candidates:
        raise ValueError(f"Не удалось распознать CSV-файл: {file_name}")
    return max(candidates, key=lambda frame: frame.width)

# Синоним для совместимости с модульным API
parse_file_to_polars = load_file_polars


def _clean_amount_expr(col_name: str, *, fill_invalid: bool = True) -> pl.Expr:
    """Normalize common financial amount formats.

    Legacy callers keep receiving 0.0 for invalid values. Reconciliation
    logic can request a nullable expression via parse_amount_polars so
    malformed source amounts remain visible instead of silently becoming zero.
    """
    c = pl.col(col_name).cast(pl.Utf8, strict=False).fill_null("").str.strip_chars()
    c = c.str.replace_all(r"[^\d\.,\-]", "")

    has_both = c.str.contains(",") & c.str.contains(r"\.")
    is_euro_both = has_both & c.str.contains(r"\..*,[^\.]*$")
    is_std_both = has_both & c.str.contains(r",.*\.[^,]*$")

    c = pl.when(is_euro_both).then(c.str.replace_all(r"\.", "").str.replace(",", ".")).otherwise(c)
    c = pl.when(is_std_both).then(c.str.replace_all(",", "")).otherwise(c)

    is_decimal_comma = c.str.contains(r"^-?\d+,\d{1,2}$")
    is_thousands_comma = c.str.contains(r"^-?\d{1,3}(,\d{3})+$")
    c = pl.when(is_decimal_comma).then(c.str.replace(",", ".")).otherwise(c)
    c = pl.when(is_thousands_comma).then(c.str.replace_all(",", "")).otherwise(c)

    is_thousands_dots = c.str.contains(r"^-?\d{1,3}(\.\d{3})+$")
    c = pl.when(is_thousands_dots).then(c.str.replace_all(r"\.", "")).otherwise(c)

    parsed = c.cast(pl.Float64, strict=False)
    return parsed.fill_null(0.0) if fill_invalid else parsed
def clean_amount_polars(first_arg, col_name: Optional[str] = None):
    """
    Поддерживает:
      clean_amount_polars(col_name) -> pl.Expr
      clean_amount_polars(df, col_name) -> pl.DataFrame
    """
    if isinstance(first_arg, (pl.DataFrame, pl.LazyFrame)):
        if col_name and col_name in first_arg.columns:
            return first_arg.with_columns(_clean_amount_expr(col_name).alias(col_name))
        return first_arg
    return _clean_amount_expr(str(first_arg))



def parse_amount_polars(col_name: str) -> pl.Expr:
    """Return normalized amount while preserving invalid/missing values as null."""
    return _clean_amount_expr(str(col_name), fill_invalid=False)

def _clean_date_expr(col_name: str) -> pl.Expr:
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


def clean_date_polars(first_arg, col_name: Optional[str] = None):
    """
    Поддерживает:
      clean_date_polars(col_name) -> pl.Expr
      clean_date_polars(df, col_name) -> pl.DataFrame
    """
    if isinstance(first_arg, (pl.DataFrame, pl.LazyFrame)):
        if col_name and col_name in first_arg.columns:
            return first_arg.with_columns(_clean_date_expr(col_name).alias(col_name))
        return first_arg
    return _clean_date_expr(str(first_arg))


def _clean_rrn_expr(col_name: str, prefix: str = "norm") -> pl.Expr:
    row_index_str = pl.int_range(0, pl.len()).cast(pl.Utf8)
    empty_filler = pl.lit(f"_EMPTY_{prefix.upper()}_") + row_index_str
    normalized = pl.col(col_name).cast(pl.Utf8).str.strip_chars().str.to_uppercase().str.replace(r"\.0$", "")
    return pl.when(normalized.is_in(["", "NAN", "NONE", "NAT"]) | normalized.is_null()).then(empty_filler).otherwise(normalized)


def clean_rrn_polars(first_arg, second_arg: str = "norm", prefix: str = "norm"):
    """
    Поддерживает:
      clean_rrn_polars(col_name, prefix) -> pl.Expr
      clean_rrn_polars(df, col_name, prefix="norm") -> pl.DataFrame
    """
    if isinstance(first_arg, (pl.DataFrame, pl.LazyFrame)):
        col_name = second_arg
        pref = prefix if prefix != "norm" else "norm"
        if col_name and col_name in first_arg.columns:
            return first_arg.with_columns(_clean_rrn_expr(col_name, pref).alias(col_name))
        return first_arg
    return _clean_rrn_expr(str(first_arg), prefix=str(second_arg or prefix))


def guess_col(df, keywords: list):
    if df is None or getattr(df, "is_empty", lambda: getattr(df, "empty", True))(): return None
    for col in df.columns:
        if any(kw in str(col).lower().strip() for kw in keywords): return col
    return None
