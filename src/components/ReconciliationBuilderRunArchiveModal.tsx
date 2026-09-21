import React, { useMemo, useState } from 'react';
import {
  CalendarDays,
  Download,
  FileSpreadsheet,
  UserRound,
  X,
} from 'lucide-react';

import {
  BuilderResultRow,
  ReconciliationBuilderConfig,
} from '../utils/reconciliationBuilderApi';
import {
  BuilderArchiveRecord,
  exportBuilderArchiveRun,
} from '../utils/reconciliationBuilderExport';

type TabId = 'matched' | 'mismatches' | 'only_a' | 'only_b';

interface Props {
  record: BuilderArchiveRecord;
  onClose: () => void;
}

function fmt(value: number): string {
  return Number(value || 0).toLocaleString('ru-RU', { maximumFractionDigits: 2 });
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

function sourceRows(row: BuilderResultRow, side: 'a' | 'b'): Record<string, any>[] {
  const source = side === 'a' ? row.source_a : row.source_b;
  if (!source || typeof source !== 'object') return [];
  if (Array.isArray((source as any).rows)) {
    return (source as any).rows.filter((item: any) => item && typeof item === 'object');
  }
  return [source as Record<string, any>];
}

function displayValue(value: any): string {
  if (value == null || value === '') return '—';
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value.toLocaleString('ru-RU', { maximumFractionDigits: 2 });
  }
  return String(value);
}

function aggregateValue(row: BuilderResultRow, side: 'a' | 'b', column: string): string {
  const values = sourceRows(row, side)
    .map(source => displayValue(source[column]))
    .filter(value => value !== '—');
  const unique = Array.from(new Set(values));
  if (!unique.length) return '—';
  if (unique.length <= 3) return unique.join(' | ');
  return `${unique.slice(0, 3).join(' | ')} · +${unique.length - 3}`;
}

function selectedColumns(
  config: ReconciliationBuilderConfig,
  resultColumns: string[] | undefined,
  side: 'a' | 'b',
): string[] {
  if (resultColumns?.length) return resultColumns.slice(0, 4);

  const amount = side === 'a' ? config.amount_a_col : config.amount_b_col;
  const date = side === 'a' ? config.date_a_col : config.date_b_col;
  const keys = (config.key_pairs || []).map(pair => side === 'a' ? pair.left : pair.right);
  return Array.from(new Set([amount, date, ...keys].filter(Boolean) as string[])).slice(0, 4);
}

export const ReconciliationBuilderRunArchiveModal: React.FC<Props> = ({ record, onClose }) => {
  const [tab, setTab] = useState<TabId>('mismatches');
  const [exportError, setExportError] = useState('');

  const result = record.result_snapshot;
  const config = record.config_snapshot || record.config;
  const generic = result?.custom_metrics?.generic;

  const tabs = useMemo(() => ([
    { id: 'matched' as const, label: 'Совпало', rows: generic?.matched || [] },
    { id: 'mismatches' as const, label: 'Расхождения', rows: generic?.mismatches || [] },
    { id: 'only_a' as const, label: 'Только A', rows: generic?.only_a || [] },
    { id: 'only_b' as const, label: 'Только B', rows: generic?.only_b || [] },
  ]), [generic]);

  const rows = tabs.find(item => item.id === tab)?.rows || [];
  const columnsA = config ? selectedColumns(config, config.result_columns_a, 'a') : [];
  const columnsB = config ? selectedColumns(config, config.result_columns_b, 'b') : [];

  const handleExport = () => {
    setExportError('');
    try {
      exportBuilderArchiveRun(record);
    } catch (error: any) {
      setExportError(error?.message || 'Не удалось экспортировать результат.');
    }
  };

  return (
    <div className="fixed inset-0 z-[80] flex items-center justify-center bg-slate-950/40 p-3 backdrop-blur-[1px]">
      <div className="flex max-h-[94vh] w-full max-w-[1600px] flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl">
        <div className="flex items-start justify-between gap-4 border-b border-slate-200 px-5 py-4">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-lg font-bold text-slate-900">
                {record.definition_name || 'Разовая сверка'}
              </h2>
              <span className="rounded-full bg-slate-100 px-2 py-1 font-mono text-[10px] text-slate-500">
                Run {record.run_id || result?.run_id || '—'}
              </span>
            </div>
            <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-500">
              <span className="inline-flex items-center gap-1.5">
                <UserRound className="h-3.5 w-3.5" />
                {record.created_by || record.username || '—'}
              </span>
              <span className="inline-flex items-center gap-1.5">
                <CalendarDays className="h-3.5 w-3.5" />
                {formatDateTime(record.created_at || record.updated_at)}
              </span>
              <span className="inline-flex min-w-0 items-center gap-1.5">
                <FileSpreadsheet className="h-3.5 w-3.5 shrink-0" />
                <span className="truncate">
                  {record.source_a_name || record.source_files?.[0] || 'Источник A'} ↔{' '}
                  {record.source_b_name || record.source_files?.[1] || 'Источник B'}
                </span>
              </span>
            </div>
          </div>

          <div className="flex shrink-0 items-center gap-2">
            <button
              onClick={handleExport}
              disabled={!result}
              className="inline-flex items-center gap-2 rounded-lg border border-slate-200 px-3 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
            >
              <Download className="h-4 w-4" />
              Excel
            </button>
            <button
              onClick={onClose}
              className="rounded-lg border border-slate-200 p-2 text-slate-500 hover:bg-slate-50"
              title="Закрыть"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>

        {!result ? (
          <div className="p-8">
            <div className="rounded-xl border border-amber-200 bg-amber-50 p-5 text-sm text-amber-800">
              Эта запись была создана до появления полного snapshot-архива. Сводка сохранена, но
              строки Matched / Mismatches / Only A / Only B восстановить для неё уже нельзя.
              Новые запуски будут сохраняться полностью.
            </div>
          </div>
        ) : (
          <>
            <div className="grid grid-cols-2 gap-2 border-b border-slate-100 bg-slate-50/70 px-5 py-4 md:grid-cols-4 xl:grid-cols-8">
              <div>
                <div className="text-[10px] uppercase text-slate-400">Период</div>
                <div className="mt-1 text-xs font-semibold text-slate-800">{record.period_month || '—'}</div>
              </div>
              <div>
                <div className="text-[10px] uppercase text-slate-400">Статус</div>
                <div className="mt-1 text-xs font-semibold text-slate-800">{record.status || result.status}</div>
              </div>
              <div>
                <div className="text-[10px] uppercase text-slate-400">Записей A</div>
                <div className="mt-1 text-xs font-semibold text-slate-800">{result.summary.total_records_a}</div>
              </div>
              <div>
                <div className="text-[10px] uppercase text-slate-400">Записей B</div>
                <div className="mt-1 text-xs font-semibold text-slate-800">{result.summary.total_records_b}</div>
              </div>
              <div>
                <div className="text-[10px] uppercase text-slate-400">Совпало</div>
                <div className="mt-1 text-xs font-semibold text-emerald-700">{result.summary.matched_count}</div>
              </div>
              <div>
                <div className="text-[10px] uppercase text-slate-400">Проблем</div>
                <div className="mt-1 text-xs font-semibold text-amber-700">{result.summary.discrepancy_count}</div>
              </div>
              <div>
                <div className="text-[10px] uppercase text-slate-400">Сходимость</div>
                <div className="mt-1 text-xs font-semibold text-indigo-700">{result.summary.match_percentage.toFixed(2)}%</div>
              </div>
              <div>
                <div className="text-[10px] uppercase text-slate-400">Δ суммы</div>
                <div className="mt-1 text-xs font-semibold text-slate-800">{fmt(result.summary.diff_sum)}</div>
              </div>
            </div>

            {exportError && (
              <div className="border-b border-rose-100 bg-rose-50 px-5 py-2 text-xs text-rose-700">
                {exportError}
              </div>
            )}

            <div className="flex gap-1 overflow-x-auto border-b border-slate-200 px-5 py-3">
              {tabs.map(item => (
                <button
                  key={item.id}
                  onClick={() => setTab(item.id)}
                  className={`rounded-lg px-3 py-2 text-xs font-semibold ${
                    tab === item.id
                      ? 'bg-indigo-600 text-white'
                      : 'text-slate-600 hover:bg-slate-100'
                  }`}
                >
                  {item.label} · {item.rows.length}
                </button>
              ))}
            </div>

            <div className="min-h-0 flex-1 overflow-auto">
              <table className="min-w-max text-sm">
                <thead className="sticky top-0 z-10 bg-slate-50 shadow-[0_1px_0_rgba(226,232,240,1)]">
                  <tr>
                    <th className="px-4 py-3 text-left text-[10px] font-semibold uppercase text-slate-400">Тип</th>
                    <th className="px-4 py-3 text-left text-[10px] font-semibold uppercase text-slate-400">Ключ</th>
                    {columnsA.map(column => (
                      <th key={`a-${column}`} className="max-w-[240px] px-4 py-3 text-left text-[10px] font-semibold uppercase text-slate-400">
                        <span className="text-indigo-500">A · </span>{column}
                      </th>
                    ))}
                    {columnsB.map(column => (
                      <th key={`b-${column}`} className="max-w-[240px] px-4 py-3 text-left text-[10px] font-semibold uppercase text-slate-400">
                        <span className="text-violet-500">B · </span>{column}
                      </th>
                    ))}
                    <th className="px-4 py-3 text-left text-[10px] font-semibold uppercase text-slate-400">Δ суммы</th>
                    <th className="px-4 py-3 text-left text-[10px] font-semibold uppercase text-slate-400">Δ дней</th>
                    <th className="px-4 py-3 text-left text-[10px] font-semibold uppercase text-slate-400">Причина</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {rows.slice(0, 1000).map((row, index) => {
                    const rowsA = row.grouped_rows_a?.length
                      ? row.grouped_rows_a.join(', ')
                      : row.row_a ?? '—';
                    const rowsB = row.grouped_rows_b?.length
                      ? row.grouped_rows_b.join(', ')
                      : row.row_b ?? '—';

                    return (
                      <tr key={`${row.key}-${index}`} className="hover:bg-slate-50">
                        <td className="px-4 py-3">
                          <span className="rounded-md bg-slate-100 px-2 py-1 text-[10px] font-bold text-slate-600">
                            {row.match_type || '1↔1'}
                          </span>
                        </td>
                        <td className="max-w-[280px] px-4 py-3">
                          <div className="truncate font-mono text-xs text-slate-800" title={row.key}>
                            {row.key || '—'}
                          </div>
                          <div className="mt-1 whitespace-nowrap text-[9px] text-slate-400">
                            A: {rowsA} · B: {rowsB}
                          </div>
                        </td>
                        {columnsA.map(column => {
                          const value = aggregateValue(row, 'a', column);
                          return (
                            <td key={`a-${column}`} className="max-w-[240px] px-4 py-3 text-xs text-slate-700">
                              <div className="truncate" title={value}>{value}</div>
                            </td>
                          );
                        })}
                        {columnsB.map(column => {
                          const value = aggregateValue(row, 'b', column);
                          return (
                            <td key={`b-${column}`} className="max-w-[240px] px-4 py-3 text-xs text-slate-700">
                              <div className="truncate" title={value}>{value}</div>
                            </td>
                          );
                        })}
                        <td className="px-4 py-3 whitespace-nowrap">{row.amount_delta == null ? '—' : fmt(row.amount_delta)}</td>
                        <td className="px-4 py-3 whitespace-nowrap">{row.date_delta_days ?? '—'}</td>
                        <td className="max-w-[300px] px-4 py-3 text-xs text-slate-600">
                          <div className="line-clamp-2" title={row.reason || ''}>{row.reason || '—'}</div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>

              {rows.length === 0 && (
                <div className="p-8 text-center text-sm text-slate-500">В этой категории строк нет.</div>
              )}

              {rows.length > 1000 && (
                <div className="border-t border-slate-100 bg-slate-50 px-5 py-3 text-xs text-slate-500">
                  В окне показаны первые 1000 из {rows.length.toLocaleString('ru-RU')} строк.
                  Excel-экспорт содержит полный snapshot.
                </div>
              )}
            </div>

            <div className="border-t border-slate-200 bg-white px-5 py-3">
              <details>
                <summary className="cursor-pointer text-xs font-semibold text-slate-600">
                  Правила, использованные в этом Run
                </summary>
                <div className="mt-3 grid grid-cols-1 gap-3 text-[11px] text-slate-600 lg:grid-cols-3">
                  <div className="rounded-lg bg-slate-50 p-3">
                    <div className="font-semibold text-slate-800">Matching</div>
                    <div className="mt-1">{config?.matching_mode || generic?.matching_mode || 'one_to_one'}</div>
                    <div className="mt-1">Допуск суммы: {config?.amount_tolerance ?? generic?.amount_mapping?.tolerance ?? 0}</div>
                    <div className="mt-1">Допуск даты: {config?.date_tolerance_days ?? generic?.date_mapping?.tolerance_days ?? 0} дн.</div>
                  </div>
                  <div className="rounded-lg bg-slate-50 p-3">
                    <div className="font-semibold text-slate-800">Ключи</div>
                    {(config?.key_pairs || generic?.key_pairs || []).map((pair, index) => (
                      <div key={index} className="mt-1 font-mono">
                        {pair.left} ↔ {pair.right} · {pair.mode}
                      </div>
                    ))}
                  </div>
                  <div className="rounded-lg bg-slate-50 p-3">
                    <div className="font-semibold text-slate-800">Подготовка</div>
                    <div className="mt-1">Фильтров: {(config?.filters || generic?.filters || []).length}</div>
                    <div className="mt-1">Вычисляемых полей: {(config?.computed_fields || generic?.computed_fields || []).length}</div>
                  </div>
                </div>
              </details>
            </div>
          </>
        )}
      </div>
    </div>
  );
};
