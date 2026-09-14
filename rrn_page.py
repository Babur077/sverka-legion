import streamlit as st
import pandas as pd
import io
import datetime as dt_mod

# Импортируем ядро и парсеры
from core.parsers import load_file_polars, guess_col
from core.recon_engine import run_rrn_reconciliation
from utils.db_manager import get_active_banks, get_epos_registry, save_reconciliation, log_action

# Оптимизированная UI-функция загрузки с кэшированием в сессии
def upload_with_preview(label: str, key: str):
    f = st.file_uploader(label, type=["xlsx", "xls", "csv"], key=key, label_visibility="collapsed")
    
    if f is not None:
        if st.session_state.get(f"name_cache_{key}") != f.name:
            file_bytes = f.getvalue()
            df_pl = load_file_polars(f.name, file_bytes)
            st.session_state[f"df_cache_{key}"] = df_pl
            st.session_state[f"name_cache_{key}"] = f.name
            st.session_state[f"preview_{key}"] = df_pl.head(5).to_pandas()
    
    cached_df = st.session_state.get(f"df_cache_{key}")
    cached_name = st.session_state.get(f"name_cache_{key}")
    
    if cached_df is not None:
        c_info, c_btn = st.columns([3, 1])
        with c_info:
            st.markdown(f"<div style='font-size:12px; color:#475569; margin-top:6px;'>📄 <strong>{cached_name or 'Загружен файл'}</strong> ({len(cached_df)} строк, {len(cached_df.columns)} колонок)</div>", unsafe_allow_html=True)
        with c_btn:
            if st.button("✕ Сброс", key=f"reset_{key}", use_container_width=True):
                st.session_state.pop(f"df_cache_{key}", None)
                st.session_state.pop(f"name_cache_{key}", None)
                st.session_state.pop(f"preview_{key}", None)
                st.rerun()

        if f"preview_{key}" in st.session_state:
            with st.expander("👁 Предпросмотр данных", expanded=False):
                st.dataframe(st.session_state[f"preview_{key}"], use_container_width=True, hide_index=True)
                
        return cached_df

    return None


def load_demo_data_to_session():
    """Создает демонстрационные датасеты 1С и Выписки банка для мгновенной проверки."""
    import polars as pl
    dates = ["10.09.2026", "11.09.2026", "12.09.2026"]
    tids = ["98234011", "98234012", "98234013", "98234014"]

    our_data = []
    bank_data = []

    for i in range(1, 26):
        date = dates[i % len(dates)]
        rrn = f"9482019{1000 + i}"
        base_amt = float((i * 75000) + 120000)
        tid = tids[i % len(tids)]

        our_data.append({
            "Дата": date,
            "Ключ RRN": rrn,
            "Сумма платежа": base_amt,
            "Статус": "Оплачено"
        })
        bank_data.append({
            "Дата проводки": date,
            "Код RRN": rrn,
            "Сумма банка": base_amt,
            "Статус операции": "SUCCESS",
            "Терминал TID": tid
        })

    # Возврат в нашей системе и в банке
    our_data.append({
        "Дата": "12.09.2026",
        "Ключ RRN": "94820191099",
        "Сумма платежа": 450000.0,
        "Статус": "Возврат клиенту"
    })
    bank_data.append({
        "Дата проводки": "12.09.2026",
        "Код RRN": "94820191099",
        "Сумма банка": 450000.0,
        "Статус операции": "REFUND",
        "Терминал TID": "98234011"
    })

    # Не сошлась сумма (расхождение)
    our_data.append({
        "Дата": "10.09.2026",
        "Ключ RRN": "94820191088",
        "Сумма платежа": 150000.0,
        "Статус": "Оплачено"
    })
    bank_data.append({
        "Дата проводки": "10.09.2026",
        "Код RRN": "94820191088",
        "Сумма банка": 145000.0,
        "Статус операции": "SUCCESS",
        "Терминал TID": "98234013"
    })

    # Только у нас
    our_data.append({
        "Дата": "11.09.2026",
        "Ключ RRN": "94820192001",
        "Сумма платежа": 320000.0,
        "Статус": "Оплачено"
    })

    # Только в банке
    bank_data.append({
        "Дата проводки": "11.09.2026",
        "Код RRN": "94820192002",
        "Сумма банка": 280000.0,
        "Статус операции": "SUCCESS",
        "Терминал TID": "98234012"
    })

    pl_our = pl.DataFrame(our_data)
    pl_bank = pl.DataFrame(bank_data)

    st.session_state["df_cache_our_v2"] = pl_our
    st.session_state["name_cache_our_v2"] = "1C_Выгрузка_Сентябрь.xlsx"
    st.session_state["preview_our_v2"] = pl_our.head(5).to_pandas()

    st.session_state["df_cache_bank_v2"] = pl_bank
    st.session_state["name_cache_bank_v2"] = "Выписка_AloqaBank.xlsx"
    st.session_state["preview_bank_v2"] = pl_bank.head(5).to_pandas()

    st.session_state["chosen_bank"] = "Aloqa Bank"


# ─── ИНТЕРФЕЙС СТРАНИЦЫ ───
def show_page():
    is_auditor = (st.session_state.get("role") == "auditor")
    
    if is_auditor:
        st.warning("🔒 **Режим аудитора (Только чтение)**: Вам доступен просмотр данных, параметров сверки и экспорт отчетов в Excel. Ручное редактирование статусов строк и сохранение результатов в архив БД заблокированы.")

    # Хедер с бейджем и кнопкой демо-данных точно как в Preview
    col_t, col_b = st.columns([2.6, 1.8])
    with col_t:
        st.markdown("""
        <div style='margin-bottom: 20px;'>
            <div style='display: flex; align-items: center; gap: 8px;'>
                <h1 style='font-size: 26px; font-weight: 700; color: #0f172a; margin: 0; padding: 0;'>Сверка по RRN</h1>
                <span style='font-size: 11px; font-weight: 600; padding: 3px 8px; border-radius: 9999px; background: #eef2ff; color: #4338ca; border: 1px solid #c7d2fe;'>
                    EPOS Core
                </span>
            </div>
            <p style='color: #64748b; font-size: 13.5px; margin-top: 4px; margin-bottom: 0;'>
                Потранзакционная сверка с автоматическим расчётом комиссий на базе реестра EPOS.
            </p>
        </div>
        """, unsafe_allow_html=True)
    with col_b:
        st.markdown("<div style='height: 4px;'></div>", unsafe_allow_html=True)
        btn_c1, btn_c2 = st.columns(2)
        with btn_c1:
            if st.button("✨ Демо-файлы", use_container_width=True, key="btn_load_demo_rrn", help="Загрузить тестовые файлы 1С и Банка"):
                load_demo_data_to_session()
                st.rerun()
        with btn_c2:
            if st.button("🔄 Сбросить", use_container_width=True, key="btn_reset_rrn", help="Очистить загруженные файлы и результаты"):
                for k in ["df_cache_our_v2", "name_cache_our_v2", "preview_our_v2", 
                          "df_cache_bank_v2", "name_cache_bank_v2", "preview_bank_v2", 
                          "res", "ed_our_v2", "ed_bank_v2"]:
                    if k in st.session_state:
                        del st.session_state[k]
                st.rerun()

    # ─── БЫСТРЫЙ ВЫБОР БАНКА-ЭКВАЙЕРА (Динамически из реестра EPOS) ───
    with st.container(border=True):
        st.markdown("""
        <div style='display: flex; align-items: center; gap: 8px; font-weight: 600; font-size: 14px; color: #0f172a; margin-bottom: 6px;'>
            <span style='color: #4f46e5; font-size: 16px;'>🏦</span>
            <span>Банк-эквайер для сверки</span>
        </div>
        """, unsafe_allow_html=True)
        
        active_banks = get_active_banks()
        bank_list = active_banks + ["Другой банк (ввести вручную)..."]
        cur_bank = st.session_state.get("chosen_bank", active_banks[0] if active_banks else "Aloqa Bank")
        
        idx = bank_list.index(cur_bank) if cur_bank in bank_list else 0
        selected_b = st.selectbox("Выберите банк из реестра или введите новый", bank_list, index=idx, key="sb_quick_bank")
        
        if selected_b == "Другой банк (ввести вручную)...":
            custom_bank_name = st.text_input("Название нового банка*", value="" if cur_bank in bank_list else cur_bank, placeholder="напр. Agrobank")
            if custom_bank_name.strip():
                st.session_state["chosen_bank"] = custom_bank_name.strip()
        else:
            st.session_state["chosen_bank"] = selected_b

    bank_name = st.session_state.get("chosen_bank", "Aloqa Bank")

    # Две отдельные карточки загрузки файлов точно как в Preview
    c1, c2 = st.columns(2)
    with c1:
        with st.container(border=True):
            st.markdown("""
            <div style='display: flex; align-items: center; gap: 8px; font-weight: 600; font-size: 14px; color: #0f172a; margin-bottom: 8px;'>
                <span style='color: #4f46e5; font-size: 16px;'>↑</span>
                <span>Ваши данные (Excel / CSV)</span>
            </div>
            """, unsafe_allow_html=True)
            df_our_raw = upload_with_preview("Ваши данные (Excel / CSV)", "our_v2")

    with c2:
        with st.container(border=True):
            st.markdown(f"""
            <div style='display: flex; align-items: center; gap: 8px; font-weight: 600; font-size: 14px; color: #0f172a; margin-bottom: 8px;'>
                <span style='color: #059669; font-size: 16px;'>↑</span>
                <span>Данные {bank_name} (Excel / CSV)</span>
            </div>
            """, unsafe_allow_html=True)
            df_bank_raw = upload_with_preview(f"Данные {bank_name} (Excel / CSV)", "bank_v2")

    if df_our_raw is not None and df_bank_raw is not None:
        with st.container(border=True):
            st.markdown("### Настройка колонок")
            
            df_our_pd, df_bank_pd = df_our_raw.to_pandas(), df_bank_raw.to_pandas()
            t1, t2 = st.tabs(["Ваши данные", "Данные банка"])
            
            # Селектор колонок для НАШИХ данных
            with t1:
                cols_o = list(df_our_pd.columns)
                ca, cb = st.columns(2)
                with ca:
                    our_date = st.selectbox("Дата", cols_o, index=cols_o.index(guess_col(df_our_pd, ["date","дата"])) if guess_col(df_our_pd, ["date","дата"]) else 0, key="our_d")
                    our_rrn = st.selectbox("RRN", cols_o, index=cols_o.index(guess_col(df_our_pd, ["rrn","ref"])) if guess_col(df_our_pd, ["rrn","ref"]) else 0, key="our_r")
                with cb:
                    _amt_o = guess_col(df_our_pd, ["amount","сумма"])
                    our_amt = st.selectbox("Сумма", ["(нет)"] + cols_o, index=cols_o.index(_amt_o)+1 if _amt_o else 0, key="our_a")
                    our_status = st.selectbox("Статус", ["(нет)"] + cols_o, key="our_s")

            # Селектор колонок для БАНКА
            with t2:
                cols_b = list(df_bank_pd.columns)
                ca2, cb2, cc2 = st.columns(3)
                with ca2:
                    bank_date = st.selectbox("Дата", cols_b, index=cols_b.index(guess_col(df_bank_pd, ["date","дата"])) if guess_col(df_bank_pd, ["date","дата"]) else 0, key="bank_d")
                    bank_rrn = st.selectbox("RRN", cols_b, index=cols_b.index(guess_col(df_bank_pd, ["rrn","ref"])) if guess_col(df_bank_pd, ["rrn","ref"]) else 0, key="bank_r")
                with cb2:
                    _amt_b = guess_col(df_bank_pd, ["amount","сумма"])
                    bank_amt = st.selectbox("Сумма", ["(нет)"] + cols_b, index=cols_b.index(_amt_b)+1 if _amt_b else 0, key="bank_a")
                    bank_status = st.selectbox("Статус", ["(нет)"] + cols_b, key="bank_s")
                with cc2:
                    _tid_b = guess_col(df_bank_pd, ["tid","terminal","терминал"])
                    bank_tid = st.selectbox("Terminal ID (TID)", ["(нет)"] + cols_b, index=cols_b.index(_tid_b)+1 if _tid_b else 0, key="bank_t", help="Связывает транзакцию с Реестром EPOS")

            our_amt = None if our_amt == "(нет)" else our_amt
            our_status = None if our_status == "(нет)" else our_status
            bank_amt = None if bank_amt == "(нет)" else bank_amt
            bank_tid = None if bank_tid == "(нет)" else bank_tid
            bank_status = None if bank_status == "(нет)" else bank_status

            # --- БЛОК ЛОГИКИ ОБРАБОТКИ ---
            st.markdown("### 🛠 Правила обработки")
            
            with st.expander("⚙️ Расширенные настройки сверки", expanded=True):
                st.markdown("#### 1️⃣ Обработка возвратов")
                rev_input = st.text_input(
                    "Маркеры возврата в колонке «Статус» (через запятую):", 
                    "reversed, возврат, refund, отказ, ошибка"
                )
                rev_words = [w.strip().lower() for w in rev_input.split(",") if w.strip()]
                st.session_state["rev_words"] = rev_words
                
                ra, rb = st.columns(2)
                with ra:
                    our_rev = st.radio("В НАШИХ данных:", 
                        ["➖ Минусовать сумму", "🗑 Удалить строку", "💥 Удалить RRN полностью", "⚪ Не обрабатывать"], 
                        index=0, key="rev_our"
                    )
                with rb:
                    bank_rev = st.radio("В данных БАНКА:", 
                        ["➖ Минусовать сумму", "🗑 Удалить строку", "💥 Удалить RRN полностью", "⚪ Не обрабатывать"], 
                        index=1, key="rev_bank"
                    )

                st.divider()
                st.markdown("#### 2️⃣ Дубликаты RRN")
                dup_action = st.radio(
                    "Действие при обнаружении дублей:",
                    ["Ничего не делать (оставить все)", "Оставить первую строку", "Оставить последнюю строку", "Удалить все дубли (и оригинал)"],
                    index=0,
                    horizontal=True
                )

                st.divider()
                st.markdown("#### 3️⃣ Строгое соответствие сумм")
                st.checkbox(
                    "💔 Разрывать связи при расхождении сумм", 
                    value=False,
                    key="unbind_mismatches",
                    help="Транзакции с одинаковым RRN, но разной суммой (вне допуска), будут разделены и попадут в 'Нет в банке' и 'Лишние от банка'."
                )

        # Вызов нашего ядра через единую функцию
        if st.button("🚀 Запустить сверку", type="primary", use_container_width=True, key="run_rrn_btn"):
            with st.status("Анализ данных запущен...", expanded=True) as status:
                
                config = {
                    "our_date": our_date, "our_rrn": our_rrn, "our_amt": our_amt, "our_status": our_status,
                    "bank_date": bank_date, "bank_rrn": bank_rrn, "bank_amt": bank_amt, "bank_tid": bank_tid, "bank_status": bank_status,
                    "rev_words": rev_words, "our_rev": our_rev, "bank_rev": bank_rev,
                    "dup_action": dup_action, 
                    "unbind_mismatches": st.session_state.get("unbind_mismatches", False),
                    "tolerance": st.session_state["settings"]["amount_tolerance"]
                }
                
                st.session_state["res"] = run_rrn_reconciliation(df_our_raw, df_bank_raw, config)
                status.update(label="Сверка успешно завершена!", state="complete", expanded=False)

    # ─── РЕЗУЛЬТАТЫ СВЕРКИ (Отображение интерфейса) ───
    if "res" in st.session_state:
        data = st.session_state["res"]
        st.markdown("---")

        dash_ph = st.container()

        tabs = st.tabs([
            "Сводка по датам",
            "Графики",
            f"Несопоставленные ({len(data.get('only_our', [])) + len(data.get('only_bank', []))})",
            f"Расхождения сумм ({data.get('mismatch_count', 0)})",
            f"Дубликаты ({data.get('dup_our_c', 0) + data.get('dup_bank_c', 0)})",
        ])

        num_cfg = lambda lbl: st.column_config.NumberColumn(lbl, format="%,.2f")
        REASON_OPTIONS = ["", "Тестовая транзакция", "Ожидает расчёта", "Спор / Chargeback", "Системная ошибка", "Ошибка загрузки данных", "Технический возврат", "Другое"]
        
        def find_offsetting_rrns_by_status(df, status_col, rev_words_list):
            if df.empty or "RRN" not in df.columns or not status_col or status_col not in df.columns: return []
            active_df = df[df["✅"] == True].copy()
            if active_df.empty: return []
            active_df["_is_reversal"] = active_df[status_col].apply(lambda x: any(w in str(x).lower().strip() for w in rev_words_list))
            grouped = active_df.groupby("RRN").agg(has_normal=("_is_reversal", lambda x: (x == False).any()), has_reversal=("_is_reversal", lambda x: (x == True).any()))
            return grouped[grouped["has_normal"] & grouped["has_reversal"]].index.tolist()

        with tabs[2]:
            st.info("💡 Здесь собраны все несопоставленные транзакции. Вы можете управлять галочками и указывать причины раздельно для каждой панели.")
            
            col_left, col_right = st.columns(2)
            
            with col_left:
                st.markdown(f"### 🔴 Отсутствуют в банке ({len(data['only_our'])})")
                df_target_our = st.session_state["res"]["only_our"]
                
                with st.expander("🛠 Массовое управление (Наши данные)", expanded=False):
                    has_date_our = "date_unified" in df_target_our.columns
                    dates_opts_our = ["(Все)"]
                    if has_date_our: dates_opts_our += list(pd.to_datetime(df_target_our["date_unified"], errors="coerce").dt.strftime("%d.%m.%Y").dropna().unique())
                    
                    stat_col_our = "status_our" if "status_our" in df_target_our.columns else None
                    stat_opts_our = ["(Все)"]
                    if stat_col_our: stat_opts_our += list(df_target_our[stat_col_our].dropna().astype(str).unique())

                    c_d, c_s = st.columns(2)
                    ex_date_our = c_d.selectbox("Фильтр по дате (Наши):", dates_opts_our, key="bulk_d_our")
                    ex_stat_our = c_s.selectbox("Фильтр по статусу (Наши):", stat_opts_our, key="bulk_s_our")
                    
                    c_b1, c_b2 = st.columns(2)
                    if c_b1.button("➖ Снять ✅ (Наши)", use_container_width=True, key="btn_rem_our"):
                        mask = pd.Series(True, index=df_target_our.index)
                        if has_date_our and ex_date_our != "(Все)": mask &= (pd.to_datetime(df_target_our["date_unified"], errors="coerce").dt.strftime("%d.%m.%Y") == ex_date_our)
                        if stat_col_our and ex_stat_our != "(Все)": mask &= (df_target_our[stat_col_our].astype(str) == ex_stat_our)
                        st.session_state["res"]["only_our"].loc[mask, "✅"] = False
                        if "ed_our_v2" in st.session_state: del st.session_state["ed_our_v2"] 
                        st.rerun()

                    if c_b2.button("➕ Вернуть ✅ (Наши)", use_container_width=True, key="btn_add_our"):
                        mask = pd.Series(True, index=df_target_our.index)
                        if has_date_our and ex_date_our != "(Все)": mask &= (pd.to_datetime(df_target_our["date_unified"], errors="coerce").dt.strftime("%d.%m.%Y") == ex_date_our)
                        if stat_col_our and ex_stat_our != "(Все)": mask &= (df_target_our[stat_col_our].astype(str) == ex_stat_our)
                        st.session_state["res"]["only_our"].loc[mask, "✅"] = True
                        if "ed_our_v2" in st.session_state: del st.session_state["ed_our_v2"]
                        st.rerun()

                    st.divider()
                    st.markdown("##### 🔄 Автоматическая компенсация (Офсеты)")
                    status_col_our = "status_our" if "status_our" in df_target_our.columns else None
                    active_rev_words = st.session_state.get("rev_words", ["reversed", "возврат", "refund", "отказ", "ошибка"])
                    offset_rrns_our = find_offsetting_rrns_by_status(df_target_our, status_col_our, active_rev_words)
                    if offset_rrns_our:
                        st.warning(f"Найдено **{len(offset_rrns_our)}** компенсирующих RRN.")
                        if st.button("🪄 Исключить компенсирующие пары (Наши)", use_container_width=True, key="btn_offset_our"):
                            mask = st.session_state["res"]["only_our"]["RRN"].isin(offset_rrns_our)
                            st.session_state["res"]["only_our"].loc[mask, "✅"] = False
                            st.session_state["res"]["only_our"].loc[mask, "📝 Причина"] = "Технический возврат"
                            if "ed_our_v2" in st.session_state: del st.session_state["ed_our_v2"]
                            st.success("Компенсирующие транзакции исключены!")
                            st.rerun()
                    else:
                        st.info("ℹ️ Компенсирующих транзакций по статусу не обнаружено.")

                show_cols_our = ["✅", "date_str", "RRN", "net_amount_our", "📝 Причина"]
                if "status_our" in df_target_our.columns: show_cols_our.append("status_our")

                disabled_our = show_cols_our if is_auditor else [c for c in show_cols_our if c not in ["✅","📝 Причина"]]
                edited_only_our = st.data_editor(
                    st.session_state["res"]["only_our"][show_cols_our],
                    column_config={
                        "✅": st.column_config.CheckboxColumn("Вкл.", default=True, width="small"),
                        "📝 Причина": st.column_config.SelectboxColumn("Причина", options=REASON_OPTIONS, width="medium"),
                        "RRN": st.column_config.TextColumn("RRN"),
                        "net_amount_our": num_cfg("Сумма"),
                    },
                    disabled=disabled_our,
                    use_container_width=True, hide_index=True, key="ed_our_v2",
                )
                if not is_auditor:
                    st.session_state["res"]["only_our"]["✅"] = edited_only_our["✅"]
                    st.session_state["res"]["only_our"]["📝 Причина"] = edited_only_our["📝 Причина"]

            with col_right:
                st.markdown(f"### 🔵 Лишние данные банка ({len(data['only_bank'])})")
                df_target_bank = st.session_state["res"]["only_bank"]
                
                with st.expander("🛠 Массовое управление (Данные банка)", expanded=False):
                    has_date_bank = "date_unified" in df_target_bank.columns
                    dates_opts_bank = ["(Все)"]
                    if has_date_bank: dates_opts_bank += list(pd.to_datetime(df_target_bank["date_unified"], errors="coerce").dt.strftime("%d.%m.%Y").dropna().unique())
                    
                    stat_col_bank = "status_bank" if "status_bank" in df_target_bank.columns else None
                    stat_opts_bank = ["(Все)"]
                    if stat_col_bank: stat_opts_bank += list(df_target_bank[stat_col_bank].dropna().astype(str).unique())

                    c_d_b, c_s_b = st.columns(2)
                    ex_date_bank = c_d_b.selectbox("Фильтр по дате (Банк):", dates_opts_bank, key="bulk_d_bank")
                    ex_stat_bank = c_s_b.selectbox("Фильтр по статусу (Банк):", stat_opts_bank, key="bulk_s_bank")
                    
                    c_b1_b, c_b2_b = st.columns(2)
                    if c_b1_b.button("➖ Снять ✅ (Банк)", use_container_width=True, key="btn_rem_bank"):
                        mask = pd.Series(True, index=df_target_bank.index)
                        if has_date_bank and ex_date_bank != "(Все)": mask &= (pd.to_datetime(df_target_bank["date_unified"], errors="coerce").dt.strftime("%d.%m.%Y") == ex_date_bank)
                        if stat_col_bank and ex_stat_bank != "(Все)": mask &= (df_target_bank[stat_col_bank].astype(str) == ex_stat_bank)
                        st.session_state["res"]["only_bank"].loc[mask, "✅"] = False
                        if "ed_bank_v2" in st.session_state: del st.session_state["ed_bank_v2"]
                        st.rerun()

                    if c_b2_b.button("➕ Вернуть ✅ (Банк)", use_container_width=True, key="btn_add_bank"):
                        mask = pd.Series(True, index=df_target_bank.index)
                        if has_date_bank and ex_date_bank != "(Все)": mask &= (pd.to_datetime(df_target_bank["date_unified"], errors="coerce").dt.strftime("%d.%m.%Y") == ex_date_bank)
                        if stat_col_bank and ex_stat_bank != "(Все)": mask &= (df_target_bank[stat_col_bank].astype(str) == ex_stat_bank)
                        st.session_state["res"]["only_bank"].loc[mask, "✅"] = True
                        if "ed_bank_v2" in st.session_state: del st.session_state["ed_bank_v2"]
                        st.rerun()

                    st.divider()
                    st.markdown("##### 🔄 Автоматическая компенсация (Офсеты)")
                    status_col_bank = "status_bank" if "status_bank" in df_target_bank.columns else None
                    active_rev_words = st.session_state.get("rev_words", ["reversed", "возврат", "refund", "отказ", "ошибка"])
                    offset_rrns_bank = find_offsetting_rrns_by_status(df_target_bank, status_col_bank, active_rev_words)
                    if offset_rrns_bank:
                        st.warning(f"Найдено **{len(offset_rrns_bank)}** компенсирующих RRN.")
                        if st.button("🪄 Исключить компенсирующие пары (Банк)", use_container_width=True, key="btn_offset_bank"):
                            mask = st.session_state["res"]["only_bank"]["RRN"].isin(offset_rrns_bank)
                            st.session_state["res"]["only_bank"].loc[mask, "✅"] = False
                            st.session_state["res"]["only_bank"].loc[mask, "📝 Причина"] = "Технический возврат"
                            if "ed_bank_v2" in st.session_state: del st.session_state["ed_bank_v2"]
                            st.success("Компенсирующие транзакции исключены!")
                            st.rerun()
                    else:
                        st.info("ℹ️ Компенсирующих транзакций по статусу не обнаружено.")

                show_cols_bank = ["✅", "date_str", "RRN", "net_amount_bank", "📝 Причина"]
                if "status_bank" in df_target_bank.columns: show_cols_bank.append("status_bank")

                disabled_bank = show_cols_bank if is_auditor else [c for c in show_cols_bank if c not in ["✅","📝 Причина"]]
                edited_only_bank = st.data_editor(
                    st.session_state["res"]["only_bank"][show_cols_bank],
                    column_config={
                        "✅": st.column_config.CheckboxColumn("Вкл.", default=True, width="small"),
                        "📝 Причина": st.column_config.SelectboxColumn("Причина", options=REASON_OPTIONS, width="medium"),
                        "RRN": st.column_config.TextColumn("RRN"),
                        "net_amount_bank": num_cfg("Сумма"),
                    },
                    disabled=disabled_bank,
                    use_container_width=True, hide_index=True, key="ed_bank_v2",
                )
                if not is_auditor:
                    st.session_state["res"]["only_bank"]["✅"] = edited_only_bank["✅"]
                    st.session_state["res"]["only_bank"]["📝 Причина"] = edited_only_bank["📝 Причина"]

        with tabs[3]:
            if st.session_state.get("unbind_mismatches", False):
                st.info("ℹ️ Опция «Разрывать связи при расхождении сумм» активна. Все транзакции с разницей в суммах были автоматически разделены и перенесены во вкладку «Несопоставленные» (как отсутствующие в банке и лишние данные банка).")
            elif data["amt_mismatches"].empty:
                st.success(f"🎉 Нет расхождений в суммах! Все сопоставлённые RRN имеют идентичные суммы.")
            else:
                total_delta = float(data["amt_mismatches"]["Δ сумма"].sum())
                c1, c2 = st.columns(2)
                c1.metric(f"Транзакций с расхождением суммы", data["mismatch_count"])
                c2.metric(f"Суммарная разница", f"{total_delta:+,.2f}")
                disp = data["amt_mismatches"].drop(columns=["_merge"], errors="ignore")
                st.dataframe(disp, use_container_width=True, hide_index=True, column_config={
                    "RRN": st.column_config.TextColumn("RRN"),
                    "net_amount_our": num_cfg("Сумма (Мы)"),
                    "net_amount_bank": num_cfg("Сумма (Банк)"),
                    "Δ сумма": st.column_config.NumberColumn("Δ Разница", format="%+,.2f"),
                })

        with tabs[4]:
            if "Оставить" in data["dup_action"]:
                c1, c2 = st.columns(2)
                fc = {"RRN": st.column_config.TextColumn("RRN"), "amount": num_cfg("Сумма"), "net_amount": num_cfg("Чистая сумма")}
                with c1:
                    st.markdown("##### 🔴 Дубликаты RRN (Наши)")
                    if data["dup_our_c"] > 0: st.dataframe(data["dups_our"], hide_index=True, use_container_width=True, column_config=fc)
                    else: st.success("Нет")
                with c2:
                    st.markdown("##### 🔵 Дубликаты RRN (Банк)")
                    if data["dup_bank_c"] > 0: st.dataframe(data["dups_bank"], hide_index=True, use_container_width=True, column_config=fc)
                    else: st.success("Нет")
            else:
                st.info("Дубликаты удалены автоматически.")

        # ── Dynamic recalculation ─────────────────────────
        adj = data["summary"][~data["summary"]["date"].str.contains("ИТОГО")].copy()
        
        ig_our = edited_only_our[~edited_only_our["✅"]].copy()
        ig_bank = edited_only_bank[~edited_only_bank["✅"]].copy()

        def subtract_exclusions(adj_df, ig_df, cnt_col, sum_col, amt_col):
            if ig_df.empty or amt_col not in ig_df.columns: return adj_df
            ig_df = ig_df.copy()
            agg = ig_df.groupby("date_str").agg(_c=("RRN","count"), _s=(amt_col,"sum"))
            adj_df = adj_df.set_index("date")
            adj_df[cnt_col] = adj_df[cnt_col].sub(agg["_c"], fill_value=0)
            adj_df[sum_col] = adj_df[sum_col].sub(agg["_s"], fill_value=0)
            return adj_df.reset_index()

        adj = subtract_exclusions(adj, ig_our, "Кол_во_у_нас", "Сумма_у_нас", "net_amount_our")
        adj = subtract_exclusions(adj, ig_bank, "Кол_во_в_банке", "Сумма_в_банке", "net_amount_bank")
        adj["Δ суммы"] = adj["Сумма_в_банке"] - adj["Сумма_у_нас"]
        adj["Δ кол-во"] = adj["Кол_во_в_банке"] - adj["Кол_во_у_нас"]

        adj_tot_our = float(adj["Сумма_у_нас"].sum())
        adj_tot_bank = float(adj["Сумма_в_банке"].sum())
        adj_diff = adj_tot_bank - adj_tot_our

        total_adj = pd.DataFrame([{
            "date": "📊 ИТОГО (с учётом исключений)",
            "Кол_во_у_нас": adj["Кол_во_у_нас"].sum(),
            "Кол_во_в_банке": adj["Кол_во_в_банке"].sum(),
            "Δ кол-во": adj["Δ кол-во"].sum(),
            "Сумма_у_нас": adj_tot_our,
            "Сумма_в_банке": adj_tot_bank,
            "Δ суммы": adj_diff,
        }])
        adj_full = pd.concat([adj, total_adj], ignore_index=True)

        # Выстраиваем колонки: Данные Банка -> Разница (посередине) -> Наши данные
        col_order = ["date", "Кол_во_в_банке", "Сумма_в_банке", "Δ суммы", "Δ кол-во", "Кол_во_у_нас", "Сумма_у_нас"]
        adj_full = adj_full[[c for c in col_order if c in adj_full.columns]]

        # ── Dashboard ─────────────────────────────────────
        total_txns = data["matched_count"] + len(data["only_our"]) + len(data["only_bank"])
        recon_rate = data["matched_count"] / max(total_txns, 1) * 100
        cur = st.session_state["settings"].get("currency", "UZS")
        tol = float(st.session_state["settings"].get("amount_tolerance", 0.01))

        with dash_ph:
            if data["matched_count"] == 0: st.error("🚨 Ни одного совпадения по RRN!")
            elif abs(adj_diff) <= tol: st.success(f"✅ Сверка сошлась! Разница в пределах допуска ({tol:,.2f} {cur})")
            else:
                ex_str = ""
                if len(ig_our) or len(ig_bank): ex_str = f" | Исключено: {len(ig_our)} (нас) + {len(ig_bank)} (банк)"
                st.warning(f"⚠️ Расхождение: **{adj_diff:+,.2f} {cur}**{ex_str}")

            col_info, col_comm = st.columns([3, 1])
            with col_comm:
                comm_pct = st.number_input("🏷️ Комиссия (%)", min_value=0.0, max_value=100.0, value=0.0, step=0.05, format="%.2f", key="comm_pct_v2")
                # ИСПРАВЛЕНО: раньше не было пояснения, из-за чего легко спутать это поле
                # с комиссией, уже вычтенной по реестру EPOS (net_amount_bank), и посчитать
                # комиссию дважды. Это отдельный ручной калькулятор "что если", а не то же самое.
                st.caption("ℹ️ Это доп. расчёт «что если» поверх итоговых сумм. Если по TID уже задана комиссия в реестре EPOS — она уже вычтена из «Итого (Банк)» ниже; используйте это поле только для симуляции другой ставки.")

            m1, m2, m3, m4, m5 = st.columns([1.1, 1.1, 1.1, 0.9, 0.8])
            def fmt_num(v, decimals=2): return f"{float(v):,.{decimals}f}"
            
            m1.metric(f"Итого (Мы), {cur}", fmt_num(adj_tot_our))
            m2.metric(f"Итого (Банк), {cur}", fmt_num(adj_tot_bank))
            m3.metric("Разница", f"{adj_diff:+,.2f}", delta=f"{adj_diff:+,.2f}", delta_color="normal" if abs(adj_diff) <= tol else "inverse")
            m4.metric("Совпало / Расх. сумм", f"{data.get('matched_count', 0):,} / {data.get('mismatch_count', 0)}", 
                      delta="Проверьте" if data.get('mismatch_count', 0) > 0 else "OK", 
                      delta_color="inverse" if data.get('mismatch_count', 0) > 0 else "normal")
            m5.metric("Совпадение", f"{recon_rate:.1f}%", delta="Отлично" if recon_rate >= 95 else ("Хорошо" if recon_rate >= 80 else "Низкий"), delta_color="normal" if recon_rate >= 80 else "inverse")

            if comm_pct > 0:
                comm_our = adj_tot_our * (comm_pct / 100.0)
                net_our = adj_tot_our - comm_our
                comm_bank = adj_tot_bank * (comm_pct / 100.0)
                net_bank = adj_tot_bank - comm_bank

                st.markdown(f"<div style='background: rgba(255, 255, 255, 0.03); border: 1px dashed rgba(255, 255, 255, 0.1); border-radius: 8px; padding: 12px; margin-top: 15px; margin-bottom: 10px;'><span style='font-size: 0.8rem; font-weight: bold; color: #94a3b8; letter-spacing: 0.05em;'>💸 РАСЧЁТ КОМИССИИ С УЧЁТОМ {fmt_num(comm_pct)}%</span></div>", unsafe_allow_html=True)
                mc1, mc2, mc3, mc4 = st.columns(4)
                mc1.metric("Комиссия (Мы)", fmt_num(comm_our))
                mc2.metric("Чистыми (Мы)", fmt_num(net_our))
                mc3.metric("Комиссия (Банк)", fmt_num(comm_bank))
                mc4.metric("Чистыми (Банк)", fmt_num(net_bank))

        # ── Summary tab ───────────────────────────────────
        with tabs[0]:
            st.caption("💡 Нажмите на строку таблицы — увидите детализацию за этот день.")
            def highlight_delta(val):
                try:
                    f = float(val)
                    if abs(f) > tol: return "color:#b91c1c;font-weight:700"
                    if abs(f) <= tol and f != 0: return "color:#15803d"
                except Exception: pass
                return ""
                
            fmt_s = {c: "{:,.2f}" for c in ["Сумма_у_нас","Сумма_в_банке","Δ суммы"] if c in adj_full.columns}
            fmt_s.update({c: "{:,.0f}" for c in ["Кол_во_у_нас","Кол_во_в_банке","Δ кол-во"] if c in adj_full.columns})
            sm = adj_full.style
            disc_cols = [c for c in ["Δ суммы","Δ кол-во"] if c in adj_full.columns]
            sm_method = sm.map if hasattr(sm, "map") else sm.applymap
            styled = sm_method(highlight_delta, subset=disc_cols).format(fmt_s)
            
            try:
                ev = st.dataframe(styled, use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row")
                sel_rows = ev.selection.rows
            except TypeError:
                st.dataframe(styled, use_container_width=True, hide_index=True)
                sel_rows = []

            if sel_rows:
                sel_date = adj_full.iloc[sel_rows[0]]["date"]
                if sel_date and "ИТОГО" not in str(sel_date):
                    st.markdown(f"---\n### 🔍 Детализация за **{sel_date}**")
                    mdf = data["merged"].copy()
                    mdf["_ds"] = pd.to_datetime(mdf["date_unified"], errors="coerce").dt.strftime("%d.%m.%Y")
                    dd = mdf[mdf["_ds"] == sel_date]

                    day_our = dd[dd["_merge"]=="left_only"].dropna(axis=1, how="all")
                    day_bank = dd[dd["_merge"]=="right_only"].dropna(axis=1, how="all")
                    if not ig_our.empty: day_our = day_our[~day_our["RRN"].isin(ig_our["RRN"])]
                    if not ig_bank.empty: day_bank = day_bank[~day_bank["RRN"].isin(ig_bank["RRN"])]

                    day_mm = pd.DataFrame()
                    if "net_amount_our" in dd.columns and "net_amount_bank" in dd.columns:
                        dm = dd[dd["_merge"]=="both"].copy()
                        dlt = (dm["net_amount_bank"].fillna(0) - dm["net_amount_our"].fillna(0))
                        day_mm = dm[dlt.abs() > tol].copy()
                        if not day_mm.empty: day_mm["Δ сумма"] = dlt[dlt.abs() > tol].values

                    dc = {"RRN": st.column_config.TextColumn("RRN"), "net_amount_our": num_cfg("Сумма (Мы)"), "net_amount_bank": num_cfg("Сумма (Банк)"), "Δ сумма": st.column_config.NumberColumn("Δ", format="%+,.2f")}

                    if not day_our.empty:
                        st.error(f"🔴 Отсутствуют в банке — **{len(day_our)}** транзакций")
                        st.dataframe(day_our.drop(columns=["_merge"], errors="ignore"), use_container_width=True, hide_index=True, column_config=dc)
                    if not day_bank.empty:
                        st.info(f"🔵 Лишние от банка — **{len(day_bank)}** транзакций")
                        st.dataframe(day_bank.drop(columns=["_merge"], errors="ignore"), use_container_width=True, hide_index=True, column_config=dc)
                    if not day_mm.empty:
                        st.warning(f"🟡 Расхождение суммы — **{len(day_mm)}** транзакций")
                        st.dataframe(day_mm.drop(columns=["_merge"], errors="ignore"), use_container_width=True, hide_index=True, column_config=dc)
                    if day_our.empty and day_bank.empty and day_mm.empty:
                        st.success("✅ С учётом исключений, за этот день расхождений нет!")

        # ── Charts tab ────────────────────────────────----
        with tabs[1]:
            import plotly.express as px
            import plotly.graph_objects as go
            plot_df = adj_full[~adj_full["date"].str.contains("ИТОГО")].copy()
            if not plot_df.empty:
                c1, c2 = st.columns(2)
                with c1:
                    fig1 = px.bar(plot_df, x="date", y=["Сумма_у_нас","Сумма_в_банке"], barmode="group", template="plotly_white", title=f"Сравнение сумм по дням ({cur})", labels={"value": cur, "variable": "Источник", "date": "Дата"}, color_discrete_map={"Сумма_у_нас":"#2563eb","Сумма_в_банке":"#059669"})
                    fig1.update_layout(legend=dict(orientation="h", y=1.05), margin=dict(t=60))
                    st.plotly_chart(fig1, use_container_width=True)
                with c2:
                    plot_df["_clr"] = plot_df["Δ суммы"].apply(lambda x: "Лишнее (банк)" if x > tol else ("Нехватка" if x < -tol else "✓ Совпадает"))
                    fig2 = px.bar(plot_df, x="date", y="Δ суммы", color="_clr", template="plotly_white", title=f"Разница по дням (допуск {tol:,.2f} {cur})", labels={"Δ суммы": f"Δ ({cur})", "date": "Дата", "_clr": "Тип"}, color_discrete_map={"Лишнее (банк)":"#2563eb","Нехватка":"#dc2626","✓ Совпадает":"#16a34a"})
                    fig2.add_hline(y=0, line_dash="dash", line_color="#94a3b8")
                    fig2.update_layout(legend=dict(orientation="h", y=1.05), margin=dict(t=60))
                    st.plotly_chart(fig2, use_container_width=True)

                fig3 = go.Figure(go.Waterfall(
                    name="", orientation="v", measure=["relative","relative","total"],
                    x=["Наши транзакции","Разница банка","Итого банк"], y=[adj_tot_our, adj_diff, adj_tot_bank],
                    connector={"line": {"color": "#94a3b8"}}, decreasing={"marker": {"color": "#dc2626"}}, increasing={"marker": {"color": "#2563eb"}}, totals={"marker": {"color": "#059669"}},
                ))
                fig3.update_layout(title="Водопадная диаграмма сверки", template="plotly_white", showlegend=False)
                st.plotly_chart(fig3, use_container_width=True)

        # ── Export ───────────────────────────────────────
        st.markdown("---")
        st.markdown("### 💾 Экспорт и сохранение")
        
        col_export, col_save = st.columns(2)
        
        with col_export:
            with st.container(border=True):
                st.markdown("#### 📥 Выгрузка отчета")
                st.caption("Скачать результаты в формате Excel")
                buf = io.BytesIO()
                with pd.ExcelWriter(buf, engine="openpyxl") as w:
                    adj_full.to_excel(w, sheet_name="Сводка_по_датам", index=False)
                    edited_only_our.to_excel(w, sheet_name="Нет_в_банке", index=False)
                    edited_only_bank.to_excel(w, sheet_name="Лишнее_от_банка", index=False)
                    if not data["amt_mismatches"].empty: data["amt_mismatches"].drop(columns=["_merge"], errors="ignore").to_excel(w, sheet_name="Расхождения_сумм", index=False)
                    if data["dup_our_c"] > 0: data["dups_our"].to_excel(w, sheet_name="Дубликаты_наши", index=False)
                    if data["dup_bank_c"] > 0: data["dups_bank"].to_excel(w, sheet_name="Дубликаты_банк", index=False)
                st.download_button(label="Скачать Excel-отчет", data=buf.getvalue(), file_name=f"Сверка_{dt_mod.datetime.now():%Y%m%d_%H%M}.xlsx", type="primary", use_container_width=True)
                
        with col_save:
            with st.container(border=True):
                st.markdown("#### 🗄 Сохранить в Архив")
                st.caption("Записать результаты в общую базу данных для аналитики")
                if is_auditor:
                    st.info("🔒 Сохранение в архив недоступно в режиме аудитора (только чтение).")
                else:
                    if st.button("Сохранить результат в БД", use_container_width=True, type="primary"):
                        user = st.session_state.get("username", "unknown")
                        bank_name = st.session_state.get("chosen_bank", "Банк")
                        success, msg = save_reconciliation(user=user, bank_name=bank_name, tot_our=adj_tot_our, tot_bank=adj_tot_bank, diff=adj_diff, matched_c=data["matched_count"], mismatch_c=data["mismatch_count"], only_our_c=len(ig_our), only_bank_c=len(ig_bank))
                        if success:
                            st.success(msg)
                            log_action(user, "SAVE_RECON", f"Сохранена сверка по банку {bank_name}")
                        else:
                            st.error(msg)
