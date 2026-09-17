import React, { useMemo, useState } from 'react';
import { BarChart3, TrendingUp, Coins, CheckCircle2, AlertTriangle, Building2, Terminal, WalletCards } from 'lucide-react';
import { ReconciliationArchive, TerminalSummaryItem, User } from '../types';
import { getArchiveData } from '../utils/storage';

interface Props { user: User; }

const money = (n: number) => n.toLocaleString('ru-RU', { maximumFractionDigits: 0 });
const pct = (n: number) => `${n.toFixed(2)}%`;

type TerminalAnalyticsRow = TerminalSummaryItem & { bank: string; runs: number };

export const BankRrnAnalytics: React.FC<Props> = ({ user }) => {
  const [archive] = useState<ReconciliationArchive[]>(getArchiveData());
  const [bank, setBank] = useState('(Все)');
  const [month, setMonth] = useState('(Все)');
  const [terminal, setTerminal] = useState('(Все)');

  const banks = useMemo(() => Array.from(new Set(archive.map(a => a.bank_name))).sort(), [archive]);
  const months = useMemo(() => Array.from(new Set(archive.map(a => a.period_month || a.timestamp.slice(0, 7)))).sort().reverse(), [archive]);

  const filtered = useMemo(() => archive.filter(a =>
    (bank === '(Все)' || a.bank_name === bank) &&
    (month === '(Все)' || (a.period_month || a.timestamp.slice(0, 7)) === month)
  ), [archive, bank, month]);

  const terminalRows = useMemo<TerminalAnalyticsRow[]>(() => {
    const map = new Map<string, TerminalAnalyticsRow>();
    filtered.forEach(a => (a.terminals_summary || []).forEach(t => {
      const tid = String(t.terminal_id || '(Без TID)');
      const current = map.get(tid);
      if (!current) {
        map.set(tid, {
          ...t,
          terminal_id: tid,
          bank: t.bank_acquirer || a.bank_name,
          merchant_id: t.merchant_id,
          legal_entity: t.legal_entity,
          tx_count: t.tx_count || 0,
          total_volume: t.total_volume || 0,
          commission_pct: t.commission_pct || 0,
          commission_amount: t.commission_amount || 0,
          net_volume: t.net_volume || 0,
          runs: 1,
        });
      } else {
        current.tx_count += t.tx_count || 0;
        current.total_volume += t.total_volume || 0;
        current.commission_amount += t.commission_amount || 0;
        current.net_volume += t.net_volume || 0;
        current.commission_pct = current.total_volume ? current.commission_amount / current.total_volume * 100 : current.commission_pct;
        current.runs += 1;
        if (!current.merchant_id && t.merchant_id) current.merchant_id = t.merchant_id;
        if (!current.legal_entity && t.legal_entity) current.legal_entity = t.legal_entity;
      }
    }));
    return Array.from(map.values()).sort((a, b) => b.total_volume - a.total_volume);
  }, [filtered]);

  const visibleTerminalRows = useMemo(() => {
    if (terminal === '(Все)') return terminalRows;
    return terminalRows.filter(t => t.terminal_id === terminal);
  }, [terminalRows, terminal]);

  const totals = useMemo(() => filtered.reduce((s, a) => ({
    our: s.our + a.total_our,
    bank: s.bank + a.total_bank,
    diff: s.diff + a.difference,
    comm: s.comm + (a.total_commission || 0),
    matched: s.matched + a.matched_count,
    total: s.total + a.matched_count + a.mismatch_count + a.only_our_count + a.only_bank_count,
  }), { our: 0, bank: 0, diff: 0, comm: 0, matched: 0, total: 0 }), [filtered]);

  const selectedTerminal = terminal === '(Все)' ? null : terminalRows.find(t => t.terminal_id === terminal) || null;
  const matchRate = totals.total ? totals.matched / totals.total * 100 : 0;
  const effectiveCommission = totals.bank ? totals.comm / totals.bank * 100 : 0;

  return <div className="space-y-5">
    <div className="flex flex-col xl:flex-row xl:items-center xl:justify-between gap-4">
      <div>
        <h3 className="text-xl font-bold text-slate-900 flex items-center gap-2"><BarChart3 className="w-5 h-5 text-indigo-600" /> Аналитика Bank RRN</h3>
        <p className="text-sm text-slate-500 mt-1">Объём, качество сопоставления, общая комиссия и финансовая детализация по каждому терминалу.</p>
      </div>
      <div className="flex flex-wrap gap-2">
        <select value={bank} onChange={e => { setBank(e.target.value); setTerminal('(Все)'); }} className="px-3 py-2.5 rounded-lg border border-slate-200 bg-white text-sm">
          <option>(Все)</option>{banks.map(b => <option key={b}>{b}</option>)}
        </select>
        <select value={month} onChange={e => { setMonth(e.target.value); setTerminal('(Все)'); }} className="px-3 py-2.5 rounded-lg border border-slate-200 bg-white text-sm">
          <option>(Все)</option>{months.map(m => <option key={m}>{m}</option>)}
        </select>
        <select value={terminal} onChange={e => setTerminal(e.target.value)} className="px-3 py-2.5 rounded-lg border border-slate-200 bg-white text-sm min-w-48">
          <option>(Все)</option>{terminalRows.map(t => <option key={t.terminal_id} value={t.terminal_id}>{t.terminal_id}</option>)}
        </select>
      </div>
    </div>

    <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-5 gap-4">
      {[
        { l: 'Match rate', v: `${matchRate.toFixed(1)}%`, i: CheckCircle2, c: 'text-emerald-600 bg-emerald-50' },
        { l: 'Оборот банка', v: money(totals.bank), i: TrendingUp, c: 'text-indigo-600 bg-indigo-50' },
        { l: 'Общая комиссия', v: money(totals.comm), i: Coins, c: 'text-violet-600 bg-violet-50' },
        { l: 'Ставка факт.', v: pct(effectiveCommission), i: WalletCards, c: 'text-sky-600 bg-sky-50' },
        { l: 'Терминалов', v: String(terminalRows.length), i: Terminal, c: 'text-amber-600 bg-amber-50' },
      ].map(x => { const I = x.i; return <div key={x.l} className="bg-white border border-slate-200 rounded-xl p-4 shadow-xs"><div className="flex justify-between"><div><div className="text-xs text-slate-500">{x.l}</div><div className="text-xl font-bold mt-1 text-slate-900">{x.v}</div></div><div className={`w-9 h-9 rounded-lg flex items-center justify-center ${x.c}`}><I className="w-4 h-4" /></div></div></div>; })}
    </div>

    {selectedTerminal && <div className="bg-slate-900 text-white rounded-xl p-5 shadow-xs">
      <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
        <div>
          <div className="text-xs font-semibold text-indigo-200 uppercase tracking-wider">Детализация терминала</div>
          <div className="text-2xl font-bold mt-1 font-mono">{selectedTerminal.terminal_id}</div>
          <div className="text-sm text-slate-300 mt-1">{selectedTerminal.merchant_id || 'MID не указан'} · {selectedTerminal.legal_entity || 'Юрлицо не указано'}</div>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 min-w-0">
          <div className="bg-white/5 rounded-xl p-3"><div className="text-[11px] text-slate-400">Транзакции</div><div className="font-semibold mt-1">{selectedTerminal.tx_count.toLocaleString('ru-RU')}</div></div>
          <div className="bg-white/5 rounded-xl p-3"><div className="text-[11px] text-slate-400">Оборот</div><div className="font-semibold mt-1">{money(selectedTerminal.total_volume)}</div></div>
          <div className="bg-white/5 rounded-xl p-3"><div className="text-[11px] text-slate-400">Комиссия</div><div className="font-semibold mt-1">{money(selectedTerminal.commission_amount)}</div></div>
          <div className="bg-white/5 rounded-xl p-3"><div className="text-[11px] text-slate-400">Нетто</div><div className="font-semibold mt-1">{money(selectedTerminal.net_volume)}</div></div>
        </div>
      </div>
    </div>}

    <div className="grid grid-cols-1 xl:grid-cols-2 gap-5">
      <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-xs">
        <div className="flex items-center justify-between mb-4"><div><h4 className="font-semibold text-slate-900">Динамика по запускам</h4><p className="text-xs text-slate-500">Объём и качество последних результатов</p></div><Building2 className="w-5 h-5 text-slate-300" /></div>
        <div className="space-y-3">{filtered.slice(0, 8).map(a => { const c = a.matched_count + a.mismatch_count + a.only_our_count + a.only_bank_count; const r = c ? a.matched_count / c * 100 : 0; return <div key={a.id}><div className="flex justify-between text-xs mb-1"><span className="text-slate-600">{new Date(a.timestamp).toLocaleDateString('ru-RU')} · {a.bank_name}</span><span className="font-semibold">{r.toFixed(1)}%</span></div><div className="h-2 rounded-full bg-slate-100 overflow-hidden"><div className="h-full bg-indigo-500 rounded-full" style={{ width: `${Math.min(100, r)}%` }} /></div></div>; })}</div>
      </div>
      <div className="bg-slate-900 text-white rounded-xl p-5 shadow-xs">
        <div className="text-xs font-semibold text-indigo-200 uppercase tracking-wider">Период анализа</div>
        <div className="text-3xl font-bold mt-2">{filtered.length}</div>
        <div className="text-sm text-slate-300 mt-1">сохранённых запусков</div>
        <div className="grid grid-cols-2 gap-3 mt-6"><div className="bg-white/5 rounded-xl p-3"><div className="text-[11px] text-slate-400">Наш реестр</div><div className="font-semibold mt-1">{money(totals.our)}</div></div><div className="bg-white/5 rounded-xl p-3"><div className="text-[11px] text-slate-400">Банк</div><div className="font-semibold mt-1">{money(totals.bank)}</div></div></div>
        <div className="mt-4 text-xs text-slate-400">Пользователь: {user.username}</div>
      </div>
    </div>

    <div className="bg-white border border-slate-200 rounded-xl shadow-xs overflow-hidden">
      <div className="px-5 py-4 border-b border-slate-100 flex flex-col md:flex-row md:items-center md:justify-between gap-2"><div><h4 className="font-semibold text-slate-900">Терминальная аналитика</h4><p className="text-xs text-slate-500 mt-0.5">Все терминалы за выбранный банк и период; комиссия агрегируется из архивных сверок.</p></div><div className="text-xs text-slate-500">Показано {visibleTerminalRows.length} из {terminalRows.length}</div></div>
      {visibleTerminalRows.length === 0 ? <div className="p-10 text-center text-sm text-slate-500">Нет терминальной детализации.</div> : <div className="overflow-x-auto"><table className="min-w-full text-sm"><thead className="bg-slate-50"><tr>{['TID', 'Продукт / MID', 'Юрлицо', 'Транзакции', 'Оборот', 'Ставка', 'Комиссия', 'Нетто'].map(h => <th key={h} className="px-4 py-3 text-left text-[11px] font-semibold uppercase tracking-wider text-slate-400">{h}</th>)}</tr></thead><tbody className="divide-y divide-slate-100">{visibleTerminalRows.map(t => <tr key={t.terminal_id} className={`hover:bg-slate-50 ${terminal === t.terminal_id ? 'bg-indigo-50/60' : ''}`}><td className="px-4 py-3.5 font-mono font-medium">{t.terminal_id}</td><td className="px-4 py-3.5">{t.merchant_id || '—'}</td><td className="px-4 py-3.5 text-slate-600">{t.legal_entity || '—'}</td><td className="px-4 py-3.5">{t.tx_count.toLocaleString('ru-RU')}</td><td className="px-4 py-3.5 font-semibold">{money(t.total_volume)}</td><td className="px-4 py-3.5">{pct(t.commission_pct)}</td><td className="px-4 py-3.5 text-violet-700 font-semibold">{money(t.commission_amount)}</td><td className="px-4 py-3.5 font-semibold">{money(t.net_volume)}</td></tr>)}</tbody></table></div>}
    </div>
  </div>;
};
