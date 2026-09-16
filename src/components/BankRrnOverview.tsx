import React from 'react';
import { ArrowUpRight, CheckCircle2, Clock3, FileWarning, Play, ShieldCheck } from 'lucide-react';
import { User } from '../types';

interface BankRrnOverviewProps {
  user: User;
  onStart: () => void;
}

const runs = [
  { date: '16.09 · 09:42', files: 2, volume: '1.24M', match: '99.4%', status: 'SUCCESS' },
  { date: '15.09 · 18:12', files: 2, volume: '0.98M', match: '99.8%', status: 'SUCCESS' },
  { date: '15.09 · 10:04', files: 2, volume: '1.31M', match: '97.1%', status: 'WARNING' },
];

export const BankRrnOverview: React.FC<BankRrnOverviewProps> = ({ user, onStart }) => {
  return (
    <div className="space-y-5">
      <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-xs">
        <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
          <div>
            <div className="text-xs text-slate-500">Добро пожаловать, {user.username}</div>
            <h3 className="text-xl font-bold text-slate-900 mt-1">Состояние сверки банков</h3>
            <p className="text-sm text-slate-500 mt-1">Краткий обзор последних запусков и текущего качества сопоставления.</p>
          </div>
          <button
            onClick={onStart}
            className="inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-semibold shadow-sm transition-colors"
          >
            <Play className="w-3.5 h-3.5 fill-white" />
            Новая сверка
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
        {[
          { label: 'Совпадение', value: '99.4%', icon: CheckCircle2, note: 'последний запуск', iconClass: 'text-emerald-600 bg-emerald-50 border-emerald-100' },
          { label: 'Транзакций', value: '1,245,382', icon: ArrowUpRight, note: 'последний запуск', iconClass: 'text-indigo-600 bg-indigo-50 border-indigo-100' },
          { label: 'Расхождения', value: '27', icon: FileWarning, note: 'требуют проверки', iconClass: 'text-amber-600 bg-amber-50 border-amber-100' },
          { label: 'Последний запуск', value: '09:42', icon: Clock3, note: 'сегодня', iconClass: 'text-slate-600 bg-slate-50 border-slate-200' },
        ].map((metric) => {
          const Icon = metric.icon;
          return (
            <div key={metric.label} className="bg-white border border-slate-200 rounded-xl p-4 shadow-xs">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="text-xs font-medium text-slate-500">{metric.label}</div>
                  <div className="text-2xl font-bold text-slate-900 mt-1">{metric.value}</div>
                  <div className="text-[11px] text-slate-400 mt-1">{metric.note}</div>
                </div>
                <div className={`w-9 h-9 rounded-lg border flex items-center justify-center ${metric.iconClass}`}>
                  <Icon className="w-4 h-4" />
                </div>
              </div>
            </div>
          );
        })}
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_300px] gap-5">
        <div className="bg-white border border-slate-200 rounded-xl shadow-xs overflow-hidden">
          <div className="px-5 py-4 border-b border-slate-100 flex items-center justify-between">
            <div>
              <h4 className="font-semibold text-slate-900">Последние запуски</h4>
              <p className="text-xs text-slate-500 mt-0.5">История последних операций этой сверки</p>
            </div>
            <span className="text-[11px] text-slate-400">3 запуска</span>
          </div>
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead className="bg-slate-50 border-b border-slate-100">
                <tr>
                  {['Дата', 'Файлы', 'Транзакции', 'Match', 'Статус'].map((head) => (
                    <th key={head} className="text-left px-5 py-3 text-[11px] font-semibold uppercase tracking-wider text-slate-400">{head}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {runs.map((run) => (
                  <tr key={`${run.date}-${run.volume}`} className="hover:bg-slate-50/80 transition-colors">
                    <td className="px-5 py-3.5 font-medium text-slate-800 whitespace-nowrap">{run.date}</td>
                    <td className="px-5 py-3.5 text-slate-600">{run.files}</td>
                    <td className="px-5 py-3.5 text-slate-600">{run.volume}</td>
                    <td className="px-5 py-3.5 font-semibold text-slate-800">{run.match}</td>
                    <td className="px-5 py-3.5">
                      {run.status === 'SUCCESS' ? (
                        <span className="inline-flex items-center gap-1.5 text-[11px] font-semibold text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-full px-2.5 py-1">
                          <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" /> Успешно
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1.5 text-[11px] font-semibold text-amber-700 bg-amber-50 border border-amber-200 rounded-full px-2.5 py-1">
                          <span className="w-1.5 h-1.5 rounded-full bg-amber-500" /> Требует внимания
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="bg-slate-900 text-white rounded-xl p-5 shadow-xs">
          <div className="flex items-center gap-2 text-indigo-200 text-xs font-semibold uppercase tracking-wider">
            <ShieldCheck className="w-4 h-4" /> Контекст модуля
          </div>
          <h4 className="text-lg font-bold mt-3">Сверка банков</h4>
          <p className="text-xs text-slate-300 leading-relaxed mt-2">
            Рабочая область эквайринга: RRN, комиссии, терминалы и контроль расхождений.
          </p>
          <div className="mt-5 space-y-2 text-xs">
            <div className="flex items-center justify-between py-2 border-b border-white/10"><span className="text-slate-400">Версия</span><span>1.4.2</span></div>
            <div className="flex items-center justify-between py-2 border-b border-white/10"><span className="text-slate-400">Статус</span><span className="text-emerald-300">Active</span></div>
            <div className="flex items-center justify-between py-2"><span className="text-slate-400">Пользователь</span><span>{user.username}</span></div>
          </div>
        </div>
      </div>
    </div>
  );
};
