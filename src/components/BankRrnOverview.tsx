import React, { useEffect, useState } from 'react';
import { ArrowUpRight, CheckCircle2, Clock3, FileWarning, Play, ShieldCheck } from 'lucide-react';
import { ReconciliationArchive, User } from '../types';
import { hasPermission } from '../utils/permissions';
import { getBankRrnArchive } from '../utils/archiveApi';
import { getReconciliationQuality } from '../utils/reconciliationMetrics';

interface BankRrnOverviewProps { user: User; onStart: () => void; }
const compact = (n: number) => n >= 1e9 ? `${(n/1e9).toFixed(2)} млрд` : n >= 1e6 ? `${(n/1e6).toFixed(2)} млн` : n >= 1e3 ? `${(n/1e3).toFixed(1)} тыс.` : n.toLocaleString('ru-RU');

export const BankRrnOverview: React.FC<BankRrnOverviewProps> = ({ user, onStart }) => {
  const canRun = hasPermission(user, 'bank_rrn.run');
  const [archive, setArchive] = useState<ReconciliationArchive[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setLoadError(null);
    void getBankRrnArchive(user.username)
      .then((data) => { if (active) setArchive(data); })
      .catch((error: any) => { if (active) setLoadError(error?.message || 'Не удалось загрузить архив.'); });
    return () => { active = false; };
  }, [user.username]);
  const latest = archive[0];
  const qualityRows = archive.map(a => getReconciliationQuality(
    a.matched_count,
    a.mismatch_count,
    a.only_our_count,
    a.only_bank_count,
  ));
  const totalTx = qualityRows.reduce((sum, quality) => sum + quality.scope, 0);
  const totalIssues = qualityRows.reduce((sum, quality) => sum + quality.issueCount, 0);
  const latestQuality = latest
    ? getReconciliationQuality(latest.matched_count, latest.mismatch_count, latest.only_our_count, latest.only_bank_count)
    : null;
  const latestMatch = latestQuality?.exactMatchRate || 0;
  const runs = archive.slice(0, 5);
  const metrics = [
    { label: 'Точное совпадение', value: latest ? `${latestMatch.toFixed(1)}%` : '—', icon: CheckCircle2, note: latest ? 'последний запуск' : 'нет запусков', cls: 'text-emerald-600 bg-emerald-50 border-emerald-100' },
    { label: 'Транзакций', value: totalTx.toLocaleString('ru-RU'), icon: ArrowUpRight, note: 'в сохранённых результатах', cls: 'text-indigo-600 bg-indigo-50 border-indigo-100' },
    { label: 'Расхождения', value: totalIssues.toLocaleString('ru-RU'), icon: FileWarning, note: 'по сохранённым запускам', cls: 'text-amber-600 bg-amber-50 border-amber-100' },
    { label: 'Последний запуск', value: latest ? new Date(latest.timestamp).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' }) : '—', icon: Clock3, note: latest ? new Date(latest.timestamp).toLocaleDateString('ru-RU') : 'нет данных', cls: 'text-slate-600 bg-slate-50 border-slate-200' },
  ];
  return <div className="space-y-5">
    <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-xs flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
      <div><div className="text-xs text-slate-500">Добро пожаловать, {user.username}</div><h3 className="text-xl font-bold text-slate-900 mt-1">Состояние сверки банков</h3><p className="text-sm text-slate-500 mt-1">Краткий обзор последних запусков и текущего качества сопоставления.</p></div>
      {canRun && (
        <button onClick={onStart} className="inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-semibold shadow-sm transition-colors">
          <Play className="w-3.5 h-3.5 fill-white" /> Новая сверка
        </button>
      )}
    </div>
    {loadError && <div className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-xs text-rose-700">{loadError}</div>}
    <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">{metrics.map(m => { const Icon = m.icon; return <div key={m.label} className="bg-white border border-slate-200 rounded-xl p-4 shadow-xs"><div className="flex items-start justify-between gap-3"><div><div className="text-xs font-medium text-slate-500">{m.label}</div><div className="text-2xl font-bold text-slate-900 mt-1">{m.value}</div><div className="text-[11px] text-slate-400 mt-1">{m.note}</div></div><div className={`w-9 h-9 rounded-lg border flex items-center justify-center ${m.cls}`}><Icon className="w-4 h-4" /></div></div></div>; })}</div>
    <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_300px] gap-5">
      <div className="bg-white border border-slate-200 rounded-xl shadow-xs overflow-hidden"><div className="px-5 py-4 border-b border-slate-100 flex items-center justify-between"><div><h4 className="font-semibold text-slate-900">Последние запуски</h4><p className="text-xs text-slate-500 mt-0.5">История последних операций этой сверки</p></div><span className="text-[11px] text-slate-400">{runs.length} из {archive.length}</span></div>{runs.length === 0 ? <div className="p-10 text-center text-sm text-slate-500">Сохранённых запусков пока нет. Начните новую сверку.</div> : <div className="overflow-x-auto"><table className="min-w-full text-sm"><thead className="bg-slate-50 border-b border-slate-100"><tr>{['Дата','Банк','Оборот','Match','Статус'].map(h => <th key={h} className="text-left px-5 py-3 text-[11px] font-semibold uppercase tracking-wider text-slate-400">{h}</th>)}</tr></thead><tbody className="divide-y divide-slate-100">{runs.map(r => { const quality = getReconciliationQuality(r.matched_count, r.mismatch_count, r.only_our_count, r.only_bank_count); const rate = quality.exactMatchRate; const warning = r.difference !== 0 || quality.issueCount > 0; return <tr key={r.id} className="hover:bg-slate-50/80 transition-colors"><td className="px-5 py-3.5 font-medium text-slate-800 whitespace-nowrap">{new Date(r.timestamp).toLocaleString('ru-RU')}</td><td className="px-5 py-3.5 text-slate-700">{r.bank_name}</td><td className="px-5 py-3.5 text-slate-600">{compact(r.total_bank)}</td><td className="px-5 py-3.5 font-semibold text-slate-800">{rate.toFixed(1)}%</td><td className="px-5 py-3.5">{warning ? <span className="inline-flex items-center gap-1.5 text-[11px] font-semibold text-amber-700 bg-amber-50 border border-amber-200 rounded-full px-2.5 py-1">Требует внимания</span> : <span className="inline-flex items-center gap-1.5 text-[11px] font-semibold text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-full px-2.5 py-1">Успешно</span>}</td></tr>; })}</tbody></table></div>}</div>
      <div className="bg-slate-900 text-white rounded-xl p-5 shadow-xs"><div className="flex items-center gap-2 text-indigo-200 text-xs font-semibold uppercase tracking-wider"><ShieldCheck className="w-4 h-4" /> Контекст модуля</div><h4 className="text-lg font-bold mt-3">Сверка банков</h4><p className="text-xs text-slate-300 leading-relaxed mt-2">Рабочая область эквайринга: RRN, комиссии, терминалы и контроль расхождений.</p><div className="mt-5 space-y-2 text-xs"><div className="flex items-center justify-between py-2 border-b border-white/10"><span className="text-slate-400">Версия</span><span>1.5.0</span></div><div className="flex items-center justify-between py-2 border-b border-white/10"><span className="text-slate-400">Сохранённых запусков</span><span>{archive.length}</span></div><div className="flex items-center justify-between py-2"><span className="text-slate-400">Пользователь</span><span>{user.username}</span></div></div></div>
    </div>
  </div>;
};
