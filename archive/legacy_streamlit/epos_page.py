import streamlit as st
import pandas as pd
import json
import io
from utils.db_manager import (
    add_epos_terminal, 
    get_epos_registry, 
    log_action, 
    delete_epos_terminal, 
    bulk_upsert_epos
)

def show_page():
    # Защита страницы: доступ только у администратора.
    if st.session_state.get("role") != "admin":
        st.error("⛔ У вас нет прав для просмотра этой страницы. Реестр доступен только администраторам.")
        return

    current_user = st.session_state.get("username", "unknown")

    st.title("Реестр банков-эквайеров и EPOS")
    st.markdown("<p style='color:#64748b; margin-top:-15px; margin-bottom:20px;'>Справочник банков-эквайеров, терминалов (TID) и персональных комиссионных ставок для расчёта нетто-сумм.</p>", unsafe_allow_html=True)

    df_registry = get_epos_registry()

    # ─── Метрики реестра ───
    with st.container(border=True):
        m1, m2, m3, m4 = st.columns(4)
        total_terminals = len(df_registry)
        active_terminals = int(df_registry["is_active"].sum()) if not df_registry.empty and "is_active" in df_registry.columns else 0
        unique_banks = df_registry["bank_acquirer"].nunique() if not df_registry.empty and "bank_acquirer" in df_registry.columns else 0
        avg_comm = df_registry["commission_pct"].mean() if not df_registry.empty and "commission_pct" in df_registry.columns else 0.0

        m1.metric("Всего терминалов", total_terminals)
        m2.metric("Активных", active_terminals)
        m3.metric("Банков-эквайеров", unique_banks)
        m4.metric("Средняя ставка", f"{avg_comm:.2f}%")

    st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)

    # Две колонки: Управление / Таблица
    col_tools, col_table = st.columns([1.1, 2.1])

    with col_tools:
        tab_add, tab_import, tab_delete = st.tabs(["➕ Добавить", "📥 Импорт/Экспорт", "🗑 Удалить"])

        # ── Вкладка 1: Добавить вручную ──
        with tab_add:
            with st.container(border=True):
                quick_banks = ["Aloqa Bank", "Open Bank", "Saderat Bank", "Davr Bank", "Hamkor Bank", "Другой банк (ввести вручную)..."]
                
                with st.form("add_epos_form", clear_on_submit=True):
                    selected_choice = st.selectbox("Банк-эквайер*", quick_banks)
                    
                    custom_bank = ""
                    if selected_choice == "Другой банк (ввести вручную)...":
                        custom_bank = st.text_input("Название нового банка*")

                    new_tid = st.text_input("Terminal ID (TID)*", placeholder="напр. 98234015")
                    new_mid = st.text_input("Merchant ID (MID)", placeholder="напр. MID_ALOQA_01")
                    new_entity = st.text_input("Юридическое лицо (компания)", placeholder="напр. ООО «Ритейл Групп»")
                    new_comm = st.number_input("Комиссия (%)*", min_value=0.0, max_value=100.0, value=1.2, step=0.05)
                    
                    submitted = st.form_submit_button("Сохранить терминал", type="primary", use_container_width=True)
                    
                    if submitted:
                        bank_name = custom_bank.strip() if selected_choice == "Другой банк (ввести вручную)..." else selected_choice
                        
                        if not bank_name:
                            st.error("Укажите название банка!")
                        elif not new_tid.strip():
                            st.error("Укажите Terminal ID (TID)!")
                        else:
                            tid_val = new_tid.strip()
                            mid_val = new_mid.strip() or f"MID_{bank_name.replace(' ', '_').upper()}"
                            entity_val = new_entity.strip()
                            
                            success, msg = add_epos_terminal(tid_val, mid_val, bank_name, entity_val, new_comm)
                            if success:
                                st.success(f"Терминал {tid_val} ({bank_name}) успешно добавлен!")
                                log_action(current_user, "ADD_EPOS", f"Добавлен терминал {tid_val} ({bank_name}, {new_comm}%)")
                                st.rerun()
                            else:
                                st.error(msg)

        # ── Вкладка 2: Импорт и Экспорт ──
        with tab_import:
            with st.container(border=True):
                st.markdown("##### 📥 Импорт из Excel / CSV")
                st.caption("Файл должен содержать колонки: `terminal_id` (или TID), `bank_acquirer` (Банк), `commission_pct` (Комиссия).")
                uploaded_file = st.file_uploader("Выберите файл", type=["xlsx", "xls", "csv"], key="epos_uploader")
                if uploaded_file is not None:
                    try:
                        if uploaded_file.name.endswith(".csv"):
                            import_df = pd.read_csv(uploaded_file)
                        else:
                            import_df = pd.read_excel(uploaded_file)
                        records = import_df.to_dict(orient="records")
                        if st.button("Загрузить терминалы в БД", type="primary", use_container_width=True):
                            count = bulk_upsert_epos(records)
                            st.success(f"Успешно импортировано {count} терминалов!")
                            log_action(current_user, "IMPORT_EPOS_FILE", f"Импортировано {count} записей из файла {uploaded_file.name}")
                            st.rerun()
                    except Exception as e:
                        st.error(f"Ошибка чтения файла: {e}")

                st.divider()
                st.markdown("##### 🔄 Миграция из React (JSON)")
                st.caption("Если вы добавляли терминалы в React-приложении, вставьте скопированный JSON:")
                json_text = st.text_area("JSON реестра", placeholder='[{"terminal_id": "98234015", "bank_acquirer": "Aloqa Bank", "commission_pct": 1.2}]', height=100)
                if st.button("Импортировать из JSON", use_container_width=True):
                    try:
                        data_json = json.loads(json_text)
                        if isinstance(data_json, list):
                            count = bulk_upsert_epos(data_json)
                            st.success(f"Импортировано {count} терминалов из JSON!")
                            log_action(current_user, "IMPORT_EPOS_JSON", f"Импортировано {count} терминалов из JSON")
                            st.rerun()
                        else:
                            st.error("JSON должен быть массивом объектов [ { ... } ]")
                    except Exception as e:
                        st.error(f"Некорректный JSON: {e}")

                st.divider()
                st.markdown("##### 📤 Экспорт реестра в Excel")
                if not df_registry.empty:
                    buf = io.BytesIO()
                    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
                        df_registry.to_excel(writer, sheet_name="Реестр_EPOS", index=False)
                    st.download_button(
                        label="Скачать реестр (.xlsx)",
                        data=buf.getvalue(),
                        file_name="Реестр_банков_и_терминалов.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True
                    )

        # ── Вкладка 3: Удаление терминала ──
        with tab_delete:
            with st.container(border=True):
                st.markdown("##### 🗑 Удаление терминала")
                if df_registry.empty:
                    st.info("Реестр пуст.")
                else:
                    tids = df_registry["terminal_id"].tolist()
                    target_tid = st.selectbox("Выберите TID для удаления", tids, key="del_target_tid")
                    selected_row = df_registry[df_registry["terminal_id"] == target_tid].iloc[0]
                    st.caption(f"Банк: **{selected_row['bank_acquirer']}** | Ставка: **{selected_row['commission_pct']}%**")
                    
                    if st.button("Удалить выбранный терминал", type="primary", use_container_width=True):
                        delete_epos_terminal(target_tid)
                        log_action(current_user, "DELETE_EPOS", f"Удален терминал {target_tid}")
                        st.success(f"Терминал {target_tid} удален!")
                        st.rerun()

    # ─── Правая колонка: Интерактивная таблица ───
    with col_table:
        with st.container(border=True):
            head_col1, head_col2 = st.columns([2, 1])
            with head_col1:
                st.markdown("### 📋 База терминалов и ставок")
            with head_col2:
                filter_bank = st.selectbox("Фильтр по банку", ["(Все банки)"] + sorted(list(df_registry["bank_acquirer"].unique())) if not df_registry.empty else ["(Все)"])

            if df_registry.empty:
                st.info("Реестр пока пуст. Добавьте первый банк или терминал слева.")
            else:
                view_df = df_registry.copy()
                if filter_bank != "(Все банки)" and not view_df.empty:
                    view_df = view_df[view_df["bank_acquirer"] == filter_bank]

                display_cols = ["bank_acquirer", "terminal_id", "merchant_id", "legal_entity", "commission_pct", "is_active"]
                available_cols = [c for c in display_cols if c in view_df.columns]
                filtered_view = view_df[available_cols].copy()
                filtered_view["is_active"] = filtered_view["is_active"].astype(bool)

                st.caption("💡 Вы можете изменять комиссию, юр. лицо и статус активности прямо в таблице, затем нажать кнопку сохранения ниже:")
                
                edited_df = st.data_editor(
                    filtered_view,
                    column_config={
                        "bank_acquirer": st.column_config.TextColumn("Банк-эквайер", disabled=True),
                        "terminal_id": st.column_config.TextColumn("TID", disabled=True),
                        "merchant_id": st.column_config.TextColumn("MID", disabled=True),
                        "legal_entity": st.column_config.TextColumn("Юр. лицо"),
                        "commission_pct": st.column_config.NumberColumn("Комиссия (%)", format="%.2f%%", min_value=0.0, max_value=100.0, step=0.05),
                        "is_active": st.column_config.CheckboxColumn("Активен")
                    },
                    use_container_width=True,
                    hide_index=True,
                    key="epos_data_editor"
                )

                if st.button("💾 Сохранить изменения в таблице", type="primary", use_container_width=True):
                    # Обновляем отредактированные записи
                    records_to_save = edited_df.to_dict(orient="records")
                    bulk_upsert_epos(records_to_save)
                    log_action(current_user, "UPDATE_EPOS_TABLE", f"Обновлено {len(records_to_save)} строк в таблице EPOS")
                    st.success("Изменения успешно сохранены в базе данных SQLite!")
                    st.rerun()
