import { User } from '../types';
import { apiFetch, clearSessionToken, setSessionToken } from './apiClient';

interface LoginApiResponse {
  id: number;
  username: string;
  role: User['role'];
  permissions?: string[];
  session_token: string;
  expires_at?: string;
}

export async function loginViaApi(username: string, password: string): Promise<User> {
  clearSessionToken();

  const response = await fetch('/api/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username: username.trim(), password }),
  });

  const payload = await response.json().catch(() => null);

  if (!response.ok) {
    throw new Error(typeof payload?.detail === 'string' ? payload.detail : 'Неверный логин или пароль');
  }

  if (!payload?.username || !payload?.role || !payload?.session_token) {
    throw new Error('Сервер вернул некорректные данные авторизации.');
  }

  const data = payload as LoginApiResponse;
  setSessionToken(data.session_token);

  return {
    id: Number(data.id || 0),
    username: data.username,
    role: data.role,
    permissions: data.permissions || [],
  };
}


export async function getCurrentUserViaApi(_username?: string): Promise<User> {
  const response = await apiFetch('/api/auth/me');
  const payload = await response.json().catch(() => null);

  if (!response.ok) {
    if (response.status === 401) clearSessionToken();
    throw new Error(typeof payload?.detail === 'string' ? payload.detail : 'Не удалось обновить права пользователя.');
  }
  if (!payload?.username || !payload?.role) {
    throw new Error('Сервер вернул некорректные данные пользователя.');
  }

  return {
    id: Number(payload.id || 0),
    username: String(payload.username),
    role: payload.role as User['role'],
    permissions: Array.isArray(payload.permissions) ? payload.permissions : [],
  };
}


export async function logoutViaApi(): Promise<void> {
  try {
    await apiFetch('/api/auth/logout', { method: 'POST' });
  } finally {
    clearSessionToken();
  }
}
