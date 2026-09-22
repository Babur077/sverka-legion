import { ReconciliationConfig, ReconciliationResult, RawRow } from '../types';
import { apiFetch } from './apiClient';
import type { FileParseOptions } from './fileParser';

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
      dup_our_rrn_c?: number;
      dup_bank_rrn_c?: number;
      dup_removed_our_c?: number;
      dup_removed_bank_c?: number;
      matched_count?: number;
      mismatch_count?: number;
      rrn_found_count?: number;
      amount_mismatch_count_before_unbind?: number;
      only_our_count_before_unbind?: number;
      only_bank_count_before_unbind?: number;
      unbound_mismatch_count?: number;
      comm_only_diff_count?: number;
      amount_mismatch_net_delta?: number;
      amount_mismatch_abs_delta?: number;
      amount_mismatch_positive_delta?: number;
      amount_mismatch_negative_delta?: number;
      amount_mismatch_invalid_delta_count?: number;
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

function toNullableNumber(value: unknown): number | null {
  if (value == null || value === '') return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
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
    amount: toNullableNumber(amount),
    status: status == null ? '' : String(status),
    terminal_id: row.terminal_id == null ? undefined : String(row.terminal_id),
    commission_pct: row.commission_pct == null ? undefined : toNumber(row.commission_pct),
    raw: row,
  };
}

function normalizeMismatch(row: RawRow): ReconciliationResult['amt_mismatches'][number] {
  const ourAmount = toNullableNumber(row.net_amount_our);
  const bankAmount = toNullableNumber(row.net_amount_bank);
  const explicitDelta = toNullableNumber(row['Δ сумма'] ?? row.delta);
  const delta = explicitDelta ?? (
    ourAmount != null && bankAmount != null
      ? bankAmount - ourAmount
      : null
  );

  return {
    RRN: String(row.RRN ?? ''),
    date_our: toDateString(row.date ?? row.date_our),
    date_bank: toDateString(row.date_bank),
    net_amount_our: ourAmount,
    net_amount_bank: bankAmount,
    'Δ сумма': delta,
    amount_issue: row.amount_issue == null ? undefined : String(row.amount_issue),
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
  _username: string,
  sourceOptions?: { our?: FileParseOptions; bank?: FileParseOptions },
): Promise<ReconciliationResult> {
  const form = new FormData();
  form.append('our_file', ourFile, ourFile.name);
  form.append('bank_file', bankFile, bankFile.name);
  form.append('our_filename', ourFile.name);
  form.append('bank_filename', bankFile.name);
  form.append('our_sheet_name', sourceOptions?.our?.sheetName || '');
  form.append('bank_sheet_name', sourceOptions?.bank?.sheetName || '');
  form.append('our_header_row', String(sourceOptions?.our?.headerRow || 1));
  form.append('bank_header_row', String(sourceOptions?.bank?.headerRow || 1));
  form.append('our_date_col', cfg.our_date.trim());
  form.append('our_rrn_col', cfg.our_rrn.trim());
  form.append('our_amt_col', (cfg.our_amt || '').trim());
  form.append('our_status_col', (cfg.our_status || '').trim());
  form.append('bank_date_col', cfg.bank_date.trim());
  form.append('bank_rrn_col', cfg.bank_rrn.trim());
  form.append('bank_amt_col', (cfg.bank_amt || '').trim());
  form.append('bank_status_col', (cfg.bank_status || '').trim());
  form.append('bank_tid_col', (cfg.bank_tid || '').trim());
  form.append('rev_words', cfg.rev_words.join(', '));
  form.append('our_rev_action', cfg.our_rev);
  form.append('bank_rev_action', cfg.bank_rev);
  form.append('dup_action', cfg.dup_action);
  form.append('unbind_mismatches', boolParam(cfg.unbind_mismatches));
  form.append('tolerance', String(cfg.tolerance));
  form.append('deduct_commission', boolParam(!!cfg.deduct_commission));

  const response = await apiFetch('/api/modules/bank_rrn/run', {
    method: 'POST',
    body: form,
  });

  if (!response.ok) {
    const rawBody = await response.text();
    let errorPayload: any = null;
    try {
      errorPayload = rawBody ? JSON.parse(rawBody) : null;
    } catch {
      errorPayload = null;
    }

    const detail = errorPayload?.detail;
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

  let payload: any = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
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
    dup_our_rrn_c: Number(rrn.dup_our_rrn_c || 0),
    dup_bank_rrn_c: Number(rrn.dup_bank_rrn_c || 0),
    dup_removed_our_c: Number(rrn.dup_removed_our_c || 0),
    dup_removed_bank_c: Number(rrn.dup_removed_bank_c || 0),
    matched_count: Number(rrn.matched_count ?? apiResult.summary.matched_count ?? 0),
    mismatch_count: Number(rrn.mismatch_count ?? 0),
    rrn_found_count: Number(
      rrn.rrn_found_count
      ?? rrn.matched_count
      ?? apiResult.summary.matched_count
      ?? 0
    ),
    amount_mismatch_count_before_unbind: Number(
      rrn.amount_mismatch_count_before_unbind
      ?? rrn.mismatch_count
      ?? 0
    ),
    only_our_count_before_unbind: Number(
      rrn.only_our_count_before_unbind
      ?? (rrn.only_our || []).length
    ),
    only_bank_count_before_unbind: Number(
      rrn.only_bank_count_before_unbind
      ?? (rrn.only_bank || []).length
    ),
    unbound_mismatch_count: Number(rrn.unbound_mismatch_count ?? 0),
    terminal_summary: (rrn.terminal_summary || []) as ReconciliationResult['terminal_summary'],
    total_commission: Number(rrn.total_commission || 0),
    effective_commission_rate: Number(rrn.effective_commission_rate || 0),
    comm_only_diff_count: Number(rrn.comm_only_diff_count || 0),
    amount_mismatch_net_delta: Number(rrn.amount_mismatch_net_delta || 0),
    amount_mismatch_abs_delta: Number(rrn.amount_mismatch_abs_delta || 0),
    amount_mismatch_positive_delta: Number(rrn.amount_mismatch_positive_delta || 0),
    amount_mismatch_negative_delta: Number(rrn.amount_mismatch_negative_delta || 0),
    amount_mismatch_invalid_delta_count: Number(rrn.amount_mismatch_invalid_delta_count || 0),
    deduct_commission: Boolean(rrn.deduct_commission),
    data_quality: rrn.data_quality || {},
    detected_months: rrn.detected_months || [],
    merged_rows: [],
    dup_action: rrn.dup_action || cfg.dup_action,
  };
}
