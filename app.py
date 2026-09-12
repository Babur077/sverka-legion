import streamlit as st

# ВАЖНО: set_page_config должен быть самой первой Streamlit-командой в скрипте.
st.set_page_config(page_title="ReconcileHub", page_icon="⚡", layout="wide")

import rrn_page
import epos_page
import admin_page
import analytics_page
from utils.db_manager import init_db, authenticate_user, log_action, get_settings

# ─── Инициализация БД (создаёт таблицы и дефолтного админа при первом запуске) ───
init_db()


def inject_modern_light_css():
    st.markdown("""
    <style>
    /* Глобальный светлый фон и текстовый цвет */
    .stApp, [data-testid="stAppViewContainer"] {
        background-color: #f8fafc !important;
        color: #0f172a !important;
    }
    
    /* Основные текстовые элементы */
    p, span, div, label {
        color: inherit;
    }
    
    /* Заголовки */
    h1, h2, h3, h4, h5, h6 {
        color: #0f172a !important;
        font-weight: 600 !important;
        letter-spacing: -0.02em !important;
    }

    /* Все метки виджетов (Label): решаем проблему белого текста на белом фоне */
    [data-testid="stWidgetLabel"],
    [data-testid="stWidgetLabel"] label,
    [data-testid="stWidgetLabel"] p,
    [data-testid="stWidgetLabel"] span {
        color: #1e293b !important;
        font-weight: 600 !important;
        font-size: 0.95rem !important;
    }

    /* Сайдбар */
    [data-testid="stSidebar"] {
        background-color: #ffffff !important;
        border-right: 1px solid #e2e8f0 !important;
    }
    [data-testid="stSidebar"] hr {
        border-color: #f1f5f9 !important;
    }
    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p,
    [data-testid="stSidebar"] span {
        color: #334155 !important;
    }
    
    /* Стилизация радио-кнопок под пункты меню в сайдбаре */
    [data-testid="stSidebar"] [data-testid="stRadio"] label,
    [data-testid="stSidebar"] .stRadio > div > label {
        padding: 10px 14px !important;
        margin-bottom: 3px !important;
        border-radius: 8px !important;
        color: #334155 !important;
        font-weight: 500 !important;
        font-size: 0.92rem !important;
        transition: all 0.2s ease-in-out;
        background-color: transparent !important;
    }
    [data-testid="stSidebar"] [data-testid="stRadio"] label p,
    [data-testid="stSidebar"] .stRadio > div > label p {
        color: #334155 !important;
    }
    [data-testid="stSidebar"] [data-testid="stRadio"] label:hover,
    [data-testid="stSidebar"] .stRadio > div > label:hover {
        background-color: #f1f5f9 !important;
        color: #0f172a !important;
    }
    [data-testid="stSidebar"] [data-testid="stRadio"] label[data-checked="true"],
    [data-testid="stSidebar"] .stRadio > div > label[data-checked="true"] {
        background-color: #e0e7ff !important; 
        color: #3730a3 !important;
        font-weight: 600 !important;
    }
    [data-testid="stSidebar"] [data-testid="stRadio"] label[data-checked="true"] p,
    [data-testid="stSidebar"] .stRadio > div > label[data-checked="true"] p {
        color: #3730a3 !important;
        font-weight: 600 !important;
    }
    [data-testid="stSidebar"] .stRadio div[role="radio"] > div {
        display: none !important;
    }

    /* Поля ввода (Text input, Number input, Selectbox) */
    .stTextInput input,
    .stNumberInput input,
    div[data-baseweb="input"] input {
        background-color: #ffffff !important;
        color: #0f172a !important;
        border: 1px solid #cbd5e1 !important;
        border-radius: 8px !important;
        padding: 8px 12px !important;
    }
    .stTextInput input::placeholder,
    div[data-baseweb="input"] input::placeholder {
        color: #94a3b8 !important;
    }
    div[data-baseweb="select"] > div {
        background-color: #ffffff !important;
        border-color: #cbd5e1 !important;
        color: #0f172a !important;
        border-radius: 8px !important;
    }

    /* Загрузчик файлов (File Uploader Dropzone) */
    [data-testid="stFileUploader"] section {
        background-color: #ffffff !important;
        border: 1.5px dashed #cbd5e1 !important;
        border-radius: 10px !important;
    }
    [data-testid="stFileUploader"] section:hover {
        border-color: #6366f1 !important;
        background-color: #f8fafc !important;
    }
    [data-testid="stFileUploader"] section button {
        background-color: #f1f5f9 !important;
        color: #0f172a !important;
        border: 1px solid #cbd5e1 !important;
        border-radius: 6px !important;
    }
    [data-testid="stFileUploader"] section span,
    [data-testid="stFileUploader"] section small {
        color: #64748b !important;
    }

    /* Карточки-контейнеры */
    [data-testid="stVerticalBlockBorderWrapper"] {
        background-color: #ffffff !important;
        border: 1px solid #e2e8f0 !important;
        border-radius: 12px !important;
        padding: 24px !important;
        box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.05) !important;
    }

    /* Табы */
    button[data-baseweb="tab"] {
        background-color: transparent !important;
        border: none !important;
        padding: 8px 16px !important;
        margin-right: 8px !important;
        border-radius: 20px !important; 
        color: #64748b !important;
        font-weight: 500 !important;
    }
    button[data-baseweb="tab"]:hover {
        background-color: #f1f5f9 !important;
        color: #0f172a !important;
    }
    button[data-baseweb="tab"][aria-selected="true"] {
        background-color: #e2e8f0 !important; 
        color: #0f172a !important;
        font-weight: 600 !important;
    }
    div[data-baseweb="tab-highlight"], div[data-baseweb="tab-border"] {
        display: none !important;
    }

    /* Кнопки */
    .stButton > button {
        border-radius: 8px !important;
        font-weight: 500 !important;
        transition: all 0.15s ease-in-out;
    }
    .stButton > button[kind="secondary"],
    .stButton > button:not([kind="primary"]) {
        background-color: #ffffff !important;
        color: #1e293b !important;
        border: 1px solid #cbd5e1 !important;
    }
    .stButton > button[kind="secondary"]:hover,
    .stButton > button:not([kind="primary"]):hover {
        background-color: #f8fafc !important;
        border-color: #94a3b8 !important;
    }
    .stButton > button[kind="primary"] {
        background-color: #4f46e5 !important;
        color: #ffffff !important;
        border: none !important;
    }
    .stButton > button[kind="primary"]:hover {
        background-color: #4338ca !important;
    }
    
    /* Верхний хедер */
    [data-testid="stHeader"] {
        background: transparent !important;
    }
    </style>
    """, unsafe_allow_html=True)


# ─── Инициализация состояния сессии ───
if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False
if "username" not in st.session_state:
    st.session_state["username"] = None
if "role" not in st.session_state:
    st.session_state["role"] = None
if "settings" not in st.session_state:
    # Настройки читаются из БД, чтобы быть общими для ВСЕХ пользователей,
    # а не только для текущей сессии браузера.
    st.session_state["settings"] = get_settings()

inject_modern_light_css()


def login_screen():
    """Экран авторизации (показывается, если пользователь не вошел)."""
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        st.markdown("<br><br><br>", unsafe_allow_html=True)
        with st.container(border=True):
            st.markdown("<h2 style='text-align: center;'>Вход в систему</h2>", unsafe_allow_html=True)
            st.markdown("<p style='text-align: center; color: #64748b;'>ReconcileHub v2.0</p>", unsafe_allow_html=True)

            with st.form("login_form"):
                username = st.text_input("Логин")
                password = st.text_input("Пароль", type="password")

                submitted = st.form_submit_button("Войти", type="primary", use_container_width=True)

                if submitted:
                    clean_user = username.strip()
                    clean_pass = password.strip()

                    if clean_user and clean_pass:
                        is_auth, role = authenticate_user(clean_user, clean_pass)
                        if is_auth:
                            st.session_state["authenticated"] = True
                            st.session_state["username"] = clean_user
                            st.session_state["role"] = role
                            log_action(clean_user, "LOGIN", "Успешный вход в систему")
                            st.rerun()
                        else:
                            st.error("Неверный логин или пароль")
                    else:
                        st.error("Пожалуйста, введите логин и пароль.")


def main_app():
    """Основной интерфейс платформы (показывается только после логина)."""

    # ─── Боковое меню ───
    with st.sidebar:
        st.markdown("""
        <div style='padding: 10px 0 20px 10px;'>
            <div style='font-size: 1.4rem; font-weight: 700; color: #0f172a;'>ReconcileHub</div>
            <div style='font-size: 0.75rem; color: #64748b;'>v2.0 • PROFESSIONAL</div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("<p style='font-size:0.75rem; color:#94a3b8; margin-left:14px; font-weight:600;'>ОБЗОР</p>", unsafe_allow_html=True)

        # Пункты меню зависят от роли. "Реестр EPOS" и "Настройки" — только для admin,
        # так как в реестре хранятся комиссионные ставки и юрлица (чувствительные данные),
        # а "Настройки" меняют общесистемные параметры для всех пользователей.
        menu_items = ["🔄 Сверка по RRN"]
        if st.session_state["role"] == "admin":
            menu_items.append("📱 Реестр EPOS")
        menu_items.append("📊 Аналитика")
        if st.session_state["role"] == "admin":
            menu_items.append("⚙️ Настройки")

        app_mode = st.radio("Навигация", menu_items, label_visibility="collapsed")

        st.divider()
        st.markdown(f"👤 Пользователь: **{st.session_state['username']}**")
        if st.button("🚪 Выйти", use_container_width=True):
            log_action(st.session_state["username"], "LOGOUT", "Выход из системы")
            st.session_state["authenticated"] = False
            st.session_state["username"] = None
            st.session_state["role"] = None
            st.rerun()

    # ─── Роутер страниц ───
    if app_mode == "🔄 Сверка по RRN":
        rrn_page.show_page()
    elif app_mode == "📱 Реестр EPOS":
        epos_page.show_page()
    elif app_mode == "📊 Аналитика":
        analytics_page.show_page()
    elif app_mode == "⚙️ Настройки":
        admin_page.show_page()


# ─── Точка входа ───
if not st.session_state["authenticated"]:
    login_screen()
else:
    main_app()
