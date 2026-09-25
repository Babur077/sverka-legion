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
  month?: string;
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
