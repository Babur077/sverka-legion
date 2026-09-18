import React, { useEffect, useState } from 'react';
import {
  AlertCircle,
  CheckCircle2,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronUp,
  Clock3,
  History,
  RefreshCw,
  Search,
} from 'lucide-react';
import {
  AuditEvent,
  AuditFilterOptions,
  getAuditFilterOptionsViaApi,
  getAuditViaApi,
} from '../utils/auditApi';
import { User } from '../types';

interface Props { user: User; }

const PAGE_SIZE = 50;
const EMPTY_FILTERS: AuditFilterOptions = { users: [], actions: [], modules: [], statuses: [] };

export const AuditPage: React.FC<Props> = ({ user }) => {
  const [items, setItems] = useState<AuditEvent[]>([]);
  const [filterOptions, setFilterOptions] = useState<AuditFilterOptions>(EMPTY_FILTERS);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [userFilter, setUserFilter] = useState('');
  const [actionFilter, setActionFilter] = useState('');
  const [moduleFilter, setModuleFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [search, setSearch] = useState('');
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [filtersLoading, setFiltersLoading] = useState(true);
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
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined,
      });
      setItems(result.items);
      setTotal(result.total);
    } catch (e: any) {
      setError(e?.message || 'Не удалось загрузить журнал аудита.');
    } finally {
      setLoading(false);
    }
  };

  const loadFilterOptions = async () => {
    setFiltersLoading(true);
    try {
      setFilterOptions(await getAuditFilterOptionsViaApi(user.username));
    } catch {
      // The event list still works if metadata cannot be loaded.
    } finally {
      setFiltersLoading(false);
    }
  };

  useEffect(() => {
    void loadFilterOptions();
  }, [user.username]);

  useEffect(() => {
    void load();
  }, [user.username, page, userFilter, actionFilter, moduleFilter, statusFilter, dateFrom, dateTo, search]);

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const fmtDate = (value: string) => new Date(value).toLocaleString('ru-RU');

  const resetFilters = () => {
    setUserFilter('');
    setActionFilter('');
    setModuleFilter('');
    setStatusFilter('');
    setDateFrom('');
    setDateTo('');
    setSearch('');
    setPage(0);
  };

  const onFilterChange = (setter: React.Dispatch<React.SetStateAction<string>>) => (value: string) => {
    setter(value);
    setPage(0);
  };

  const hasFilters = !!(
    userFilter || actionFilter || moduleFilter || statusFilter || dateFrom || dateTo || search.trim()
  );

  return (
    <div className="p-8 w-full max-w-[1800px] mx-auto space-y-6">
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold text-slate-900 flex items-center gap-2">
            <History className="w-5 h-5 text-indigo-600" />
            Журнал аудита
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            Неизменяемый серверный журнал запусков сверок, изменений доступа, архива, EPOS и системных настроек.
          </p>
        </div>
        <button
          onClick={() => {
            void load();
            void loadFilterOptions();
          }}
          disabled={loading}
          className="inline-flex items-center gap-2 px-4 py-2.5 bg-white border border-slate-200 rounded-xl text-xs font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          Обновить
        </button>
      </div>

      <div className="bg-white rounded-2xl border border-slate-200 p-4 shadow-xs space-y-3">
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-6 gap-3">
          <div className="relative md:col-span-2">
            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
            <input
              value={search}
              onChange={e => onFilterChange(setSearch)(e.target.value)}
              placeholder="Run ID, объект, пользователь, детали…"
              className="w-full pl-9 pr-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs focus:bg-white focus:outline-none focus:ring-1 focus:ring-indigo-500"
            />
          </div>

          <select
            value={userFilter}
            disabled={filtersLoading}
            onChange={e => onFilterChange(setUserFilter)(e.target.value)}
            className="px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs focus:outline-none disabled:opacity-50"
          >
            <option value="">Все пользователи</option>
            {filterOptions.users.map(value => <option key={value} value={value}>{value}</option>)}
          </select>

          <select
            value={actionFilter}
            disabled={filtersLoading}
            onChange={e => onFilterChange(setActionFilter)(e.target.value)}
            className="px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs focus:outline-none disabled:opacity-50"
          >
            <option value="">Все действия</option>
            {filterOptions.actions.map(value => <option key={value} value={value}>{value}</option>)}
          </select>

          <select
            value={moduleFilter}
            disabled={filtersLoading}
            onChange={e => onFilterChange(setModuleFilter)(e.target.value)}
            className="px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs focus:outline-none disabled:opacity-50"
          >
            <option value="">Все модули</option>
            {filterOptions.modules.map(value => <option key={value} value={value}>{value}</option>)}
          </select>

          <select
            value={statusFilter}
            disabled={filtersLoading}
            onChange={e => onFilterChange(setStatusFilter)(e.target.value)}
            className="px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs focus:outline-none disabled:opacity-50"
          >
            <option value="">Все статусы</option>
            {filterOptions.statuses.map(value => <option key={value} value={value}>{value}</option>)}
          </select>
        </div>

        <div className="flex flex-col lg:flex-row lg:items-end justify-between gap-3">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <label className="text-[11px] text-slate-500">
              <span className="block mb-1 font-semibold text-slate-600">С даты</span>
              <input
                type="date"
                value={dateFrom}
                max={dateTo || undefined}
                onChange={e => onFilterChange(setDateFrom)(e.target.value)}
                className="px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs"
              />
            </label>
            <label className="text-[11px] text-slate-500">
              <span className="block mb-1 font-semibold text-slate-600">По дату</span>
              <input
                type="date"
                value={dateTo}
                min={dateFrom || undefined}
                onChange={e => onFilterChange(setDateTo)(e.target.value)}
                className="px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs"
              />
            </label>
          </div>

          <div className="flex items-center gap-3">
            {hasFilters && (
              <button onClick={resetFilters} className="text-xs font-semibold text-indigo-600 hover:underline">
                Сбросить фильтры
              </button>
            )}
            <span className="text-xs text-slate-500">
              Всего событий: <strong className="text-slate-800">{total}</strong>
            </span>
          </div>
        </div>
      </div>

      <div className="bg-white rounded-2xl border border-slate-200 shadow-xs overflow-hidden">
        {loading ? (
          <div className="p-12 text-center text-sm text-slate-400">Загрузка журнала…</div>
        ) : error ? (
          <div className="p-12 text-center text-sm text-rose-600 flex flex-col items-center gap-2">
            <AlertCircle className="w-5 h-5" />
            {error}
          </div>
        ) : items.length === 0 ? (
          <div className="p-12 text-center text-sm text-slate-400">Событий по выбранным фильтрам нет.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full text-xs">
              <thead className="bg-slate-50 border-b border-slate-200 text-slate-700 font-bold">
                <tr>
                  <th className="px-4 py-3 text-left w-8"></th>
                  <th className="px-4 py-3 text-left">Время</th>
                  <th className="px-4 py-3 text-left">Пользователь</th>
                  <th className="px-4 py-3 text-left">Действие</th>
                  <th className="px-4 py-3 text-left">Модуль</th>
                  <th className="px-4 py-3 text-left">Объект / Run ID</th>
                  <th className="px-4 py-3 text-left">Статус</th>
                  <th className="px-4 py-3 text-right">Время, мс</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {items.map(item => {
                  const expanded = expandedId === item.id;
                  return (
                    <React.Fragment key={item.id}>
                      <tr className="hover:bg-slate-50 align-top">
                        <td className="px-3 py-3">
                          <button
                            type="button"
                            onClick={() => setExpandedId(current => current === item.id ? null : item.id)}
                            className="p-1 rounded text-slate-400 hover:text-indigo-600 hover:bg-indigo-50"
                            title={expanded ? 'Скрыть детали' : 'Показать детали'}
                          >
                            {expanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                          </button>
                        </td>
                        <td className="px-4 py-3 whitespace-nowrap text-slate-500">{fmtDate(item.timestamp)}</td>
                        <td className="px-4 py-3 font-semibold text-slate-900">{item.user_id}</td>
                        <td className="px-4 py-3 font-mono text-[11px] text-indigo-700 whitespace-nowrap">{item.action}</td>
                        <td className="px-4 py-3 text-slate-600">{item.module_id || '—'}</td>
                        <td className="px-4 py-3 text-slate-600">
                          {item.object_type || item.object_id ? (
                            <div>
                              <div>{item.object_type || 'Объект'}</div>
                              {item.object_id && <div className="font-mono text-[10px] text-slate-400 mt-0.5">{item.object_id}</div>}
                            </div>
                          ) : '—'}
                        </td>
                        <td className="px-4 py-3 whitespace-nowrap">
                          {item.status === 'SUCCESS' ? (
                            <span className="inline-flex items-center gap-1 text-emerald-700 font-semibold">
                              <CheckCircle2 className="w-3.5 h-3.5" />SUCCESS
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1 text-rose-700 font-semibold">
                              <AlertCircle className="w-3.5 h-3.5" />{item.status || '—'}
                            </span>
                          )}
                        </td>
                        <td className="px-4 py-3 text-right text-slate-500 tabular-nums">
                          {typeof item.duration_ms === 'number' && item.duration_ms ? Math.round(item.duration_ms) : '—'}
                        </td>
                      </tr>
                      {expanded && (
                        <tr className="bg-slate-50/60">
                          <td></td>
                          <td colSpan={7} className="px-4 py-3">
                            <div className="grid grid-cols-1 lg:grid-cols-[1fr_220px] gap-4">
                              <div>
                                <div className="text-[10px] uppercase tracking-wider text-slate-400 font-semibold">Подробности события</div>
                                <div className="mt-1 text-xs text-slate-700 whitespace-pre-wrap break-words">{item.details || 'Нет дополнительных деталей.'}</div>
                              </div>
                              <div className="text-[11px] text-slate-500 space-y-1">
                                <div><span className="text-slate-400">Event ID:</span> {item.id}</div>
                                <div><span className="text-slate-400">IP:</span> {item.ip_address || '—'}</div>
                                <div><span className="text-slate-400">Object ID:</span> <span className="font-mono">{item.object_id || '—'}</span></div>
                              </div>
                            </div>
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        <div className="flex items-center justify-between px-4 py-3 border-t border-slate-200 bg-slate-50/60">
          <span className="text-xs text-slate-500">Страница {Math.min(page + 1, totalPages)} из {totalPages}</span>
          <div className="flex items-center gap-1">
            <button
              onClick={() => setPage(value => Math.max(0, value - 1))}
              disabled={page === 0 || loading}
              className="p-2 rounded-lg border border-slate-200 bg-white disabled:opacity-40"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            <button
              onClick={() => setPage(value => Math.min(totalPages - 1, value + 1))}
              disabled={page >= totalPages - 1 || loading}
              className="p-2 rounded-lg border border-slate-200 bg-white disabled:opacity-40"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>

      <div className="flex items-center gap-2 text-[11px] text-slate-400">
        <Clock3 className="w-3.5 h-3.5" />
        Источник данных: серверный audit_events в SQLite. Фильтрация и пагинация выполняются на backend.
      </div>
    </div>
  );
};
