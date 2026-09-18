import { apiFetch } from './apiClient';

export const DEFAULT_BANKS = [
  'Aloqa Bank',
  'Kapitalbank',
  'Ipak Yuli',
  'NBU',
  'TBC Bank',
  'Agrobank',
  'Humo',
  'Uzcard',
];

export async function getBanksViaApi(): Promise<string[]> {
  const response = await apiFetch('/api/banks');
  const payload = await response.json().catch(() => null);

  if (!response.ok) {
    throw new Error(typeof payload?.detail === 'string' ? payload.detail : 'Не удалось загрузить список банков.');
  }

  if (!Array.isArray(payload)) return DEFAULT_BANKS;

  const banks = payload
    .map((item) => String(item || '').trim())
    .filter(Boolean);

  return Array.from(new Set([...DEFAULT_BANKS, ...banks]));
}
