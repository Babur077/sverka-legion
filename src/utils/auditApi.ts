import { AuditLog } from '../types';

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

export async function getAuditViaApi(username: string, filters: AuditFilters): Promise<AuditResponse> {
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

  const response = await fetch('/api/audit?' + params.toString(), {
    headers: { 'X-User': username },
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(typeof payload?.detail === 'string' ? payload.detail : 'Не удалось загрузить журнал аудита.');
  }
  return payload;
}


export async function getAuditFilterOptionsViaApi(username: string): Promise<AuditFilterOptions> {
  const response = await fetch('/api/audit/filters', {
    headers: { 'X-User': username },
  });
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
