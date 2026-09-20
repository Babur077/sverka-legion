import { apiFetch } from './apiClient';

export type BuilderKeyTransform = 'none' | 'remove_spaces' | 'digits_only' | 'strip_leading_zeros' | 'alnum';

export interface BuilderKeyPair {
  left: string;
  right: string;
  mode: 'exact' | 'text' | 'numeric';
  left_transform?: BuilderKeyTransform;
  right_transform?: BuilderKeyTransform;
}

export interface BuilderFilterRule {
  side: 'a' | 'b';
  column: string;
  operator: 'equals' | 'not_equals' | 'contains' | 'not_contains' | 'empty' | 'not_empty' | 'gt' | 'gte' | 'lt' | 'lte';
  value?: string;
}

export type BuilderAmountTransform = 'as_is' | 'invert' | 'absolute';
export type BuilderMatchingMode = 'one_to_one' | 'one_to_many' | 'many_to_one';

export interface ReconciliationBuilderConfig {
  key_pairs: BuilderKeyPair[];
  amount_a_col?: string;
  amount_b_col?: string;
  amount_tolerance: number;
  amount_a_transform?: BuilderAmountTransform;
  amount_b_transform?: BuilderAmountTransform;
  matching_mode?: BuilderMatchingMode;
  filters?: BuilderFilterRule[];
  date_a_col?: string;
  date_b_col?: string;
  date_tolerance_days: number;
  ignore_empty_keys: boolean;
  dayfirst: boolean;
}

export interface ReconciliationDefinition {
  id: number;
  name: string;
  description: string;
  config: ReconciliationBuilderConfig;
  created_by: string;
  created_at: string;
  updated_at: string;
  is_active: boolean;
}

export interface BuilderRunSummary {
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

export interface BuilderResultRow {
  key: string;
  row_a?: number;
  row_b?: number;
  amount_a?: number | null;
  amount_b?: number | null;
  amount_delta?: number | null;
  date_a?: string | null;
  date_b?: string | null;
  date_delta_days?: number | null;
  match_type?: '1↔1' | '1↔N' | 'N↔1';
  grouped_rows_a?: number[];
  grouped_rows_b?: number[];
  reason?: string;
  source_a?: Record<string, any>;
  source_b?: Record<string, any>;
}

export interface BuilderRunResult {
  run_id: string;
  module_id: string;
  timestamp: string;
  status: string;
  summary: BuilderRunSummary;
  discrepancies: BuilderResultRow[];
  custom_metrics?: {
    generic?: {
      definition_id?: number | null;
      definition_name?: string;
      key_pairs?: BuilderKeyPair[];
      amount_mapping?: {
        left?: string | null;
        right?: string | null;
        tolerance?: number;
      };
      date_mapping?: {
        left?: string | null;
        right?: string | null;
        tolerance_days?: number;
      };
      matched?: BuilderResultRow[];
      mismatches?: BuilderResultRow[];
      only_a?: BuilderResultRow[];
      only_b?: BuilderResultRow[];
      columns_a?: string[];
      columns_b?: string[];
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

export async function getReconciliationDefinitions(): Promise<ReconciliationDefinition[]> {
  const response = await apiFetch('/api/reconciliation-definitions');
  const payload = await readJson(response);
  return Array.isArray(payload) ? payload : [];
}

export async function createReconciliationDefinition(
  name: string,
  description: string,
  config: ReconciliationBuilderConfig,
): Promise<{ id: number; message: string }> {
  const response = await apiFetch('/api/reconciliation-definitions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, description, config }),
  });
  const payload = await readJson(response);
  return { id: Number(payload?.id), message: String(payload?.message || '') };
}

export async function updateReconciliationDefinition(
  id: number,
  name: string,
  description: string,
  config: ReconciliationBuilderConfig,
): Promise<{ id: number; message: string }> {
  const response = await apiFetch('/api/reconciliation-definitions/' + id, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, description, config }),
  });
  const payload = await readJson(response);
  return { id: Number(payload?.id), message: String(payload?.message || '') };
}

export async function deleteReconciliationDefinition(id: number): Promise<void> {
  const response = await apiFetch('/api/reconciliation-definitions/' + id, {
    method: 'DELETE',
  });
  await readJson(response);
}

export async function runReconciliationBuilder(
  sourceA: File,
  sourceB: File,
  config: ReconciliationBuilderConfig,
  definition?: { id?: number; name?: string },
): Promise<BuilderRunResult> {
  const form = new FormData();
  form.append('source_a', sourceA, sourceA.name);
  form.append('source_b', sourceB, sourceB.name);
  form.append('source_a_filename', sourceA.name);
  form.append('source_b_filename', sourceB.name);
  form.append('key_pairs', JSON.stringify(config.key_pairs));
  form.append('filters', JSON.stringify(config.filters || []));
  form.append('matching_mode', config.matching_mode || 'one_to_one');
  form.append('amount_a_col', config.amount_a_col || '');
  form.append('amount_b_col', config.amount_b_col || '');
  form.append('amount_tolerance', String(config.amount_tolerance || 0));
  form.append('amount_a_transform', config.amount_a_transform || 'as_is');
  form.append('amount_b_transform', config.amount_b_transform || 'as_is');
  form.append('date_a_col', config.date_a_col || '');
  form.append('date_b_col', config.date_b_col || '');
  form.append('date_tolerance_days', String(config.date_tolerance_days || 0));
  form.append('ignore_empty_keys', config.ignore_empty_keys ? 'true' : 'false');
  form.append('dayfirst', config.dayfirst ? 'true' : 'false');
  form.append('definition_id', definition?.id == null ? '' : String(definition.id));
  form.append('definition_name', definition?.name || '');

  const response = await apiFetch('/api/modules/reconciliation_builder/run', {
    method: 'POST',
    body: form,
  });
  return readJson(response) as Promise<BuilderRunResult>;
}
