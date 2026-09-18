import { ReconciliationConfig, ReconciliationResult, RawRow } from '../types';

interface BankRrnApiResult {
  run_id: string;
  module_id: string;
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
  by_date: RawRow[];
  discrepancies: RawRow[];
  custom_metrics?: {
    rrn?: Partial<ReconciliationResult> & {
      only_our?: RawRow[];
      only_bank?: RawRow[];
      amt_mismatches?: RawRow[];
      dups_our?: RawRow[];
      dups_bank?: RawRow[];
      dup_our_c?: number;
      dup_bank_c?: number;
      matched_count?: number;
      mismatch_count?: number;
      comm_only_diff_count?: number;
      deduct_commission?: boolean;
      terminal_summary?: RawRow[];
      total_commission?: number;
      effective_commission_rate?: number;
      data_quality?: ReconciliationResult['data_quality'];
      detected_months?: string[];
      dup_action?: string;
    };
  };
}

function boolParam(value: boolean): string {
  return value ? 'true' : 'false';
}

function toNumber(value: unknown): number {
  const n = Number(value);
  return Number.isFinite(n) ? n : 0;
}

function toDateString(value: unknown): string {
  const text = value == null ? '' : String(value);
  if (!text) return '';
  const datePart = text.slice(0, 10);
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(datePart);
  return match ? `${match[3]}.${match[2]}.${match[1]}` : text;
}

function normalizeUnmatched(row: RawRow, side: 'our' | 'bank'): ReconciliationResult['only_our'][number] {
  const amount = side === 'our'
    ? row.net_amount_our ?? row.amount ?? 0
    : row.net_amount_bank ?? row.raw_amount ?? row.amount ?? 0;
  const status = side === 'our' ? row.status_our ?? row.status : row.status_bank ?? row.status;
  const checkedRaw = row['✅'];

  return {
    checked: typeof checkedRaw === 'boolean' ? checkedRaw : true,
    reason: String(row['📝 Причина'] ?? row.reason ?? ''),
    date_str: String(row.date_str || toDateString(side === 'our' ? row.date ?? row.date_unified : row.date_bank ?? row.date_unified ?? row.date)),
    RRN: String(row.RRN ?? ''),
    amount: toNumber(amount),
    status: status == null ? '' : String(status),
    terminal_id: row.terminal_id == null ? undefined : String(row.terminal_id),
    commission_pct: row.commission_pct == null ? undefined : toNumber(row.commission_pct),
    raw: row,
  };
}

function normalizeMismatch(row: RawRow): ReconciliationResult['amt_mismatches'][number] {
  return {
    RRN: String(row.RRN ?? ''),
    date_our: toDateString(row.date ?? row.date_our),
    date_bank: toDateString(row.date_bank),
    net_amount_our: toNumber(row.net_amount_our),
    net_amount_bank: toNumber(row.net_amount_bank),
    'Δ сумма': toNumber(row['Δ сумма'] ?? row.delta ?? (toNumber(row.net_amount_bank) - toNumber(row.net_amount_our))),
    status_our: row.status_our == null ? undefined : String(row.status_our),
    status_bank: row.status_bank == null ? undefined : String(row.status_bank),
  };
}

/**
 * Runs Bank RRN through the FastAPI module contract.
 * The backend is the source of truth for reconciliation execution;
 * this adapter converts its rich response to the existing React result shape.
 */
export async function runBankRrnViaApi(
  ourFile: File,
  bankFile: File,
  cfg: ReconciliationConfig,
  username: string,
): Promise<ReconciliationResult> {
  const form = new FormData();
  form.append('our_file', ourFile, ourFile.name);
  form.append('bank_file', bankFile, bankFile.name);
  form.append('our_filename', ourFile.name);
  form.append('bank_filename', bankFile.name);
  form.append('our_date_col', cfg.our_date);
  form.append('our_rrn_col', cfg.our_rrn);
  form.append('our_amt_col', cfg.our_amt || '');
  form.append('our_status_col', cfg.our_status || '');
  form.append('bank_date_col', cfg.bank_date);
  form.append('bank_rrn_col', cfg.bank_rrn);
  form.append('bank_amt_col', cfg.bank_amt || '');
  form.append('bank_status_col', cfg.bank_status || '');
  form.append('bank_tid_col', cfg.bank_tid || '');
  form.append('rev_words', cfg.rev_words.join(', '));
  form.append('our_rev_action', cfg.our_rev);
  form.append('bank_rev_action', cfg.bank_rev);
  form.append('dup_action', cfg.dup_action);
  form.append('unbind_mismatches', boolParam(cfg.unbind_mismatches));
  form.append('tolerance', String(cfg.tolerance));
  form.append('deduct_commission', boolParam(!!cfg.deduct_commission));

  const response = await fetch('/api/modules/bank_rrn/run', {
    method: 'POST',
    headers: { 'X-User': username },
    body: form,
  });

  const rawBody = await response.text();
  let payload: any = null;
  try {
    payload = rawBody ? JSON.parse(rawBody) : null;
  } catch {
    payload = null;
  }

  if (!response.ok) {
    const detail = payload?.detail;
    const validationErrors = Array.isArray(detail)
      ? detail
          .map((item: any) => item?.msg || item?.message || String(item))
          .filter(Boolean)
          .join('; ')
      : detail?.errors?.join?.('; ');
    const message = typeof detail === 'string'
      ? detail
      : validationErrors
        || (rawBody && rawBody !== 'Internal Server Error' ? rawBody : '')
        || `FastAPI не смог выполнить сверку (HTTP ${response.status}).`;
    throw new Error(message);
  }

  if (!payload) {
    throw new Error('FastAPI вернул пустой или некорректный ответ после сверки.');
  }

  const apiResult = payload as BankRrnApiResult;
  const rrn = apiResult.custom_metrics?.rrn || {};

  return {
    run_id: apiResult.run_id,
    run_timestamp: apiResult.timestamp,
    summary: (apiResult.by_date || []) as ReconciliationResult['summary'],
    only_our: (rrn.only_our || []).map(row => normalizeUnmatched(row, 'our')),
    only_bank: (rrn.only_bank || []).map(row => normalizeUnmatched(row, 'bank')),
    amt_mismatches: (rrn.amt_mismatches || []).map(normalizeMismatch),
    dups_our: (rrn.dups_our || []) as ReconciliationResult['dups_our'],
    dups_bank: (rrn.dups_bank || []) as ReconciliationResult['dups_bank'],
    dup_our_c: Number(rrn.dup_our_c || 0),
    dup_bank_c: Number(rrn.dup_bank_c || 0),
    matched_count: Number(rrn.matched_count ?? apiResult.summary.matched_count ?? 0),
    mismatch_count: Number(rrn.mismatch_count ?? 0),
    terminal_summary: (rrn.terminal_summary || []) as ReconciliationResult['terminal_summary'],
    total_commission: Number(rrn.total_commission || 0),
    effective_commission_rate: Number(rrn.effective_commission_rate || 0),
    comm_only_diff_count: Number(rrn.comm_only_diff_count || 0),
    deduct_commission: Boolean(rrn.deduct_commission),
    data_quality: rrn.data_quality || {},
    detected_months: rrn.detected_months || [],
    merged_rows: [],
    dup_action: rrn.dup_action || cfg.dup_action,
  };
}
