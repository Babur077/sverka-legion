import { User } from '../types';

interface LoginApiResponse {
  id: number;
  username: string;
  role: User['role'];
  permissions?: string[];
}

export async function loginViaApi(username: string, password: string): Promise<User> {
  const response = await fetch('/api/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username: username.trim(), password }),
  });

  const payload = await response.json().catch(() => null);

  if (!response.ok) {
    throw new Error(typeof payload?.detail === 'string' ? payload.detail : 'Неверный логин или пароль');
  }

  if (!payload?.username || !payload?.role) {
    throw new Error('Сервер вернул некорректные данные авторизации.');
  }

  const data = payload as LoginApiResponse;
  return {
    id: Number((data as LoginApiResponse & { id?: number }).id || 0),
    username: data.username,
    role: data.role,
    permissions: data.permissions || [],
  };
}


export async function getCurrentUserViaApi(username: string): Promise<User> {
  const response = await fetch('/api/auth/me', {
    headers: { 'X-User': username },
  });
  const payload = await response.json().catch(() => null);

  if (!response.ok) {
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
