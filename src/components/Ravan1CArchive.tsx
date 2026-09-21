import React, { useEffect, useMemo, useState } from 'react';
import {
  CalendarDays,
  ChevronLeft,
  ChevronRight,
  Download,
  FileSpreadsheet,
  FolderOpen,
  LoaderCircle,
  RefreshCcw,
  Search,
  Trash2,
  X,
} from 'lucide-react';

import {
  exportRavan1CToExcel,
  Ravan1CArchiveRecord,
  Ravan1CRunResult,
} from '../utils/ravan1cApi';

interface Props {
  records: Ravan1CArchiveRecord[];
  loading: boolean;
  canExport: boolean;
  canDelete: boolean;
  onRefresh: () => void | Promise<void>;
  onOpen: (record: Ravan1CArchiveRecord) => void;
  onDelete: (record: Ravan1CArchiveRecord) => void | Promise<void>;
}

const PAGE_SIZE = 12;

function archiveSummary(record: Ravan1CArchiveRecord): Ravan1CRunResult['summary'] | undefined {
  return record.summary || record.result_snapshot?.summary;
}

function archiveUser(record: Ravan1CArchiveRecord): string {
  return String(record.created_by || record.username || '').trim();
}

function archiveDate(record: Ravan1CArchiveRecord): string {
  return String(record.created_at || record.timestamp || '').trim();
}

function formatNumber(value: number | null | undefined, digits = 2): string {
  const number = Number(value ?? 0);
  return Number.isFinite(number)
    ? number.toLocaleString('ru-RU', { maximumFractionDigits: digits })
    : '—';
}

function formatDateTime(value?: string): string {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleString('ru-RU', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      });
}

function parseStartOfDay(value: string): number | null {
  if (!value) return null;
  const timestamp = new Date(`${value}T00:00:00`).getTime();
  return Number.isNaN(timestamp) ? null : timestamp;
}

function parseEndOfDay(value: string): number | null {
  if (!value) return null;
  const timestamp = new Date(`${value}T23:59:59.999`).getTime();
  return Number.isNaN(timestamp) ? null : timestamp;
}

export const Ravan1CArchive: React.FC<Props> = ({
  records,
  loading,
  canExport,
  canDelete,
  onRefresh,
  onOpen,
  onDelete,
}) => {
  const [query, setQuery] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [userFilter, setUserFilter] = useState('Все');
  const [page, setPage] = useState(1);
  const [deletingId, setDeletingId] = useState<number | null>(null);

  const users = useMemo(
    () => Array.from(new Set(records.map(archiveUser).filter(Boolean))).sort((a, b) => a.localeCompare(b, 'ru')),
    [records],
  );

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const start = parseStartOfDay(dateFrom);
    const end = parseEndOfDay(dateTo);

    return records.filter(record => {
      const username = archiveUser(record);
      if (userFilter !== 'Все' && username !== userFilter) return false;

      const rawDate = archiveDate(record);
      if (start != null || end != null) {
        const timestamp = new Date(rawDate).getTime();
        if (Number.isNaN(timestamp)) return false;
        if (start != null && timestamp < start) return false;
        if (end != null && timestamp > end) return false;
      }

      if (!needle) return true;
      const haystack = [
        record.run_id,
        record.id,
        username,
        ...(record.source_files || []),
      ]
        .filter(value => value != null)
        .join(' ')
        .toLowerCase();
      return haystack.includes(needle);
    });
  }, [records, query, dateFrom, dateTo, userFilter]);

  useEffect(() => {
    setPage(1);
  }, [query, dateFrom, dateTo, userFilter, records.length]);

  const totals = useMemo(
    () => filtered.reduce(
      (acc, record) => {
        const summary = archiveSummary(record);
        acc.ravan += Number(summary?.total_sum_a || 0);
        acc.oneC += Number(summary?.total_sum_b || 0);
        acc.diff += Number(summary?.diff_sum || 0);
        acc.discrepancies += Number(summary?.discrepancy_count || 0);
        return acc;
      },
      { ravan: 0, oneC: 0, diff: 0, discrepancies: 0 },
    ),
    [filtered],
  );

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const safePage = Math.min(page, totalPages);
  const pageRows = filtered.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE);
  const hasFilters = Boolean(query || dateFrom || dateTo || userFilter !== 'Все');

  const resetFilters = () => {
    setQuery('');
    setDateFrom('');
    setDateTo('');
    setUserFilter('Все');
  };

  const handleDelete = async (record: Ravan1CArchiveRecord) => {
    if (!canDelete || deletingId != null) return;
    const label = record.run_id ? `Run ${record.run_id}` : `запись #${record.id}`;
    const confirmed = window.confirm(
      `Удалить ${label} из архива?\n\nЭто действие нельзя отменить.`,
    );
    if (!confirmed) return;

    setDeletingId(record.id);
    try {
      await onDelete(record);
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-xs">
      <div className="flex flex-col gap-4 border-b border-slate-100 px-5 py-4 xl:flex-row xl:items-center xl:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <FolderOpen className="h-4 w-4 text-indigo-500" />
            <h2 className="text-sm font-bold text-slate-900">Архив сверок погашений</h2>
          </div>
          <p className="mt-1 text-xs text-slate-500">
            Поиск, фильтры, суммы и повторное открытие сохранённых результатов.
          </p>
        </div>

        <button
          type="button"
          onClick={() => void onRefresh()}
          disabled={loading}
          className="inline-flex items-center justify-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-50 disabled:opacity-50"
        >
          <RefreshCcw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
          Обновить
        </button>
      </div>

      <div className="border-b border-slate-100 bg-slate-50/60 p-4">
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-[minmax(260px,1fr)_170px_170px_210px_auto]">
          <label className="relative">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <input
              value={query}
              onChange={event => setQuery(event.target.value)}
              placeholder="Run ID, файл или пользователь"
              className="w-full rounded-lg border border-slate-200 bg-white py-2.5 pl-9 pr-3 text-xs text-slate-700 outline-none transition focus:border-indigo-300 focus:ring-2 focus:ring-indigo-100"
            />
          </label>

          <label className="relative">
            <CalendarDays className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <input
              type="date"
              value={dateFrom}
              onChange={event => setDateFrom(event.target.value)}
              title="Дата с"
              className="w-full rounded-lg border border-slate-200 bg-white py-2.5 pl-9 pr-3 text-xs text-slate-700 outline-none transition focus:border-indigo-300 focus:ring-2 focus:ring-indigo-100"
            />
          </label>

          <label className="relative">
            <CalendarDays className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <input
              type="date"
              value={dateTo}
              onChange={event => setDateTo(event.target.value)}
              title="Дата по"
              className="w-full rounded-lg border border-slate-200 bg-white py-2.5 pl-9 pr-3 text-xs text-slate-700 outline-none transition focus:border-indigo-300 focus:ring-2 focus:ring-indigo-100"
            />
          </label>

          <select
            value={userFilter}
            onChange={event => setUserFilter(event.target.value)}
            className="rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-xs font-semibold text-slate-600 outline-none transition focus:border-indigo-300 focus:ring-2 focus:ring-indigo-100"
          >
            <option value="Все">Все пользователи</option>
            {users.map(username => (
              <option key={username} value={username}>{username}</option>
            ))}
          </select>

          <button
            type="button"
            onClick={resetFilters}
            disabled={!hasFilters}
            className="inline-flex items-center justify-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-xs font-semibold text-slate-600 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
          >
            <X className="h-4 w-4" />
            Сбросить
          </button>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 border-b border-slate-100 p-4 lg:grid-cols-5">
        {[
          ['Запусков', filtered.length.toLocaleString('ru-RU')],
          ['Сумма Ravan', formatNumber(totals.ravan)],
          ['Сумма 1C', formatNumber(totals.oneC)],
          ['Δ суммы', formatNumber(totals.diff)],
          ['Расхождений', totals.discrepancies.toLocaleString('ru-RU')],
        ].map(([label, value]) => (
          <div key={label} className="rounded-xl border border-slate-200 bg-white p-3">
            <div className="truncate text-lg font-black text-slate-900" title={value}>{value}</div>
            <div className="mt-1 text-[10px] font-semibold uppercase tracking-wide text-slate-400">{label}</div>
          </div>
        ))}
      </div>

      <div className="overflow-x-auto">
        <table className="min-w-[1180px] w-full text-xs">
          <thead className="bg-slate-50">
            <tr className="text-[10px] uppercase tracking-wider text-slate-400">
              <th className="px-4 py-3 text-left">Дата</th>
              <th className="px-4 py-3 text-left">Run / пользователь</th>
              <th className="px-4 py-3 text-left">Файлы</th>
              <th className="px-4 py-3 text-right">Ravan</th>
              <th className="px-4 py-3 text-right">1C</th>
              <th className="px-4 py-3 text-right">Δ</th>
              <th className="px-4 py-3 text-right">Расх.</th>
              <th className="px-4 py-3 text-right">Сходимость</th>
              <th className="px-4 py-3 text-right">Действия</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {pageRows.map(record => {
              const summary = archiveSummary(record);
              const snapshot = record.result_snapshot;
              const files = record.source_files || [];
              return (
                <tr key={record.id} className="hover:bg-slate-50/70">
                  <td className="whitespace-nowrap px-4 py-3 text-slate-600">
                    {formatDateTime(archiveDate(record))}
                  </td>
                  <td className="px-4 py-3">
                    <div className="font-semibold text-slate-800">Run {record.run_id || `#${record.id}`}</div>
                    <div className="mt-0.5 text-[10px] text-slate-400">{archiveUser(record) || '—'}</div>
                  </td>
                  <td className="max-w-[260px] px-4 py-3 text-slate-600">
                    <div className="flex items-start gap-2">
                      <FileSpreadsheet className="mt-0.5 h-3.5 w-3.5 shrink-0 text-slate-400" />
                      <div className="min-w-0">
                        {files.length
                          ? files.map(file => (
                              <div key={file} className="truncate" title={file}>{file}</div>
                            ))
                          : <span className="text-slate-400">—</span>}
                      </div>
                    </div>
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-right tabular-nums text-slate-700">
                    {formatNumber(summary?.total_sum_a)}
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-right tabular-nums text-slate-700">
                    {formatNumber(summary?.total_sum_b)}
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-right font-semibold tabular-nums text-slate-800">
                    {formatNumber(summary?.diff_sum)}
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-right font-semibold tabular-nums text-amber-700">
                    {Number(summary?.discrepancy_count || 0).toLocaleString('ru-RU')}
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-right font-semibold tabular-nums text-slate-700">
                    {formatNumber(summary?.match_percentage, 1)}%
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex justify-end gap-2">
                      <button
                        type="button"
                        onClick={() => onOpen(record)}
                        disabled={!snapshot}
                        title={snapshot ? 'Открыть сохранённый результат' : 'Полный snapshot не сохранён'}
                        className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-[11px] font-semibold text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
                      >
                        <FolderOpen className="h-3.5 w-3.5" />
                        Открыть
                      </button>
                      <button
                        type="button"
                        onClick={() => snapshot && exportRavan1CToExcel(snapshot)}
                        disabled={!canExport || !snapshot}
                        title={!snapshot ? 'Полный snapshot не сохранён' : 'Выгрузить сохранённый результат в Excel'}
                        className="inline-flex items-center gap-1.5 rounded-lg border border-emerald-200 bg-emerald-50 px-2.5 py-1.5 text-[11px] font-semibold text-emerald-700 hover:bg-emerald-100 disabled:cursor-not-allowed disabled:opacity-40"
                      >
                        <Download className="h-3.5 w-3.5" />
                        Excel
                      </button>
                      {canDelete && (
                        <button
                          type="button"
                          onClick={() => void handleDelete(record)}
                          disabled={deletingId != null}
                          title="Удалить запись из архива"
                          className="inline-flex items-center gap-1.5 rounded-lg border border-rose-200 bg-rose-50 px-2.5 py-1.5 text-[11px] font-semibold text-rose-700 hover:bg-rose-100 disabled:cursor-not-allowed disabled:opacity-40"
                        >
                          {deletingId === record.id
                            ? <LoaderCircle className="h-3.5 w-3.5 animate-spin" />
                            : <Trash2 className="h-3.5 w-3.5" />}
                          Удалить
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>

        {!loading && filtered.length === 0 && (
          <div className="px-5 py-12 text-center text-sm text-slate-500">
            {records.length === 0
              ? 'В архиве пока нет запусков этой сверки.'
              : 'По выбранным фильтрам записи не найдены.'}
          </div>
        )}

        {loading && records.length === 0 && (
          <div className="px-5 py-12 text-center text-sm text-slate-500">
            Загружаем архив…
          </div>
        )}
      </div>

      <div className="flex flex-col gap-3 border-t border-slate-100 px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="text-xs text-slate-500">
          Показано {pageRows.length.toLocaleString('ru-RU')} из {filtered.length.toLocaleString('ru-RU')} записей
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setPage(current => Math.max(1, current - 1))}
            disabled={safePage <= 1}
            className="rounded-lg border border-slate-200 bg-white p-2 text-slate-500 hover:bg-slate-50 disabled:opacity-40"
            title="Предыдущая страница"
          >
            <ChevronLeft className="h-4 w-4" />
          </button>
          <span className="min-w-20 text-center text-xs font-semibold text-slate-600">
            {safePage} / {totalPages}
          </span>
          <button
            type="button"
            onClick={() => setPage(current => Math.min(totalPages, current + 1))}
            disabled={safePage >= totalPages}
            className="rounded-lg border border-slate-200 bg-white p-2 text-slate-500 hover:bg-slate-50 disabled:opacity-40"
            title="Следующая страница"
          >
            <ChevronRight className="h-4 w-4" />
          </button>
        </div>
      </div>
    </section>
  );
};
