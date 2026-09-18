import { PermissionCatalog, PermissionOverrides, Role, User } from '../types';
import { apiFetch } from './apiClient';

const request = async (path: string, _username: string, init: RequestInit = {}) => {
  const response = await apiFetch(path, {
    ...init,
    headers: {
      ...(init.headers || {}),
      'Content-Type': 'application/json',
    },
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(typeof payload?.detail === 'string' ? payload.detail : 'Ошибка управления пользователями.');
  }
  return payload;
};

export async function getUsersViaApi(username: string): Promise<User[]> {
  return request('/api/admin/users', username);
}

export async function createUserViaApi(
  username: string,
  newUsername: string,
  password: string,
  role: User['role'],
): Promise<void> {
  await request('/api/admin/users', username, {
    method: 'POST',
    body: JSON.stringify({ username: newUsername, password, role }),
  });
}

export async function deleteUserViaApi(username: string, userId: number): Promise<void> {
  await request('/api/admin/users/' + userId, username, { method: 'DELETE' });
}


export async function getPermissionCatalogViaApi(username: string): Promise<PermissionCatalog> {
  return request('/api/admin/permissions', username);
}

export async function updateUserAccessViaApi(
  username: string,
  userId: number,
  role: Role,
  overrides: PermissionOverrides,
): Promise<User> {
  return request('/api/admin/users/' + userId + '/access', username, {
    method: 'PUT',
    body: JSON.stringify({
      role,
      allow: overrides.allow,
      deny: overrides.deny,
    }),
  });
}
