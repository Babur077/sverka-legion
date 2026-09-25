# ruff: noqa: BLE001, I001, F401, F541
import pandas as pd
from sqlalchemy import create_engine, text
import os

try:
    from .db_config import DATABASE_URL
except ImportError:
    from db_config import DATABASE_URL

engine = create_engine(DATABASE_URL)

def upload_file_to_db(file_name, table_name, use_cols):
    """Читает первый лист Excel и дописывает строки в конец таблицы"""
    if not os.path.exists(file_name):
        print(f"⚠️  Файл '{file_name}' не найден, пропускаем.")
        return

    print(f"\n📂 Читаем {file_name}...")

    try:
        df = pd.read_excel(file_name, sheet_name=0, dtype={'INN': str, 'ИНН': str})
    except Exception as e:
        print(f"❌ Не удалось прочитать файл {file_name}: {e}")
        return

    if df.empty:
        print(f"⚠️  Файл пустой, пропускаем.")
        return

    df.columns = [str(col).strip() for col in df.columns]

    missing_cols = [col for col in use_cols if col not in df.columns]
    if missing_cols:
        print(f"❌ Отсутствуют колонки: {missing_cols}")
        return

    df_filtered = df[use_cols].copy()

    # ── ОЧИСТКА ИНН ──
    if 'INN' in df_filtered.columns:
        df_filtered['INN'] = df_filtered['INN'].astype(str).str.strip()
        df_filtered['INN'] = df_filtered['INN'].str.replace(r'\.0$', '', regex=True)
        df_filtered['INN'] = df_filtered['INN'].replace(['nan', 'None', 'null', 'NaN', ''], '-')

    if 'Data' in df_filtered.columns:
        df_filtered['Data'] = pd.to_datetime(df_filtered['Data'], dayfirst=True, errors='coerce')

    # ── МЕСЯЦ И ГОД берём из КАЖДОЙ строки отдельно ──
    # Это позволяет загружать файлы сразу за несколько месяцев.
    if 'Data' in df_filtered.columns and df_filtered['Data'].notna().any():
        dates = pd.to_datetime(df_filtered['Data'], errors='coerce')
        df_filtered['period_month'] = dates.dt.month
        df_filtered['period_year']  = dates.dt.year
        # Строки без даты заполняем из ближайших соседей (ffill/bfill)
        df_filtered['period_month'] = df_filtered['period_month'].ffill().bfill().astype('Int64')
        df_filtered['period_year']  = df_filtered['period_year'].ffill().bfill().astype('Int64')
        months_loaded = sorted(
            df_filtered.groupby(['period_year', 'period_month']).size().index.tolist()
        )
        for y, m in months_loaded:
            print(f"📅 Найден период: {int(m):02d}.{int(y)}")
    else:
        # Если столбца Data нет — спросить у пользователя
        month = int(input("Введите номер месяца (1-12): "))
        year  = int(input("Введите год (например 2025): "))
        df_filtered['period_month'] = month
        df_filtered['period_year']  = year

    df_filtered.to_sql(table_name, engine, if_exists='append', index=False, chunksize=10000)
    print(f"✅ Добавлено {len(df_filtered)} строк в '{table_name}'!")


# --- ЗАПУСК ---
if __name__ == '__main__':
    print("🚀 Загрузка данных в базу...")
    print("Какой файл загружаем?")
    print("  1 — VBASE   (Продажи)")
    print("  2 — VBANK   (Оплаты)")
    print("  3 — VFAKTURA (Фактуры)")
    print("  4 — VIPP    (Партнёры)")
    print("  0 — Все четыре файла сразу")

    choice = input("\nВаш выбор: ").strip()

    if choice in ('1', '0'):
        upload_file_to_db("VBASE.xlsx",    "vbase",    ["Data", "Partner", "INN", "Service", "Status", "Sales", "Komissiya", "VID"])
    if choice in ('2', '0'):
        upload_file_to_db("VBANK.xlsx",    "vbank",    ["Data", "Partner", "INN", "Summ", "VID"])
    if choice in ('3', '0'):
        upload_file_to_db("VFAKTURA.xlsx", "vfaktura", ["Data", "Partner", "INN", "Summ", "VID"])
    if choice in ('4', '0'):
        upload_file_to_db("VIPP.xlsx",     "vipp",     ["№", "Partner", "INN", "VID"])

    print("\n🎉 Готово!")
