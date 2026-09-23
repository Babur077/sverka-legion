import * as XLSX from 'xlsx';

import { apiFetch } from './apiClient';
import {
  deleteModuleArchive,
  getModuleArchiveRecord,
  getModuleArchiveSummary,
  saveModuleArchive,
} from './archiveApi';

export interface RepaymentRow {
  'Номер платежа': string;
  'Дата'?: string | null;
  'Сумма': number;
  'Дата Meta'?: string | null;
  'Сумма Meta': number;
  'Дата в системе'?: string | null;
  'Сумма опознание': number;
  'Номер договора опознание'?: string | null;
  'Комментарий': string;
  'Δ суммы': number;
}

export interface RepaymentsRunResult {
  run_id: string;
  module_id: 'repayments';
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
  discrepancies: RepaymentRow[];
  custom_metrics?: {
    repayments?: {
      sum_tolerance?: number;
      status_counts?: Record<string, number>;
      rows?: RepaymentRow[];
      source_1c_rows?: number;
      source_meta_rows?: number;
      unique_1c?: number;
      unique_meta?: number;
      unique_total?: number;
      source_files?: string[];
      header_rows?: {
        one_c?: number;
        meta?: number;
      };
    };
  };
}

export interface RepaymentsArchiveRecord {
  id: number;
  run_id?: string | null;
  status?: string;
  timestamp?: string;
  created_at?: string;
  created_by?: string;
  username?: string;
  source_files?: string[];
  summary?: RepaymentsRunResult['summary'];
  result_snapshot?: RepaymentsRunResult;
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

export async function runRepayments(
  oneCFile: File,
  metaFile: File,
  oneCHeaderRow = 1,
  metaHeaderRow = 1,
): Promise<RepaymentsRunResult> {
  const form = new FormData();
  form.append('one_c_file', oneCFile, oneCFile.name);
  form.append('meta_file', metaFile, metaFile.name);
  form.append('one_c_header_row', String(oneCHeaderRow));
  form.append('meta_header_row', String(metaHeaderRow));

  const response = await apiFetch('/api/modules/repayments/run', {
    method: 'POST',
    body: form,
  });
  return readJson(response) as Promise<RepaymentsRunResult>;
}

export async function saveRepaymentsRun(
  username: string,
  result: RepaymentsRunResult,
): Promise<string> {
  const saved = await saveModuleArchive(username, 'repayments', {
    run_id: result.run_id,
  });
  return saved.message;
}

export async function getRepaymentsArchive(
  username: string,
): Promise<RepaymentsArchiveRecord[]> {
  return getModuleArchiveSummary<RepaymentsArchiveRecord>(username, 'repayments');
}

export async function getRepaymentsArchiveRecord(
  username: string,
  id: number,
): Promise<RepaymentsArchiveRecord> {
  return getModuleArchiveRecord<RepaymentsArchiveRecord>(username, 'repayments', id);
}

export async function deleteRepaymentsArchive(
  username: string,
  id: number,
): Promise<void> {
  await deleteModuleArchive(username, 'repayments', id);
}

function safeCell(value: unknown): string | number {
  if (value == null) return '';
  if (typeof value === 'number') return Number.isFinite(value) ? value : '';
  const text = String(value);
  return /^[=+\-@]/.test(text) ? `'${text}` : text;
}

export function exportRepaymentsToExcel(result: RepaymentsRunResult): void {
  const workbook = XLSX.utils.book_new();
  const metrics = result.custom_metrics?.repayments;
  const rows = metrics?.rows || [];

  const summaryRows = [
    { Показатель: 'Модуль', Значение: 'Сверка Погашений' },
    { Показатель: 'Run ID', Значение: result.run_id },
    { Показатель: 'Статус', Значение: result.status },
    { Показатель: 'Строк 1С', Значение: result.summary.total_records_a },
    { Показатель: 'Строк Meta', Значение: result.summary.total_records_b },
    { Показатель: 'Уникальных в 1С', Значение: metrics?.unique_1c ?? 0 },
    { Показатель: 'Уникальных в Meta', Значение: metrics?.unique_meta ?? 0 },
    { Показатель: 'Всего уникальных', Значение: metrics?.unique_total ?? rows.length },
    { Показатель: 'Правильно', Значение: result.summary.matched_count },
    { Показатель: 'Расхождений', Значение: result.summary.discrepancy_count },
    { Показатель: 'Сходимость, %', Значение: result.summary.match_percentage },
    { Показатель: 'Сумма 1С', Значение: result.summary.total_sum_a },
    { Показатель: 'Сумма Meta', Значение: result.summary.total_sum_b },
    { Показатель: 'Δ Meta − 1С', Значение: result.summary.diff_sum },
    { Показатель: 'Допуск суммы', Значение: metrics?.sum_tolerance ?? 1 },
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
    XLSX.utils.json_to_sheet(normalized.length ? normalized : [{ Комментарий: 'Нет данных' }]),
    'Результат',
  );

  const issues = normalized.filter(row => row['Комментарий'] !== 'Правильно');
  XLSX.utils.book_append_sheet(
    workbook,
    XLSX.utils.json_to_sheet(issues.length ? issues : [{ Комментарий: 'Нет расхождений' }]),
    'Расхождения',
  );

  const stamp = new Date().toISOString().slice(0, 16).replace(/[-:T]/g, '');
  XLSX.writeFile(workbook, `Сверка_Погашений_${stamp}.xlsx`);
}
