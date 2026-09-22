import * as XLSX from 'xlsx';

import { apiFetch } from './apiClient';
import { deleteModuleArchive, getModuleArchive, saveModuleArchive } from './archiveApi';

export type Ravan1CMatchType = 'exact' | 'fuzzy' | 'unmatched' | 'manual_unlinked';

export interface Ravan1CRow {
  Row_ID?: string;
  Match_Type?: Ravan1CMatchType | string;
  Name_Similarity?: number | null;
  Needs_Review?: boolean;
  Match_Confirmed?: boolean;
  Partner_Ravan?: string | null;
  NDS?: number | null;
  Kolvo_Ravan?: number | null;
  Summ_Ravan?: number | null;
  Summ_Corrected?: number | null;
  Partner_C?: string | null;
  Kolvo_C?: number | null;
  Summ_C?: number | null;
  Kolvo_Difference?: number | null;
  Summ_Difference?: number | null;
  Status: string;
}

export interface Ravan1CRunResult {
  run_id: string;
  module_id: 'ravan_1c';
  timestamp: string;
  status: string;
  summary: {
    total_records_a: number;
    total_records_b: number;
    total_sum_a: number;
    total_sum_b: number;
    matched_count: number;
    discrepancy_count: number;
    diff_sum: number;
    match_percentage: number;
    execution_time_ms: number;
  };
  by_category: Array<{ status: string; count: number }>;
  discrepancies: Ravan1CRow[];
  custom_metrics?: {
    ravan_1c?: {
      producer?: string;
      sum_tolerance?: number;
      status_counts?: Record<string, number>;
      rows?: Ravan1CRow[];
      source_ravan_rows?: number;
      source_1c_rows?: number;
      source_files?: string[];
      fuzzy_review_count?: number;
      fuzzy_name_threshold?: number;
    };
  };
}

export interface Ravan1CArchiveRecord {
  id: number;
  run_id?: string | null;
  timestamp?: string;
  created_at?: string;
  created_by?: string;
  username?: string;
  status?: string;
  period_month?: string;
  source_files?: string[];
  summary?: Ravan1CRunResult['summary'];
  result_snapshot?: Ravan1CRunResult;
  sum_tolerance?: number;
}

async function readJson(response: Response): Promise<any> {
  const raw = await response.text();
  let payload: any = null;
  try { payload = raw ? JSON.parse(raw) : null; } catch {}

  if (!response.ok) {
    const detail = payload?.detail;
    const validation = detail?.errors;
    throw new Error(
      typeof detail === 'string'
        ? detail
        : Array.isArray(validation)
          ? validation.join('; ')
          : raw || `HTTP ${response.status}`,
    );
  }
  return payload;
}

export async function runRavan1C(
  ravanFile: File,
  cFile: File,
  sumTolerance = 1,
): Promise<Ravan1CRunResult> {
  const form = new FormData();
  form.append('ravan_file', ravanFile, ravanFile.name);
  form.append('c_file', cFile, cFile.name);
  form.append('sum_tolerance', String(sumTolerance));

  const response = await apiFetch('/api/modules/ravan_1c/run', {
    method: 'POST',
    body: form,
  });
  return readJson(response) as Promise<Ravan1CRunResult>;
}

export async function saveRavan1CSnapshot(
  username: string,
  result: Ravan1CRunResult,
  _sourceFiles?: string[],
): Promise<string> {
  const saved = await saveModuleArchive(username, 'ravan_1c', {
    run_id: result.run_id,
  });
  return saved.message;
}

export async function saveRavan1CRun(
  username: string,
  result: Ravan1CRunResult,
  ravanFile: File,
  cFile: File,
  _sumTolerance: number,
): Promise<string> {
  return saveRavan1CSnapshot(
    username,
    result,
    [ravanFile.name, cFile.name],
  );
}

export async function getRavan1CArchive(username: string): Promise<Ravan1CArchiveRecord[]> {
  return getModuleArchive<Ravan1CArchiveRecord>(username, 'ravan_1c');
}

export async function deleteRavan1CArchive(username: string, id: number): Promise<void> {
  await deleteModuleArchive(username, 'ravan_1c', id);
}

export async function updateRavan1CMatchDecision(
  _username: string,
  runId: string,
  rowId: string,
  decision: 'confirm' | 'unlink',
): Promise<Ravan1CRunResult> {
  const response = await apiFetch(
    '/api/modules/ravan_1c/archive/'
      + encodeURIComponent(runId)
      + '/matches/'
      + encodeURIComponent(rowId),
    {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ decision }),
    },
  );
  const payload = await readJson(response);
  if (!payload?.result_snapshot) {
    throw new Error('Сервер не вернул обновлённый snapshot сверки.');
  }
  return payload.result_snapshot as Ravan1CRunResult;
}

const RAVAN_STATUS_ORDER = [
  'OK',
  'Ошибка Kolvo',
  'Ошибка Summ',
  'Ошибка Kolvo + Summ',
  'Нет в !C',
  'Нет в Ravan',
  'Ошибка',
];

function recalculateRavan1CResult(
  result: Ravan1CRunResult,
  nextRows: Ravan1CRow[],
): Ravan1CRunResult {
  const rows = nextRows.map(row => ({ ...row }));
  const statusCounts: Record<string, number> = {};
  rows.forEach(row => {
    statusCounts[row.Status] = (statusCounts[row.Status] || 0) + 1;
  });

  const matchedCount = rows.filter(row => row.Status === 'OK').length;
  const discrepancyCount = rows.length - matchedCount;
  const orderedCategories = [
    ...RAVAN_STATUS_ORDER,
    ...Object.keys(statusCounts).filter(status => !RAVAN_STATUS_ORDER.includes(status)),
  ]
    .filter((status, index, values) => values.indexOf(status) === index)
    .filter(status => (statusCounts[status] || 0) > 0)
    .map(status => ({ status, count: statusCounts[status] }));

  const metrics = result.custom_metrics?.ravan_1c || {};
  return {
    ...result,
    status: discrepancyCount === 0 ? 'COMPLETED' : 'WARNING',
    summary: {
      ...result.summary,
      matched_count: matchedCount,
      discrepancy_count: discrepancyCount,
      match_percentage: rows.length
        ? Math.round((matchedCount / rows.length) * 10000) / 100
        : 0,
    },
    by_category: orderedCategories,
    discrepancies: rows.filter(row => row.Status !== 'OK'),
    custom_metrics: {
      ...(result.custom_metrics || {}),
      ravan_1c: {
        ...metrics,
        rows,
        status_counts: statusCounts,
        fuzzy_review_count: rows.filter(row => row.Needs_Review).length,
      },
    },
  };
}

export function confirmRavan1CFuzzyMatch(
  result: Ravan1CRunResult,
  rowId: string,
): Ravan1CRunResult {
  const rows = result.custom_metrics?.ravan_1c?.rows || [];
  const nextRows = rows.map(row => (
    row.Row_ID === rowId
      ? { ...row, Needs_Review: false, Match_Confirmed: true }
      : { ...row }
  ));
  return recalculateRavan1CResult(result, nextRows);
}

export function unlinkRavan1CFuzzyMatch(
  result: Ravan1CRunResult,
  rowId: string,
): Ravan1CRunResult {
  const rows = result.custom_metrics?.ravan_1c?.rows || [];
  const target = rows.find(row => row.Row_ID === rowId);
  if (!target || !target.Partner_Ravan || !target.Partner_C) {
    return result;
  }

  const ravanOnly: Ravan1CRow = {
    ...target,
    Row_ID: `${rowId}-r`,
    Match_Type: 'manual_unlinked',
    Name_Similarity: null,
    Needs_Review: false,
    Match_Confirmed: false,
    Partner_C: null,
    Kolvo_C: null,
    Summ_C: null,
    Kolvo_Difference: -(Number(target.Kolvo_Ravan) || 0),
    Summ_Difference: -(Number(target.Summ_Corrected) || 0),
    Status: 'Нет в !C',
  };

  const oneCOnly: Ravan1CRow = {
    ...target,
    Row_ID: `${rowId}-c`,
    Match_Type: 'manual_unlinked',
    Name_Similarity: null,
    Needs_Review: false,
    Match_Confirmed: false,
    Partner_Ravan: null,
    NDS: null,
    Kolvo_Ravan: null,
    Summ_Ravan: null,
    Summ_Corrected: null,
    Kolvo_Difference: Number(target.Kolvo_C) || 0,
    Summ_Difference: Number(target.Summ_C) || 0,
    Status: 'Нет в Ravan',
  };

  const nextRows: Ravan1CRow[] = [];
  rows.forEach(row => {
    if (row.Row_ID === rowId) {
      nextRows.push(ravanOnly, oneCOnly);
    } else {
      nextRows.push({ ...row });
    }
  });
  return recalculateRavan1CResult(result, nextRows);
}

function safeCell(value: unknown): string | number {
  if (value == null) return '';
  if (typeof value === 'number') return Number.isFinite(value) ? value : '';
  const text = String(value);
  return /^[=+\-@]/.test(text) ? `'${text}` : text;
}

export function exportRavan1CToExcel(result: Ravan1CRunResult): void {
  const workbook = XLSX.utils.book_new();
  const rows = result.custom_metrics?.ravan_1c?.rows || [];

  const summaryRows = [
    { Показатель: 'Модуль', Значение: 'Сверка погашений' },
    { Показатель: 'Produced by', Значение: 'Sayfulloh Abdusalomov' },
    { Показатель: 'Run ID', Значение: result.run_id },
    { Показатель: 'Статус', Значение: result.status },
    { Показатель: 'Строк Ravan', Значение: result.summary.total_records_a },
    { Показатель: 'Строк 1C', Значение: result.summary.total_records_b },
    { Показатель: 'OK', Значение: result.summary.matched_count },
    { Показатель: 'Расхождений', Значение: result.summary.discrepancy_count },
    { Показатель: 'Сходимость', Значение: result.summary.match_percentage },
    { Показатель: 'Сумма Ravan скорр.', Значение: result.summary.total_sum_a },
    { Показатель: 'Сумма 1C', Значение: result.summary.total_sum_b },
    { Показатель: 'Разница', Значение: result.summary.diff_sum },
    {
      Показатель: 'Допуск суммы',
      Значение: result.custom_metrics?.ravan_1c?.sum_tolerance ?? 1,
    },
  ];
  XLSX.utils.book_append_sheet(
    workbook,
    XLSX.utils.json_to_sheet(summaryRows),
    'Summary',
  );

  const normalized = rows.map(row => {
    const output: Record<string, string | number> = {};
    Object.entries(row).forEach(([key, value]) => {
      output[key] = safeCell(value);
    });
    return output;
  });
  XLSX.utils.book_append_sheet(
    workbook,
    XLSX.utils.json_to_sheet(normalized),
    'Comparison',
  );

  const issues = normalized.filter(row => row.Status !== 'OK');
  XLSX.utils.book_append_sheet(
    workbook,
    XLSX.utils.json_to_sheet(issues.length ? issues : [{ Status: 'Нет расхождений' }]),
    'Issues',
  );

  const stamp = new Date().toISOString().slice(0, 16).replace(/[-:T]/g, '');
  XLSX.writeFile(workbook, `Сверка_погашений_${stamp}.xlsx`);
}
