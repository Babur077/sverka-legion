import io
import polars as pl
import pandas as pd

def load_file_polars(file_name: str, file_bytes: bytes, sheet_name=0) -> pl.DataFrame:
    if file_name.lower().endswith((".xlsx", ".xls")):
        sheet_id = 1 if sheet_name in (0, None) else sheet_name + 1
        try:
            return pl.read_excel(io.BytesIO(file_bytes), sheet_id=sheet_id, engine="calamine")
        except Exception:
            try:
                return pl.read_excel(io.BytesIO(file_bytes), sheet_id=sheet_id, engine="fastexcel")
            except Exception:
                try:
                    return pl.read_excel(io.BytesIO(file_bytes), sheet_id=sheet_id)
                except Exception:
                    # В крайнем случае читаем через pandas и конвертируем в polars
                    pdf = pd.read_excel(io.BytesIO(file_bytes), sheet_name=sheet_name or 0)
                    return pl.from_pandas(pdf)
    else:
        try:
            return pl.read_csv(io.BytesIO(file_bytes), separator=";", ignore_errors=True)
        except Exception:
            return pl.read_csv(io.BytesIO(file_bytes), separator=",", ignore_errors=True)

def clean_amount_polars(col_name: str) -> pl.Expr:
    c = pl.col(col_name).cast(pl.Utf8)
    c = c.str.replace_all(r"[^\d\.,\-]", "")

    has_both = c.str.contains(",") & c.str.contains(r"\.")
    # Если есть и запятые, и точка:
    # 1. Европейский формат: последняя запятая идет после последней точки (напр. "1.234,56" или "1.234.567,89")
    # -> убираем точки (разделители тысяч), а запятую меняем на точку
    is_euro_both = has_both & c.str.contains(r"\..*,[^\.]*$")
    # 2. Стандартный/US формат: последняя точка идет после последней запятой (напр. "1,234.56" или "1,234,567.89")
    # -> убираем запятые
    is_std_both = has_both & c.str.contains(r",.*\.[^,]*$")

    c = pl.when(is_euro_both).then(c.str.replace_all(r"\.", "").str.replace(",", ".")).otherwise(c)
    c = pl.when(is_std_both).then(c.str.replace_all(",", "")).otherwise(c)

    # Запятая с 1-2 цифрами после и без точки — десятичный разделитель (напр. "1234,56").
    is_decimal_comma = c.str.contains(r"^-?\d+,\d{1,2}$")
    # Запятая(-ые), разбивающая(-ие) число на группы РОВНО по 3 цифры, без точки —
    # разделитель тысяч (напр. "1,234" или "12,345,678"), а не десятичная дробь.
    is_thousands_comma = c.str.contains(r"^-?\d{1,3}(,\d{3})+$")

    c = pl.when(is_decimal_comma).then(c.str.replace(",", ".")).otherwise(c)
    c = pl.when(is_thousands_comma).then(c.str.replace_all(",", "")).otherwise(c)

    # Несколько точек без запятых как разделители тысяч: "1.234.567"
    is_thousands_dots = c.str.contains(r"^-?\d{1,3}(\.\d{3})+$")
    c = pl.when(is_thousands_dots).then(c.str.replace_all(r"\.", "")).otherwise(c)

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
