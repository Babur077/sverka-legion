import streamlit as st
from utils.db_manager import add_user, get_all_users, get_audit_logs, log_action, save_settings

def show_page():
    # 1. Защита страницы: доступ только у администратора
    if st.session_state.get("role") != "admin":
        st.error("⛔ У вас нет прав для просмотра этой страницы.")
        return

    st.title("Настройки системы")
    st.markdown("<p style='color:#64748b; margin-top:-15px; margin-bottom:30px;'>Управление профилями, безопасностью и системный аудит.</p>", unsafe_allow_html=True)
    
    current_user = st.session_state.get("username", "system")
    
    tab1, tab2, tab3 = st.tabs(["👥 Пользователи", "📝 Журнал действий", "🔧 Параметры сверки"])
    
    # ─── Вкладка 1: Управление пользователями ───
    with tab1:
        col1, col2 = st.columns([1, 2])
        
        with col1:
            with st.container(border=True):
                st.markdown("### ➕ Новый профиль")
                
                with st.form("add_user_form", clear_on_submit=True):
                    new_user = st.text_input("Логин*")
                    new_pass = st.text_input("Пароль*", type="password")
                    new_role = st.selectbox("Роль*", ["accountant", "auditor", "admin"])
                    
                    if st.form_submit_button("Создать пользователя", type="primary", use_container_width=True):
                        if new_user and new_pass:
                            success, msg = add_user(new_user, new_pass, new_role)
                            if success:
                                st.success(msg)
                                log_action(current_user, "ADD_USER", f"Создан пользователь {new_user} с ролью {new_role}")
                                st.rerun()
                            else:
                                st.error(msg)
                        else:
                            st.error("Пожалуйста, заполните логин и пароль.")
                            
        with col2:
            with st.container(border=True):
                st.markdown("### 📋 Список пользователей")
                df_users = get_all_users()
                st.dataframe(
                    df_users, 
                    use_container_width=True, 
                    hide_index=True,
                    column_config={
                        "id": "ID",
                        "username": "Логин",
                        "role": "Уровень доступа"
                    }
                )

    # ─── Вкладка 2: Системный аудит ───
    with tab2:
        with st.container(border=True):
            st.markdown("### 📝 Audit Log (Журнал событий)")
            st.caption("Показаны последние 100 действий в системе для контроля безопасности.")
            df_logs = get_audit_logs()
            
            if df_logs.empty:
                st.info("Журнал пока пуст.")
            else:
                st.dataframe(
                    df_logs, 
                    use_container_width=True, 
                    hide_index=True,
                    column_config={
                        "timestamp": st.column_config.DatetimeColumn("Время", format="DD.MM.YYYY HH:mm:ss"),
                        "username": "Пользователь",
                        "action": "Действие",
                        "details": "Детали"
                    }
                )

    # ─── Вкладка 3: Глобальные параметры ───
    with tab3:
        with st.container(border=True):
            st.markdown("### 🔧 Настройки по умолчанию")
            st.caption("Эти параметры хранятся в базе данных и общие для всех пользователей системы — не только для вашей текущей сессии.")
            
            new_tol = st.number_input(
                "Допуск суммы (игнорировать Δ ≤)", 
                value=float(st.session_state["settings"]["amount_tolerance"]), 
                step=0.01
            )
            new_curr = st.selectbox(
                "Базовая валюта", 
                ["UZS", "USD", "EUR"], 
                index=["UZS", "USD", "EUR"].index(st.session_state["settings"]["currency"])
            )
            
            if st.button("💾 Сохранить настройки", type="primary"):
                st.session_state["settings"]["amount_tolerance"] = new_tol
                st.session_state["settings"]["currency"] = new_curr
                save_settings(st.session_state["settings"])
                log_action(current_user, "UPDATE_SETTINGS", f"Изменены параметры: {new_curr}, допуск {new_tol}")
                st.success("Глобальные параметры обновлены — изменения видны всем пользователям!")
