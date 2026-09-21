import { AuditLog } from '../types';
import { apiFetch } from './apiClient';

export interface AuditEvent extends AuditLog {
  user_id: string;
  module_id?: string | null;
  object_type?: string | null;
  object_id?: string | null;
  status?: string;
  ip_address?: string | null;
  duration_ms?: number;
}

export interface AuditResponse {
  items: AuditEvent[];
  total: number;
  limit: number;
  offset: number;
}

export interface AuditFilters {
  limit: number;
  offset: number;
  user?: string;
  action?: string;
  module_id?: string;
  status?: string;
  search?: string;
  date_from?: string;
  date_to?: string;
}

export interface AuditFilterOptions {
  users: string[];
  actions: string[];
  modules: string[];
  statuses: string[];
}

export async function getAuditViaApi(_username: string, filters: AuditFilters): Promise<AuditResponse> {
  const params = new URLSearchParams();
  params.set('limit', String(filters.limit));
  params.set('offset', String(filters.offset));
  if (filters.user) params.set('user', filters.user);
  if (filters.action) params.set('action', filters.action);
  if (filters.module_id) params.set('module_id', filters.module_id);
  if (filters.status) params.set('status', filters.status);
  if (filters.search) params.set('search', filters.search);
  if (filters.date_from) params.set('date_from', filters.date_from);
  if (filters.date_to) params.set('date_to', filters.date_to);

  const response = await apiFetch('/api/audit?' + params.toString());
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(typeof payload?.detail === 'string' ? payload.detail : 'Не удалось загрузить журнал аудита.');
  }
  return payload;
}


export async function getAuditFilterOptionsViaApi(_username: string): Promise<AuditFilterOptions> {
  const response = await apiFetch('/api/audit/filters');
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(typeof payload?.detail === 'string' ? payload.detail : 'Не удалось загрузить фильтры аудита.');
  }
  return {
    users: Array.isArray(payload?.users) ? payload.users : [],
    actions: Array.isArray(payload?.actions) ? payload.actions : [],
    modules: Array.isArray(payload?.modules) ? payload.modules : [],
    statuses: Array.isArray(payload?.statuses) ? payload.statuses : [],
  };
}

export type AuditAiAttentionLevel = 'normal' | 'attention' | 'review';

export interface AuditAiResult {
  provider: 'openai' | 'local' | string;
  model?: string | null;
  attention_level: AuditAiAttentionLevel;
  attention_label: string;
  summary: string;
  explanation: string;
  checks: string[];
  warning?: string | null;
  disclaimer: string;
  privacy: string;
}

export async function analyzeAuditEventViaApi(
  _username: string,
  eventId: number,
): Promise<AuditAiResult> {
  const response = await apiFetch('/api/audit/' + eventId + '/ai', {
    method: 'POST',
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(
      typeof payload?.detail === 'string'
        ? payload.detail
        : 'Не удалось выполнить AI-анализ события.',
    );
  }
  return payload as AuditAiResult;
}
