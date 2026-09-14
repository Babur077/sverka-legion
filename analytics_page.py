import streamlit as st
import pandas as pd
import plotly.express as px
from utils.db_manager import get_archive_data, delete_archive_record

def show_page():
    st.title("Аналитика и Архив сверок")
    st.markdown("<p style='color:#64748b; margin-top:-15px; margin-bottom:30px;'>Статистика, тренды и история проведенных сверок.</p>", unsafe_allow_html=True)
    
    df_archive = get_archive_data()
    
    if df_archive.empty:
        st.info("📭 Архив пока пуст. Сохраните результаты на странице 'Сверка по RRN', чтобы увидеть аналитику.")
        return
        
    # Преобразуем строковые даты в формат datetime для графиков
    df_archive['timestamp'] = pd.to_datetime(df_archive['timestamp'])
    df_archive['date_str'] = df_archive['timestamp'].dt.strftime('%d.%m.%Y %H:%M')

    # ─── БЛОК 1: KPI Метрики ───
    with st.container(border=True):
        total_recons = len(df_archive)
        total_diff = df_archive['difference'].sum()
        total_mismatches = df_archive['mismatch_count'].sum()
        
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Всего проведено сверок", total_recons)
        m2.metric("Банков в системе", df_archive['bank_name'].nunique())
        m3.metric("Общее расхождение", f"{total_diff:,.2f}", delta="Требует внимания" if abs(total_diff) > 0 else "В норме", delta_color="inverse" if abs(total_diff) > 0 else "normal")
        m4.metric("Ошибок сумм (за всё время)", total_mismatches)

    st.markdown("<br>", unsafe_allow_html=True)

    # ─── БЛОК 2: Графики и Таблица ───
    tab_charts, tab_data = st.tabs(["📊 Графики", "📋 Управление архивом"])
    
    with tab_charts:
        col1, col2 = st.columns(2)
        with col1:
            with st.container(border=True):
                st.markdown("#### Динамика расхождений (Δ)")
                fig_bar = px.bar(
                    df_archive, x='date_str', y='difference', color='bank_name',
                    labels={'date_str': 'Дата проведения', 'difference': 'Разница', 'bank_name': 'Банк'},
                    template="plotly_white"
                )
                fig_bar.add_hline(y=0, line_dash="dash", line_color="#94a3b8")
                st.plotly_chart(fig_bar, use_container_width=True)
                
        with col2:
            with st.container(border=True):
                st.markdown("#### Несопоставленные транзакции")
                fig_line = px.line(
                    df_archive, x='date_str', y=['only_our_count', 'only_bank_count'],
                    labels={'date_str': 'Дата', 'value': 'Количество транзакций', 'variable': 'Категория'},
                    template="plotly_white",
                    markers=True
                )
                newnames = {'only_our_count': 'Нет в банке', 'only_bank_count': 'Лишние от банка'}
                fig_line.for_each_trace(lambda t: t.update(name = newnames.get(t.name, t.name)))
                st.plotly_chart(fig_line, use_container_width=True)

    with tab_data:
        st.markdown("💡 **Совет:** Чтобы удалить записи из архива, поставьте галочку в столбце «Удалить» и нажмите кнопку ниже.")
        
        # Подготавливаем dataframe для редактирования
        df_display = df_archive.copy()
        df_display.insert(0, "🗑️ Удалить", False)
        
        with st.container(border=True):
            edited_df = st.data_editor(
                df_display,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "🗑️ Удалить": st.column_config.CheckboxColumn("Удалить", help="Отметьте для удаления", default=False),
                    "id": None, # Скрываем ID
                    "date_str": None, # Скрываем техническую колонку
                    "timestamp": st.column_config.DatetimeColumn("Время сверки", format="DD.MM.YYYY HH:mm"),
                    "username": "Инициатор",
                    "bank_name": "Банк",
                    "total_our": st.column_config.NumberColumn("Сумма (Мы)", format="%,.2f"),
                    "total_bank": st.column_config.NumberColumn("Сумма (Банк)", format="%,.2f"),
                    "difference": st.column_config.NumberColumn("Расхождение (Δ)", format="%+,.2f"),
                    "matched_count": st.column_config.NumberColumn("Совпало"),
                    "mismatch_count": st.column_config.NumberColumn("Δ Сумм"),
                    "only_our_count": st.column_config.NumberColumn("Только у нас"),
                    "only_bank_count": st.column_config.NumberColumn("Только банк")
                },
                disabled=["id", "timestamp", "username", "bank_name", "total_our", "total_bank", "difference", "matched_count", "mismatch_count", "only_our_count", "only_bank_count"]
            )
            
        # Проверяем, есть ли отмеченные для удаления
        to_delete = edited_df[edited_df["🗑️ Удалить"] == True]
        if not to_delete.empty:
            st.warning(f"⚠️ Выбрано записей для удаления: {len(to_delete)}")
            if st.button("🗑️ Подтвердить удаление выбранных записей", type="primary"):
                for idx, row in to_delete.iterrows():
                    delete_archive_record(row['id'])
                st.success("✅ Записи успешно удалены из архива!")
                st.rerun()
