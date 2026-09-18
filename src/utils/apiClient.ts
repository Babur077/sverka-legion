const SESSION_TOKEN_KEY = 'reconcile_session_token';

export function getSessionToken(): string {
  try {
    return sessionStorage.getItem(SESSION_TOKEN_KEY) || '';
  } catch {
    return '';
  }
}

export function setSessionToken(token: string): void {
  try {
    if (token) sessionStorage.setItem(SESSION_TOKEN_KEY, token);
    else sessionStorage.removeItem(SESSION_TOKEN_KEY);
  } catch {}
}

export function clearSessionToken(): void {
  setSessionToken('');
}

export async function apiFetch(input: RequestInfo | URL, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers || {});
  const token = getSessionToken();
  if (token) headers.set('Authorization', 'Bearer ' + token);

  return fetch(input, {
    ...init,
    headers,
  });
}
