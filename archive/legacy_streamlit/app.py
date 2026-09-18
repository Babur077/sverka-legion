import html
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
    /* Глобальный светлый фон и шрифты */
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important;
    }

    .stApp, [data-testid="stAppViewContainer"] {
        background-color: #f8fafc !important;
        color: #0f172a !important;
    }

    /* Верхний хедер */
    [data-testid="stHeader"] {
        background: transparent !important;
    }

    /* Сайдбар */
    [data-testid="stSidebar"] {
        background-color: #ffffff !important;
        border-right: 1px solid #e2e8f0 !important;
        padding-top: 1rem !important;
    }
    [data-testid="stSidebar"] > div:first-child {
        padding-top: 1rem !important;
    }

    /* Полное скрытие радио-кружков в меню сайдбара */
    [data-testid="stSidebar"] div[role="radiogroup"] label > div:first-child,
    [data-testid="stSidebar"] [data-testid="stRadio"] label > div:first-child,
    [data-testid="stSidebar"] label[data-baseweb="radio"] > div:first-child,
    [data-testid="stSidebar"] div[role="radiogroup"] label svg,
    [data-testid="stSidebar"] div[role="radiogroup"] label input {
        display: none !important;
        visibility: hidden !important;
        width: 0 !important;
        height: 0 !important;
        margin: 0 !important;
        padding: 0 !important;
        opacity: 0 !important;
    }

    /* Пункты меню в сайдбаре - аккуратные скругленные вкладки с адаптивными SVG иконками */
    [data-testid="stSidebar"] div[role="radiogroup"] label,
    [data-testid="stSidebar"] [data-testid="stRadio"] label,
    [data-testid="stSidebar"] label[data-baseweb="radio"] {
        display: flex !important;
        align-items: center !important;
        padding: 10px 14px !important;
        margin-bottom: 4px !important;
        border-radius: 12px !important;
        color: #475569 !important;
        font-weight: 500 !important;
        font-size: 0.92rem !important;
        transition: all 0.15s ease-in-out !important;
        background-color: transparent !important;
        cursor: pointer !important;
        border: none !important;
        width: 100% !important;
    }
    [data-testid="stSidebar"] div[role="radiogroup"] label p,
    [data-testid="stSidebar"] [data-testid="stRadio"] label p {
        color: inherit !important;
        font-size: 0.92rem !important;
        font-weight: 500 !important;
        margin: 0 !important;
        display: flex !important;
        align-items: center !important;
        gap: 10px !important;
    }
    /* Адаптивная к цвету SVG иконка (наследует currentColor текста) */
    [data-testid="stSidebar"] div[role="radiogroup"] label p::before {
        content: "" !important;
        display: inline-block !important;
        width: 17px !important;
        height: 17px !important;
        background-color: currentColor !important;
        -webkit-mask-size: contain !important;
        mask-size: contain !important;
        -webkit-mask-repeat: no-repeat !important;
        mask-repeat: no-repeat !important;
        -webkit-mask-position: center !important;
        mask-position: center !important;
        flex-shrink: 0 !important;
        transition: background-color 0.15s ease-in-out !important;
    }
    /* 1. Сверка по RRN */
    [data-testid="stSidebar"] div[role="radiogroup"] label:nth-of-type(1) p::before {
        -webkit-mask-image: url("data:image/svg+xml;charset=utf-8,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8'/%3E%3Cpath d='M21 3v5h-5'/%3E%3Cpath d='M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16'/%3E%3Cpath d='M8 16H3v5'/%3E%3C/svg%3E") !important;
        mask-image: url("data:image/svg+xml;charset=utf-8,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8'/%3E%3Cpath d='M21 3v5h-5'/%3E%3Cpath d='M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16'/%3E%3Cpath d='M8 16H3v5'/%3E%3C/svg%3E") !important;
    }
    /* 2. Реестр EPOS */
    [data-testid="stSidebar"] div[role="radiogroup"] label:nth-of-type(2) p::before {
        -webkit-mask-image: url("data:image/svg+xml;charset=utf-8,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Crect width='14' height='20' x='5' y='2' rx='2' ry='2'/%3E%3Cpath d='M12 18h.01'/%3E%3C/svg%3E") !important;
        mask-image: url("data:image/svg+xml;charset=utf-8,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Crect width='14' height='20' x='5' y='2' rx='2' ry='2'/%3E%3Cpath d='M12 18h.01'/%3E%3C/svg%3E") !important;
    }
    /* 3. Аналитика */
    [data-testid="stSidebar"] div[role="radiogroup"] label:nth-of-type(3) p::before {
        -webkit-mask-image: url("data:image/svg+xml;charset=utf-8,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M3 3v18h18'/%3E%3Cpath d='M18 17V9'/%3E%3Cpath d='M13 17V5'/%3E%3Cpath d='M8 17v-3'/%3E%3C/svg%3E") !important;
        mask-image: url("data:image/svg+xml;charset=utf-8,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M3 3v18h18'/%3E%3Cpath d='M18 17V9'/%3E%3Cpath d='M13 17V5'/%3E%3Cpath d='M8 17v-3'/%3E%3C/svg%3E") !important;
    }
    /* 4. Настройки */
    [data-testid="stSidebar"] div[role="radiogroup"] label:nth-of-type(4) p::before {
        -webkit-mask-image: url("data:image/svg+xml;charset=utf-8,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z'/%3E%3Ccircle cx='12' cy='12' r='3'/%3E%3C/svg%3E") !important;
        mask-image: url("data:image/svg+xml;charset=utf-8,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z'/%3E%3Ccircle cx='12' cy='12' r='3'/%3E%3C/svg%3E") !important;
    }

    [data-testid="stSidebar"] div[role="radiogroup"] label:hover,
    [data-testid="stSidebar"] [data-testid="stRadio"] label:hover {
        background-color: #f8fafc !important;
        color: #0f172a !important;
    }
    [data-testid="stSidebar"] div[role="radiogroup"] label:hover p {
        color: #0f172a !important;
    }
    /* Активный выбранный пункт меню */
    [data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked),
    [data-testid="stSidebar"] div[role="radiogroup"] label[data-checked="true"] {
        background-color: #eef2ff !important;
        color: #4338ca !important;
        font-weight: 600 !important;
        box-shadow: 0 1px 2px rgba(67, 56, 202, 0.05) !important;
    }
    [data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked) p,
    [data-testid="stSidebar"] div[role="radiogroup"] label[data-checked="true"] p {
        color: #4338ca !important;
        font-weight: 600 !important;
    }

    /* Кнопка выхода в сайдбаре - точь-в-точь как в Preview */
    [data-testid="stSidebar"] .stButton > button {
        background-color: #ffffff !important;
        border: 1px solid #e2e8f0 !important;
        color: #475569 !important;
        border-radius: 10px !important;
        font-size: 13px !important;
        font-weight: 500 !important;
        padding: 8px 14px !important;
        box-shadow: none !important;
        width: 100% !important;
        transition: all 0.15s ease-in-out !important;
    }
    [data-testid="stSidebar"] .stButton > button:hover {
        border-color: #fecdd3 !important;
        background-color: #fff1f2 !important;
        color: #e11d48 !important;
    }

    /* Карточки-контейнеры */
    [data-testid="stVerticalBlockBorderWrapper"] {
        background-color: #ffffff !important;
        border: 1px solid #e2e8f0 !important;
        border-radius: 16px !important;
        padding: 20px !important;
        box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.03) !important;
    }

    /* Дропзона загрузки файлов */
    [data-testid="stFileUploader"] section {
        background-color: #f8fafc !important;
        border: 2px dashed #cbd5e1 !important;
        border-radius: 14px !important;
        padding: 20px 14px !important;
        transition: all 0.2s ease-in-out !important;
    }
    [data-testid="stFileUploader"] section:hover {
        border-color: #818cf8 !important;
        background-color: #f5f7ff !important;
    }
    [data-testid="stFileUploader"] section button {
        background-color: #ffffff !important;
        color: #1e293b !important;
        border: 1px solid #cbd5e1 !important;
        border-radius: 8px !important;
        font-weight: 500 !important;
        box-shadow: 0 1px 2px rgba(0,0,0,0.04) !important;
    }
    [data-testid="stFileUploader"] section button:hover {
        background-color: #f1f5f9 !important;
        border-color: #94a3b8 !important;
    }

    /* Поля ввода и селекты */
    .stTextInput input,
    .stNumberInput input,
    div[data-baseweb="input"] input {
        background-color: #ffffff !important;
        color: #0f172a !important;
        border: 1px solid #cbd5e1 !important;
        border-radius: 10px !important;
        padding: 9px 12px !important;
    }
    div[data-baseweb="select"] > div {
        background-color: #ffffff !important;
        border-color: #cbd5e1 !important;
        color: #0f172a !important;
        border-radius: 10px !important;
    }

    /* Вкладки (Табы) */
    button[data-baseweb="tab"] {
        background-color: transparent !important;
        border: none !important;
        padding: 8px 18px !important;
        margin-right: 6px !important;
        border-radius: 20px !important; 
        color: #64748b !important;
        font-weight: 500 !important;
        font-size: 14px !important;
    }
    button[data-baseweb="tab"]:hover {
        background-color: #f1f5f9 !important;
        color: #0f172a !important;
    }
    button[data-baseweb="tab"][aria-selected="true"] {
        background-color: #e0e7ff !important; 
        color: #3730a3 !important;
        font-weight: 600 !important;
    }
    div[data-baseweb="tab-highlight"], div[data-baseweb="tab-border"] {
        display: none !important;
    }

    /* Первичные кнопки */
    .stButton > button[kind="primary"] {
        background-color: #4f46e5 !important;
        color: #ffffff !important;
        border: none !important;
        border-radius: 10px !important;
        font-weight: 600 !important;
        padding: 8px 16px !important;
        box-shadow: 0 1px 2px rgba(79, 70, 229, 0.2) !important;
    }
    .stButton > button[kind="primary"]:hover {
        background-color: #4338ca !important;
    }
    
    /* Второстепенные кнопки в основном контенте */
    .stMainBlockContainer .stButton > button:not([kind="primary"]) {
        background-color: #f1f5f9 !important;
        color: #334155 !important;
        border: 1px solid #e2e8f0 !important;
        border-radius: 10px !important;
        font-weight: 500 !important;
    }
    .stMainBlockContainer .stButton > button:not([kind="primary"]):hover {
        background-color: #e2e8f0 !important;
        color: #0f172a !important;
    }

    /* Карточки метрик (st.metric): убираем обрезание длинных финансовых сумм троеточием */
    [data-testid="stMetric"] {
        background: #ffffff !important;
        padding: 12px 14px !important;
        border-radius: 12px !important;
        border: 1px solid #f1f5f9 !important;
        box-shadow: 0 1px 2px rgba(0, 0, 0, 0.02) !important;
        overflow: visible !important;
    }
    [data-testid="stMetricLabel"] {
        white-space: nowrap !important;
        overflow: hidden !important;
        text-overflow: ellipsis !important;
        font-size: 0.82rem !important;
        color: #64748b !important;
        font-weight: 500 !important;
    }
    [data-testid="stMetricValue"] {
        font-size: clamp(1.15rem, 1.6vw, 1.7rem) !important;
        font-weight: 700 !important;
        color: #0f172a !important;
        line-height: 1.25 !important;
        white-space: normal !important;
        word-break: break-word !important;
        overflow: visible !important;
        text-overflow: clip !important;
    }
    [data-testid="stMetricValue"] > div {
        overflow: visible !important;
        text-overflow: clip !important;
        white-space: normal !important;
    }
    [data-testid="stMetricDelta"] {
        font-size: 0.8rem !important;
        overflow: visible !important;
        white-space: nowrap !important;
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
    col1, col2, col3 = st.columns([1, 1.2, 1])
    with col2:
        st.markdown("<br><br>", unsafe_allow_html=True)
        with st.container(border=True):
            st.markdown("""
            <div style='text-align: center; margin-bottom: 20px;'>
                <div style='width: 44px; height: 44px; border-radius: 12px; background: #4f46e5; display: flex; align-items: center; justify-content: center; color: #ffffff; margin: 0 auto 12px auto; box-shadow: 0 4px 6px -1px rgba(79, 70, 229, 0.2);'>
                    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" fill="currentColor"/></svg>
                </div>
                <h2 style='font-size: 20px; font-weight: 700; color: #0f172a; margin: 0 0 4px 0;'>ReconcileHub</h2>
                <p style='color: #64748b; font-size: 13px; margin: 0;'>Вход в финансовую платформу сверки</p>
            </div>
            """, unsafe_allow_html=True)

            with st.form("login_form"):
                username = st.text_input("Логин", placeholder="admin")
                password = st.text_input("Пароль", type="password", placeholder="••••••••")

                submitted = st.form_submit_button("Войти в систему", type="primary", use_container_width=True)

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

            st.markdown("""
            <div style='margin-top: 16px; padding: 10px 12px; border-radius: 10px; background: #f8fafc; border: 1px solid #e2e8f0; font-size: 12px; color: #64748b; text-align: center;'>
                Демо-доступ: <strong>admin</strong> / <strong>admin123</strong>
            </div>
            """, unsafe_allow_html=True)


def main_app():
    """Основной интерфейс платформы (показывается только после логина)."""

    # ─── Боковое меню ───
    with st.sidebar:
        # Бренд-хедер с иконкой молнии точно как в Preview
        st.markdown("""
        <div style='display: flex; align-items: center; gap: 11px; padding: 4px 0 16px 4px; border-bottom: 1px solid #f1f5f9; margin-bottom: 14px;'>
            <div style='width: 36px; height: 36px; border-radius: 9px; background: #4f46e5; display: flex; align-items: center; justify-content: center; color: #ffffff; box-shadow: 0 1px 3px rgba(79, 70, 229, 0.25);'>
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" fill="currentColor"/></svg>
            </div>
            <div>
                <div style='font-size: 16px; font-weight: 700; color: #0f172a; line-height: 1.2;'>ReconcileHub</div>
                <div style='font-size: 11px; font-weight: 600; color: #94a3b8; letter-spacing: 0.05em;'>v2.0 • PROFESSIONAL</div>
            </div>
        </div>
        <div style='font-size: 11px; font-weight: 700; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.06em; padding-left: 8px; margin-bottom: 8px;'>
            ОБЗОР
        </div>
        """, unsafe_allow_html=True)

        # Пункты меню зависят от роли. "Реестр банков" и "Настройки" — только для admin
        menu_items = ["Сверка по RRN"]
        if st.session_state["role"] == "admin":
            menu_items.append("Реестр банков")
        menu_items.append("Аналитика")
        if st.session_state["role"] == "admin":
            menu_items.append("Настройки")

        app_mode = st.radio("Навигация", menu_items, label_visibility="collapsed")

        # Карточка пользователя внизу сайдбара точно как в Preview
        cur_user = st.session_state.get("username", "admin") or "admin"
        safe_user = html.escape(str(cur_user))
        user_initials = html.escape(cur_user[:2].upper())
        role_key = st.session_state.get("role", "admin")
        if role_key == "admin":
            role_title = "Администратор"
            role_badge_style = "color: #4338ca; background: #eef2ff; border: 1px solid #c7d2fe;"
        elif role_key == "accountant":
            role_title = "Бухгалтер"
            role_badge_style = "color: #059669; background: #ecfdf5; border: 1px solid #a7f3d0;"
        elif role_key == "auditor":
            role_title = "Аудитор • Только чтение"
            role_badge_style = "color: #d97706; background: #fffbeb; border: 1px solid #fde68a;"
        else:
            role_title = "Пользователь"
            role_badge_style = "color: #475569; background: #f1f5f9; border: 1px solid #cbd5e1;"
        safe_role_title = html.escape(role_title)

        st.markdown(f"""
        <div style='margin-top: 32px; padding-top: 16px; border-top: 1px solid #f1f5f9;'>
            <div style='display: flex; align-items: center; gap: 10px; margin-bottom: 12px; padding: 4px 6px;'>
                <div style='width: 34px; height: 34px; border-radius: 50%; background: #e2e8f0; display: flex; align-items: center; justify-content: center; color: #334155; font-size: 12px; font-weight: 700; flex-shrink: 0;'>
                    {user_initials}
                </div>
                <div style='overflow: hidden;'>
                    <div style='font-size: 13px; font-weight: 700; color: #0f172a; line-height: 1.2;'>{safe_user}</div>
                    <div style='display: inline-block; font-size: 10px; font-weight: 600; {role_badge_style} border-radius: 4px; padding: 1px 6px; margin-top: 2px;'>
                        {safe_role_title}
                    </div>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        if st.button("Выйти из системы", use_container_width=True, key="btn_logout_clean"):
            log_action(st.session_state["username"], "LOGOUT", "Выход из системы")
            st.session_state["authenticated"] = False
            st.session_state["username"] = None
            st.session_state["role"] = None
            st.rerun()

    # ─── Роутер страниц ───
    if "Сверка по RRN" in app_mode:
        rrn_page.show_page()
    elif "Реестр банков" in app_mode or "Реестр EPOS" in app_mode:
        epos_page.show_page()
    elif "Аналитика" in app_mode:
        analytics_page.show_page()
    elif "Настройки" in app_mode:
        admin_page.show_page()


# ─── Точка входа ───
if not st.session_state["authenticated"]:
    login_screen()
else:
    main_app()
