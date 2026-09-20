import { ReconciliationArchive, ReconciliationResult } from '../types';
import { apiFetch } from './apiClient';

const apiRequest = async (path: string, _username: string, init: RequestInit = {}) => {
  const response = await apiFetch(path, {
    ...init,
    headers: { ...(init.headers || {}), 'Content-Type': 'application/json' },
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(typeof payload?.detail === 'string' ? payload.detail : 'Ошибка серверного архива.');
  }
  return payload;
};

export async function getModuleArchive<T = Record<string, any>>(
  username: string,
  moduleId: string,
): Promise<T[]> {
  return apiRequest('/api/modules/' + encodeURIComponent(moduleId) + '/archive', username);
}

export async function saveModuleArchive(
  username: string,
  moduleId: string,
  payload: Record<string, any>,
): Promise<{ id?: number; message: string }> {
  const response = await apiRequest(
    '/api/modules/' + encodeURIComponent(moduleId) + '/archive',
    username,
    {
      method: 'POST',
      body: JSON.stringify(payload),
    },
  );

  return {
    id: response?.id == null ? undefined : Number(response.id),
    message: String(response?.message || 'Сверка сохранена в архив.'),
  };
}

export async function deleteModuleArchive(
  username: string,
  moduleId: string,
  id: number,
): Promise<void> {
  await apiRequest(
    '/api/modules/' + encodeURIComponent(moduleId) + '/archive/' + id,
    username,
    { method: 'DELETE' },
  );
}

export async function getBankRrnArchive(username: string): Promise<ReconciliationArchive[]> {
  return getModuleArchive<ReconciliationArchive>(username, 'bank_rrn');
}

export async function saveBankRrnArchive(
  username: string,
  bankName: string,
  result: ReconciliationResult,
  totals: {
    total_our: number;
    total_bank: number;
    difference: number;
    period_month?: string;
    only_our_count?: number;
    only_bank_count?: number;
    total_commission?: number;
    assigned_terminal_id?: string;
    terminals_summary?: ReconciliationResult['terminal_summary'];
  },
  context?: {
    source_our_name?: string;
    source_bank_name?: string;
    config?: Record<string, any>;
  },
): Promise<string> {
  const saved = await saveModuleArchive(username, 'bank_rrn', {
    bank_name: bankName,
    total_our: totals.total_our,
    total_bank: totals.total_bank,
    difference: totals.difference,
    matched_count: result.matched_count,
    mismatch_count: result.mismatch_count,
    only_our_count: totals.only_our_count ?? result.only_our.length,
    only_bank_count: totals.only_bank_count ?? result.only_bank.length,
    period_month: totals.period_month,
    total_commission: totals.total_commission ?? result.total_commission ?? 0,
    assigned_terminal_id: totals.assigned_terminal_id || null,
    terminals_summary: totals.terminals_summary ?? result.terminal_summary ?? [],
    run_id: result.run_id || null,
    source_our_name: context?.source_our_name || '',
    source_bank_name: context?.source_bank_name || '',
    config: context?.config || {},
    status: 'COMPLETED',
  });
  return saved.message;
}

export async function deleteBankRrnArchive(username: string, id: number): Promise<void> {
  await deleteModuleArchive(username, 'bank_rrn', id);
}
