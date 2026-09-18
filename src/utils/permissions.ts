import { User } from '../types';

export function hasPermission(user: Pick<User, 'permissions'>, permission: string): boolean {
  const permissions = user.permissions || [];
  if (permission === '*') return permissions.includes('*');
  return permissions.includes('*') || permissions.includes(permission);
}

export function hasAnyPermission(
  user: Pick<User, 'permissions'>,
  permissions: string[],
): boolean {
  return permissions.some(permission => hasPermission(user, permission));
}
