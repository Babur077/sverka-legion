import * as XLSX from 'xlsx';

import { apiFetch } from './apiClient';
import { getModuleArchive, saveModuleArchive } from './archiveApi';

export interface Ravan1CRow {
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

export async function saveRavan1CRun(
  username: string,
  result: Ravan1CRunResult,
  ravanFile: File,
  cFile: File,
  sumTolerance: number,
): Promise<string> {
  const saved = await saveModuleArchive(username, 'ravan_1c', {
    run_id: result.run_id,
    status: result.status,
    source_files: [ravanFile.name, cFile.name],
    summary: result.summary,
    producer: 'Sayfulloh Abdusalomov',
    sum_tolerance: sumTolerance,
    result_snapshot: result,
    archive_schema_version: 1,
  });
  return saved.message;
}

export async function getRavan1CArchive(username: string): Promise<Ravan1CArchiveRecord[]> {
  return getModuleArchive<Ravan1CArchiveRecord>(username, 'ravan_1c');
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
  XLSX.writeFile(workbook, `Ravan_1C_${stamp}.xlsx`);
}
