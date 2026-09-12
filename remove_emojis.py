import re
import os

def fix_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Generic emojis removal (most of them)
    # We will manually replace some first that we want to add icons to

    # RrnPage specific:
    content = content.replace("<h2>⚙️ Настройка колонок и правил сверки</h2>", "<h2 className=\"text-base font-bold text-slate-900 flex items-center gap-2\"><Settings className=\"w-5 h-5 text-slate-700\" /> Настройка колонок и правил сверки</h2>")
    content = content.replace("📤 Ваши данные:", "Ваши данные:")
    content = content.replace("🏦 Данные банка:", "Данные банка:")
    content = content.replace("📅 Дата*", "Дата*")
    content = content.replace("🔑 RRN*", "RRN*")
    content = content.replace("💰 Сумма", "Сумма")
    content = content.replace("🏷 Статус", "Статус")
    content = content.replace("📱 Terminal ID", "Terminal ID")
    content = content.replace("⚙️ Расширенные настройки", "Расширенные настройки")
    
    content = content.replace("1️⃣ ", "1. ")
    content = content.replace("2️⃣ ", "2. ")
    
    content = content.replace("➖ Минусовать сумму", "Минусовать сумму")
    content = content.replace("🗑 Удалить строку", "Удалить строку")
    content = content.replace("💥 Удалить RRN полностью", "Удалить RRN полностью")
    content = content.replace("⚪ Не обрабатывать", "Не обрабатывать")
    
    content = content.replace("💔 Разрывать связи при расхождении сумм", "Разрывать связи при расхождении сумм")
    
    content = content.replace("🚀 Запустить сверку транзакций", "Запустить сверку транзакций")
    content = content.replace("🚨 Ни одного совпадения", "Ни одного совпадения")
    content = content.replace("✅ Сверка сошлась!", "Сверка сошлась!")
    content = content.replace("⚠️ Обнаружено расхождение:", "Обнаружено расхождение:")
    
    content = content.replace("🏷️ Быстрый расчет комиссии (%):", "Быстрый расчет комиссии (%):")
    
    content = content.replace("📅 Сводка по датам", "Сводка по датам")
    content = content.replace("📈 Графики", "Графики")
    content = content.replace("🔍 Несопоставленные", "Несопоставленные")
    content = content.replace("🟡 Расхождения сумм", "Расхождения сумм")
    content = content.replace("⚠️ Дубликаты", "Дубликаты")
    
    content = content.replace("📊 ИТОГО", "ИТОГО")
    content = content.replace("💡 Нажмите", "Нажмите")
    
    content = content.replace("🔍 Детализация", "Детализация")
    content = content.replace("🔴 Отсутствуют в банке", "Отсутствуют в банке")
    content = content.replace("🔵 Лишние от банка", "Лишние от банка")
    content = content.replace("🔵 Лишние данные банка", "Лишние данные банка")
    content = content.replace("🎉 Нет расхождений", "Нет расхождений")
    
    content = content.replace("🔴 Дубликаты", "Дубликаты")
    content = content.replace("🔵 Дубликаты", "Дубликаты")
    
    content = content.replace("➖ Снять галочки", "Снять галочки")
    content = content.replace("➕ Вернуть галочки", "Вернуть галочки")
    content = content.replace("🪄 Офсеты", "Офсеты")
    content = content.replace("💾 Экспорт и фиксация в системе", "Экспорт и фиксация в системе")

    # Analytics page specific:
    content = content.replace("📊 Динамика сведённых объёмов", "Динамика сведённых объёмов")
    content = content.replace("📉 Тренд расхождений (Δ)", "Тренд расхождений (Δ)")
    content = content.replace("📜 Журнал проведённых сверок", "Журнал проведённых сверок")

    # General emoji regex cleanup just in case
    # This matches common emojis but keeps Russian text
    content = re.sub(r'[\U00010000-\U0010ffff]', '', content)

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

fix_file('src/components/RrnPage.tsx')
fix_file('src/components/AnalyticsPage.tsx')
