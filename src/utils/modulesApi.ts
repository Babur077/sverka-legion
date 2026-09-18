import { ReconciliationModuleManifest } from '../types';

async function readResponse(response: Response): Promise<any> {
  const raw = await response.text();
  let payload: any = null;
  try { payload = raw ? JSON.parse(raw) : null; } catch {}

  if (!response.ok) {
    const detail = payload?.detail;
    throw new Error(
      typeof detail === 'string'
        ? detail
        : raw || `Не удалось загрузить модули (HTTP ${response.status})`,
    );
  }

  return payload;
}

export async function getModulesViaApi(username: string): Promise<ReconciliationModuleManifest[]> {
  const response = await fetch('/api/modules', {
    headers: { 'X-User': username },
  });
  const payload = await readResponse(response);
  return Array.isArray(payload) ? payload : [];
}
