import streamlit as st
from utils.db_manager import add_epos_terminal, get_epos_registry, log_action

def show_page():
    # Защита страницы: доступ только у администратора.
    # Пункт меню в app.py тоже скрыт для не-админов, но проверка здесь нужна
    # как независимый рубеж защиты (rubric: "never rely only on hiding a menu item"),
    # на случай прямого вызова функции или будущих изменений в логике меню.
    if st.session_state.get("role") != "admin":
        st.error("⛔ У вас нет прав для просмотра этой страницы.")
        return

    current_user = st.session_state.get("username", "unknown")

    st.title("Реестр EPOS терминалов")
    st.markdown("<p style='color:#64748b; margin-top:-15px; margin-bottom:30px;'>Справочник эквайринговых терминалов и комиссионных ставок.</p>", unsafe_allow_html=True)
    
    col1, col2 = st.columns([1, 2])
    
    # ─── Левая колонка: Форма добавления ───
    with col1:
        with st.container(border=True):
            st.markdown("### ➕ Добавить терминал")
            
            with st.form("add_epos_form", clear_on_submit=True):
                new_tid = st.text_input("Terminal ID (TID)*")
                new_mid = st.text_input("Merchant ID (MID)")
                new_bank = st.selectbox("Банк-эквайер*", ["Soliq", "Kapital", "NBU", "Davr", "Другой"])
                new_entity = st.text_input("Юр. лицо / Точка")
                new_comm = st.number_input("Комиссия (%)*", min_value=0.0, max_value=100.0, value=0.0, step=0.1)
                
                submitted = st.form_submit_button("Сохранить", type="primary", use_container_width=True)
                
                if submitted:
                    if not new_tid:
                        st.error("Поле TID обязательно для заполнения!")
                    else:
                        success, msg = add_epos_terminal(new_tid, new_mid, new_bank, new_entity, new_comm)
                        if success:
                            st.success(msg)
                            # Пишем реального инициатора действия, а не хардкод "admin"
                            log_action(current_user, "ADD_EPOS", f"Добавлен терминал {new_tid} ({new_bank})")
                            st.rerun() # Перезагружаем страницу для обновления таблицы
                        else:
                            st.error(msg)

    # ─── Правая колонка: Таблица терминалов ───
    with col2:
        with st.container(border=True):
            st.markdown("### 📋 Текущий реестр")
            df_registry = get_epos_registry()
            
            if df_registry.empty:
                st.info("Реестр пока пуст. Добавьте первый терминал слева.")
            else:
                st.dataframe(
                    df_registry, 
                    use_container_width=True, 
                    hide_index=True,
                    column_config={
                        "terminal_id": "TID",
                        "merchant_id": "MID",
                        "bank_acquirer": "Банк",
                        "legal_entity": "Юр. лицо",
                        "commission_pct": st.column_config.NumberColumn("Комиссия (%)", format="%.2f"),
                        "is_active": st.column_config.CheckboxColumn("Активен")
                    }
                )
