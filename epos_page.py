import streamlit as st
from utils.db_manager import add_epos_terminal, get_epos_registry, log_action

def show_page():
    # Защита страницы: доступ только у администратора.
    if st.session_state.get("role") != "admin":
        st.error("⛔ У вас нет прав для просмотра этой страницы.")
        return

    current_user = st.session_state.get("username", "unknown")

    st.title("Реестр банков-эквайеров")
    st.markdown("<p style='color:#64748b; margin-top:-15px; margin-bottom:30px;'>Справочник банков-эквайеров и персональных комиссионных ставок для расчёта нетто-сумм при сверке.</p>", unsafe_allow_html=True)
    
    col1, col2 = st.columns([1, 2])
    
    # ─── Левая колонка: Форма добавления ───
    with col1:
        with st.container(border=True):
            st.markdown("### ➕ Добавить банк в реестр")
            
            # Быстрый набор банков
            quick_banks = ["Aloqa Bank", "Open Bank", "Saderat Bank", "Davr Bank", "Hamkor Bank", "Другой банк (ввести вручную)..."]
            
            with st.form("add_epos_form", clear_on_submit=True):
                selected_choice = st.selectbox("Банк-эквайер (быстрый набор)*", quick_banks)
                
                custom_bank = ""
                if selected_choice == "Другой банк (ввести вручную)...":
                    custom_bank = st.text_input("Введите название нового банка*")

                new_tid = st.text_input("Terminal ID (TID)", placeholder="напр. 98234015 (или оставьте пустым)")
                new_mid = st.text_input("Merchant ID (MID)", placeholder="напр. MID_ALOQA_01")
                new_comm = st.number_input("Комиссия (%)*", min_value=0.0, max_value=100.0, value=1.2, step=0.05)
                
                submitted = st.form_submit_button("Сохранить банк в реестр", type="primary", use_container_width=True)
                
                if submitted:
                    bank_name = custom_bank.strip() if selected_choice == "Другой банк (ввести вручную)..." else selected_choice
                    
                    if not bank_name:
                        st.error("Укажите название банка!")
                    else:
                        tid_val = new_tid.strip() or f"TID_{bank_name.replace(' ', '_').upper()}"
                        mid_val = new_mid.strip() or f"MID_{bank_name.replace(' ', '_').upper()}"
                        
                        success, msg = add_epos_terminal(tid_val, mid_val, bank_name, "", new_comm)
                        if success:
                            st.success(f"Банк «{bank_name}» успешно сохранен в реестр!")
                            log_action(current_user, "ADD_EPOS", f"Добавлен банк {bank_name} (TID: {tid_val}, {new_comm}%)")
                            st.rerun()
                        else:
                            st.error(msg)

    # ─── Правая колонка: Таблица банков-эквайеров ───
    with col2:
        with st.container(border=True):
            st.markdown("### 📋 Зарегистрированные банки-эквайеры")
            df_registry = get_epos_registry()
            
            if df_registry.empty:
                st.info("Реестр пока пуст. Добавьте первый банк слева.")
            else:
                # В реестре отображаем ТОЛЬКО банки без колонки юр. лица
                display_cols = ["bank_acquirer", "terminal_id", "merchant_id", "commission_pct", "is_active"]
                available_cols = [c for c in display_cols if c in df_registry.columns]
                clean_df = df_registry[available_cols]

                st.dataframe(
                    clean_df, 
                    use_container_width=True, 
                    hide_index=True,
                    column_config={
                        "bank_acquirer": "Банк-эквайер",
                        "terminal_id": "TID",
                        "merchant_id": "MID",
                        "commission_pct": st.column_config.NumberColumn("Комиссия (%)", format="%.2f%%"),
                        "is_active": st.column_config.CheckboxColumn("Активен")
                    }
                )
