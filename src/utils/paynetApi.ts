export interface PaynetRunConfig {
  billingIdCol: string;
  billingAmountCol: string;
  billingStatusCol?: string;
  agentIdCol: string;
  agentAmountCol: string;
  agentStatusCol?: string;
  agentCommissionCol?: string;
  providerName: string;
  tolerance: number;
}

export interface PaynetSummary {
  total_records_a: number;
  total_records_b: number;
  total_sum_a: number;
  total_sum_b: number;
  matched_count: number;
  discrepancy_count: number;
  diff_sum: number;
  match_percentage: number;
  execution_time_ms: number;
}

export interface PaynetRunResult {
  run_id: string;
  module_id: string;
  timestamp: string;
  status: string;
  summary: PaynetSummary;
  discrepancies: Array<Record<string, any>>;
  custom_metrics?: {
    paynet?: {
      provider_name?: string;
      only_billing?: Array<Record<string, any>>;
      only_agent?: Array<Record<string, any>>;
      amount_mismatches?: Array<Record<string, any>>;
      status_mismatches?: Array<Record<string, any>>;
      billing_duplicates?: Array<Record<string, any>>;
      agent_duplicates?: Array<Record<string, any>>;
      total_commission?: number;
      tolerance?: number;
    };
  };
}

export interface PaynetArchiveRecord {
  id: number;
  timestamp: string;
  username: string;
  bank_name: string;
  total_our: number;
  total_bank: number;
  difference: number;
  matched_count: number;
  mismatch_count: number;
  only_our_count: number;
  only_bank_count: number;
  period_month?: string;
  total_commission?: number;
  module_id: string;
  extra?: Record<string, any>;
}

async function readResponse(response: Response): Promise<any> {
  const raw = await response.text();
  let payload: any = null;
  try { payload = raw ? JSON.parse(raw) : null; } catch {}

  if (!response.ok) {
    const detail = payload?.detail;
    const message = typeof detail === 'string'
      ? detail
      : detail?.errors?.join?.('; ')
        || (Array.isArray(detail) ? detail.map((x: any) => x?.msg || String(x)).join('; ') : '')
        || raw
        || `Ошибка сервера (HTTP ${response.status})`;
    throw new Error(message);
  }
  return payload;
}

export async function runPaynetViaApi(
  username: string,
  billingFile: File,
  agentFile: File,
  config: PaynetRunConfig,
): Promise<PaynetRunResult> {
  const form = new FormData();
  form.append('billing_file', billingFile, billingFile.name);
  form.append('agent_file', agentFile, agentFile.name);
  form.append('billing_id_col', config.billingIdCol);
  form.append('billing_amount_col', config.billingAmountCol);
  form.append('billing_status_col', config.billingStatusCol || '');
  form.append('agent_id_col', config.agentIdCol);
  form.append('agent_amount_col', config.agentAmountCol);
  form.append('agent_status_col', config.agentStatusCol || '');
  form.append('agent_commission_col', config.agentCommissionCol || '');
  form.append('provider_name', config.providerName || 'Paynet / Payme');
  form.append('tolerance', String(config.tolerance));

  const response = await fetch('/api/modules/paynet/run', {
    method: 'POST',
    headers: { 'X-User': username },
    body: form,
  });
  return readResponse(response);
}

export async function getPaynetArchive(username: string): Promise<PaynetArchiveRecord[]> {
  const response = await fetch('/api/modules/paynet/archive', {
    headers: { 'X-User': username },
  });
  return readResponse(response);
}

export async function savePaynetArchive(
  username: string,
  result: PaynetRunResult,
  providerName: string,
): Promise<void> {
  const paynet = result.custom_metrics?.paynet || {};
  const response = await fetch('/api/modules/paynet/archive', {
    method: 'POST',
    headers: { 'X-User': username, 'Content-Type': 'application/json' },
    body: JSON.stringify({
      label: providerName || paynet.provider_name || 'Paynet / Payme',
      total_a: result.summary.total_sum_a,
      total_b: result.summary.total_sum_b,
      difference: result.summary.diff_sum,
      matched_count: result.summary.matched_count,
      discrepancy_count: result.summary.discrepancy_count,
      mismatch_count: (paynet.amount_mismatches?.length || 0) + (paynet.status_mismatches?.length || 0),
      only_a_count: paynet.only_billing?.length || 0,
      only_b_count: paynet.only_agent?.length || 0,
      total_commission: paynet.total_commission || 0,
      extra: {
        run_id: result.run_id,
        provider_name: providerName || paynet.provider_name || '',
        match_percentage: result.summary.match_percentage,
        amount_mismatch_count: paynet.amount_mismatches?.length || 0,
        status_mismatch_count: paynet.status_mismatches?.length || 0,
        billing_duplicate_groups: paynet.billing_duplicates?.length || 0,
        agent_duplicate_groups: paynet.agent_duplicates?.length || 0,
      },
    }),
  });
  await readResponse(response);
}

export async function deletePaynetArchive(username: string, id: number): Promise<void> {
  const response = await fetch('/api/modules/paynet/archive/' + id, {
    method: 'DELETE',
    headers: { 'X-User': username },
  });
  await readResponse(response);
}
