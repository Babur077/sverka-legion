import React, { useEffect, useMemo, useState } from 'react';
import {
  ArrowLeft,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Download,
  FileSpreadsheet,
  FolderOpen,
  LoaderCircle,
  Play,
  RefreshCcw,
  Search,
  Trash2,
  Upload,
} from 'lucide-react';

import { User } from '../types';
import { hasPermission } from '../utils/permissions';
import {
  deleteRepaymentsArchive,
  exportRepaymentsToExcel,
  getRepaymentsArchive,
  getRepaymentsArchiveRecord,
  RepaymentRow,
  RepaymentsArchiveRecord,
  RepaymentsRunResult,
  runRepayments,
  saveRepaymentsRun,
} from '../utils/repaymentsApi';

interface Props {
  user: User;
  onBack: () => void;
}

const STATUS_ORDER = [
  'Все',
  'Правильно',
  'Не верная сумма',
  'Не верная дата',
  'Не верно',
  'Не опознано',
  'Нет в системе',
  'Нет в 1С',
];

const PAGE_SIZE = 100;

function money(value: number | null | undefined): string {
  const number = Number(value ?? 0);
  return Number.isFinite(number)
    ? number.toLocaleString('ru-RU', { maximumFractionDigits: 2 })
    : '—';
}

function formatDateTime(value?: string): string {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function statusClass(status: string): string {
  if (status === 'Правильно') return 'bg-emerald-50 text-emerald-700 border-emerald-200';
  if (status.startsWith('Нет в')) return 'bg-slate-50 text-slate-700 border-slate-200';
  if (status === 'Не опознано') return 'bg-violet-50 text-violet-700 border-violet-200';
  if (status === 'Не верно') return 'bg-rose-50 text-rose-700 border-rose-200';
  return 'bg-amber-50 text-amber-700 border-amber-200';
}

export const RepaymentsWorkspace: React.FC<Props> = ({ user, onBack }) => {
  const canRun = hasPermission(user, 'repayments.run');
  const canExport = hasPermission(user, 'repayments.export');

  const [oneCFile, setOneCFile] = useState<File | null>(null);
  const [metaFile, setMetaFile] = useState<File | null>(null);
  const [oneCHeaderRow, setOneCHeaderRow] = useState(1);
  const [metaHeaderRow, setMetaHeaderRow] = useState(1);
  const [result, setResult] = useState<RepaymentsRunResult | null>(null);
  const [running, setRunning] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error' | 'info'; text: string } | null>(null);
  const [statusFilter, setStatusFilter] = useState('Все');
  const [query, setQuery] = useState('');
  const [page, setPage] = useState(1);
  const [expandedPayments, setExpandedPayments] = useState<Set<string>>(() => new Set());

  const [archive, setArchive] = useState<RepaymentsArchiveRecord[]>([]);
  const [archiveLoading, setArchiveLoading] = useState(false);
  const [archiveRecordLoading, setArchiveRecordLoading] = useState<number | null>(null);
  const [deletingId, setDeletingId] = useState<number | null>(null);

  const rows = result?.custom_metrics?.repayments?.rows || [];
  const statusCounts = result?.custom_metrics?.repayments?.status_counts || {};

  const filteredRows = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return rows.filter(row => {
      if (statusFilter !== 'Все' && row['Комментарий'] !== statusFilter) return false;
      if (!needle) return true;
      return [
        row['Номер платежа'],
        row['Номер договора опознание'],
        row['Назначение платежа'],
        row['Комментарий'],
      ].some(value => String(value || '').toLowerCase().includes(needle));
    });
  }, [rows, query, statusFilter]);

  useEffect(() => {
    setPage(1);
  }, [query, statusFilter, rows.length]);

  const totalPages = Math.max(1, Math.ceil(filteredRows.length / PAGE_SIZE));
  const safePage = Math.min(page, totalPages);
  const pageRows = filteredRows.slice(
    (safePage - 1) * PAGE_SIZE,
    safePage * PAGE_SIZE,
  );

  const togglePaymentPurpose = (paymentNumber: string) => {
    setExpandedPayments(current => {
      const next = new Set(current);
      if (next.has(paymentNumber)) next.delete(paymentNumber);
      else next.add(paymentNumber);
      return next;
    });
  };

  const loadArchive = async () => {
    setArchiveLoading(true);
    try {
      setArchive(await getRepaymentsArchive(user.username));
    } catch (error: any) {
      setMessage({
        type: 'info',
        text: error?.message || 'Не удалось загрузить архив.',
      });
    } finally {
      setArchiveLoading(false);
    }
  };

  useEffect(() => {
    void loadArchive();
  }, [user.username]);

  const handleRun = async () => {
    if (!canRun || running) return;
    if (!oneCFile || !metaFile) {
      setMessage({ type: 'error', text: 'Загрузите оба файла: 1C Погашение и Meta Погашение.' });
      return;
    }

    setRunning(true);
    setMessage(null);
    setResult(null);
    try {
      const next = await runRepayments(
        oneCFile,
        metaFile,
        oneCHeaderRow,
        metaHeaderRow,
      );
      setResult(next);
      setStatusFilter('Все');
      setQuery('');
      setExpandedPayments(new Set());

      try {
        const archiveMessage = await saveRepaymentsRun(user.username, next);
        setMessage({ type: 'success', text: `Сверка завершена. ${archiveMessage}` });
        await loadArchive();
      } catch (archiveError: any) {
        setMessage({
          type: 'info',
          text: `Сверка завершена, но архив не сохранился: ${archiveError?.message || archiveError}`,
        });
      }
    } catch (error: any) {
      setMessage({ type: 'error', text: error?.message || 'Не удалось выполнить сверку.' });
    } finally {
      setRunning(false);
    }
  };

  const openArchive = async (record: RepaymentsArchiveRecord) => {
    setArchiveRecordLoading(record.id);
    try {
      const full = await getRepaymentsArchiveRecord(user.username, record.id);
      if (!full.result_snapshot) {
        throw new Error('Для этой записи не сохранён полный snapshot результата.');
      }
      setResult(full.result_snapshot);
      setStatusFilter('Все');
      setQuery('');
      setExpandedPayments(new Set());
      window.scrollTo({ top: 0, behavior: 'smooth' });
      setMessage({
        type: 'info',
        text: `Открыт архивный Run ${record.run_id || '#' + record.id}.`,
      });
    } catch (error: any) {
      setMessage({ type: 'error', text: error?.message || 'Не удалось открыть архивную запись.' });
    } finally {
      setArchiveRecordLoading(null);
    }
  };

  const deleteArchive = async (record: RepaymentsArchiveRecord) => {
    if (!canRun || deletingId != null) return;
    if (!window.confirm(`Удалить Run ${record.run_id || '#' + record.id} из архива?\n\nДействие нельзя отменить.`)) {
      return;
    }

    setDeletingId(record.id);
    try {
      await deleteRepaymentsArchive(user.username, record.id);
      setArchive(current => current.filter(item => item.id !== record.id));
      if (record.run_id && result?.run_id === record.run_id) setResult(null);
      setMessage({ type: 'success', text: 'Архивная запись удалена.' });
    } catch (error: any) {
      setMessage({ type: 'error', text: error?.message || 'Не удалось удалить архивную запись.' });
    } finally {
      setDeletingId(null);
    }
  };

  const metrics = result?.custom_metrics?.repayments;

  return (
    <div className="min-h-full bg-slate-50">
      <div className="sticky top-0 z-20 border-b border-slate-200 bg-white/95 px-5 py-4 backdrop-blur">
        <div className="mx-auto flex max-w-[1800px] items-center justify-between gap-4">
          <div className="flex min-w-0 items-center gap-3">
            <button
              type="button"
              onClick={onBack}
              className="rounded-lg border border-slate-200 bg-white p-2 text-slate-500 hover:bg-slate-50"
              title="Назад к модулям"
            >
              <ArrowLeft className="h-4 w-4" />
            </button>
            <div>
              <h1 className="text-lg font-black text-slate-900">Сверка Погашений</h1>
              <p className="text-xs text-slate-500">1C ↔ Meta по номеру платежа</p>
            </div>
          </div>

          {result && canExport && (
            <button
              type="button"
              onClick={() => exportRepaymentsToExcel(result)}
              className="inline-flex items-center gap-2 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs font-bold text-emerald-700 hover:bg-emerald-100"
            >
              <Download className="h-4 w-4" />
              Excel
            </button>
          )}
        </div>
      </div>

      <div className="mx-auto max-w-[1800px] space-y-5 p-5">
        <section className="grid grid-cols-1 gap-4 xl:grid-cols-2">
          {[
            {
              title: '1C Погашение',
              file: oneCFile,
              setFile: setOneCFile,
              header: oneCHeaderRow,
              setHeader: setOneCHeaderRow,
              columns: 'Вх.номер · Дата · Сумма',
            },
            {
              title: 'Meta Погашение',
              file: metaFile,
              setFile: setMetaFile,
              header: metaHeaderRow,
              setHeader: setMetaHeaderRow,
              columns: 'withdraw_unique_id · bank_date · bank_amount · our_system_date · our_system_amount_success · contract_number',
            },
          ].map(source => (
            <div key={source.title} className="rounded-2xl border border-slate-200 bg-white p-5 shadow-xs">
              <div className="mb-3 flex items-center gap-2">
                <FileSpreadsheet className="h-4 w-4 text-indigo-600" />
                <h2 className="text-sm font-bold text-slate-900">{source.title}</h2>
              </div>

              <label className="flex cursor-pointer items-center justify-between gap-4 rounded-xl border border-dashed border-slate-300 bg-slate-50 px-4 py-4 hover:bg-slate-100">
                <div className="min-w-0">
                  <div className="truncate text-xs font-semibold text-slate-700">
                    {source.file?.name || 'Выберите Excel или CSV'}
                  </div>
                  <div className="mt-1 text-[10px] text-slate-400">Обязательные колонки: {source.columns}</div>
                </div>
                <Upload className="h-5 w-5 shrink-0 text-indigo-500" />
                <input
                  type="file"
                  accept=".xlsx,.xls,.csv"
                  className="hidden"
                  onChange={event => source.setFile(event.target.files?.[0] || null)}
                />
              </label>

              <label className="mt-3 flex items-center gap-3 text-xs text-slate-600">
                <span className="font-semibold">Строка заголовков</span>
                <input
                  type="number"
                  min={1}
                  max={200}
                  value={source.header}
                  onChange={event => source.setHeader(Math.max(1, Number(event.target.value) || 1))}
                  className="w-20 rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs font-semibold outline-none focus:border-indigo-300 focus:ring-2 focus:ring-indigo-100"
                />
              </label>
            </div>
          ))}
        </section>

        <div className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={() => void handleRun()}
            disabled={!canRun || running || !oneCFile || !metaFile}
            className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-5 py-3 text-sm font-bold text-white shadow-sm hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {running ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4 fill-current" />}
            {running ? 'Сверяем…' : 'Запустить сверку'}
          </button>
          <div className="text-xs text-slate-500">
            Допуск суммы: <strong>±1</strong>. Дата в системе — только информационная.
          </div>
        </div>

        {message && (
          <div className={`rounded-xl border px-4 py-3 text-xs ${
            message.type === 'error'
              ? 'border-rose-200 bg-rose-50 text-rose-700'
              : message.type === 'success'
                ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
                : 'border-indigo-200 bg-indigo-50 text-indigo-700'
          }`}>
            {message.text}
          </div>
        )}

        {result && (
          <>
            <section className="grid grid-cols-2 gap-3 xl:grid-cols-6">
              {[
                ['Уникальных платежей', metrics?.unique_total ?? rows.length],
                ['Правильно', result.summary.matched_count],
                ['Расхождений', result.summary.discrepancy_count],
                ['Сходимость', `${money(result.summary.match_percentage)}%`],
                ['Сумма 1С', money(result.summary.total_sum_a)],
                ['Δ Meta − 1С', money(result.summary.diff_sum)],
              ].map(([label, value]) => (
                <div key={String(label)} className="rounded-xl border border-slate-200 bg-white p-4 shadow-xs">
                  <div className="truncate text-lg font-black text-slate-900" title={String(value)}>{value}</div>
                  <div className="mt-1 text-[10px] font-semibold uppercase tracking-wide text-slate-400">{label}</div>
                </div>
              ))}
            </section>

            <section className="rounded-2xl border border-slate-200 bg-white shadow-xs">
              <div className="flex flex-col gap-3 border-b border-slate-100 p-4 lg:flex-row lg:items-center lg:justify-between">
                <div className="flex flex-wrap gap-2">
                  {STATUS_ORDER.map(status => (
                    <button
                      key={status}
                      type="button"
                      onClick={() => setStatusFilter(status)}
                      className={`rounded-lg border px-3 py-1.5 text-[11px] font-semibold ${
                        statusFilter === status
                          ? 'border-indigo-600 bg-indigo-600 text-white'
                          : 'border-slate-200 bg-white text-slate-600 hover:bg-slate-50'
                      }`}
                    >
                      {status}
                      {status !== 'Все' && statusCounts[status] != null ? ` · ${statusCounts[status]}` : ''}
                    </button>
                  ))}
                </div>

                <label className="relative min-w-[280px]">
                  <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                  <input
                    value={query}
                    onChange={event => setQuery(event.target.value)}
                    placeholder="Номер платежа, договор, назначение, комментарий"
                    className="w-full rounded-lg border border-slate-200 py-2 pl-9 pr-3 text-xs outline-none focus:border-indigo-300 focus:ring-2 focus:ring-indigo-100"
                  />
                </label>
              </div>

              <div className="overflow-x-auto">
                <table className="min-w-[1400px] w-full text-xs">
                  <thead className="bg-slate-50 text-[10px] uppercase tracking-wide text-slate-400">
                    <tr>
                      <th className="px-3 py-3 text-left">Номер платежа</th>
                      <th className="px-3 py-3 text-left">Дата 1С</th>
                      <th className="px-3 py-3 text-right">Сумма 1С</th>
                      <th className="px-3 py-3 text-left">Дата Meta</th>
                      <th className="px-3 py-3 text-right">Сумма Meta</th>
                      <th className="px-3 py-3 text-right">Δ суммы</th>
                      <th className="px-3 py-3 text-left">Дата в системе</th>
                      <th className="px-3 py-3 text-right">Сумма опознание</th>
                      <th className="px-3 py-3 text-left">Договор</th>
                      <th className="px-3 py-3 text-left">Комментарий</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {pageRows.map((row: RepaymentRow, index) => {
                      const paymentNumber = String(row['Номер платежа'] || '');
                      const paymentPurpose = String(row['Назначение платежа'] || '').trim();
                      const isExpanded = expandedPayments.has(paymentNumber);

                      return (
                        <React.Fragment key={`${paymentNumber}-${index}`}>
                          <tr className={`hover:bg-slate-50/70 ${isExpanded ? 'bg-indigo-50/30' : ''}`}>
                            <td className="px-3 py-2 font-mono font-semibold text-slate-800">
                              <div className="flex items-center gap-1.5">
                                <button
                                  type="button"
                                  onClick={() => togglePaymentPurpose(paymentNumber)}
                                  disabled={!paymentPurpose}
                                  className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-md text-slate-400 hover:bg-indigo-50 hover:text-indigo-600 disabled:cursor-default disabled:opacity-20"
                                  title={paymentPurpose ? (isExpanded ? 'Скрыть назначение платежа' : 'Показать назначение платежа') : 'Назначение платежа отсутствует'}
                                >
                                  <ChevronDown className={`h-3.5 w-3.5 transition-transform ${isExpanded ? 'rotate-180' : ''}`} />
                                </button>
                                <span>{paymentNumber}</span>
                              </div>
                            </td>
                            <td className="px-3 py-2 text-slate-600">{row['Дата'] || '—'}</td>
                            <td className="px-3 py-2 text-right tabular-nums">{money(row['Сумма'])}</td>
                            <td className="px-3 py-2 text-slate-600">{row['Дата Meta'] || '—'}</td>
                            <td className="px-3 py-2 text-right tabular-nums">{money(row['Сумма Meta'])}</td>
                            <td className={`px-3 py-2 text-right font-bold tabular-nums ${
                              Math.abs(Number(row['Δ суммы'] || 0)) <= 1 ? 'text-emerald-600' : 'text-rose-600'
                            }`}>
                              {Number(row['Δ суммы'] || 0) > 0 ? '+' : ''}{money(row['Δ суммы'])}
                            </td>
                            <td className="px-3 py-2 text-slate-600">{row['Дата в системе'] || '—'}</td>
                            <td className="px-3 py-2 text-right tabular-nums">{money(row['Сумма опознание'])}</td>
                            <td className="max-w-[260px] truncate px-3 py-2 text-slate-600" title={row['Номер договора опознание'] || ''}>
                              {row['Номер договора опознание'] || '—'}
                            </td>
                            <td className="px-3 py-2">
                              <span className={`inline-flex rounded-full border px-2 py-1 text-[10px] font-bold ${statusClass(row['Комментарий'])}`}>
                                {row['Комментарий']}
                              </span>
                            </td>
                          </tr>

                          {isExpanded && paymentPurpose && (
                            <tr className="bg-indigo-50/50">
                              <td colSpan={10} className="px-10 py-3">
                                <div className="rounded-xl border border-indigo-100 bg-white px-4 py-3">
                                  <div className="mb-1 text-[10px] font-bold uppercase tracking-wide text-indigo-500">
                                    Назначение платежа
                                  </div>
                                  <div className="whitespace-pre-wrap break-words text-xs leading-5 text-slate-700">
                                    {paymentPurpose}
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

                {filteredRows.length === 0 && (
                  <div className="px-5 py-10 text-center text-sm text-slate-500">По фильтрам строки не найдены.</div>
                )}
              </div>

              <div className="flex items-center justify-between border-t border-slate-100 px-4 py-3">
                <div className="text-xs text-slate-500">
                  Показано {pageRows.length} из {filteredRows.length}
                </div>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => setPage(value => Math.max(1, value - 1))}
                    disabled={safePage <= 1}
                    className="rounded-lg border border-slate-200 p-2 text-slate-500 disabled:opacity-40"
                  >
                    <ChevronLeft className="h-4 w-4" />
                  </button>
                  <span className="min-w-20 text-center text-xs font-semibold text-slate-600">{safePage} / {totalPages}</span>
                  <button
                    type="button"
                    onClick={() => setPage(value => Math.min(totalPages, value + 1))}
                    disabled={safePage >= totalPages}
                    className="rounded-lg border border-slate-200 p-2 text-slate-500 disabled:opacity-40"
                  >
                    <ChevronRight className="h-4 w-4" />
                  </button>
                </div>
              </div>
            </section>
          </>
        )}

        <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-xs">
          <div className="flex items-center justify-between border-b border-slate-100 px-5 py-4">
            <div>
              <h2 className="text-sm font-bold text-slate-900">Архив Сверки Погашений</h2>
              <p className="mt-1 text-xs text-slate-500">Полный результат загружается только при открытии записи.</p>
            </div>
            <button
              type="button"
              onClick={() => void loadArchive()}
              disabled={archiveLoading}
              className="inline-flex items-center gap-2 rounded-lg border border-slate-200 px-3 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-50 disabled:opacity-40"
            >
              <RefreshCcw className={`h-4 w-4 ${archiveLoading ? 'animate-spin' : ''}`} />
              Обновить
            </button>
          </div>

          <div className="overflow-x-auto">
            <table className="min-w-[900px] w-full text-xs">
              <thead className="bg-slate-50 text-[10px] uppercase tracking-wide text-slate-400">
                <tr>
                  <th className="px-4 py-3 text-left">Дата</th>
                  <th className="px-4 py-3 text-left">Run / пользователь</th>
                  <th className="px-4 py-3 text-left">Файлы</th>
                  <th className="px-4 py-3 text-right">Правильно</th>
                  <th className="px-4 py-3 text-right">Расхождения</th>
                  <th className="px-4 py-3 text-right">Δ</th>
                  <th className="px-4 py-3 text-right">Действия</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {archive.slice(0, 20).map(record => (
                  <tr key={record.id} className="hover:bg-slate-50/70">
                    <td className="px-4 py-3 text-slate-600">{formatDateTime(record.created_at || record.timestamp)}</td>
                    <td className="px-4 py-3">
                      <div className="font-semibold text-slate-800">Run {record.run_id || `#${record.id}`}</div>
                      <div className="text-[10px] text-slate-400">{record.created_by || record.username || '—'}</div>
                    </td>
                    <td className="max-w-[260px] px-4 py-3 text-slate-600">
                      {(record.source_files || []).map(file => (
                        <div key={file} className="truncate" title={file}>{file}</div>
                      ))}
                    </td>
                    <td className="px-4 py-3 text-right font-semibold text-emerald-700">{record.summary?.matched_count ?? 0}</td>
                    <td className="px-4 py-3 text-right font-semibold text-amber-700">{record.summary?.discrepancy_count ?? 0}</td>
                    <td className="px-4 py-3 text-right font-semibold tabular-nums">{money(record.summary?.diff_sum)}</td>
                    <td className="px-4 py-3">
                      <div className="flex justify-end gap-2">
                        <button
                          type="button"
                          onClick={() => void openArchive(record)}
                          disabled={archiveRecordLoading === record.id}
                          className="inline-flex items-center gap-1 rounded-lg border border-slate-200 px-2.5 py-1.5 text-[11px] font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-40"
                        >
                          {archiveRecordLoading === record.id
                            ? <LoaderCircle className="h-3.5 w-3.5 animate-spin" />
                            : <FolderOpen className="h-3.5 w-3.5" />}
                          Открыть
                        </button>
                        {canRun && (
                          <button
                            type="button"
                            onClick={() => void deleteArchive(record)}
                            disabled={deletingId != null}
                            className="inline-flex items-center gap-1 rounded-lg border border-rose-200 bg-rose-50 px-2.5 py-1.5 text-[11px] font-semibold text-rose-700 hover:bg-rose-100 disabled:opacity-40"
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
                ))}
              </tbody>
            </table>

            {!archiveLoading && archive.length === 0 && (
              <div className="px-5 py-10 text-center text-sm text-slate-500">Архив пока пуст.</div>
            )}
          </div>
        </section>
      </div>
    </div>
  );
};
