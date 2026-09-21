import { apiFetch } from './apiClient';

export interface DashboardSummary {
  runs: number;
  completed_runs: number;
  failed_runs: number;
  problem_runs: number;
  average_match_percentage: number;
  discrepancies: number;
  running_jobs: number;
  queued_jobs: number;
  failed_jobs: number;
}

export interface DashboardTrendPoint {
  month: string;
  runs: number;
  average_match_percentage: number;
  discrepancies: number;
}

export interface DashboardModuleSummary {
  module_id: string;
  module_name: string;
  runs: number;
  average_match_percentage: number;
  problem_runs: number;
  discrepancies: number;
}

export interface DashboardRecentRun {
  id: number;
  module_id: string;
  module_name: string;
  run_id?: string | null;
  status: string;
  period_month: string;
  created_at?: string | null;
  updated_at?: string | null;
  created_by: string;
  matched_count: number;
  discrepancy_count: number;
  match_percentage: number;
  definition_name?: string | null;
  definition_version_number?: number | null;
  bank_name?: string | null;
}

export interface DashboardJob {
  id: number;
  module_id: string;
  status: string;
  progress: number;
  stage: string;
  created_by: string;
  created_at: string;
  updated_at: string;
  started_at?: string | null;
  finished_at?: string | null;
  run_id?: string | null;
  error?: string | null;
}

export interface DashboardData {
  period: {
    months: number;
    from_month: string;
    to_month: string;
  };
  filters: {
    module_id?: string | null;
    available_modules: Array<{ id: string; name: string }>;
  };
  summary: DashboardSummary;
  trend: DashboardTrendPoint[];
  modules: DashboardModuleSummary[];
  recent_runs: DashboardRecentRun[];
  jobs: DashboardJob[];
}

async function readJson(response: Response): Promise<any> {
  const raw = await response.text();
  let payload: any = null;
  try { payload = raw ? JSON.parse(raw) : null; } catch {}

  if (!response.ok) {
    throw new Error(
      typeof payload?.detail === 'string'
        ? payload.detail
        : raw || `HTTP ${response.status}`,
    );
  }
  return payload;
}

export async function getDashboardData(
  months = 6,
  moduleId?: string,
): Promise<DashboardData> {
  const query = new URLSearchParams({ months: String(months) });
  if (moduleId) query.set('module_id', moduleId);
  const response = await apiFetch(`/api/dashboard?${query.toString()}`);
  return readJson(response) as Promise<DashboardData>;
}
