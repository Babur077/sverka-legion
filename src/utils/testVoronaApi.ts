import { apiFetch } from './apiClient';

export interface TestVoronaRow {
  partner: string;
  inn: string;
  vid: string;
  payment: number;
  bank: number;
  faktura: number;
  komissiya: number;
  opening_balance: number;
  saldo: number;
  one_c: number;
  difference: number;
  difference_1c: number;
  status: string;
}

export interface TestVoronaSourceRow {
  month?: string | number;
  month_num?: number;
  date?: string | null;
  inn?: string;
  vid?: string;
  partner?: string;
  amount?: number;
  commission?: number;
  Status?: string;
  Service?: string;
  side?: string;
}

export type TestVoronaSourceType =
  | 'sales'
  | 'bank'
  | 'faktura'
  | 'one_c'
  | 'partners'
  | 'opening_balances';

export interface TestVoronaImportBatch {
  id: number;
  source_type: TestVoronaSourceType;
  period_key: string;
  year?: number | null;
  month?: number | null;
  filename: string;
  file_hash: string;
  rows_count: number;
  status: string;
  is_active: number | boolean;
  uploaded_by: string;
  uploaded_at: string;
  replaced_by_batch_id?: number | null;
}

export interface TestVoronaImportResult {
  state: 'saved' | 'duplicate';
  batch: TestVoronaImportBatch;
  replaced_batch_id?: number | null;
  message: string;
}

export class TestVoronaImportConflictError extends Error {
  batch?: TestVoronaImportBatch;

  constructor(message: string, batch?: TestVoronaImportBatch) {
    super(message);
    this.name = 'TestVoronaImportConflictError';
    this.batch = batch;
  }
}

export interface TestVoronaRunResult {
  run_id: string;
  module_id: 'test_vorona';
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
  custom_metrics?: {
    test_vorona?: {
      year?: number;
      tolerance?: number;
      rows?: TestVoronaRow[];
      status_counts?: Record<string, number>;
      totals?: Record<string, number>;
      source_counts?: Record<string, number>;
      datasets?: {
        sales?: TestVoronaSourceRow[];
        bank?: TestVoronaSourceRow[];
        faktura?: TestVoronaSourceRow[];
        partners?: TestVoronaSourceRow[];
        opening_balances?: TestVoronaSourceRow[];
        one_c?: TestVoronaSourceRow[];
      };
    };
  };
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

export async function runTestVorona(
  files: {
    baza: File;
    bank: File;
    faktura: File;
    vipp: File;
    vorona: File;
  },
  year: number,
): Promise<TestVoronaRunResult> {
  const form = new FormData();
  form.append('baza_file', files.baza, files.baza.name);
  form.append('bank_file', files.bank, files.bank.name);
  form.append('faktura_file', files.faktura, files.faktura.name);
  form.append('vipp_file', files.vipp, files.vipp.name);
  form.append('vorona_file', files.vorona, files.vorona.name);
  form.append('year', String(year));

  const response = await apiFetch('/api/modules/test_vorona/run', {
    method: 'POST',
    body: form,
  });
  return readJson(response) as Promise<TestVoronaRunResult>;
}


export async function getTestVoronaImports(
  year?: number,
  month?: number,
  includeReplaced = true,
): Promise<TestVoronaImportBatch[]> {
  const params = new URLSearchParams();
  if (year) params.set('year', String(year));
  if (month) params.set('month', String(month));
  params.set('include_replaced', includeReplaced ? 'true' : 'false');

  const response = await apiFetch(
    '/api/modules/test_vorona/imports?' + params.toString(),
  );
  return readJson(response) as Promise<TestVoronaImportBatch[]>;
}

export async function uploadTestVoronaSource(
  sourceType: TestVoronaSourceType,
  file: File,
  options: {
    year?: number;
    month?: number;
    replaceExisting?: boolean;
  } = {},
): Promise<TestVoronaImportResult> {
  const form = new FormData();
  form.append('file', file, file.name);
  if (options.year) form.append('year', String(options.year));
  if (options.month) form.append('month', String(options.month));
  if (options.replaceExisting) form.append('replace_existing', 'true');

  const response = await apiFetch(
    '/api/modules/test_vorona/imports/' + encodeURIComponent(sourceType),
    {
      method: 'POST',
      body: form,
    },
  );

  if (response.status === 409) {
    const raw = await response.text();
    let payload: any = null;
    try { payload = raw ? JSON.parse(raw) : null; } catch {}
    const detail = payload?.detail;
    throw new TestVoronaImportConflictError(
      detail?.message || 'Для этого периода уже есть активная загрузка.',
      detail?.batch,
    );
  }

  return readJson(response) as Promise<TestVoronaImportResult>;
}

export async function runStoredTestVorona(
  year: number,
  throughMonth?: number,
): Promise<TestVoronaRunResult> {
  const response = await apiFetch('/api/modules/test_vorona/run-stored', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      year,
      through_month: throughMonth ?? null,
    }),
  });
  return readJson(response) as Promise<TestVoronaRunResult>;
}
