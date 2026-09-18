import React, { useEffect, useMemo, useState } from 'react';
import { History, Search, RefreshCw, ChevronLeft, ChevronRight, AlertCircle, CheckCircle2, Clock3 } from 'lucide-react';
import { AuditEvent } from '../utils/auditApi';
import { getAuditViaApi } from '../utils/auditApi';
import { User } from '../types';

interface Props { user: User; }

const PAGE_SIZE = 50;

export const AuditPage: React.FC<Props> = ({ user }) => {
  const [items, setItems] = useState<AuditEvent[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [userFilter, setUserFilter] = useState('');
  const [actionFilter, setActionFilter] = useState('');
  const [moduleFilter, setModuleFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await getAuditViaApi(user.username, {
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
        user: userFilter || undefined,
        action: actionFilter || undefined,
        module_id: moduleFilter || undefined,
        status: statusFilter || undefined,
        search: search.trim() || undefined,
      });
      setItems(result.items);
      setTotal(result.total);
    } catch (e: any) {
      setError(e?.message || 'Не удалось загрузить журнал аудита.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void load(); }, [user.username, page, userFilter, actionFilter, moduleFilter, statusFilter, search]);

  const actionOptions = useMemo(() => Array.from(new Set(items.map(i => i.action))).sort(), [items]);
  const moduleOptions = useMemo(() => Array.from(new Set(items.map(i => i.module_id).filter(Boolean) as string[])).sort(), [items]);

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const fmtDate = (value: string) => new Date(value).toLocaleString('ru-RU');

  const resetFilters = () => {
    setUserFilter('');
    setActionFilter('');
    setModuleFilter('');
    setStatusFilter('');
    setSearch('');
    setPage(0);
  };

  const onFilterChange = (setter: React.Dispatch<React.SetStateAction<string>>) => (value: string) => {
    setter(value);
    setPage(0);
  };

  return (
    <div className="p-8 w-full max-w-[1800px] mx-auto space-y-6">
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold text-slate-900 flex items-center gap-2">
            <History className="w-5 h-5 text-indigo-600" />
            Журнал аудита
          </h1>
          <p className="text-sm text-slate-500 mt-1">Централизованный серверный журнал действий ReconcileHub.</p>
        </div>
        <button onClick={() => void load()} disabled={loading} className="inline-flex items-center gap-2 px-4 py-2.5 bg-white border border-slate-200 rounded-xl text-xs font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50">
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          Обновить
        </button>
      </div>

      <div className="bg-white rounded-2xl border border-slate-200 p-4 shadow-xs">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-3">
          <div className="relative lg:col-span-2">
            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
            <input value={search} onChange={e => onFilterChange(setSearch)(e.target.value)} placeholder="Поиск по пользователю, действию, объекту, деталям…" className="w-full pl-9 pr-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs focus:bg-white focus:outline-none focus:ring-1 focus:ring-indigo-500" />
          </div>
          <input value={userFilter} onChange={e => onFilterChange(setUserFilter)(e.target.value)} placeholder="Пользователь" className="px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs focus:bg-white focus:outline-none focus:ring-1 focus:ring-indigo-500" />
          <select value={actionFilter} onChange={e => onFilterChange(setActionFilter)(e.target.value)} className="px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs focus:outline-none">
            <option value="">Все действия</option>
            {actionOptions.map(a => <option key={a} value={a}>{a}</option>)}
          </select>
          <select value={moduleFilter} onChange={e => onFilterChange(setModuleFilter)(e.target.value)} className="px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs focus:outline-none">
            <option value="">Все модули</option>
            {moduleOptions.map(m => <option key={m} value={m}>{m}</option>)}
          </select>
        </div>
        <div className="flex flex-wrap items-center justify-between gap-3 mt-3">
          <div className="flex items-center gap-3">
            <select value={statusFilter} onChange={e => onFilterChange(setStatusFilter)(e.target.value)} className="px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs focus:outline-none">
              <option value="">Все статусы</option>
              <option value="SUCCESS">SUCCESS</option>
              <option value="FAILED">FAILED</option>
            </select>
            <button onClick={resetFilters} className="text-xs font-semibold text-indigo-600 hover:underline">Сбросить фильтры</button>
          </div>
          <span className="text-xs text-slate-500">Всего событий: <strong className="text-slate-800">{total}</strong></span>
        </div>
      </div>

      <div className="bg-white rounded-2xl border border-slate-200 shadow-xs overflow-hidden">
        {loading ? (
          <div className="p-12 text-center text-sm text-slate-400">Загрузка журнала…</div>
        ) : error ? (
          <div className="p-12 text-center text-sm text-rose-600 flex flex-col items-center gap-2"><AlertCircle className="w-5 h-5" />{error}</div>
        ) : items.length === 0 ? (
          <div className="p-12 text-center text-sm text-slate-400">Событий по выбранным фильтрам нет.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full text-xs">
              <thead className="bg-slate-50 border-b border-slate-200 text-slate-700 font-bold">
                <tr>
                  <th className="px-4 py-3 text-left">Время</th>
                  <th className="px-4 py-3 text-left">Пользователь</th>
                  <th className="px-4 py-3 text-left">Действие</th>
                  <th className="px-4 py-3 text-left">Модуль</th>
                  <th className="px-4 py-3 text-left">Объект</th>
                  <th className="px-4 py-3 text-left">Статус</th>
                  <th className="px-4 py-3 text-right">Время, мс</th>
                  <th className="px-4 py-3 text-left">Подробности</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {items.map(item => (
                  <tr key={item.id} className="hover:bg-slate-50 align-top">
                    <td className="px-4 py-3 whitespace-nowrap text-slate-500">{fmtDate(item.timestamp)}</td>
                    <td className="px-4 py-3 font-semibold text-slate-900">{item.user_id}</td>
                    <td className="px-4 py-3 font-mono text-[11px] text-indigo-700 whitespace-nowrap">{item.action}</td>
                    <td className="px-4 py-3 text-slate-600">{item.module_id || '—'}</td>
                    <td className="px-4 py-3 text-slate-600">{item.object_type ? `${item.object_type}${item.object_id ? ` #${item.object_id}` : ''}` : '—'}</td>
                    <td className="px-4 py-3 whitespace-nowrap">
                      {item.status === 'SUCCESS' ? <span className="inline-flex items-center gap-1 text-emerald-700 font-semibold"><CheckCircle2 className="w-3.5 h-3.5" />SUCCESS</span> : <span className="inline-flex items-center gap-1 text-rose-700 font-semibold"><AlertCircle className="w-3.5 h-3.5" />{item.status || '—'}</span>}
                    </td>
                    <td className="px-4 py-3 text-right text-slate-500 tabular-nums">{typeof item.duration_ms === 'number' && item.duration_ms ? Math.round(item.duration_ms) : '—'}</td>
                    <td className="px-4 py-3 text-slate-600 max-w-[520px]">{item.details || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <div className="flex items-center justify-between px-4 py-3 border-t border-slate-200 bg-slate-50/60">
          <span className="text-xs text-slate-500">Страница {Math.min(page + 1, totalPages)} из {totalPages}</span>
          <div className="flex items-center gap-1">
            <button onClick={() => setPage(p => Math.max(0, p - 1))} disabled={page === 0 || loading} className="p-2 rounded-lg border border-slate-200 bg-white disabled:opacity-40"><ChevronLeft className="w-4 h-4" /></button>
            <button onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))} disabled={page >= totalPages - 1 || loading} className="p-2 rounded-lg border border-slate-200 bg-white disabled:opacity-40"><ChevronRight className="w-4 h-4" /></button>
          </div>
        </div>
      </div>

      <div className="flex items-center gap-2 text-[11px] text-slate-400">
        <Clock3 className="w-3.5 h-3.5" />
        Источник данных: серверный audit_events в SQLite.
      </div>
    </div>
  );
};
