import React, { useEffect, useMemo, useState } from 'react';
import {
  AlertCircle,
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  CheckCircle,
  KeyRound,
  Save,
  Settings as SettingsIcon,
  Shield,
  Trash2,
  UserPlus,
  Users,
  X,
} from 'lucide-react';
import {
  PermissionCatalog,
  PermissionOverrides,
  Role,
  SystemSettings,
  User,
} from '../types';
import { saveSettingsViaApi } from '../utils/settingsApi';
import {
  createUserViaApi,
  deleteUserViaApi,
  getPermissionCatalogViaApi,
  getUsersViaApi,
  updateUserAccessViaApi,
} from '../utils/adminUsersApi';
import { AlertModal, ConfirmModal } from './Modal';

interface AdminPageProps {
  user: User;
  settings: SystemSettings;
  onUpdateSettings: (newSettings: SystemSettings) => void;
}

const ROLE_LABELS: Record<string, string> = {
  admin: 'Администратор',
  finance_manager: 'Финансовый менеджер',
  accountant_acquiring: 'Бухгалтер эквайринга',
  auditor: 'Аудитор',
  accountant: 'Бухгалтер (legacy)',
};

const CANONICAL_ROLES: Role[] = [
  'finance_manager',
  'accountant_acquiring',
  'auditor',
  'admin',
];

const emptyOverrides = (): PermissionOverrides => ({ allow: [], deny: [] });

export const AdminPage: React.FC<AdminPageProps> = ({ user, settings, onUpdateSettings }) => {
  const [users, setUsers] = useState<User[]>([]);
  const [permissionCatalog, setPermissionCatalog] = useState<PermissionCatalog | null>(null);
  const [usersLoading, setUsersLoading] = useState(true);
  const [usersError, setUsersError] = useState<string | null>(null);

  const [newUsername, setNewUsername] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [newRole, setNewRole] = useState<Role>('accountant_acquiring');
  const [userMsg, setUserMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  const [selectedAccessUserId, setSelectedAccessUserId] = useState<number | null>(null);
  const [accessRole, setAccessRole] = useState<Role>('auditor');
  const [accessOverrides, setAccessOverrides] = useState<PermissionOverrides>(emptyOverrides);
  const [accessSaving, setAccessSaving] = useState(false);

  const [tolerance, setTolerance] = useState<number>(settings.amount_tolerance);
  const [currency, setCurrency] = useState<string>(settings.currency);
  const [settingsSaved, setSettingsSaved] = useState(false);

  const [sortField, setSortField] = useState<'username' | 'role'>('username');
  const [sortAsc, setSortAsc] = useState(true);

  const [alertState, setAlertState] = useState<{
    isOpen: boolean;
    title: string;
    message: string;
    type?: 'info' | 'warning' | 'error' | 'success';
  }>({ isOpen: false, title: '', message: '' });

  const [confirmState, setConfirmState] = useState<{
    isOpen: boolean;
    title: string;
    message: string;
    onConfirm: () => void;
  }>({ isOpen: false, title: '', message: '', onConfirm: () => {} });

  const refreshUsers = async () => {
    setUsersLoading(true);
    setUsersError(null);
    try {
      const [loadedUsers, catalog] = await Promise.all([
        getUsersViaApi(user.username),
        getPermissionCatalogViaApi(user.username),
      ]);
      setUsers(loadedUsers);
      setPermissionCatalog(catalog);
    } catch (error: any) {
      setUsersError(error?.message || 'Не удалось загрузить пользователей и права.');
    } finally {
      setUsersLoading(false);
    }
  };

  useEffect(() => {
    void refreshUsers();
  }, [user.username]);

  const selectedAccessUser = useMemo(
    () => users.find(item => item.id === selectedAccessUserId) || null,
    [users, selectedAccessUserId],
  );

  const roleBasePermissions = useMemo(
    () => new Set(permissionCatalog?.roles?.[accessRole] || []),
    [permissionCatalog, accessRole],
  );

  const sortedUsers = useMemo(() => {
    return [...users].sort((a, b) => {
      const valA = String(a[sortField] || '');
      const valB = String(b[sortField] || '');
      const cmp = valA.localeCompare(valB);
      return sortAsc ? cmp : -cmp;
    });
  }, [users, sortField, sortAsc]);

  const toggleSort = (field: 'username' | 'role') => {
    if (sortField === field) {
      setSortAsc(prev => !prev);
    } else {
      setSortField(field);
      setSortAsc(true);
    }
  };

  const openAccessEditor = (target: User) => {
    setSelectedAccessUserId(target.id);
    setAccessRole(target.role === 'accountant' ? 'accountant_acquiring' : target.role);
    setAccessOverrides({
      allow: [...(target.permission_overrides?.allow || [])],
      deny: [...(target.permission_overrides?.deny || [])],
    });
    setUserMsg(null);
  };

  const isPermissionEnabled = (permission: string) => {
    if (accessRole === 'admin') return true;
    if (accessOverrides.deny.includes(permission)) return false;
    return roleBasePermissions.has(permission) || accessOverrides.allow.includes(permission);
  };

  const togglePermission = (permission: string) => {
    if (accessRole === 'admin' || selectedAccessUser?.username === 'admin') return;

    const currentlyEnabled = isPermissionEnabled(permission);
    const comesFromRole = roleBasePermissions.has(permission);

    setAccessOverrides(current => {
      const allow = new Set(current.allow);
      const deny = new Set(current.deny);

      if (currentlyEnabled) {
        allow.delete(permission);
        if (comesFromRole) deny.add(permission);
        else deny.delete(permission);
      } else {
        deny.delete(permission);
        if (!comesFromRole) allow.add(permission);
      }

      return { allow: [...allow], deny: [...deny] };
    });
  };

  const handleSaveAccess = async () => {
    if (!selectedAccessUser) return;
    setAccessSaving(true);
    setUserMsg(null);
    try {
      const updated = await updateUserAccessViaApi(
        user.username,
        selectedAccessUser.id,
        accessRole,
        accessOverrides,
      );
      setUsers(current => current.map(item => item.id === updated.id ? updated : item));
      setAccessOverrides(updated.permission_overrides || emptyOverrides());
      setAccessRole(updated.role);
      setUserMsg({ type: 'success', text: `Доступ пользователя «${updated.username}» обновлён.` });
    } catch (error: any) {
      setUserMsg({ type: 'error', text: error?.message || 'Не удалось обновить права пользователя.' });
    } finally {
      setAccessSaving(false);
    }
  };

  const handleCreateUser = async (event: React.FormEvent) => {
    event.preventDefault();
    setUserMsg(null);
    try {
      await createUserViaApi(user.username, newUsername, newPassword, newRole);
      await refreshUsers();
      setUserMsg({ type: 'success', text: 'Пользователь успешно создан. Права можно настроить справа в списке.' });
      setNewUsername('');
      setNewPassword('');
    } catch (error: any) {
      setUserMsg({ type: 'error', text: error?.message || 'Не удалось создать пользователя.' });
    }
  };

  const handleDeleteUser = (id: number, username: string) => {
    if (username === 'admin') {
      setAlertState({
        isOpen: true,
        title: 'Действие запрещено',
        message: 'Нельзя удалить главного администратора системы (admin).',
        type: 'warning',
      });
      return;
    }

    setConfirmState({
      isOpen: true,
      title: 'Удаление пользователя',
      message: `Вы действительно хотите безвозвратно удалить учётную запись «${username}»?`,
      onConfirm: async () => {
        try {
          await deleteUserViaApi(user.username, id);
          if (selectedAccessUserId === id) setSelectedAccessUserId(null);
          await refreshUsers();
        } catch (error: any) {
          setUserMsg({ type: 'error', text: error?.message || 'Не удалось удалить пользователя.' });
        }
      },
    });
  };

  const handleSaveSettings = async (event: React.FormEvent) => {
    event.preventDefault();
    const newSettings: SystemSettings = {
      ...settings,
      amount_tolerance: tolerance,
      currency,
    };

    try {
      await saveSettingsViaApi(user.username, newSettings);
      onUpdateSettings(newSettings);
      setSettingsSaved(true);
      setTimeout(() => setSettingsSaved(false), 3000);
    } catch (error: any) {
      setAlertState({
        isOpen: true,
        title: 'Не удалось сохранить настройки',
        message: error?.message || 'Сервер не принял изменения системных параметров.',
        type: 'error',
      });
    }
  };

  return (
    <div className="p-8 max-w-[1800px] mx-auto space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-slate-900 tracking-tight">Администрирование и безопасность</h1>
        <p className="text-sm text-slate-500 mt-1">
          Роль задаёт базовый шаблон доступа, а индивидуальные разрешения позволяют подключать новые сверки без создания новой роли.
        </p>
      </div>

      {userMsg && (
        <div className={`p-3 rounded-xl text-xs flex items-center gap-2 ${
          userMsg.type === 'success'
            ? 'bg-emerald-50 text-emerald-800 border border-emerald-200'
            : 'bg-rose-50 text-rose-800 border border-rose-200'
        }`}>
          {userMsg.type === 'success'
            ? <CheckCircle className="w-4 h-4 text-emerald-600 shrink-0" />
            : <AlertCircle className="w-4 h-4 text-rose-600 shrink-0" />}
          <span>{userMsg.text}</span>
        </div>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-[320px_minmax(0,1fr)] gap-6">
        <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-xs h-fit">
          <h2 className="text-sm font-bold text-slate-900 mb-4 flex items-center gap-2">
            <UserPlus className="w-4 h-4 text-indigo-600" />
            Создать пользователя
          </h2>

          <form onSubmit={handleCreateUser} className="space-y-3.5 text-xs">
            <div>
              <label className="block font-semibold text-slate-700 mb-1">Логин*</label>
              <input
                id="admin-new-user"
                type="text"
                value={newUsername}
                onChange={event => setNewUsername(event.target.value)}
                placeholder="напр. ivan_bukh"
                className="w-full py-2 px-3 border border-slate-200 rounded-lg text-xs focus:ring-1 focus:ring-indigo-500"
                required
              />
            </div>

            <div>
              <label className="block font-semibold text-slate-700 mb-1">Пароль*</label>
              <input
                id="admin-new-password"
                type="password"
                value={newPassword}
                onChange={event => setNewPassword(event.target.value)}
                placeholder="••••••••"
                className="w-full py-2 px-3 border border-slate-200 rounded-lg text-xs focus:ring-1 focus:ring-indigo-500"
                required
              />
            </div>

            <div>
              <label className="block font-semibold text-slate-700 mb-1">Базовая роль*</label>
              <select
                id="admin-new-role"
                value={newRole}
                onChange={event => setNewRole(event.target.value as Role)}
                className="w-full py-2 px-3 border border-slate-200 rounded-lg text-xs focus:ring-1 focus:ring-indigo-500"
              >
                {CANONICAL_ROLES.map(role => (
                  <option key={role} value={role}>{ROLE_LABELS[role]}</option>
                ))}
              </select>
            </div>

            <p className="text-[11px] leading-relaxed text-slate-400">
              После создания можно добавить или убрать конкретные права независимо от базовой роли.
            </p>

            <button
              id="admin-create-user-btn"
              type="submit"
              className="w-full mt-2 py-2.5 px-4 bg-indigo-600 hover:bg-indigo-700 text-white font-semibold rounded-lg shadow-xs transition-colors"
            >
              Добавить пользователя
            </button>
          </form>
        </div>

        <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-xs space-y-4 min-w-0">
          <div className="flex items-center justify-between gap-3">
            <h2 className="text-sm font-bold text-slate-900 flex items-center gap-2">
              <Users className="w-4 h-4 text-indigo-600" />
              Учётные записи системы ({users.length})
            </h2>
            <div className="text-[11px] text-slate-400">Backend остаётся источником истины по доступу</div>
          </div>

          <div className="overflow-x-auto rounded-xl border border-slate-200 text-xs">
            <table className="min-w-full divide-y divide-slate-200">
              <thead className="bg-slate-50 font-bold text-slate-700">
                <tr>
                  <th onClick={() => toggleSort('username')} className="px-3 py-2.5 text-left cursor-pointer hover:bg-slate-100">
                    <div className="flex items-center gap-1.5">
                      Логин
                      {sortField === 'username'
                        ? (sortAsc ? <ArrowUp className="w-3.5 h-3.5 text-indigo-600" /> : <ArrowDown className="w-3.5 h-3.5 text-indigo-600" />)
                        : <ArrowUpDown className="w-3.5 h-3.5 text-slate-400" />}
                    </div>
                  </th>
                  <th onClick={() => toggleSort('role')} className="px-3 py-2.5 text-left cursor-pointer hover:bg-slate-100">
                    <div className="flex items-center gap-1.5">
                      Роль
                      {sortField === 'role'
                        ? (sortAsc ? <ArrowUp className="w-3.5 h-3.5 text-indigo-600" /> : <ArrowDown className="w-3.5 h-3.5 text-indigo-600" />)
                        : <ArrowUpDown className="w-3.5 h-3.5 text-slate-400" />}
                    </div>
                  </th>
                  <th className="px-3 py-2.5 text-left">Эффективный доступ</th>
                  <th className="px-3 py-2.5 text-right">Действия</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 bg-white">
                {usersLoading ? (
                  <tr><td colSpan={4} className="px-3 py-8 text-center text-slate-400">Загрузка пользователей…</td></tr>
                ) : usersError ? (
                  <tr><td colSpan={4} className="px-3 py-8 text-center text-rose-600">{usersError}</td></tr>
                ) : sortedUsers.map(target => {
                  const overrideCount = (target.permission_overrides?.allow.length || 0) + (target.permission_overrides?.deny.length || 0);
                  return (
                    <tr key={target.id} className={selectedAccessUserId === target.id ? 'bg-indigo-50/40' : 'hover:bg-slate-50'}>
                      <td className="px-3 py-2.5 font-bold text-slate-900">{target.username}</td>
                      <td className="px-3 py-2.5">
                        <span className={`px-2 py-0.5 rounded-full text-[10px] font-semibold border ${
                          target.role === 'admin'
                            ? 'bg-indigo-50 text-indigo-700 border-indigo-200'
                            : target.role === 'auditor'
                              ? 'bg-amber-50 text-amber-700 border-amber-200'
                              : 'bg-emerald-50 text-emerald-700 border-emerald-200'
                        }`}>
                          {ROLE_LABELS[target.role] || target.role}
                        </span>
                      </td>
                      <td className="px-3 py-2.5 text-slate-600">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span>{target.permissions?.includes('*') ? 'Полный доступ' : `${target.permissions?.length || 0} разрешений`}</span>
                          {overrideCount > 0 && (
                            <span className="px-1.5 py-0.5 rounded bg-slate-100 text-[10px] text-slate-500">
                              {overrideCount} индивидуальных
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="px-3 py-2.5 text-right whitespace-nowrap">
                        <button
                          onClick={() => openAccessEditor(target)}
                          className="p-1.5 text-slate-400 hover:text-indigo-600 transition-colors"
                          title="Настроить доступ"
                        >
                          <KeyRound className="w-4 h-4" />
                        </button>
                        {target.username !== 'admin' && (
                          <button
                            onClick={() => handleDeleteUser(target.id, target.username)}
                            className="p-1.5 text-slate-400 hover:text-rose-600 transition-colors"
                            title="Удалить"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {selectedAccessUser && permissionCatalog && (
            <div className="rounded-2xl border border-indigo-200 bg-indigo-50/20 overflow-hidden">
              <div className="px-5 py-4 bg-white border-b border-indigo-100 flex flex-col md:flex-row md:items-center justify-between gap-3">
                <div>
                  <div className="text-sm font-bold text-slate-900 flex items-center gap-2">
                    <Shield className="w-4 h-4 text-indigo-600" />
                    Доступ: {selectedAccessUser.username}
                  </div>
                  <div className="text-[11px] text-slate-500 mt-1">
                    Галочка показывает итоговый доступ после роли и индивидуальных allow/deny.
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => setSelectedAccessUserId(null)}
                  className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100 self-end md:self-auto"
                  title="Закрыть"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>

              <div className="p-5 space-y-5">
                <div className="grid grid-cols-1 md:grid-cols-[280px_minmax(0,1fr)] gap-4 items-start">
                  <div>
                    <label className="block text-xs font-semibold text-slate-700 mb-1.5">Базовая роль</label>
                    <select
                      value={accessRole}
                      disabled={selectedAccessUser.username === 'admin'}
                      onChange={event => setAccessRole(event.target.value as Role)}
                      className="w-full border border-slate-200 bg-white rounded-lg px-3 py-2 text-xs disabled:bg-slate-100 disabled:text-slate-500"
                    >
                      {CANONICAL_ROLES.map(role => (
                        <option key={role} value={role}>{ROLE_LABELS[role]}</option>
                      ))}
                    </select>
                  </div>
                  <div className="rounded-xl border border-slate-200 bg-white px-4 py-3 text-xs text-slate-600">
                    {accessRole === 'admin'
                      ? 'Роль admin всегда даёт полный доступ (*). Индивидуальные ограничения к ней не применяются.'
                      : 'Чтобы отозвать право, которое пришло из роли, снимите галочку. Чтобы добавить право новой сверки — включите его. Изменения сохраняются только после кнопки «Сохранить доступ».'}
                  </div>
                </div>

                <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
                  {permissionCatalog.groups.map(group => (
                    <div key={group.id} className="rounded-xl border border-slate-200 bg-white p-4">
                      <div className="flex items-center justify-between gap-2 mb-3">
                        <div>
                          <div className="text-xs font-bold text-slate-900">{group.name}</div>
                          <div className="text-[10px] uppercase tracking-wider text-slate-400 mt-0.5">
                            {group.type === 'module' ? 'Модуль сверки' : 'Платформа'}
                          </div>
                        </div>
                        {group.status && group.status !== 'active' && (
                          <span className="text-[10px] px-2 py-0.5 rounded-full bg-amber-50 text-amber-700 border border-amber-200">
                            {group.status}
                          </span>
                        )}
                      </div>

                      <div className="space-y-2">
                        {group.permissions.map(permission => {
                          const enabled = isPermissionEnabled(permission.id);
                          const denied = accessOverrides.deny.includes(permission.id);
                          const manuallyAllowed = accessOverrides.allow.includes(permission.id);
                          const fromRole = roleBasePermissions.has(permission.id);

                          return (
                            <label
                              key={permission.id}
                              className={`flex items-start gap-3 rounded-lg border px-3 py-2.5 ${
                                enabled ? 'border-indigo-200 bg-indigo-50/40' : 'border-slate-200 bg-slate-50/40'
                              } ${accessRole === 'admin' || selectedAccessUser.username === 'admin' ? 'cursor-default' : 'cursor-pointer'}`}
                            >
                              <input
                                type="checkbox"
                                checked={enabled}
                                disabled={accessRole === 'admin' || selectedAccessUser.username === 'admin'}
                                onChange={() => togglePermission(permission.id)}
                                className="mt-0.5 rounded text-indigo-600"
                              />
                              <div className="min-w-0 flex-1">
                                <div className="text-xs font-semibold text-slate-800">{permission.label}</div>
                                <div className="font-mono text-[10px] text-slate-400 mt-0.5">{permission.id}</div>
                              </div>
                              <span className={`text-[10px] whitespace-nowrap ${
                                denied
                                  ? 'text-rose-600'
                                  : manuallyAllowed && !fromRole
                                    ? 'text-indigo-600'
                                    : fromRole || accessRole === 'admin'
                                      ? 'text-emerald-600'
                                      : 'text-slate-400'
                              }`}>
                                {denied
                                  ? 'Запрещено'
                                  : manuallyAllowed && !fromRole
                                    ? 'Добавлено'
                                    : fromRole || accessRole === 'admin'
                                      ? 'Из роли'
                                      : 'Нет доступа'}
                              </span>
                            </label>
                          );
                        })}
                      </div>
                    </div>
                  ))}
                </div>

                <div className="flex items-center justify-between gap-3 border-t border-indigo-100 pt-4">
                  <div className="text-[11px] text-slate-500">
                    Allow: {accessOverrides.allow.length} · Deny: {accessOverrides.deny.length}
                  </div>
                  <button
                    type="button"
                    onClick={() => void handleSaveAccess()}
                    disabled={accessSaving || selectedAccessUser.username === 'admin'}
                    className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-700 disabled:bg-slate-300 text-white text-xs font-semibold"
                  >
                    <Save className="w-3.5 h-3.5" />
                    {accessSaving ? 'Сохранение…' : 'Сохранить доступ'}
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-xs space-y-4">
        <div className="flex items-center justify-between border-b border-slate-100 pb-3">
          <h2 className="text-sm font-bold text-slate-900 flex items-center gap-2">
            <SettingsIcon className="w-4 h-4 text-indigo-600" />
            Глобальные параметры сверки
          </h2>
          {settingsSaved && (
            <span className="text-xs font-semibold text-emerald-600 flex items-center gap-1">
              <CheckCircle className="w-3.5 h-3.5" />
              Параметры сохранены
            </span>
          )}
        </div>

        <form onSubmit={handleSaveSettings} className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs">
          <div>
            <label className="block font-semibold text-slate-700 mb-1">Допустимая погрешность расхождений</label>
            <input
              type="number"
              step="0.01"
              min="0"
              value={tolerance}
              onChange={event => setTolerance(parseFloat(event.target.value) || 0)}
              className="w-full py-2 px-3 border border-slate-200 rounded-lg text-xs font-semibold"
            />
          </div>

          <div>
            <label className="block font-semibold text-slate-700 mb-1">Основная расчётная валюта</label>
            <select
              value={currency}
              onChange={event => setCurrency(event.target.value)}
              className="w-full py-2 px-3 border border-slate-200 rounded-lg text-xs font-semibold"
            >
              <option value="UZS">UZS (Узбекский сум)</option>
              <option value="USD">USD ($ Доллар США)</option>
              <option value="RUB">RUB (₽ Российский рубль)</option>
              <option value="EUR">EUR (€ Евро)</option>
            </select>
          </div>

          <div className="flex items-end">
            <button
              id="admin-save-settings-btn"
              type="submit"
              className="w-full py-2.5 px-4 bg-slate-900 hover:bg-slate-800 text-white font-semibold rounded-lg shadow-xs transition-colors"
            >
              Сохранить параметры
            </button>
          </div>
        </form>
      </div>

      <ConfirmModal
        isOpen={confirmState.isOpen}
        title={confirmState.title}
        message={confirmState.message}
        confirmText="Удалить"
        isDanger={true}
        onConfirm={confirmState.onConfirm}
        onClose={() => setConfirmState(prev => ({ ...prev, isOpen: false }))}
      />

      <AlertModal
        isOpen={alertState.isOpen}
        title={alertState.title}
        message={alertState.message}
        type={alertState.type}
        onClose={() => setAlertState(prev => ({ ...prev, isOpen: false }))}
      />
    </div>
  );
};
