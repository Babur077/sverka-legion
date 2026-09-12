const fs = require('fs');

let rrn = fs.readFileSync('src/components/RrnPage.tsx', 'utf8');

rrn = rrn.replace(/import \{([\s\S]*?)\} from 'lucide-react';/, (match, p1) => {
    return `import {${p1}, Settings, UploadCloud, Landmark, CalendarDays, Key, Coins, Tag as TagIcon, Settings2, Unlink, Percent, CalendarRange, Search, AlertCircle, Copy, FileText, CheckSquare, Square, FileCheck, Layers} from 'lucide-react';`;
});

// Section headers
rrn = rrn.replace("Ваши данные: соответствие колонок", "<div className=\"flex items-center gap-1.5\"><UploadCloud className=\"w-4 h-4 text-indigo-600\"/> Ваши данные: соответствие колонок</div>");
rrn = rrn.replace("Данные банка: соответствие колонок", "<div className=\"flex items-center gap-1.5\"><Landmark className=\"w-4 h-4 text-emerald-600\"/> Данные банка: соответствие колонок</div>");

// Selectors
rrn = rrn.replace("Дата*", "<div className=\"flex items-center gap-1\"><CalendarDays className=\"w-3 h-3 text-slate-400\"/> Дата*</div>");
rrn = rrn.replace("RRN*", "<div className=\"flex items-center gap-1\"><Key className=\"w-3 h-3 text-slate-400\"/> RRN*</div>");
rrn = rrn.replace(">Сумма<", "><div className=\"flex items-center gap-1\"><Coins className=\"w-3 h-3 text-slate-400\"/> Сумма</div><");
rrn = rrn.replace(">Статус<", "><div className=\"flex items-center gap-1\"><TagIcon className=\"w-3 h-3 text-slate-400\"/> Статус</div><");
rrn = rrn.replace(">Terminal ID (TID) EPOS<", "><div className=\"flex items-center gap-1\"><Smartphone className=\"w-3 h-3 text-slate-400\"/> Terminal ID (TID) EPOS</div><");

// Advanced settings
rrn = rrn.replace("Расширенные настройки (возвраты, дубликаты, строгий допуск)", "<div className=\"flex items-center gap-2\"><Settings2 className=\"w-4 h-4 text-slate-500\"/> Расширенные настройки (возвраты, дубликаты, строгий допуск)</div>");
rrn = rrn.replace("Разрывать связи при расхождении сумм", "<div className=\"flex items-center gap-1\"><Unlink className=\"w-4 h-4 text-indigo-500\"/> Разрывать связи при расхождении сумм</div>");

// Buttons and Banners
rrn = rrn.replace("Быстрый расчет комиссии (%):", "<div className=\"flex items-center gap-1.5\"><Percent className=\"w-4 h-4 text-slate-500\"/> Быстрый расчет комиссии (%):</div>");

// Tabs
rrn = rrn.replace("Сводка по датам", "<div className=\"flex items-center gap-1.5\"><CalendarRange className=\"w-4 h-4\"/> Сводка по датам</div>");
rrn = rrn.replace("Графики", "<div className=\"flex items-center gap-1.5\"><BarChart2 className=\"w-4 h-4\"/> Графики</div>");
rrn = rrn.replace("Несопоставленные (", "<div className=\"flex items-center gap-1.5\"><Search className=\"w-4 h-4\"/> Несопоставленные (");
rrn = rrn.replace("Расхождения сумм (", "<div className=\"flex items-center gap-1.5\"><AlertCircle className=\"w-4 h-4\"/> Расхождения сумм (");
rrn = rrn.replace("Дубликаты (", "<div className=\"flex items-center gap-1.5\"><Copy className=\"w-4 h-4\"/> Дубликаты (");

fs.writeFileSync('src/components/RrnPage.tsx', rrn);

let an = fs.readFileSync('src/components/AnalyticsPage.tsx', 'utf8');

an = an.replace("Динамика сведённых объёмов", "<div className=\"flex items-center gap-1.5\"><BarChart3 className=\"w-4 h-4 text-indigo-600\"/> Динамика сведённых объёмов</div>");
an = an.replace("Тренд расхождений (Δ)", "<div className=\"flex items-center gap-1.5\"><TrendingUp className=\"w-4 h-4 text-rose-600\"/> Тренд расхождений (Δ)</div>");
an = an.replace("Журнал проведённых сверок", "<div className=\"flex items-center gap-1.5\"><Archive className=\"w-4 h-4 text-emerald-600\"/> Журнал проведённых сверок</div>");

fs.writeFileSync('src/components/AnalyticsPage.tsx', an);
