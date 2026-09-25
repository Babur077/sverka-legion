import { apiFetch } from './apiClient';

export async function openVoronaSession(): Promise<string> {
  const response = await apiFetch('/api/vorona/session', { method: 'POST' });
  if (!response.ok) {
    let detail = 'Не удалось открыть Сверку Vorona.';
    try {
      const body = await response.json();
      detail = body?.detail || detail;
    } catch {}
    throw new Error(detail);
  }
  const body = await response.json();
  return String(body?.url || '/vorona/');
}
