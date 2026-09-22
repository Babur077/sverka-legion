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

export async function getModuleArchiveSummary<T = Record<string, any>>(
  username: string,
  moduleId: string,
): Promise<T[]> {
  return apiRequest(
    '/api/modules/' + encodeURIComponent(moduleId) + '/archive?summary_only=true',
    username,
  );
}

export async function getModuleArchiveRecord<T = Record<string, any>>(
  username: string,
  moduleId: string,
  recordId: number,
): Promise<T> {
  return apiRequest(
    '/api/modules/' + encodeURIComponent(moduleId) + '/archive/' + recordId,
    username,
  );
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
  return getModuleArchiveSummary<ReconciliationArchive>(username, 'bank_rrn');
}

export async function getBankRrnArchiveRecord(
  username: string,
  id: number,
): Promise<ReconciliationArchive> {
  return getModuleArchiveRecord<ReconciliationArchive>(username, 'bank_rrn', id);
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
  _context?: {
    source_our_name?: string;
    source_bank_name?: string;
    config?: Record<string, any>;
  },
): Promise<string> {
  const excludedOurIndices: number[] = [];
  const excludedBankIndices: number[] = [];
  const reasonsOur: Record<string, string> = {};
  const reasonsBank: Record<string, string> = {};

  result.only_our.forEach((row, index) => {
    if (!row.checked) excludedOurIndices.push(index);
    if (row.reason) reasonsOur[String(index)] = String(row.reason);
  });
  result.only_bank.forEach((row, index) => {
    if (!row.checked) excludedBankIndices.push(index);
    if (row.reason) reasonsBank[String(index)] = String(row.reason);
  });

  const saved = await saveModuleArchive(username, 'bank_rrn', {
    run_id: result.run_id || null,
    bank_name: bankName,
    period_month: totals.period_month,
    assigned_terminal_id: totals.assigned_terminal_id || null,
    review: {
      excluded_our_indices: excludedOurIndices,
      excluded_bank_indices: excludedBankIndices,
      reasons_our: reasonsOur,
      reasons_bank: reasonsBank,
    },
  });
  return saved.message;
}

export async function deleteBankRrnArchive(username: string, id: number): Promise<void> {
  await deleteModuleArchive(username, 'bank_rrn', id);
}
