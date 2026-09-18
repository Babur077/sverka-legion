import { SystemSettings } from '../types';

const apiRequest = async (path: string, username: string, init: RequestInit = {}) => {
  const response = await fetch(path, {
    ...init,
    headers: {
      ...(init.headers || {}),
      'X-User': username,
      'Content-Type': 'application/json',
    },
  });

  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(typeof payload?.detail === 'string' ? payload.detail : 'Ошибка серверных настроек.');
  }
  return payload;
};

export async function getSettingsViaApi(username: string): Promise<SystemSettings> {
  return apiRequest('/api/settings', username);
}

export async function saveSettingsViaApi(
  username: string,
  settings: SystemSettings,
): Promise<void> {
  await apiRequest('/api/settings', username, {
    method: 'PUT',
    body: JSON.stringify(settings),
  });
}
