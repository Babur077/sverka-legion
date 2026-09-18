import React, { useMemo, useState } from 'react';
import { Archive, Eye, Search, Trash2, RefreshCw, X, Terminal } from 'lucide-react';
import { ReconciliationArchive, User } from '../types';
import { deleteBankRrnArchive, getBankRrnArchive } from '../utils/archiveApi';
import { ConfirmModal } from './Modal';
import { getReconciliationQuality } from '../utils/reconciliationMetrics';

interface Props { user: User; onNewReconciliation: () => void; }
const money = (n: number) => n.toLocaleString('ru-RU', { maximumFractionDigits: 2 });
const pct = (n: number) => `${n.toFixed(2)}%`;

export const BankRrnArchive: React.FC<Props> = ({ user, onNewReconciliation }) => {
  const [archive, setArchive] = useState<ReconciliationArchive[]>([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState('');
  const [month, setMonth] = useState('(Все)');
  const [selected, setSelected] = useState<ReconciliationArchive | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<ReconciliationArchive | null>(null);

  const months = useMemo(() => Array.from(new Set(archive.map(a => a.period_month || a.timestamp.slice(0, 7)))).sort().reverse(), [archive]);
  const filtered = useMemo(() => archive.filter(a => {
    const q = query.trim().toLowerCase();
    const hit = !q || a.bank_name.toLowerCase().includes(q) || a.username.toLowerCase().includes(q);
    const aMonth = a.period_month || a.timestamp.slice(0, 7);
    return hit && (month === '(Все)' || aMonth === month);
  }), [archive, query, month]);

  const refresh = async () => {
    setLoading(true);
    try { setArchive(await getBankRrnArchive(user.username)); }
    catch (error: any) { console.error(error); setArchive([]); }
    finally { setLoading(false); }
  };

  React.useEffect(() => { refresh(); }, [user.username]);
  const confirmDelete = async () => {
    if (!deleteTarget) return;
    try {
      await deleteBankRrnArchive(user.username, deleteTarget.id);
      setDeleteTarget(null);
      setSelected(null);
      await refresh();
    } catch (error) {
      console.error(error);
    }
  };

  const selectedTerminals = useMemo(() => [...(selected?.terminals_summary || [])].sort((a, b) => b.total_volume - a.total_volume), [selected]);
  const selectedTerminalTotals = useMemo(() => selectedTerminals.reduce((s, t) => ({
    tx: s.tx + t.tx_count,
    volume: s.volume + t.total_volume,
    commission: s.commission + t.commission_amount,
    net: s.net + t.net_volume,
  }), { tx: 0, volume: 0, commission: 0, net: 0 }), [selectedTerminals]);
  const selectedQuality = useMemo(
    () => selected
      ? getReconciliationQuality(selected.matched_count, selected.mismatch_count, selected.only_our_count, selected.only_bank_count)
      : null,
    [selected],
  );

  return <div className="space-y-5">
    <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
      <div><h3 className="text-xl font-bold text-slate-900 flex items-center gap-2"><Archive className="w-5 h-5 text-indigo-600" /> Архив сверки</h3><p className="text-sm text-slate-500 mt-1">Сохранённые результаты Bank RRN с общей комиссией и детализацией по терминалам.</p></div>
      <button onClick={onNewReconciliation} className="px-4 py-2.5 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-semibold">Новая сверка</button>
    </div>

    <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-xs flex flex-col md:flex-row gap-3">
      <div className="relative flex-1"><Search className="w-4 h-4 text-slate-400 absolute left-3 top-3" /><input value={query} onChange={e => setQuery(e.target.value)} placeholder="Поиск по банку или оператору" className="w-full pl-9 pr-3 py-2.5 rounded-lg border border-slate-200 text-sm outline-none focus:ring-2 focus:ring-indigo-100 focus:border-indigo-400" /></div>
      <select value={month} onChange={e => setMonth(e.target.value)} className="md:w-44 py-2.5 px-3 rounded-lg border border-slate-200 text-sm bg-white"><option>(Все)</option>{months.map(m => <option key={m}>{m}</option>)}</select>
      <button onClick={refresh} className="inline-flex items-center justify-center gap-2 px-3 py-2.5 rounded-lg border border-slate-200 text-sm text-slate-600 hover:bg-slate-50"><RefreshCw className="w-4 h-4" /> Обновить</button>
    </div>

    <div className="bg-white border border-slate-200 rounded-xl shadow-xs overflow-hidden">
      <div className="px-5 py-4 border-b border-slate-100"><div className="font-semibold text-slate-900">Результаты</div><div className="text-xs text-slate-500 mt-0.5">Показано {filtered.length} из {archive.length}</div></div>
      {filtered.length === 0 ? <div className="p-12 text-center text-slate-500 text-sm">Записи не найдены.</div> : <div className="overflow-x-auto"><table className="min-w-full text-sm"><thead className="bg-slate-50"><tr>{['Дата', 'Банк', 'Оператор', 'Сумма банка', 'Комиссия', 'Δ', 'Точное совпадение', 'Действия'].map(h => <th key={h} className="px-5 py-3 text-left text-[11px] font-semibold uppercase tracking-wider text-slate-400">{h}</th>)}</tr></thead><tbody className="divide-y divide-slate-100">{filtered.map(a => { const quality = getReconciliationQuality(a.matched_count, a.mismatch_count, a.only_our_count, a.only_bank_count); const rate = quality.exactMatchRate; return <tr key={a.id} className="hover:bg-slate-50"><td className="px-5 py-3.5 whitespace-nowrap">{new Date(a.timestamp).toLocaleString('ru-RU')}</td><td className="px-5 py-3.5 font-medium">{a.bank_name}</td><td className="px-5 py-3.5 text-slate-600">{a.username}</td><td className="px-5 py-3.5 text-slate-600">{money(a.total_bank)}</td><td className="px-5 py-3.5 text-violet-700 font-semibold">{money(a.total_commission || 0)}</td><td className={`px-5 py-3.5 font-medium ${a.difference === 0 ? 'text-emerald-600' : 'text-amber-600'}`}>{money(a.difference)}</td><td className="px-5 py-3.5"><span className="font-semibold">{rate.toFixed(1)}%</span><span className="text-xs text-slate-400 ml-2">({quality.exactMatched})</span></td><td className="px-5 py-3.5"><div className="flex items-center gap-1"><button onClick={() => setSelected(a)} className="p-2 rounded-lg hover:bg-indigo-50 text-slate-500 hover:text-indigo-600" title="Просмотр"><Eye className="w-4 h-4" /></button><button onClick={() => setDeleteTarget(a)} className="p-2 rounded-lg hover:bg-rose-50 text-slate-500 hover:text-rose-600" title="Удалить"><Trash2 className="w-4 h-4" /></button></div></td></tr>; })}</tbody></table></div>}
    </div>

    {selected && <div className="fixed inset-0 z-50 bg-slate-950/40 flex items-center justify-center p-4" onClick={() => setSelected(null)}>
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-6xl max-h-[90vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
        <div className="px-5 py-4 border-b flex items-center justify-between"><div><h4 className="font-bold text-slate-900">Сверка #{selected.id}</h4><p className="text-xs text-slate-500">{new Date(selected.timestamp).toLocaleString('ru-RU')} · {selected.bank_name}</p></div><button onClick={() => setSelected(null)} className="p-2 rounded-lg hover:bg-slate-100"><X className="w-4 h-4" /></button></div>
        <div className="p-5 grid grid-cols-2 md:grid-cols-4 gap-3">{[
          ['Сумма у нас', money(selected.total_our)],
          ['Сумма банка', money(selected.total_bank)],
          ['Разница', money(selected.difference)],
          ['Общая комиссия', money(selected.total_commission || 0)],
          ['Точно совпало', (selectedQuality?.exactMatched || 0).toLocaleString('ru-RU')],
          ['Расхождения сумм', selected.mismatch_count.toLocaleString('ru-RU')],
          ['Только у нас / банка', `${selected.only_our_count} / ${selected.only_bank_count}`],
          ['Период', selected.period_month || '—'],
        ].map(([label, value]) => <div key={label} className="bg-slate-50 rounded-xl p-3"><div className="text-[11px] text-slate-500">{label}</div><div className="text-sm font-bold text-slate-900 mt-1">{value}</div></div>)}</div>

        <div className="px-5 pb-5">
          <div className="flex items-center justify-between gap-3 mb-3"><div><div className="text-sm font-semibold text-slate-900 flex items-center gap-2"><Terminal className="w-4 h-4 text-indigo-600" /> Разбивка по терминалам</div><div className="text-xs text-slate-500 mt-0.5">Каждый TID можно рассматривать как отдельный продукт.</div></div><div className="text-xs text-slate-500">{selectedTerminals.length} терминалов</div></div>
          {selectedTerminals.length ? <div className="overflow-x-auto border border-slate-200 rounded-xl"><table className="min-w-full text-sm"><thead className="bg-slate-50"><tr>{['TID', 'Продукт / MID', 'Юрлицо', 'Транзакции', 'Оборот', 'Ставка', 'Комиссия', 'Нетто'].map(h => <th key={h} className="px-4 py-3 text-left text-[11px] font-semibold uppercase tracking-wider text-slate-400">{h}</th>)}</tr></thead><tbody className="divide-y divide-slate-100">{selectedTerminals.map(t => <tr key={t.terminal_id}><td className="px-4 py-3.5 font-mono font-medium">{t.terminal_id}</td><td className="px-4 py-3.5">{t.merchant_id || '—'}</td><td className="px-4 py-3.5 text-slate-600">{t.legal_entity || '—'}</td><td className="px-4 py-3.5">{t.tx_count.toLocaleString('ru-RU')}</td><td className="px-4 py-3.5 font-semibold">{money(t.total_volume)}</td><td className="px-4 py-3.5">{pct(t.commission_pct)}</td><td className="px-4 py-3.5 text-violet-700 font-semibold">{money(t.commission_amount)}</td><td className="px-4 py-3.5 font-semibold">{money(t.net_volume)}</td></tr>)}</tbody><tfoot className="bg-slate-50 border-t border-slate-200"><tr><td className="px-4 py-3 font-semibold" colSpan={3}>ИТОГО</td><td className="px-4 py-3 font-semibold">{selectedTerminalTotals.tx.toLocaleString('ru-RU')}</td><td className="px-4 py-3 font-semibold">{money(selectedTerminalTotals.volume)}</td><td></td><td className="px-4 py-3 font-semibold text-violet-700">{money(selectedTerminalTotals.commission)}</td><td className="px-4 py-3 font-semibold">{money(selectedTerminalTotals.net)}</td></tr></tfoot></table></div> : <div className="text-sm text-slate-500 border border-slate-200 rounded-xl p-6">Детализация по терминалам отсутствует. Новые сохранённые сверки будут хранить её автоматически.</div>}
        </div>
      </div>
    </div>}

    <ConfirmModal isOpen={!!deleteTarget} title="Удалить запись архива?" message={deleteTarget ? `Запись сверки «${deleteTarget.bank_name}» будет удалена из серверного архива.` : ''} confirmText="Удалить" isDanger onConfirm={confirmDelete} onClose={() => setDeleteTarget(null)} />
  </div>;
};
