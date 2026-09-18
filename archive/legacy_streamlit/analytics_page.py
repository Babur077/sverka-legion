import io
import json
import streamlit as st
import pandas as pd
import plotly.express as px
from utils.db_manager import get_archive_data, delete_archive_record, log_action

def show_page():
    st.title("Аналитика и архив сверок")
    st.markdown(
        "<p style='color:#64748b; margin-top:-15px; margin-bottom:20px;'>"
        "История завершённых сверок, детализация по отчётным месяцам, аналитика комиссий и оборота в разрезе терминалов."
        "</p>",
        unsafe_allow_html=True
    )
    
    df_archive = get_archive_data()
    
    if df_archive.empty:
        st.info("📭 В архиве пока нет проведённых сверок. Загрузите реестры на странице «Сверка по RRN», проведите сверку и запишите результат в архив базы данных.")
        return
        
    # Преобразуем строковые даты
    df_archive['timestamp_dt'] = pd.to_datetime(df_archive['timestamp'], errors='coerce')
    df_archive['date_str'] = df_archive['timestamp_dt'].dt.strftime('%d.%m.%Y %H:%M')
    
    if 'period_month' not in df_archive.columns or df_archive['period_month'].isnull().all():
        df_archive['period_month'] = df_archive['timestamp_dt'].dt.strftime('%Y-%m')
    else:
        df_archive['period_month'] = df_archive['period_month'].fillna(df_archive['timestamp_dt'].dt.strftime('%Y-%m'))
        
    if 'total_commission' not in df_archive.columns:
        df_archive['total_commission'] = 0.0
    else:
        df_archive['total_commission'] = df_archive['total_commission'].fillna(0.0)

    # ─── Извлечение всех терминальных данных из архива ───
    all_terminals = []
    for _, row in df_archive.iterrows():
        t_json = row.get('terminals_json', '')
        p_month = row.get('period_month', '')
        arch_bank = row.get('bank_name', '')
        arch_ts = row.get('date_str', '')
        arch_id = row.get('id', 0)
        
        if t_json and isinstance(t_json, str) and t_json.strip():
            try:
                parsed = json.loads(t_json)
                if isinstance(parsed, list):
                    for item in parsed:
                        if isinstance(item, dict):
                            all_terminals.append({
                                'archive_id': arch_id,
                                'date_str': arch_ts,
                                'period_month': p_month,
                                'archive_bank': arch_bank,
                                'terminal_id': str(item.get('terminal_id', '')),
                                'bank_acquirer': str(item.get('bank_acquirer') or arch_bank),
                                'merchant_id': str(item.get('merchant_id', '')),
                                'legal_entity': str(item.get('legal_entity', '')),
                                'tx_count': int(item.get('tx_count', 0)),
                                'total_volume': float(item.get('total_volume', 0.0)),
                                'commission_pct': float(item.get('commission_pct', 0.0)),
                                'commission_amount': float(item.get('commission_amount', 0.0)),
                                'net_volume': float(item.get('net_volume', 0.0)),
                            })
            except Exception:
                pass

    df_all_terminals = pd.DataFrame(all_terminals) if all_terminals else pd.DataFrame(columns=[
        'archive_id', 'date_str', 'period_month', 'archive_bank', 'terminal_id',
        'bank_acquirer', 'merchant_id', 'legal_entity', 'tx_count', 'total_volume',
        'commission_pct', 'commission_amount', 'net_volume'
    ])

    # ─── БЛОК ФИЛЬТРОВ ───
    available_months = sorted(list(set(df_archive['period_month'].dropna().unique())), reverse=True)
    available_banks = sorted(list(set(df_archive['bank_name'].dropna().unique())))
    available_tids = sorted(list(set(df_all_terminals['terminal_id'].dropna().unique()))) if not df_all_terminals.empty else []

    with st.container(border=True):
        st.markdown("##### 🔍 Фильтры выборки архива")
        f1, f2, f3, f4 = st.columns([2, 2, 2, 1.5])
        
        with f1:
            month_filter = st.selectbox("📅 Отчётный месяц:", ["(Все месяцы)"] + available_months, index=0)
        with f2:
            bank_filter = st.selectbox("🏛️ Банк:", ["(Все банки)"] + available_banks, index=0)
        with f3:
            tid_filter = st.selectbox("📟 Терминал (TID):", ["(Все терминалы)"] + available_tids, index=0)
        with f4:
            st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
            has_filter = (month_filter != "(Все месяцы)" or bank_filter != "(Все банки)" or tid_filter != "(Все терминалы)")
            if has_filter:
                if st.button("✕ Сбросить", use_container_width=True):
                    st.rerun()

    # Фильтрация записей архива
    df_filtered_archive = df_archive.copy()
    if month_filter != "(Все месяцы)":
        df_filtered_archive = df_filtered_archive[df_filtered_archive['period_month'] == month_filter]
    if bank_filter != "(Все банки)":
        df_filtered_archive = df_filtered_archive[df_filtered_archive['bank_name'] == bank_filter]
    if tid_filter != "(Все терминалы)":
        matching_archive_ids = set(df_all_terminals[df_all_terminals['terminal_id'] == tid_filter]['archive_id'])
        df_filtered_archive = df_filtered_archive[df_filtered_archive['id'].isin(matching_archive_ids)]

    # Фильтрация терминалов
    df_filtered_terminals = df_all_terminals.copy()
    if not df_filtered_terminals.empty:
        if month_filter != "(Все месяцы)":
            df_filtered_terminals = df_filtered_terminals[df_filtered_terminals['period_month'] == month_filter]
        if bank_filter != "(Все банки)":
            df_filtered_terminals = df_filtered_terminals[
                (df_filtered_terminals['archive_bank'] == bank_filter) |
                (df_filtered_terminals['bank_acquirer'] == bank_filter)
            ]
        if tid_filter != "(Все терминалы)":
            df_filtered_terminals = df_filtered_terminals[df_filtered_terminals['terminal_id'] == tid_filter]

    # Экспорт в Excel со всеми вкладками
    buf_excel = io.BytesIO()
    with pd.ExcelWriter(buf_excel, engine="openpyxl") as writer:
        df_exp_archive = df_filtered_archive.drop(columns=['timestamp_dt'], errors='ignore').copy()
        df_exp_archive.to_excel(writer, sheet_name="Сводка_сверок", index=False)
        if not df_filtered_terminals.empty:
            df_filtered_terminals.to_excel(writer, sheet_name="Аналитика_терминалов", index=False)
    
    st.download_button(
        label="📥 Скачать полную аналитику в Excel со всеми вкладками",
        data=buf_excel.getvalue(),
        file_name=f"Аналитика_сверок_и_терминалов_{pd.Timestamp.now():%Y%m%d_%H%M}.xlsx",
        use_container_width=True
    )

    st.markdown("<br>", unsafe_allow_html=True)

    # ─── ВКЛАДКИ КАК В РЕАКТ ───
    tab_banks, tab_terminals = st.tabs([
        f"🏛️ Сводка по банкам и сверкам ({len(df_filtered_archive)})",
        f"📟 Аналитика по терминалам и комиссии EPOS ({len(df_filtered_terminals)})"
    ])

    # ═════════════════════════════════════════════════════════════
    # ВКЛАДКА 1: СВОДКА ПО БАНКАМ И СВЕРКАМ
    # ═════════════════════════════════════════════════════════════
    with tab_banks:
        if df_filtered_archive.empty:
            st.warning("По выбранным критериям не найдено записей в архиве сверок.")
        else:
            # 4 KPI Карточки
            with st.container(border=True):
                tot_recons = len(df_filtered_archive)
                tot_our_vol = df_filtered_archive['total_our'].sum()
                tot_bank_vol = df_filtered_archive['total_bank'].sum()
                tot_comm_arch = df_filtered_archive['total_commission'].sum()
                tot_diff = df_filtered_archive['difference'].sum()
                
                k1, k2, k3, k4 = st.columns(4)
                k1.metric("Всего сверок", tot_recons)
                k2.metric("Объём (Наши данные)", f"{tot_our_vol:,.2f} UZS")
                k3.metric("Объём (Банк)", f"{tot_bank_vol:,.2f} UZS")
                k4.metric(
                    "Комиссия EPOS",
                    f"{tot_comm_arch:,.2f} UZS",
                    delta=f"Δ: {tot_diff:+,.2f} UZS",
                    delta_color="inverse" if abs(tot_diff) > 0.01 else "normal"
                )

            st.markdown("<br>", unsafe_allow_html=True)

            # Графики
            c1, c2 = st.columns(2)
            with c1:
                with st.container(border=True):
                    st.markdown("#### 📊 Динамика сведённых объёмов (Мы vs Банк)")
                    plot_bars = df_filtered_archive.copy().sort_values('timestamp')
                    fig_vol = px.bar(
                        plot_bars,
                        x='date_str',
                        y=['total_our', 'total_bank'],
                        barmode='group',
                        labels={'date_str': 'Дата сверки', 'value': 'Сумма (UZS)', 'variable': 'Источник'},
                        color_discrete_map={'total_our': '#4f46e5', 'total_bank': '#059669'},
                        template="plotly_white"
                    )
                    vol_names = {'total_our': 'Наши данные', 'total_bank': 'Банк'}
                    fig_vol.for_each_trace(lambda t: t.update(name=vol_names.get(t.name, t.name)))
                    st.plotly_chart(fig_vol, use_container_width=True)

            with c2:
                with st.container(border=True):
                    st.markdown("#### 📈 Тренд расхождений (Δ = Банк - Мы)")
                    plot_diff = df_filtered_archive.copy().sort_values('timestamp')
                    fig_diff = px.line(
                        plot_diff,
                        x='date_str',
                        y='difference',
                        markers=True,
                        labels={'date_str': 'Дата сверки', 'difference': 'Разница Δ (UZS)'},
                        template="plotly_white"
                    )
                    fig_diff.update_traces(line_color='#e11d48')
                    fig_diff.add_hline(y=0, line_dash="dash", line_color="#94a3b8")
                    st.plotly_chart(fig_diff, use_container_width=True)

            # Журнал проведённых сверок
            st.markdown("### 📋 Журнал проведённых сверок")
            st.caption("Для удаления отметьте галочкой строку и подтвердите действие кнопкой внизу.")

            df_display = df_filtered_archive.copy()
            df_display.insert(0, "🗑️", False)

            with st.container(border=True):
                edited_df = st.data_editor(
                    df_display,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "🗑️": st.column_config.CheckboxColumn("Удалить", default=False),
                        "id": st.column_config.NumberColumn("ID", width="small"),
                        "timestamp": None,
                        "timestamp_dt": None,
                        "date_str": st.column_config.TextColumn("Дата / Время"),
                        "period_month": st.column_config.TextColumn("Месяц"),
                        "username": "Оператор",
                        "bank_name": "Банк",
                        "total_our": st.column_config.NumberColumn("Сумма (Мы)", format="%,.2f"),
                        "total_bank": st.column_config.NumberColumn("Сумма (Банк)", format="%,.2f"),
                        "difference": st.column_config.NumberColumn("Разница (Δ)", format="%+,.2f"),
                        "total_commission": st.column_config.NumberColumn("Комиссия EPOS", format="%,.2f"),
                        "matched_count": st.column_config.NumberColumn("Совпало"),
                        "mismatch_count": st.column_config.NumberColumn("Δ Сумм"),
                        "only_our_count": st.column_config.NumberColumn("Только у нас"),
                        "only_bank_count": st.column_config.NumberColumn("Только банк"),
                        "terminals_json": None,
                    },
                    disabled=[
                        "id", "date_str", "period_month", "username", "bank_name",
                        "total_our", "total_bank", "difference", "total_commission",
                        "matched_count", "mismatch_count", "only_our_count", "only_bank_count"
                    ]
                )

            # Кнопка удаления
            to_delete = edited_df[edited_df["🗑️"] == True]
            if not to_delete.empty:
                st.warning(f"⚠️ Отмечено для удаления записей: {len(to_delete)}")
                if st.button("🗑️ Подтвердить удаление выбранных записей из архива", type="primary"):
                    user_curr = st.session_state.get("username", "admin")
                    for _, row_del in to_delete.iterrows():
                        delete_archive_record(row_del['id'])
                        log_action(user_curr, "DELETE_ARCHIVE", f"Удалена запись сверки ID {row_del['id']} ({row_del['bank_name']})")
                    st.success("✅ Записи удалены!")
                    st.rerun()

            # Инспекция терминалов конкретной сверки
            with st.expander("🔎 Детальный просмотр терминалов по конкретной сверке"):
                recon_options = {
                    r['id']: f"ID #{r['id']} — {r['bank_name']} ({r['date_str']}) | Месяц: {r['period_month']}"
                    for _, r in df_filtered_archive.iterrows()
                }
                sel_id = st.selectbox(
                    "Выберите сверку для инспекции терминалов:",
                    options=list(recon_options.keys()),
                    format_func=lambda x: recon_options[x]
                )
                if sel_id:
                    rec_row = df_filtered_archive[df_filtered_archive['id'] == sel_id].iloc[0]
                    t_json_rec = rec_row.get('terminals_json', '')
                    if t_json_rec:
                        try:
                            terms_parsed = json.loads(t_json_rec)
                            if terms_parsed:
                                df_ins = pd.DataFrame(terms_parsed)
                                st.dataframe(
                                    df_ins,
                                    use_container_width=True,
                                    hide_index=True,
                                    column_config={
                                        "terminal_id": "TID Терминала",
                                        "bank_acquirer": "Банк-эквайер",
                                        "merchant_id": "MID",
                                        "legal_entity": "Юр. лицо / Точка",
                                        "tx_count": st.column_config.NumberColumn("Сделок"),
                                        "total_volume": st.column_config.NumberColumn("Оборот (UZS)", format="%,.2f"),
                                        "commission_pct": st.column_config.NumberColumn("Ставка %", format="%.2f%%"),
                                        "commission_amount": st.column_config.NumberColumn("Комиссия (UZS)", format="%,.2f"),
                                        "net_volume": st.column_config.NumberColumn("К зачислению (UZS)", format="%,.2f"),
                                    }
                                )
                            else:
                                st.info("В этой сверке нет данных по терминалам.")
                        except Exception as e:
                            st.error(f"Ошибка чтения данных: {e}")
                    else:
                        st.info("В этой сверке нет сохранённых данных по терминалам.")

    # ═════════════════════════════════════════════════════════════
    # ВКЛАДКА 2: АНАЛИТИКА ПО ТЕРМИНАЛАМ И КОМИССИИ EPOS
    # ═════════════════════════════════════════════════════════════
    with tab_terminals:
        if df_filtered_terminals.empty:
            st.info("ℹ️ Данные по терминалам не найдены для выбранных фильтров. Убедитесь, что при сверках колонка TID была заполнена и сохранена в архив.")
        else:
            # Сводные карточки терминалов
            tot_tids = df_filtered_terminals['terminal_id'].nunique()
            tot_tx = df_filtered_terminals['tx_count'].sum()
            tot_vol_term = df_filtered_terminals['total_volume'].sum()
            tot_comm_term = df_filtered_terminals['commission_amount'].sum()
            tot_net_term = df_filtered_terminals['net_volume'].sum()
            avg_rate = (tot_comm_term / tot_vol_term * 100.0) if tot_vol_term > 0 else 0.0

            with st.container(border=True):
                tm1, tm2, tm3, tm4 = st.columns(4)
                tm1.metric("Всего терминалов (TID)", tot_tids, delta=f"{tot_tx:,} транзакций", delta_color="normal")
                tm2.metric("Совокупный оборот терминалов", f"{tot_vol_term:,.2f} UZS")
                tm3.metric("Начислено комиссии эквайринга", f"{tot_comm_term:,.2f} UZS", delta=f"{avg_rate:.2f}% ставка", delta_color="inverse")
                tm4.metric("К зачислению (нетто)", f"{tot_net_term:,.2f} UZS", delta="Оборот минус комиссия", delta_color="normal")

            st.markdown("<br>", unsafe_allow_html=True)

            # График: Топ-10 терминалов по обороту и комиссии
            with st.container(border=True):
                st.markdown("#### 📊 Топ-10 терминалов по обороту и комиссии эквайринга")
                top_terms = df_filtered_terminals.groupby('terminal_id').agg({
                    'total_volume': 'sum',
                    'commission_amount': 'sum'
                }).reset_index().sort_values('total_volume', ascending=False).head(10)
                
                fig_top = px.bar(
                    top_terms,
                    x='terminal_id',
                    y=['total_volume', 'commission_amount'],
                    barmode='group',
                    labels={'terminal_id': 'TID Терминала', 'value': 'Сумма (UZS)', 'variable': 'Показатель'},
                    color_discrete_map={'total_volume': '#4f46e5', 'commission_amount': '#e11d48'},
                    template="plotly_white"
                )
                t_names = {'total_volume': 'Оборот терминала', 'commission_amount': 'Комиссия банка'}
                fig_top.for_each_trace(lambda t: t.update(name=t_names.get(t.name, t.name)))
                st.plotly_chart(fig_top, use_container_width=True)

            # Таблица терминалов с быстрым поиском
            st.markdown("### 📋 Детализированный реестр по терминалам")
            search_query = st.text_input("🔍 Быстрый поиск по TID, мерчанту или юр. лицу:", placeholder="Введите TID или название точки...")

            df_table_terms = df_filtered_terminals.copy()
            if search_query.strip():
                q = search_query.strip().lower()
                df_table_terms = df_table_terms[
                    df_table_terms['terminal_id'].str.lower().str.contains(q, na=False) |
                    df_table_terms['merchant_id'].str.lower().str.contains(q, na=False) |
                    df_table_terms['legal_entity'].str.lower().str.contains(q, na=False)
                ]

            with st.container(border=True):
                st.dataframe(
                    df_table_terms[[
                        'terminal_id', 'bank_acquirer', 'merchant_id', 'legal_entity',
                        'period_month', 'tx_count', 'total_volume', 'commission_pct',
                        'commission_amount', 'net_volume', 'date_str'
                    ]],
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "terminal_id": "TID Терминала",
                        "bank_acquirer": "Банк-эквайер",
                        "merchant_id": "MID",
                        "legal_entity": "Юр. лицо / Точка",
                        "period_month": st.column_config.TextColumn("Месяц"),
                        "tx_count": st.column_config.NumberColumn("Сделок"),
                        "total_volume": st.column_config.NumberColumn("Оборот (UZS)", format="%,.2f"),
                        "commission_pct": st.column_config.NumberColumn("Ставка %", format="%.2f%%"),
                        "commission_amount": st.column_config.NumberColumn("Комиссия (UZS)", format="%,.2f"),
                        "net_volume": st.column_config.NumberColumn("К зачислению (UZS)", format="%,.2f"),
                        "date_str": st.column_config.TextColumn("Дата фиксации"),
                    }
                )
