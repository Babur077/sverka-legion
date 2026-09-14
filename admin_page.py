import streamlit as st
import os
import socket
from utils.db_manager import (
    add_user, 
    get_all_users, 
    get_audit_logs, 
    log_action, 
    save_settings, 
    delete_user,
    DB_PATH
)

def get_local_ip():
    """Определяет локальный IP-адрес сервера в сети предприятия."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

def show_page():
    # 1. Защита страницы: доступ только у администратора
    if st.session_state.get("role") != "admin":
        st.error("⛔ У вас нет прав для просмотра этой страницы.")
        return

    st.title("Настройки системы")
    st.markdown("<p style='color:#64748b; margin-top:-15px; margin-bottom:30px;'>Управление профилями, безопасностью, базой данных и сетью.</p>", unsafe_allow_html=True)
    
    current_user = st.session_state.get("username", "system")
    
    tab1, tab2, tab3, tab4 = st.tabs(["Пользователи", "Журнал действий", "Параметры сверки", "База данных и сеть"])
    
    # ─── Вкладка 1: Управление пользователями ───
    with tab1:
        col1, col2 = st.columns([1.1, 1.9])
        
        with col1:
            with st.container(border=True):
                st.markdown("### Новый профиль")
                
                with st.form("add_user_form", clear_on_submit=True):
                    new_user = st.text_input("Логин*")
                    new_pass = st.text_input("Пароль*", type="password")
                    new_role = st.selectbox("Роль*", ["accountant", "auditor", "admin"], format_func=lambda r: {
                        "accountant": "Бухгалтер (полный доступ к сверке)",
                        "auditor": "Аудитор (только чтение и экспорт)",
                        "admin": "Администратор (полный доступ)"
                    }.get(r, r))
                    
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

            # Форма удаления пользователя
            with st.container(border=True):
                st.markdown("### 🗑 Удалить пользователя")
                df_u = get_all_users()
                non_admin_users = df_u[df_u["username"] != "admin"]
                if non_admin_users.empty:
                    st.caption("Нет дополнительных пользователей для удаления.")
                else:
                    user_opts = dict(zip(non_admin_users["username"], non_admin_users["id"]))
                    selected_del_name = st.selectbox("Выберите пользователя", list(user_opts.keys()))
                    if st.button("Удалить выбранного пользователя", use_container_width=True):
                        uid = user_opts[selected_del_name]
                        ok, msg = delete_user(uid)
                        if ok:
                            st.success(msg)
                            log_action(current_user, "DELETE_USER", f"Удален пользователь {selected_del_name}")
                            st.rerun()
                        else:
                            st.error(msg)
                            
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

    # ─── Вкладка 4: База данных и Сеть ───
    with tab4:
        col_db, col_net = st.columns(2)
        with col_db:
            with st.container(border=True):
                st.markdown("### 🗄 Централизованная база данных")
                st.markdown(f"""
                - **Тип СУБД**: SQLite 3
                - **Расположение**: `{DB_PATH}`
                - **Размер файла**: `{os.path.getsize(DB_PATH) / 1024:.1f} KB` (если существует)
                - **Синхронизация**: Мгновенная для всех пользователей в сети
                """)

                if os.path.exists(DB_PATH):
                    with open(DB_PATH, "rb") as f:
                        db_bytes = f.read()
                    st.download_button(
                        label="📥 Скачать резервную копию базы данных (.db)",
                        data=db_bytes,
                        file_name="reconcile_hub_backup.db",
                        mime="application/x-sqlite3",
                        use_container_width=True
                    )

        with col_net:
            with st.container(border=True):
                st.markdown("### 🌐 Доступ для коллег в офисе")
                local_ip = get_local_ip()
                st.markdown(f"""
                Чтобы коллеги могли работать с вашей системой и общей базой данных без интернета и облачного хостинга:

                1. Запустите приложение командой:
                ```bash
                streamlit run app.py --server.address 0.0.0.0 --server.port 8501
                ```
                2. Ссылка для вас на этом ПК:
                   **`http://localhost:8501`**
                3. Ссылка для коллег в локальной сети:
                   **`http://{local_ip}:8501`**

                *Все пользователи будут автоматически видеть одни и те же добавленные банки, реестр и архив сверок!*
                """)
