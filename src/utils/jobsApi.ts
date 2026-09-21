import { apiFetch } from './apiClient';

export type ReconciliationJobStatus =
  | 'QUEUED'
  | 'RUNNING'
  | 'COMPLETED'
  | 'FAILED'
  | 'CANCELLED';

export interface ReconciliationJob {
  id: number;
  module_id: string;
  status: ReconciliationJobStatus;
  progress: number;
  stage: string;
  created_by: string;
  created_at: string;
  updated_at: string;
  started_at?: string | null;
  finished_at?: string | null;
  run_id?: string | null;
  error?: string | null;
  cancel_requested?: boolean;
}

async function readJson(response: Response): Promise<any> {
  const raw = await response.text();
  let payload: any = null;
  try { payload = raw ? JSON.parse(raw) : null; } catch {}

  if (!response.ok) {
    const detail = payload?.detail;
    throw new Error(
      typeof detail === 'string'
        ? detail
        : raw || `HTTP ${response.status}`,
    );
  }

  return payload;
}

export async function enqueueReconciliationJob(
  moduleId: string,
  form: FormData,
): Promise<ReconciliationJob> {
  const response = await apiFetch(`/api/jobs/${moduleId}`, {
    method: 'POST',
    body: form,
  });
  return readJson(response) as Promise<ReconciliationJob>;
}

export async function getReconciliationJobs(
  moduleId?: string,
  limit = 20,
): Promise<ReconciliationJob[]> {
  const query = new URLSearchParams();
  if (moduleId) query.set('module_id', moduleId);
  query.set('limit', String(limit));

  const response = await apiFetch(`/api/jobs?${query.toString()}`);
  const payload = await readJson(response);
  return Array.isArray(payload) ? payload : [];
}

export async function getReconciliationJob(
  jobId: number,
): Promise<ReconciliationJob> {
  const response = await apiFetch(`/api/jobs/${jobId}`);
  return readJson(response) as Promise<ReconciliationJob>;
}

export async function cancelReconciliationJob(
  jobId: number,
): Promise<ReconciliationJob> {
  const response = await apiFetch(`/api/jobs/${jobId}/cancel`, {
    method: 'POST',
  });
  return readJson(response) as Promise<ReconciliationJob>;
}
