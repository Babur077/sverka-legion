import React, { useEffect, useMemo, useState } from 'react';
import {
  ArrowLeft,
  Building2,
  CheckCircle2,
  Download,
  FileSpreadsheet,
  History,
  LoaderCircle,
  Play,
  RefreshCcw,
  Upload,
  XCircle,
} from 'lucide-react';

import { User } from '../types';
import { hasPermission } from '../utils/permissions';
import {
  exportRavan1CToExcel,
  getRavan1CArchive,
  Ravan1CArchiveRecord,
  Ravan1CRow,
  Ravan1CRunResult,
  runRavan1C,
  saveRavan1CRun,
} from '../utils/ravan1cApi';

interface Props {
  user: User;
  onBack: () => void;
}

const STATUS_ORDER = [
  'Все',
  'OK',
  'Ошибка Kolvo',
  'Ошибка Summ',
  'Ошибка Kolvo + Summ',
  'Нет в 1C',
  'Нет в Ravan',
];

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

function statusClass(status: string): string {
  if (status === 'OK') return 'border-emerald-200 bg-emerald-50 text-emerald-700';
  if (status.startsWith('Нет в')) return 'border-slate-200 bg-slate-50 text-slate-600';
  if (status.includes('Kolvo + Summ')) return 'border-rose-200 bg-rose-50 text-rose-700';
  return 'border-amber-200 bg-amber-50 text-amber-700';
}

export const Ravan1CWorkspace: React.FC<Props> = ({ user, onBack }) => {
  const canRun = hasPermission(user, 'ravan_1c.run');
  const canExport = hasPermission(user, 'ravan_1c.export');

  const [ravanFile, setRavanFile] = useState<File | null>(null);
  const [cFile, setCFile] = useState<File | null>(null);
  const [sumTolerance, setSumTolerance] = useState(1);
  const [result, setResult] = useState<Ravan1CRunResult | null>(null);
  const [running, setRunning] = useState(false);
  const [message, setMessage] = useState<{ type: 'info' | 'success' | 'error'; text: string } | null>(null);
  const [statusFilter, setStatusFilter] = useState('Все');
  const [archive, setArchive] = useState<Ravan1CArchiveRecord[]>([]);
  const [archiveLoading, setArchiveLoading] = useState(false);

  const rows = result?.custom_metrics?.ravan_1c?.rows || [];
  const filteredRows = useMemo(
    () => statusFilter === 'Все' ? rows : rows.filter(row => row.Status === statusFilter),
    [rows, statusFilter],
  );
  const statusCounts = result?.custom_metrics?.ravan_1c?.status_counts || {};

  const loadArchive = async () => {
    setArchiveLoading(true);
    try {
      const records = await getRavan1CArchive(user.username);
      setArchive(records.slice(0, 8));
    } catch {
      // Archive is secondary to the reconciliation workspace.
    } finally {
      setArchiveLoading(false);
    }
  };

  useEffect(() => {
    void loadArchive();
  }, [user.username]);

  const handleRun = async () => {
    if (!canRun || running) return;
    if (!ravanFile || !cFile) {
      setMessage({ type: 'error', text: 'Загрузите оба файла: Ravan и 1C.' });
      return;
    }

    setRunning(true);
    setMessage(null);
    setResult(null);
    try {
      const next = await runRavan1C(ravanFile, cFile, sumTolerance);
      setResult(next);
      setStatusFilter('Все');

      try {
        const archiveMessage = await saveRavan1CRun(
          user.username,
          next,
          ravanFile,
          cFile,
          sumTolerance,
        );
        setMessage({ type: 'success', text: `Сверка завершена. ${archiveMessage}` });
        await loadArchive();
      } catch (archiveError: any) {
        setMessage({
          type: 'info',
          text: `Сверка завершена, но архив не сохранился: ${archiveError?.message || archiveError}`,
        });
      }
    } catch (error: any) {
      setMessage({
        type: 'error',
        text: error?.message || 'Не удалось выполнить сверку.',
      });
    } finally {
      setRunning(false);
    }
  };

  const restoreArchive = (record: Ravan1CArchiveRecord) => {
    if (!record.result_snapshot) {
      setMessage({
        type: 'info',
        text: 'Для этой записи полный snapshot результата не сохранён.',
      });
      return;
    }
    setResult(record.result_snapshot);
    setStatusFilter('Все');
    setMessage({
      type: 'info',
      text: `Открыт архивный Run ${record.run_id || '#' + record.id}.`,
    });
  };

  return (
    <div className="min-h-full bg-slate-50">
      <div className="sticky top-0 z-20 border-b border-slate-200 bg-white/95 px-5 py-4 backdrop-blur">
        <div className="mx-auto flex max-w-[1800px] items-center justify-between gap-4">
          <div className="flex min-w-0 items-center gap-3">
            <button
              type="button"
              onClick={onBack}
              className="rounded-lg border border-slate-200 bg-white p-2 text-slate-500 hover:bg-slate-50 hover:text-slate-800"
              title="Назад к модулям"
            >
              <ArrowLeft className="h-4 w-4" />
            </button>
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-indigo-50 text-indigo-600">
              <Building2 className="h-5 w-5" />
            </div>
            <div className="min-w-0">
              <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-indigo-600">
                Produced by Sayfulloh Abdusalomov
              </div>
              <h1 className="truncate text-xl font-black text-slate-900">Ravan ↔ 1C</h1>
              <p className="mt-0.5 text-xs text-slate-500">
                Сверка контрагентов, количества и суммы с корректировкой по NDS.
              </p>
            </div>
          </div>

          {result && canExport && (
            <button
              type="button"
              onClick={() => exportRavan1CToExcel(result)}
              className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3.5 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50"
            >
              <Download className="h-4 w-4" />
              Excel
            </button>
          )}
        </div>
      </div>

      <div className="mx-auto max-w-[1800px] space-y-5 p-5 xl:p-7">
        <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-xs">
          <div className="mb-4">
            <h2 className="text-sm font-bold text-slate-900">Исходные файлы</h2>
            <p className="mt-1 text-xs leading-5 text-slate-500">
              Ravan должен содержать колонки <strong>Partner, NDS, Kolvo, Summ</strong>.
              В файле 1C первая строка считается данными, а первые три колонки интерпретируются как
              <strong> Partner, Kolvo, Summ</strong>.
            </p>
          </div>

          <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
            <label className="cursor-pointer rounded-xl border border-dashed border-indigo-200 bg-indigo-50/40 p-5 hover:bg-indigo-50">
              <div className="flex items-start gap-3">
                <div className="rounded-lg bg-white p-2 text-indigo-600 shadow-xs">
                  <Upload className="h-4 w-4" />
                </div>
                <div className="min-w-0">
                  <div className="text-xs font-bold uppercase tracking-wider text-indigo-500">Ravan</div>
                  <div className="mt-1 truncate text-sm font-semibold text-slate-900">
                    {ravanFile?.name || 'Выберите Ravan.xlsx'}
                  </div>
                  <div className="mt-1 text-xs text-slate-500">Ожидаются Partner / NDS / Kolvo / Summ.</div>
                </div>
              </div>
              <input
                type="file"
                accept=".xlsx,.xls,.csv"
                className="hidden"
                onChange={event => {
                  setRavanFile(event.target.files?.[0] || null);
                  setResult(null);
                }}
              />
            </label>

            <label className="cursor-pointer rounded-xl border border-dashed border-emerald-200 bg-emerald-50/40 p-5 hover:bg-emerald-50">
              <div className="flex items-start gap-3">
                <div className="rounded-lg bg-white p-2 text-emerald-600 shadow-xs">
                  <FileSpreadsheet className="h-4 w-4" />
                </div>
                <div className="min-w-0">
                  <div className="text-xs font-bold uppercase tracking-wider text-emerald-600">1C</div>
                  <div className="mt-1 truncate text-sm font-semibold text-slate-900">
                    {cFile?.name || 'Выберите файл 1C'}
                  </div>
                  <div className="mt-1 text-xs text-slate-500">Без строки заголовков: Partner / Kolvo / Summ.</div>
                </div>
              </div>
              <input
                type="file"
                accept=".xlsx,.xls,.csv"
                className="hidden"
                onChange={event => {
                  setCFile(event.target.files?.[0] || null);
                  setResult(null);
                }}
              />
            </label>
          </div>

          <div className="mt-4 flex flex-col gap-3 rounded-xl bg-slate-50 p-4 sm:flex-row sm:items-end sm:justify-between">
            <label className="text-xs font-semibold text-slate-700">
              Допустимая разница по сумме
              <input
                type="number"
                min="0"
                step="0.01"
                value={sumTolerance}
                onChange={event => setSumTolerance(Math.max(0, Number(event.target.value) || 0))}
                className="mt-1 block w-40 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-normal text-slate-800"
              />
              <span className="mt-1 block text-[10px] font-normal text-slate-400">
                Исходное правило Sayfulloh: 1.
              </span>
            </label>

            <button
              type="button"
              onClick={() => void handleRun()}
              disabled={!canRun || !ravanFile || !cFile || running}
              className="inline-flex items-center justify-center gap-2 rounded-xl bg-indigo-600 px-5 py-2.5 text-sm font-bold text-white shadow-sm hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {running ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
              {running ? 'Выполняем сверку…' : 'Запустить сверку'}
            </button>
          </div>
        </section>

        {message && (
          <div className={`rounded-xl border px-4 py-3 text-sm ${
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
            <section className="grid grid-cols-2 gap-3 lg:grid-cols-4 xl:grid-cols-6">
              {[
                ['Всего компаний', rows.length],
                ['OK', result.summary.matched_count],
                ['Расхождения', result.summary.discrepancy_count],
                ['Сходимость', `${result.summary.match_percentage.toFixed(1)}%`],
                ['Δ суммы', formatNumber(result.summary.diff_sum)],
                ['Время', `${formatNumber(result.summary.execution_time_ms, 0)} ms`],
              ].map(([label, value]) => (
                <div key={String(label)} className="rounded-xl border border-slate-200 bg-white p-4 shadow-xs">
                  <div className="text-2xl font-black tracking-tight text-slate-900">{String(value)}</div>
                  <div className="mt-1 text-[11px] font-semibold text-slate-500">{String(label)}</div>
                </div>
              ))}
            </section>

            <section className="grid grid-cols-1 gap-5 xl:grid-cols-[320px_1fr]">
              <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-xs">
                <h2 className="text-sm font-bold text-slate-900">Статусы</h2>
                <div className="mt-3 space-y-2">
                  {STATUS_ORDER.filter(status => status !== 'Все').map(status => {
                    const count = Number(statusCounts[status] || 0);
                    return (
                      <button
                        key={status}
                        type="button"
                        onClick={() => setStatusFilter(status)}
                        className="flex w-full items-center justify-between rounded-lg border border-slate-100 px-3 py-2 text-left hover:bg-slate-50"
                      >
                        <span className="text-xs font-medium text-slate-600">{status}</span>
                        <span className="text-xs font-bold tabular-nums text-slate-900">{count}</span>
                      </button>
                    );
                  })}
                </div>

                <div className="mt-4 border-t border-slate-100 pt-4 text-[11px] leading-5 text-slate-500">
                  <div>Формула суммы:</div>
                  <div className="mt-1 rounded-lg bg-slate-50 p-2 font-mono text-[10px] text-slate-700">
                    Summ_Corrected = Summ_Ravan × (112 − NDS) / 112
                  </div>
                </div>
              </div>

              <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-xs">
                <div className="flex flex-col gap-3 border-b border-slate-100 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
                  <div>
                    <h2 className="text-sm font-bold text-slate-900">Результат сравнения</h2>
                    <p className="mt-0.5 text-[10px] text-slate-400">
                      Показано {filteredRows.length.toLocaleString('ru-RU')} из {rows.length.toLocaleString('ru-RU')} строк.
                    </p>
                  </div>
                  <select
                    value={statusFilter}
                    onChange={event => setStatusFilter(event.target.value)}
                    className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-600"
                  >
                    {STATUS_ORDER.map(status => (
                      <option key={status} value={status}>{status}</option>
                    ))}
                  </select>
                </div>

                <div className="max-h-[650px] overflow-auto">
                  <table className="min-w-[1350px] w-full text-xs">
                    <thead className="sticky top-0 z-10 bg-slate-50">
                      <tr className="text-[10px] uppercase tracking-wider text-slate-400">
                        <th className="px-3 py-2 text-left">Ravan</th>
                        <th className="px-3 py-2 text-left">1C</th>
                        <th className="px-3 py-2 text-right">NDS</th>
                        <th className="px-3 py-2 text-right">Kolvo Ravan</th>
                        <th className="px-3 py-2 text-right">Kolvo 1C</th>
                        <th className="px-3 py-2 text-right">Δ Kolvo</th>
                        <th className="px-3 py-2 text-right">Summ Ravan</th>
                        <th className="px-3 py-2 text-right">Summ corrected</th>
                        <th className="px-3 py-2 text-right">Summ 1C</th>
                        <th className="px-3 py-2 text-right">Δ Summ</th>
                        <th className="px-3 py-2 text-left">Статус</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {filteredRows.slice(0, 2000).map((row: Ravan1CRow, index) => (
                        <tr key={index} className="hover:bg-slate-50">
                          <td className="max-w-[220px] px-3 py-2 font-medium text-slate-800">
                            <div className="truncate" title={String(row.Partner_Ravan || '')}>{row.Partner_Ravan || '—'}</div>
                          </td>
                          <td className="max-w-[220px] px-3 py-2 text-slate-700">
                            <div className="truncate" title={String(row.Partner_C || '')}>{row.Partner_C || '—'}</div>
                          </td>
                          <td className="px-3 py-2 text-right tabular-nums">{formatNumber(row.NDS)}</td>
                          <td className="px-3 py-2 text-right tabular-nums">{formatNumber(row.Kolvo_Ravan)}</td>
                          <td className="px-3 py-2 text-right tabular-nums">{formatNumber(row.Kolvo_C)}</td>
                          <td className="px-3 py-2 text-right font-semibold tabular-nums">{formatNumber(row.Kolvo_Difference)}</td>
                          <td className="px-3 py-2 text-right tabular-nums">{formatNumber(row.Summ_Ravan)}</td>
                          <td className="px-3 py-2 text-right tabular-nums">{formatNumber(row.Summ_Corrected)}</td>
                          <td className="px-3 py-2 text-right tabular-nums">{formatNumber(row.Summ_C)}</td>
                          <td className="px-3 py-2 text-right font-semibold tabular-nums">{formatNumber(row.Summ_Difference)}</td>
                          <td className="px-3 py-2">
                            <span className={`inline-flex rounded-full border px-2 py-1 text-[9px] font-bold ${statusClass(row.Status)}`}>
                              {row.Status}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>

                  {filteredRows.length > 2000 && (
                    <div className="border-t border-slate-100 bg-amber-50 px-4 py-3 text-xs text-amber-700">
                      В интерфейсе показаны первые 2 000 строк. Excel-экспорт содержит полный результат.
                    </div>
                  )}
                </div>
              </div>
            </section>
          </>
        )}

        <section className="rounded-xl border border-slate-200 bg-white shadow-xs">
          <div className="flex items-center justify-between border-b border-slate-100 px-5 py-4">
            <div className="flex items-center gap-2">
              <History className="h-4 w-4 text-slate-400" />
              <div>
                <h2 className="text-sm font-bold text-slate-900">Последние Run</h2>
                <p className="mt-0.5 text-[10px] text-slate-400">Архив модуля Ravan ↔ 1C.</p>
              </div>
            </div>
            <button
              type="button"
              onClick={() => void loadArchive()}
              disabled={archiveLoading}
              className="rounded-lg p-2 text-slate-400 hover:bg-slate-50 hover:text-slate-700"
            >
              <RefreshCcw className={`h-4 w-4 ${archiveLoading ? 'animate-spin' : ''}`} />
            </button>
          </div>

          <div className="divide-y divide-slate-100">
            {archive.map(record => {
              const summary = record.summary;
              const snapshot = record.result_snapshot;
              const problemCount = summary?.discrepancy_count ?? snapshot?.summary.discrepancy_count ?? 0;
              return (
                <button
                  key={record.id}
                  type="button"
                  onClick={() => restoreArchive(record)}
                  className="grid w-full grid-cols-[1fr_auto] gap-4 px-5 py-3 text-left hover:bg-slate-50"
                >
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      {problemCount === 0
                        ? <CheckCircle2 className="h-4 w-4 text-emerald-500" />
                        : <XCircle className="h-4 w-4 text-amber-500" />}
                      <span className="truncate text-xs font-semibold text-slate-800">
                        Run {record.run_id || '#' + record.id}
                      </span>
                    </div>
                    <div className="mt-1 text-[10px] text-slate-400">
                      {record.created_by || record.username || '—'} · {formatDateTime(record.created_at || record.timestamp)}
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="text-xs font-bold text-slate-800">
                      {formatNumber(summary?.match_percentage ?? snapshot?.summary.match_percentage, 1)}%
                    </div>
                    <div className="mt-0.5 text-[10px] text-slate-400">
                      {problemCount} расх.
                    </div>
                  </div>
                </button>
              );
            })}

            {!archiveLoading && archive.length === 0 && (
              <div className="px-5 py-8 text-center text-xs text-slate-500">
                В архиве пока нет запусков этой сверки.
              </div>
            )}
          </div>
        </section>
      </div>
    </div>
  );
};
