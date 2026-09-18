import { ReconciliationArchive, ReconciliationResult } from '../types';

const apiRequest = async (path: string, username: string, init: RequestInit = {}) => {
  const response = await fetch(path, {
    ...init,
    headers: { ...(init.headers || {}), 'X-User': username, 'Content-Type': 'application/json' },
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(typeof payload?.detail === 'string' ? payload.detail : 'Ошибка серверного архива.');
  }
  return payload;
};

export async function getBankRrnArchive(username: string): Promise<ReconciliationArchive[]> {
  return apiRequest('/api/modules/bank_rrn/archive', username);
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
    terminals_summary?: ReconciliationResult['terminal_summary'];
  },
): Promise<void> {
  await apiRequest('/api/modules/bank_rrn/archive', username, {
    method: 'POST',
    body: JSON.stringify({
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
      terminals_summary: totals.terminals_summary ?? result.terminal_summary ?? [],
    }),
  });
}

export async function deleteBankRrnArchive(username: string, id: number): Promise<void> {
  await apiRequest('/api/modules/bank_rrn/archive/' + id, username, { method: 'DELETE' });
}
