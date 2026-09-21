import { ReconciliationResult } from '../types';
import { apiFetch } from './apiClient';

export type BankAiConfidence = 'low' | 'medium' | 'high';

export interface BankAiInsight {
  kind: string;
  title: string;
  explanation: string;
  confidence: BankAiConfidence;
  confidence_label: string;
  evidence: string[];
}

export interface BankAiSummary {
  provider: 'openai' | 'local' | string;
  model?: string | null;
  executive_summary: string;
  insights: BankAiInsight[];
  context: {
    bank_name: string;
    currency: string;
    summary: {
      matched_count: number;
      discrepancy_count: number;
      match_percentage: number;
      total_our: number;
      total_bank: number;
      difference_bank_minus_our: number;
    };
    unmatched: {
      only_our: { count: number; amount: number };
      only_bank: { count: number; amount: number };
    };
    [key: string]: any;
  };
  warning?: string | null;
  disclaimer: string;
  privacy: string;
}

interface AnalyzeBankRrnPayload {
  bank_name: string;
  currency: string;
  result: ReconciliationResult;
  adjusted: {
    total_our: number;
    total_bank: number;
    difference: number;
    active_only_our_count: number;
    active_only_bank_count: number;
  };
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

export async function analyzeBankRrnWithAi(
  payload: AnalyzeBankRrnPayload,
): Promise<BankAiSummary> {
  const response = await apiFetch('/api/modules/bank_rrn/ai/summary', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });

  return readJson(response) as Promise<BankAiSummary>;
}
