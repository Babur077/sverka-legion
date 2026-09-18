import { EposTerminal } from '../types';

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
    throw new Error(typeof payload?.detail === 'string' ? payload.detail : 'Ошибка серверного реестра EPOS.');
  }
  return payload;
};

export async function getEposViaApi(username: string): Promise<EposTerminal[]> {
  return apiRequest('/api/epos', username);
}

export async function createEposViaApi(username: string, terminal: EposTerminal): Promise<void> {
  await apiRequest('/api/epos', username, {
    method: 'POST',
    body: JSON.stringify(terminal),
  });
}

export async function updateEposViaApi(username: string, terminal: EposTerminal): Promise<void> {
  await apiRequest('/api/epos/' + encodeURIComponent(terminal.terminal_id), username, {
    method: 'PUT',
    body: JSON.stringify(terminal),
  });
}

export async function deleteEposViaApi(username: string, terminalId: string): Promise<void> {
  await apiRequest('/api/epos/' + encodeURIComponent(terminalId), username, {
    method: 'DELETE',
  });
}
