# ruff: noqa: BLE001,I001, DTZ011
from flask import Flask, render_template, request, jsonify, send_file, make_response
import pandas as pd
import math
from decimal import Decimal
from sqlalchemy import create_engine, text
import datetime

try:
    from .db_config import DATABASE_URL
except ImportError:
    from db_config import DATABASE_URL

app = Flask(__name__)

engine = create_engine(DATABASE_URL)


def ensure_audit_table():
    """Создаёт таблицу audit_log при первом запуске, если её ещё нет."""
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id            SERIAL PRIMARY KEY,
                changed_at    TIMESTAMP NOT NULL DEFAULT NOW(),
                table_name    TEXT NOT NULL,
                row_pk        TEXT,
                action        TEXT NOT NULL,      -- INSERT / UPDATE / DELETE
                column_name   TEXT,                -- для UPDATE: какая колонка менялась
                old_value     TEXT,
                new_value     TEXT,
                changed_by    TEXT                 -- зарезервировано на будущее (логины пользователей)
            );
        """))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_audit_log_changed_at ON audit_log (changed_at DESC);"
        ))
        # Колонка VID — на будущее позволяет фильтровать историю по конкретному
        # партнёру, а не только по таблице. ADD COLUMN IF NOT EXISTS — безопасно
        # для уже существующей БД (не пересоздаёт таблицу).
        conn.execute(text(
            "ALTER TABLE audit_log ADD COLUMN IF NOT EXISTS vid TEXT;"
        ))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_audit_log_vid ON audit_log (vid);"
        ))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS saldo_initial (
                id      SERIAL PRIMARY KEY,
                year    INTEGER NOT NULL,
                vid     TEXT NOT NULL,
                partner TEXT,
                inn     TEXT,
                saldo   NUMERIC(18,2) NOT NULL DEFAULT 0,
                UNIQUE (year, vid)
            );
        """))


ensure_audit_table()


def log_change(conn, table, pk_val, action, column_name=None, old_value=None, new_value=None, changed_by=None, vid=None):
    """Пишет одну запись в audit_log. conn — открытое соединение (та же транзакция,
    что и сама операция), чтобы лог и изменение фиксировались атомарно.
    vid — VID партнёра, к которому относится строка (если известен), нужен
    для фильтрации истории по конкретному партнёру."""
    conn.execute(
        text("""
            INSERT INTO audit_log (table_name, row_pk, action, column_name, old_value, new_value, changed_by, vid)
            VALUES (:table_name, :row_pk, :action, :column_name, :old_value, :new_value, :changed_by, :vid)
        """),
        {
            'table_name': table,
            'row_pk': str(pk_val) if pk_val is not None else None,
            'action': action,
            'column_name': column_name,
            'old_value': str(old_value) if old_value is not None else None,
            'new_value': str(new_value) if new_value is not None else None,
            'changed_by': changed_by,
            'vid': str(vid).strip().upper() if vid else None,
        }
    )

MONTH_MAP = {
    "Январь": 1, "Февраль": 2, "Март": 3, "Апрель": 4,
    "Май": 5, "Июнь": 6, "Июль": 7, "Август": 8,
    "Сентябрь": 9, "Октябрь": 10, "Ноябрь": 11, "Декабрь": 12
}
NUM_TO_MONTH = {v: k for k, v in MONTH_MAP.items()}


def group_by_vid(rows, value_keys, str_keys=None):
    """Группирует строки по VID — единому идентификатору партнёра, суммируя числовые поля.
    Нужно там, где SQL возвращает несколько строк на один VID (например, сверка за
    несколько месяцев сразу — period_month <= N). str_keys — дополнительные строковые
    поля, которые входят в ключ группировки (например Service/Status во вкладке Продажи)."""
    str_keys = str_keys or []
    grouped = {}
    for row in rows:
        vid = row.get('VID')
        if not vid:
            # Строк без VID быть не должно — SQL уже отсекает их через JOIN на vipp/vipp_canon.
            # Пропускаем на всякий случай, чтобы не упасть.
            continue
        str_vals = tuple(str(row.get(k, '')) for k in str_keys)
        key = (vid,) + str_vals
        if key not in grouped:
            grouped[key] = {
                'VID': vid,
                'ИНН': row.get('ИНН') or '-',
                'Партнер': row.get('Партнер') or '-',
            }
            for k in value_keys:
                grouped[key][k] = 0.0
            for k in str_keys:
                grouped[key][k] = str(row.get(k, ''))
        for k in value_keys:
            grouped[key][k] += float(row.get(k, 0) or 0)
    return list(grouped.values())


def df_records(df):
    """Конвертирует DataFrame в список dict, безопасный для jsonify():
    Decimal -> float, NaN/NaT -> 0. Без этого jsonify падает с
    'Object of type Decimal is not JSON serializable', если столбцы в Postgres
    имеют тип NUMERIC/DECIMAL."""
    records = df.to_dict(orient='records')
    for row in records:
        for k, v in row.items():
            if isinstance(v, Decimal):
                row[k] = float(v)
            elif isinstance(v, float) and math.isnan(v):
                row[k] = 0
            elif pd.isna(v):
                row[k] = None
    return records


def resolve_partner(inn_or_vid):
    """Резолвит ИНН или VID партнёра в (vid, partner_name) через справочник vipp_canon.
    Сначала пробует как ИНН, если не найдено — как VID напрямую.
    Возвращает (None, None), если партнёр не найден."""
    val = str(inn_or_vid or '').strip()
    if not val:
        return None, None
    try:
        q_inn = text('SELECT "VID", "Partner" FROM vipp_canon WHERE "INN" = :val LIMIT 1')
        df = pd.read_sql(q_inn, engine, params={'val': val})
        if not df.empty:
            return str(df.iloc[0]['VID']), str(df.iloc[0]['Partner'])
        q_vid = text('SELECT "VID", "Partner" FROM vipp_canon WHERE "VID" = :val LIMIT 1')
        df2 = pd.read_sql(q_vid, engine, params={'val': val})
        if not df2.empty:
            return str(df2.iloc[0]['VID']), str(df2.iloc[0]['Partner'])
    except Exception as e:
        print(f"❌ Ошибка поиска VID по ИНН/VID: {e}")
    return None, None


@app.route('/', methods=['GET', 'POST'])
def index():
    recon_data = []
    selected_month = "Май"
    selected_year = datetime.date.today().year
    db_month = "Май"
    db_year = datetime.date.today().year
    active_tab = "all"

    if request.method == 'POST':
        selected_month = request.form.get('month', 'Май')
        selected_year = int(request.form.get('year', datetime.date.today().year))
        db_month = request.form.get('db_month', selected_month)
        db_year = int(request.form.get('db_year', selected_year))
        active_tab = request.form.get('active_tab', 'all')

    # Числовые значения периодов
    month_numeric = MONTH_MAP.get(selected_month, 5)
    db_month_numeric = MONTH_MAP.get(db_month, 5)

    # Главная сверка: только партнёры (по VID), у которых ЕСТЬ продажи в vbase.
    # Данные по фактурам, оплатам и 1С подтягиваются через LEFT JOIN внутри самой вьюхи.
    # view_monthly_reconciliation уже учитывает только строки с валидным VID (JOIN на vipp).
    #
    # Saldo считаем НЕ построчно (иначе начальное сальдо задваивалось бы на каждый месяц
    # периода), а один раз после агрегации сумм по всему периоду (с начала года по
    # выбранный месяц включительно):
    #   Saldo = НС (начальное сальдо) + SUM(Payment) − SUM(Bank) − SUM(Komissiya)
    query = f"""
        SELECT
            vmr."VID"             AS "VID",
            COALESCE(vmr."INN", '-') AS "ИНН",
            vmr."Partner"            AS "Партнер",
            payment_val   AS "Payment",
            bank_val      AS "Bank",
            faktura_val   AS "Faktura",
            komissiya_val AS "Komissiya",
            balance_1c_val AS "1С"
        FROM view_monthly_reconciliation vmr
        INNER JOIN (
            SELECT DISTINCT "VID"
            FROM vbase
            WHERE period_month <= {month_numeric}
              AND period_year  = {selected_year}
        ) v ON vmr."VID" = v."VID"
        WHERE vmr.period_month <= {month_numeric}
          AND vmr.period_year  = {selected_year};
    """
    try:
        df = pd.read_sql(query, engine)
        recon_data = df.to_dict(orient='records')
    except Exception as e:
        print(f"❌ Ошибка при чтении из базы: {e}")

    # Переименовываем ключ '1С' -> '1C' для единообразия и группируем по VID,
    # суммируя Payment/Bank/Faktura/Komissiya/1C за весь период (период «<=» может
    # вернуть несколько строк на один VID — по одной на каждый месяц).
    for row in recon_data:
        row['1C'] = float(row.pop('1С', 0) or 0)
    recon_data = group_by_vid(recon_data, ['Payment', 'Bank', 'Faktura', 'Komissiya', '1C'])

    # Начальное сальдо (НС) на выбранный год — по одному значению на VID,
    # НЕ суммируется по месяцам периода.
    saldo_initial_map = {}
    try:
        df_si = pd.read_sql(
            text('SELECT vid, saldo FROM saldo_initial WHERE year = :year'),
            engine, params={'year': selected_year}
        )
        for _, r in df_si.iterrows():
            saldo_initial_map[str(r['vid']).strip().upper()] = float(r['saldo'] or 0)
    except Exception as e:
        print(f"❌ Ошибка чтения начального сальдо: {e}")

    for row in recon_data:
        ns = saldo_initial_map.get(str(row.get('VID', '')).strip().upper(), 0.0)
        saldo = ns + row['Payment'] - row['Bank'] - row['Komissiya']
        row['НС'] = ns
        row['Saldo'] = saldo
        row['Difference'] = saldo - row['1C']

    # ── ДАННЫЕ ЗА СТРОГО ВЫБРАННЫЙ МЕСЯЦ для вкладок Продажи / Фактуры / Оплаты ──
    # Джойним каждую таблицу на vipp_canon по VID — это и фильтрует "мусорные" VID
    # (NULL, опечатки, искусственно изменённые типа 'V107(другой договор)'), и сразу
    # даёт канонический ИНН/Партнёр на отображение (без задвоения ИНН+ПИНФЛ).

    # А) Продажи из vbase — период базы (управляется отдельной кнопкой)
    query_sales_tab = f"""
        SELECT
            vbase.id                AS "id",
            vc."VID"               AS "VID",
            COALESCE(vc."INN", '-') AS "ИНН",
            vc."Partner"            AS "Партнер",
            vbase."Service"         AS "Service",
            vbase."Status"          AS "Status",
            vbase."Sales"           AS "Payment",
            vbase."Komissiya"       AS "Komissiya"
        FROM vbase
        INNER JOIN vipp_canon vc ON vbase."VID" = vc."VID"
        WHERE vbase.period_month = {db_month_numeric}
          AND vbase.period_year  = {db_year}
        ORDER BY vc."Partner", vbase.id;
    """

    # Б) Фактуры из vfaktura — период базы
    query_faktura_tab = f"""
        SELECT
            vc."VID"             AS "VID",
            COALESCE(vc."INN", '-') AS "ИНН",
            vc."Partner"            AS "Партнер",
            SUM(vfaktura."Summ")    AS "Faktura"
        FROM vfaktura
        INNER JOIN vipp_canon vc ON vfaktura."VID" = vc."VID"
        WHERE vfaktura.period_month = {db_month_numeric}
          AND vfaktura.period_year  = {db_year}
        GROUP BY vc."VID", vc."INN", vc."Partner"
        ORDER BY vc."Partner";
    """

    # В) Оплаты из vbank — период базы
    query_bank_tab = f"""
        SELECT
            vc."VID"             AS "VID",
            COALESCE(vc."INN", '-') AS "ИНН",
            vc."Partner"            AS "Партнер",
            SUM(vbank."Summ")       AS "Bank"
        FROM vbank
        INNER JOIN vipp_canon vc ON vbank."VID" = vc."VID"
        WHERE vbank.period_month = {db_month_numeric}
          AND vbank.period_year  = {db_year}
        GROUP BY vc."VID", vc."INN", vc."Partner"
        ORDER BY vc."Partner";
    """

    sales_tab = []
    faktura_tab = []
    bank_tab = []

    # Группировка SQL уже идёт по VID — задвоений нет, доп. group_by_vid не нужен
    try:
        sales_tab = pd.read_sql(query_sales_tab, engine).to_dict(orient='records')
    except Exception as e:
        print(f"❌ Ошибка вкладки Продажи: {e}")

    try:
        faktura_tab = pd.read_sql(query_faktura_tab, engine).to_dict(orient='records')
    except Exception as e:
        print(f"❌ Ошибка вкладки Фактуры: {e}")

    try:
        bank_tab = pd.read_sql(query_bank_tab, engine).to_dict(orient='records')
    except Exception as e:
        print(f"❌ Ошибка вкладки Оплаты: {e}")

    return render_template(
        'index.html',
        data=recon_data,
        sales_data=sales_tab,
        faktura_data=faktura_tab,
        bank_data=bank_tab,
        month=selected_month,
        year=selected_year,
        db_month=db_month,
        db_year=db_year,
        active_tab=active_tab
    )


@app.route('/get_partner_details', methods=['POST'])
def get_partner_details():
    """Детализация по партнёру для попапа. Партнёр определяется строго по VID —
    передаётся с фронта (data-vid на клике), а не по ИНН/имени."""
    data = request.get_json() or {}
    vid = str(data.get('vid') if data.get('vid') is not None else '').strip()

    # Поддержка диапазона: month_from/year_from — month_to/year_to
    # Для обратной совместимости принимаем и старый формат (month/year)
    month_from_str = data.get('month_from') or data.get('month', 'Январь')
    year_from      = int(data.get('year_from') or data.get('year', datetime.date.today().year))
    month_to_str   = data.get('month_to')   or data.get('month', 'Декабрь')
    year_to        = int(data.get('year_to') or data.get('year', datetime.date.today().year))

    month_from = MONTH_MAP.get(month_from_str, 1)
    month_to   = MONTH_MAP.get(month_to_str,  12)

    # Универсальное условие по периоду: (year, month) между from и to
    def period_condition(year_col, month_col):
        return (
            f"(({year_col} = {year_from} AND {month_col} >= {month_from})"
            f" OR ({year_col} > {year_from} AND {year_col} < {year_to})"
            f" OR ({year_col} = {year_to}   AND {month_col} <= {month_to}))"
        )

    sales_data    = []
    faktura_data  = []
    bank_data     = []

    if not vid:
        # Без VID нет однозначного партнёра — отдаём пустую детализацию
        return jsonify({'sales': [], 'faktura': [], 'bank': []})

    safe_vid = vid.replace("'", "''")

    # 1. Продажи из vbase
    query_sales = f"""
        SELECT
            "VID"                AS "vid",
            COALESCE("INN", '-') AS "inn",
            "Partner"            AS "partner",
            "Service"            AS "service",
            "Status"             AS "status",
            SUM("Sales")         AS "sales",
            SUM("Komissiya")     AS "komissiya"
        FROM vbase
        WHERE "VID" = '{safe_vid}'
          AND {period_condition('period_year', 'period_month')}
        GROUP BY "VID", "INN", "Partner", "Service", "Status"
        ORDER BY "Partner";
    """
    try:
        sales_data = df_records(pd.read_sql(query_sales, engine))
    except Exception as e:
        print(f"❌ Ошибка детализации (продажи): {e}")

    # 2. Фактуры из vfaktura
    query_faktura = f"""
        SELECT
            "VID"                AS "vid",
            COALESCE("INN", '-') AS "inn",
            "Partner"            AS "partner",
            SUM("Summ")          AS "summ"
        FROM vfaktura
        WHERE "VID" = '{safe_vid}'
          AND {period_condition('period_year', 'period_month')}
        GROUP BY "VID", "INN", "Partner"
        ORDER BY "Partner";
    """
    try:
        faktura_data = df_records(pd.read_sql(query_faktura, engine))
    except Exception as e:
        print(f"❌ Ошибка детализации (фактуры): {e}")

    # 3. Оплаты из vbank
    query_bank = f"""
        SELECT
            "VID"                AS "vid",
            COALESCE("INN", '-') AS "inn",
            "Partner"            AS "partner",
            SUM("Summ")          AS "summ"
        FROM vbank
        WHERE "VID" = '{safe_vid}'
          AND {period_condition('period_year', 'period_month')}
        GROUP BY "VID", "INN", "Partner"
        ORDER BY "Partner";
    """
    try:
        bank_data = df_records(pd.read_sql(query_bank, engine))
    except Exception as e:
        print(f"❌ Ошибка детализации (оплаты): {e}")

    print(f"🔍 Детализация: vid={vid!r}, "
          f"{month_from_str} {year_from} — {month_to_str} {year_to}")
    print(f"   sales={len(sales_data)}, faktura={len(faktura_data)}, bank={len(bank_data)}")

    return jsonify({
        'sales':   sales_data,
        'faktura': faktura_data,
        'bank':    bank_data
    })


@app.route('/partner-monthly', methods=['GET'])
def partner_monthly():
    """Отдельная страница: помесячная динамика сверки по одному партнёру.
    Пользователь ищет по привычному ИНН — сервер сам резолвит его в VID через vipp_canon."""
    prefill_inn = request.args.get('inn', '').strip()
    return render_template('partner_monthly.html', current_year=datetime.date.today().year, prefill_inn=prefill_inn)


@app.route('/get_partner_monthly_report', methods=['POST'])
def get_partner_monthly_report():
    """Возвращает помесячную (накопительную, как на главной странице) сверку по партнёру
    за весь выбранный год. Партнёр ищется по ИНН или VID, сверка строится по VID."""
    data = request.get_json() or {}
    inn = str(data.get('inn') or '').strip()
    year = int(data.get('year') or datetime.date.today().year)

    if not inn:
        return jsonify({'error': 'ИНН не указан'}), 400

    # 1. Резолвим ИНН -> VID через справочник vipp_canon (или напрямую как VID)
    vid, partner_name = resolve_partner(inn)
    if not vid:
        return jsonify({'error': 'Партнёр с таким ИНН/VID не найден в справочнике VIPP'}), 404

    value_cols = ['Payment', 'Bank', 'Faktura', 'Komissiya', '1C']
    monthly = {m: {c: 0.0 for c in value_cols} for m in range(1, 13)}

    # 2. Сверка за весь год по этому VID (помесячные, не накопленные значения —
    # накопление Saldo считаем сами ниже, отдельно, по формуле нарастающего итога)
    query = text("""
        SELECT
            vmr.period_month       AS month_num,
            vmr.payment_val        AS "Payment",
            vmr.bank_val           AS "Bank",
            vmr.faktura_val        AS "Faktura",
            vmr.komissiya_val      AS "Komissiya",
            vmr.balance_1c_val     AS "1C"
        FROM view_monthly_reconciliation vmr
        WHERE vmr."VID" = :vid
          AND vmr.period_year = :year
        ORDER BY vmr.period_month;
    """)

    try:
        df = pd.read_sql(query, engine, params={'vid': vid, 'year': year})
        for _, row in df.iterrows():
            m = int(row['month_num'])
            if m < 1 or m > 12:
                continue
            for c in value_cols:
                v = row.get(c, 0)
                if isinstance(v, Decimal):
                    v = float(v)
                elif v is None or (isinstance(v, float) and math.isnan(v)):
                    v = 0.0
                monthly[m][c] += float(v)
    except Exception as e:
        print(f"❌ Ошибка помесячного отчёта (сверка): {e}")
        return jsonify({'error': 'Ошибка при чтении из базы'}), 500

    # 3. Начальное сальдо из saldo_initial для этого VID и года
    saldo_initial_val = 0.0
    try:
        q_saldo = text('SELECT saldo FROM saldo_initial WHERE LOWER(vid) = LOWER(:vid) AND year = :year LIMIT 1')
        df_saldo = pd.read_sql(q_saldo, engine, params={'vid': vid, 'year': year})
        if not df_saldo.empty:
            v = df_saldo.iloc[0]['saldo']
            saldo_initial_val = float(v) if v is not None else 0.0
    except Exception as e:
        print(f"❌ Ошибка чтения начального сальдо: {e}")

    # 4. Saldo нарастающим итогом по месяцам:
    #    Январь: Saldo = начальное сальдо + Payment - Bank - Komissiya
    #    Остальные месяцы: Saldo = Saldo(пред. месяца) + Payment - Bank - Komissiya
    rows_out = []
    running_saldo = saldo_initial_val
    for m in range(1, 13):
        running_saldo = running_saldo + monthly[m]['Payment'] - monthly[m]['Bank'] - monthly[m]['Komissiya']
        saldo_val = running_saldo
        rows_out.append({
            'month_num': m,
            'month': NUM_TO_MONTH[m],
            'Payment': monthly[m]['Payment'],
            'Bank': monthly[m]['Bank'],
            'Faktura': monthly[m]['Faktura'],
            'Komissiya': monthly[m]['Komissiya'],
            'Saldo': saldo_val,
            '1C': monthly[m]['1C'],
            'Difference': saldo_val - monthly[m]['1C'],
        })

    return jsonify({'inn': inn, 'vid': vid, 'partner': partner_name, 'year': year,
                    'saldo_initial': saldo_initial_val, 'rows': rows_out})


@app.route('/get_partner_reconciliation_act', methods=['POST'])
def get_partner_reconciliation_act():
    """Акт сверки по партнёру за год — построчная детализация документов, как в
    классическом акте сверки взаиморасчётов:
      • Счёт-фактура №  (комиссия, vfaktura.Summ)   — колонка «Дебет»
      • Передано        (продажи, vbase.Sales)      — колонка «Кредит»
      • Оплата №        (оплаты, vbank.Summ)         — колонка «Дебет»
    Сальдо конечное = Сальдо начальное + Кредит (обороты) − Дебет (обороты)."""
    data = request.get_json() or {}
    inn = str(data.get('inn') or '').strip()
    year = int(data.get('year') or datetime.date.today().year)

    if not inn:
        return jsonify({'error': 'ИНН не указан'}), 400

    vid, partner_name = resolve_partner(inn)
    if not vid:
        return jsonify({'error': 'Партнёр с таким ИНН/VID не найден в справочнике VIPP'}), 404

    # (таблица, колонка суммы, порядок внутри одной даты, подпись документа, сторона)
    doc_defs = [
        ('vfaktura', 'Summ',  0, 'Счет-фактура №', 'debit'),
        ('vbase',    'Sales', 1, 'Передано',        'credit'),
        ('vbank',    'Summ',  2, 'Оплата №',        'debit'),
    ]

    all_rows = []
    try:
        for table, amount_col, order, label, side in doc_defs:
            q = text(f'''
                SELECT "Data" AS "date", "{amount_col}" AS "amount"
                FROM {table}
                WHERE "VID" = :vid AND period_year = :year
                ORDER BY "Data", id;
            ''')
            df = pd.read_sql(q, engine, params={'vid': vid, 'year': year})
            for _, r in df.iterrows():
                amt = r['amount']
                if isinstance(amt, Decimal):
                    amt = float(amt)
                elif amt is None or (isinstance(amt, float) and math.isnan(amt)):
                    amt = 0.0
                dt = pd.to_datetime(r['date'], errors='coerce')
                all_rows.append({'dt': dt, 'order': order, 'label': label, 'side': side, 'amount': float(amt)})
    except Exception as e:
        print(f"❌ Ошибка построения акта сверки: {e}")
        return jsonify({'error': 'Ошибка при чтении из базы'}), 500

    all_rows.sort(key=lambda r: (r['dt'] if pd.notna(r['dt']) else pd.Timestamp.max, r['order']))

    rows_out = []
    for r in all_rows:
        if pd.notna(r['dt']):
            date_short = r['dt'].strftime('%d.%m.%y')
            date_full = r['dt'].strftime('%d.%m.%Y')
        else:
            date_short = date_full = '—'
        rows_out.append({
            'date_short': date_short,
            'date_full': date_full,
            'label': r['label'],
            'side': r['side'],
            'amount': r['amount'],
        })

    debit_total = sum(r['amount'] for r in rows_out if r['side'] == 'debit')
    credit_total = sum(r['amount'] for r in rows_out if r['side'] == 'credit')

    saldo_initial_val = 0.0
    try:
        q_saldo = text('SELECT saldo FROM saldo_initial WHERE LOWER(vid) = LOWER(:vid) AND year = :year LIMIT 1')
        df_saldo = pd.read_sql(q_saldo, engine, params={'vid': vid, 'year': year})
        if not df_saldo.empty:
            v = df_saldo.iloc[0]['saldo']
            saldo_initial_val = float(v) if v is not None else 0.0
    except Exception as e:
        print(f"❌ Ошибка чтения начального сальдо: {e}")

    saldo_final_val = saldo_initial_val + credit_total - debit_total

    return jsonify({
        'inn': inn, 'vid': vid, 'partner': partner_name, 'year': year,
        'saldo_initial': saldo_initial_val,
        'saldo_final': saldo_final_val,
        'rows': rows_out,
        'debit_total': debit_total,
        'credit_total': credit_total,
    })


# ── РЕДАКТИРОВАНИЕ БАЗЫ ДАННЫХ ──────────────────────────────────────────────

# Таблицы и их первичные ключи
DB_TABLES = {
    'vbase':    {'pk': 'id', 'cols': ['VID','INN','Partner','Service','Status','Sales','Komissiya','period_month','period_year']},
    'vfaktura': {'pk': 'id', 'cols': ['VID','INN','Partner','Data','Summ','period_month','period_year']},
    'vbank':    {'pk': 'id', 'cols': ['VID','INN','Partner','Data','Summ','period_month','period_year']},
}


def _safe_table(table):
    if table not in DB_TABLES:
        return None
    return table


@app.route('/db/lookup_vid', methods=['POST'])
def db_lookup_vid():
    """Поиск ИНН и Партнёра по VID в справочнике vipp_canon — для автозаполнения
    при добавлении новой строки."""
    data = request.get_json() or {}
    vid = str(data.get('vid') or '').strip()
    if not vid:
        return jsonify({'error': 'VID не указан'}), 400

    try:
        q = text('SELECT "VID", "INN", "Partner" FROM vipp_canon WHERE "VID" = :vid LIMIT 1')
        df = pd.read_sql(q, engine, params={'vid': vid})
        if df.empty:
            return jsonify({'found': False})
        row = df.iloc[0]
        return jsonify({
            'found': True,
            'VID': str(row['VID']),
            'INN': str(row['INN']) if row['INN'] is not None else '',
            'Partner': str(row['Partner']) if row['Partner'] is not None else '',
        })
    except Exception as e:
        print(f"❌ db_lookup_vid error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/db/update', methods=['POST'])
def db_update():
    """Обновить одну ячейку: {table, pk_val, col, value}"""
    data = request.get_json() or {}
    table = _safe_table(data.get('table', ''))
    if not table:
        return jsonify({'error': 'Неизвестная таблица'}), 400

    pk_col = DB_TABLES[table]['pk']
    allowed_cols = DB_TABLES[table]['cols']
    col = data.get('col', '')
    if col not in allowed_cols:
        return jsonify({'error': f'Недопустимый столбец: {col}'}), 400

    pk_val = data.get('pk_val')
    value  = data.get('value')
    if value == '':
        value = None

    try:
        with engine.begin() as conn:
            # Считываем старое значение ДО изменения, а заодно VID строки (для
            # фильтрации истории по партнёру) — если сам столбец col это VID,
            # второй SELECT не нужен, используем old_value напрямую.
            old_row = conn.execute(
                text(f'SELECT "{col}", "VID" FROM "{table}" WHERE "{pk_col}" = :pk'),
                {'pk': pk_val}
            ).fetchone()
            old_value = old_row[0] if old_row else None
            row_vid = old_row[1] if old_row else None

            conn.execute(
                text(f'UPDATE "{table}" SET "{col}" = :val WHERE "{pk_col}" = :pk'),
                {'val': value, 'pk': pk_val}
            )

            log_change(conn, table, pk_val, 'UPDATE', column_name=col,
                       old_value=old_value, new_value=value, vid=row_vid)
        return jsonify({'ok': True})
    except Exception as e:
        print(f"❌ db_update error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/db/insert', methods=['POST'])
def db_insert():
    """Добавить новую строку: {table, row: {col: val, ...}}"""
    data = request.get_json() or {}
    table = _safe_table(data.get('table', ''))
    if not table:
        return jsonify({'error': 'Неизвестная таблица'}), 400

    allowed_cols = DB_TABLES[table]['cols']
    row = {k: v for k, v in (data.get('row') or {}).items() if k in allowed_cols}
    if not row:
        return jsonify({'error': 'Нет данных для вставки'}), 400

    # Пустая строка '' не валидна для numeric/int полей в Postgres ('' != NULL) —
    # превращаем такие значения в None, чтобы вставлялся NULL, а не пустая строка.
    for k, v in list(row.items()):
        if v == '' or v is None:
            row[k] = None

    cols_sql  = ', '.join(f'"{c}"' for c in row)
    vals_sql  = ', '.join(f':{c}' for c in row)
    pk_col    = DB_TABLES[table]['pk']

    try:
        with engine.begin() as conn:
            result = conn.execute(
                text(f'INSERT INTO "{table}" ({cols_sql}) VALUES ({vals_sql}) RETURNING "{pk_col}"'),
                row
            )
            new_pk = result.scalar()
            log_change(conn, table, new_pk, 'INSERT', new_value=row, vid=row.get('VID'))
        return jsonify({'ok': True, 'pk_val': new_pk})
    except Exception as e:
        print(f"❌ db_insert error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/db/delete', methods=['POST'])
def db_delete():
    """Удалить строку: {table, pk_val}"""
    data = request.get_json() or {}
    table = _safe_table(data.get('table', ''))
    if not table:
        return jsonify({'error': 'Неизвестная таблица'}), 400

    pk_col = DB_TABLES[table]['pk']
    pk_val = data.get('pk_val')

    try:
        with engine.begin() as conn:
            # Сохраняем содержимое строки до удаления, чтобы было что показать в истории
            old_row = conn.execute(
                text(f'SELECT * FROM "{table}" WHERE "{pk_col}" = :pk'),
                {'pk': pk_val}
            ).mappings().fetchone()
            old_row_dict = dict(old_row) if old_row else None

            conn.execute(
                text(f'DELETE FROM "{table}" WHERE "{pk_col}" = :pk'),
                {'pk': pk_val}
            )

            log_change(conn, table, pk_val, 'DELETE', old_value=old_row_dict,
                       vid=(old_row_dict.get('VID') if old_row_dict else None))
        return jsonify({'ok': True})
    except Exception as e:
        print(f"❌ db_delete error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/db/export_filtered', methods=['POST'])
def db_export_filtered():
    """Скачать отфильтрованные данные из фронта как Excel."""
    import io
    import openpyxl

    data    = request.get_json() or {}
    table   = data.get('table', 'table')
    headers = data.get('headers', [])
    rows    = data.get('rows', [])

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = table[:31]

    ws.append(headers)
    for row in rows:
        ws.append(row)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    resp = make_response(buf.read())
    resp.headers['Content-Type'] = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    resp.headers['Content-Disposition'] = f'attachment; filename="{table}_filtered.xlsx"'
    return resp


@app.route('/db/export/<table_name>')
def db_export(table_name):
    """Скачать всю таблицу как Excel: /db/export/vbase?month=5&year=2025&full=1"""
    import io
    import openpyxl

    table = _safe_table(table_name)
    if not table:
        return jsonify({'error': 'Неизвестная таблица'}), 400

    full = request.args.get('full', '0') == '1'
    month = request.args.get('month', type=int)
    year  = request.args.get('year',  type=int)

    if full or not month or not year:
        q = f'SELECT * FROM "{table}" ORDER BY id'
        params = {}
    else:
        q = f'SELECT * FROM "{table}" WHERE period_month = :m AND period_year = :y ORDER BY id'
        params = {'m': month, 'y': year}

    try:
        df = pd.read_sql(text(q), engine, params=params)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

    # Конвертируем Decimal -> float
    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].apply(lambda x: float(x) if isinstance(x, Decimal) else x)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = table

    # Заголовки
    ws.append(list(df.columns))
    for row in df.itertuples(index=False):
        ws.append(list(row))

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    label = 'all' if (full or not month) else f'{month}_{year}'
    filename = f'{table}_{label}.xlsx'

    return send_file(
        buf,
        as_attachment=True,
        download_name=filename,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )


@app.route('/db/history', methods=['GET'])
def db_history():
    """Последние изменения в базе: /db/history?limit=200&table=vbase
    table не обязателен — без него отдаются изменения по всем таблицам."""
    limit = request.args.get('limit', 200, type=int)
    limit = max(1, min(limit, 1000))
    table = request.args.get('table')
    vid = str(request.args.get('vid') or '').strip()

    conditions = []
    params = {'limit': limit}
    if table and table in DB_TABLES:
        conditions.append('table_name = :table')
        params['table'] = table
    if vid:
        conditions.append('vid = :vid')
        params['vid'] = vid.upper()
    where = ('WHERE ' + ' AND '.join(conditions)) if conditions else ''

    query = text(f"""
        SELECT id, changed_at, table_name, row_pk, action, column_name, old_value, new_value, changed_by, vid
        FROM audit_log
        {where}
        ORDER BY changed_at DESC, id DESC
        LIMIT :limit
    """)

    try:
        df = pd.read_sql(query, engine, params=params)
        if not df.empty:
            df['changed_at'] = df['changed_at'].astype(str)
        rows = df_records(df)
        return jsonify({'rows': rows})
    except Exception as e:
        print(f"❌ db_history error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/db/export_history')
def db_export_history():
    """Скачать журнал изменений как Excel: /db/export_history?table=vbase&limit=1000"""
    import io
    import openpyxl

    limit = request.args.get('limit', 1000, type=int)
    limit = max(1, min(limit, 10000))
    table = request.args.get('table')
    vid = str(request.args.get('vid') or '').strip()

    conditions = []
    params = {'limit': limit}
    if table and table in DB_TABLES:
        conditions.append('table_name = :table')
        params['table'] = table
    if vid:
        conditions.append('vid = :vid')
        params['vid'] = vid.upper()
    where = ('WHERE ' + ' AND '.join(conditions)) if conditions else ''

    query = text(f"""
        SELECT id, changed_at, table_name, row_pk, action, column_name, old_value, new_value, changed_by, vid
        FROM audit_log
        {where}
        ORDER BY changed_at DESC, id DESC
        LIMIT :limit
    """)

    try:
        df = pd.read_sql(query, engine, params=params)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'audit_log'
    ws.append(list(df.columns))
    for row in df.itertuples(index=False):
        ws.append([str(v) if v is not None else '' for v in row])

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    return send_file(
        buf,
        as_attachment=True,
        download_name='audit_log.xlsx',
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )


@app.route('/db/check_periods', methods=['POST'])
def db_check_periods():
    """Проверить, какие периоды (месяц/год) из присланного списка уже есть в таблице.
    Используется фронтом для предпросмотра файла ДО загрузки — чтобы предупредить
    о дублях, не дожидаясь ответа от /db/upload_excel.
    Тело запроса: {table, periods: [[year, month], ...]}"""
    data = request.get_json() or {}
    table = _safe_table(data.get('table', ''))
    if not table:
        return jsonify({'error': 'Неизвестная таблица'}), 400

    periods = data.get('periods') or []
    already = []
    try:
        with engine.connect() as conn:
            for p in periods:
                if not isinstance(p, (list, tuple)) or len(p) != 2:
                    continue
                y, m = p
                y, m = int(y), int(m)
                count = conn.execute(
                    text(f'SELECT COUNT(*) FROM "{table}" WHERE period_month = :m AND period_year = :y'),
                    {"m": m, "y": y}
                ).scalar()
                if count > 0:
                    already.append({'year': y, 'month': m, 'count': count})
    except Exception as e:
        print(f"❌ check_periods error: {e}")
        return jsonify({'error': str(e)}), 500

    return jsonify({'already': already})


@app.route('/db/upload_excel', methods=['POST'])
def db_upload_excel():
    """Загрузить Excel-файл (один лист) и дописать строки в таблицу."""
    import io, json
    try:
        f = request.files.get('file')
        if not f:
            return jsonify({'error': 'Файл не передан'}), 400

        table = request.form.get('table', '')
        if table not in DB_TABLES:
            return jsonify({'error': f'Неизвестная таблица: {table}'}), 400

        use_cols = json.loads(request.form.get('cols', '[]'))
        if not use_cols:
            return jsonify({'error': 'Не переданы колонки'}), 400

        raw = f.read()
        df = pd.read_excel(io.BytesIO(raw), sheet_name=0, dtype={'INN': str, 'ИНН': str})

        if df.empty:
            return jsonify({'error': 'Файл пустой'}), 400

        df.columns = [str(c).strip() for c in df.columns]

        missing = [c for c in use_cols if c not in df.columns]
        if missing:
            return jsonify({'error': f'Отсутствуют колонки: {missing}'}), 400

        df = df[use_cols].copy()

        if 'INN' in df.columns:
            df['INN'] = df['INN'].astype(str).str.strip()
            df['INN'] = df['INN'].str.replace(r'\.0$', '', regex=True)
            df['INN'] = df['INN'].replace(['nan', 'None', 'null', 'NaN', ''], '-')

        if 'Data' in df.columns:
            # Оставляем как datetime (не .dt.date), иначе повторный pd.to_datetime()
            # теряет dayfirst и путает день/месяц в датах типа 05.01.2026
            df['Data'] = pd.to_datetime(df['Data'], dayfirst=True, errors='coerce')

        if 'Data' in df.columns and df['Data'].notna().any():
            # period_month/year берём из КАЖДОЙ строки — файл может содержать несколько месяцев
            df['period_month'] = df['Data'].dt.month
            df['period_year']  = df['Data'].dt.year
            # Строки без даты заполняем из ближайших соседей
            df['period_month'] = df['period_month'].ffill().bfill().astype('Int64')
            df['period_year']  = df['period_year'].ffill().bfill().astype('Int64')

            periods = sorted(df.groupby(['period_year', 'period_month']).size().index.tolist())
            period_label = ', '.join(f"{int(m):02d}.{int(y)}" for y, m in periods)
        else:
            return jsonify({'error': 'Не удалось определить период (нет дат в колонке Data)'}), 400

        # Проверяем дубликаты по каждому найденному периоду
        already = []
        with engine.connect() as conn:
            for y, m in periods:
                count = conn.execute(
                    text(f'SELECT COUNT(*) FROM "{table}" WHERE period_month = :m AND period_year = :y'),
                    {"m": int(m), "y": int(y)}
                ).scalar()
                if count > 0:
                    already.append(f"{int(m):02d}.{int(y)} ({count} строк)")
        if already:
            return jsonify({'error': f'Данные уже есть в таблице: {", ".join(already)}. Сначала удалите их если хотите перезагрузить.'}), 400

        # Нормализуем VID к верхнему регистру перед записью
        if 'VID' in df.columns:
            df['VID'] = df['VID'].astype(str).str.strip().str.upper()

        # Конвертируем Data в date для записи в БД
        if 'Data' in df.columns:
            df['Data'] = df['Data'].dt.date

        df.to_sql(table, engine, if_exists='append', index=False, chunksize=10000)

        log = f"✅ Успешно загружено!\n📅 Периоды: {period_label}\n📊 Таблица: {table}\n📝 Добавлено строк: {len(df)}"
        return jsonify({'log': log})

    except Exception as e:
        print(f"❌ upload_excel error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/db/upload_saldo_initial', methods=['POST'])
def db_upload_saldo_initial():
    """Загрузить начальное сальдо из Excel (VID, Partner, INN, Saldo)."""
    import io
    try:
        f = request.files.get('file')
        year = int(request.form.get('year', datetime.date.today().year))
        if not f:
            return jsonify({'error': 'Файл не передан'}), 400

        raw = f.read()
        df = pd.read_excel(io.BytesIO(raw), sheet_name=0, dtype={'INN': str})

        if df.empty:
            return jsonify({'error': 'Файл пустой'}), 400

        df.columns = [str(c).strip() for c in df.columns]

        required = ['VID', 'Saldo']
        missing = [c for c in required if c not in df.columns]
        if missing:
            return jsonify({'error': f'Отсутствуют колонки: {missing}. Нужны: VID, Partner, INN, Saldo'}), 400

        df = df[['VID'] + [c for c in ['Partner', 'INN', 'Saldo'] if c in df.columns]].copy()
        df['year'] = year

        if 'INN' in df.columns:
            df['INN'] = df['INN'].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
            df['INN'] = df['INN'].replace(['nan', 'None', 'null', 'NaN', ''], '-')

        df['VID'] = df['VID'].astype(str).str.strip().str.upper()
        df['Saldo'] = pd.to_numeric(df['Saldo'], errors='coerce').fillna(0)

        # Upsert — обновляем если уже есть, добавляем если нет
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM saldo_initial WHERE year = :year"), {"year": year})
            df.rename(columns={'VID': 'vid', 'Partner': 'partner', 'INN': 'inn', 'Saldo': 'saldo'}, inplace=True)
            df.to_sql('saldo_initial', conn, if_exists='append', index=False)

        return jsonify({'log': f"✅ Начальное сальдо загружено!\n📅 Год: {year}\n📝 Партнёров: {len(df)}"})

    except Exception as e:
        print(f"❌ upload_saldo_initial error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/db/upload_balance_1c', methods=['POST'])
def db_upload_balance_1c():
    """Загрузить сальдо 1С из листа 'КС06' Excel-файла.

    Лист устроен как два независимых блока партнёров бок о бок:
      левый  блок: колонки A-D  (VID, Partner, INN, Saldo)
      правый блок: колонки F-I  (Vorona Code, Partner, INN, Saldo)

    Итоговое сальдо на партнёра (VID) = СУММА Saldo в правом блоке
    минус СУММА Saldo в левом блоке (как в формуле СУММЕСЛИ у бухгалтера).
    Если партнёр встретился только в одном блоке — второе слагаемое считается 0.

    ИНН и название партнёра для записи в базу берутся не из самого Excel
    (там встречаются опечатки/расхождения), а из справочника vipp_canon по VID —
    чтобы гарантированно совпадать с тем, как эти же партнёры сопоставляются
    во вьюхе view_monthly_reconciliation.
    """
    import io
    try:
        f = request.files.get('file')
        month = int(request.form.get('month', 0))
        year = int(request.form.get('year', datetime.date.today().year))
        if not f:
            return jsonify({'error': 'Файл не передан'}), 400
        if not (1 <= month <= 12):
            return jsonify({'error': 'Некорректный месяц'}), 400

        raw = f.read()
        try:
            df = pd.read_excel(io.BytesIO(raw), sheet_name='КС06', header=0, dtype=str)
        except ValueError:
            return jsonify({'error': "На листе 'КС06' не найден в файле. Проверьте название листа."}), 400

        if df.empty:
            return jsonify({'error': "Лист 'КС06' пустой"}), 400

        if df.shape[1] < 9:
            return jsonify({'error': f"На листе 'КС06' ожидается минимум 9 колонок (2 блока: VID..Saldo, Vorona Code..Saldo), найдено {df.shape[1]}"}), 400

        # Левый блок: VID, Partner, INN, Saldo (колонки 0-3) — вычитается
        left = df.iloc[:, [0, 1, 2, 3]].copy()
        left.columns = ['VID', 'Partner', 'INN', 'Saldo']
        left['sign'] = -1

        # Правый блок: Vorona Code (=VID), Partner, INN, Saldo (колонки 5-8) — складывается
        right = df.iloc[:, [5, 6, 7, 8]].copy()
        right.columns = ['VID', 'Partner', 'INN', 'Saldo']
        right['sign'] = 1

        combined = pd.concat([left, right], ignore_index=True)
        combined['VID'] = combined['VID'].astype(str).str.strip().str.upper()
        combined = combined[(combined['VID'] != '') & (combined['VID'] != 'NAN') & (combined['VID'] != 'NONE')]

        combined['Saldo'] = pd.to_numeric(combined['Saldo'], errors='coerce').fillna(0)
        combined['signed_saldo'] = combined['Saldo'] * combined['sign']

        grouped = combined.groupby('VID', as_index=False)['signed_saldo'].sum()
        grouped.rename(columns={'signed_saldo': 'end_balance'}, inplace=True)

        if grouped.empty:
            return jsonify({'error': 'Не найдено ни одного VID на листе КС06'}), 400

        # Резолвим VID -> (INN, Partner) через справочник vipp_canon в базе,
        # чтобы ИНН гарантированно совпадал с тем, что использует вьюха для JOIN.
        with engine.connect() as conn:
            canon = pd.read_sql(text('SELECT "VID", "INN", "Partner" FROM vipp_canon'), conn)
        canon['VID_UP'] = canon['VID'].astype(str).str.strip().str.upper()
        canon = canon.drop_duplicates(subset='VID_UP').drop(columns=['VID'])

        merged = grouped.merge(canon, left_on='VID', right_on='VID_UP', how='left')

        unresolved = merged[merged['INN'].isna()]['VID'].tolist()
        resolved = merged.dropna(subset=['INN']).copy()

        if resolved.empty:
            return jsonify({'error': f'Ни один VID из файла не найден в справочнике vipp_canon. Примеры: {unresolved[:10]}'}), 400

        resolved['INN'] = resolved['INN'].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
        out = resolved.rename(columns={'Partner': 'partner_name'})[['INN', 'partner_name', 'end_balance']].copy()
        out['period_month'] = month
        out['period_year'] = year

        # Заменяем данные за этот месяц/год (перезагрузка = обновление, а не задвоение)
        with engine.begin() as conn:
            conn.execute(
                text('DELETE FROM balance_1c WHERE period_month = :m AND period_year = :y'),
                {"m": month, "y": year}
            )
            out.to_sql('balance_1c', conn, if_exists='append', index=False)

        log = (
            f"✅ Сальдо 1С загружено!\n"
            f"📅 Период: {month:02d}.{year}\n"
            f"📝 Партнёров загружено: {len(out)}"
        )
        if unresolved:
            log += f"\n⚠️ Не найдено в справочнике VIPP ({len(unresolved)} VID): {', '.join(unresolved[:15])}"
            if len(unresolved) > 15:
                log += "…"

        return jsonify({'log': log})

    except Exception as e:
        print(f"❌ upload_balance_1c error: {e}")
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    print("🌍 Сервер VORONA запущен → http://127.0.0.1:5000")
    app.run(debug=True, port=5000, exclude_patterns=["upload_to_db.py"])
