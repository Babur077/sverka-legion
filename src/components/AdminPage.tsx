import React, { useState, useMemo, useEffect } from 'react';
import { Shield, UserPlus, Users, Settings as SettingsIcon, History, Trash2, CheckCircle, AlertCircle, ArrowUpDown, ArrowUp, ArrowDown } from 'lucide-react';
import { User, AuditLog, SystemSettings } from '../types';
import { getAuditLogs } from '../utils/storage';
import { saveSettingsViaApi } from '../utils/settingsApi';
import { getUsersViaApi, createUserViaApi, deleteUserViaApi } from '../utils/adminUsersApi';
import { ConfirmModal, AlertModal } from './Modal';

interface AdminPageProps {
  user: User;
  settings: SystemSettings;
  onUpdateSettings: (newSettings: SystemSettings) => void;
}

export const AdminPage: React.FC<AdminPageProps> = ({ user, settings, onUpdateSettings }) => {
  const [users, setUsers] = useState<User[]>([]);
  const [usersLoading, setUsersLoading] = useState(true);
  const [usersError, setUsersError] = useState<string | null>(null);
  const [auditLogs, setAuditLogs] = useState<AuditLog[]>(getAuditLogs());

  // Add User Form
  const [newUsername, setNewUsername] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [newRole, setNewRole] = useState<'admin' | 'accountant' | 'auditor'>('accountant');
  const [userMsg, setUserMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  // Settings state
  const [tolerance, setTolerance] = useState<number>(settings.amount_tolerance);
  const [currency, setCurrency] = useState<string>(settings.currency);
  const [settingsSaved, setSettingsSaved] = useState(false);

  // Sorting state for users
  const [sortField, setSortField] = useState<'username' | 'role'>('username');
  const [sortAsc, setSortAsc] = useState<boolean>(true);

  // Custom modal states
  const [alertState, setAlertState] = useState<{ isOpen: boolean; title: string; message: string; type?: 'info' | 'warning' | 'error' | 'success' }>({
    isOpen: false,
    title: '',
    message: '',
  });

  const [confirmState, setConfirmState] = useState<{
    isOpen: boolean;
    title: string;
    message: string;
    onConfirm: () => void;
  }>({
    isOpen: false,
    title: '',
    message: '',
    onConfirm: () => {},
  });

  const refreshUsers = async () => {
    setUsersLoading(true);
    setUsersError(null);
    try {
      setUsers(await getUsersViaApi(user.username));
    } catch (error: any) {
      setUsersError(error?.message || 'Не удалось загрузить пользователей.');
    } finally {
      setUsersLoading(false);
    }
  };

  useEffect(() => {
    refreshUsers();
  }, [user.username]);

  const handleCreateUser = async (e: React.FormEvent) => {
    e.preventDefault();
    setUserMsg(null);
    try {
      await createUserViaApi(user.username, newUsername, newPassword, newRole);
      await refreshUsers();
      setUserMsg({ type: 'success', text: 'Пользователь успешно создан!' });
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
        message: 'Нельзя удалить главного администратора системы (admin)!',
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
          await refreshUsers();
        } catch (error: any) {
          setUserMsg({ type: 'error', text: error?.message || 'Не удалось удалить пользователя.' });
        }
      },
    });
  };

  const sortedUsers = useMemo(() => {
    return [...users].sort((a, b) => {
      const valA = a[sortField] || '';
      const valB = b[sortField] || '';
      const cmp = valA.localeCompare(valB);
      return sortAsc ? cmp : -cmp;
    });
  }, [users, sortField, sortAsc]);

  const toggleSort = (field: 'username' | 'role') => {
    if (sortField === field) {
      setSortAsc(!sortAsc);
    } else {
      setSortField(field);
      setSortAsc(true);
    }
  };

  const handleSaveSettings = async (e: React.FormEvent) => {
    e.preventDefault();
    const newSettings: SystemSettings = {
      ...settings,
      amount_tolerance: tolerance,
      currency: currency,
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
    <div className="p-8 max-w-7xl mx-auto space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-slate-900 tracking-tight flex items-center gap-2">
          <span>Администрирование и безопасность</span>
        </h1>
        <p className="text-sm text-slate-500 mt-1">
          Управление доступом пользователей (RBAC), системные параметры и аудит событий.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Create User Form */}
        <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-xs h-fit">
          <h2 className="text-sm font-bold text-slate-900 mb-4 flex items-center gap-2">
            <UserPlus className="w-4 h-4 text-indigo-600" />
            <span>Создать пользователя</span>
          </h2>

          {userMsg && (
            <div className={`mb-4 p-3 rounded-lg text-xs flex items-center gap-2 ${userMsg.type === 'success' ? 'bg-emerald-50 text-emerald-800 border border-emerald-200' : 'bg-rose-50 text-rose-800 border border-rose-200'}`}>
              {userMsg.type === 'success' ? <CheckCircle className="w-4 h-4 text-emerald-600 shrink-0" /> : <AlertCircle className="w-4 h-4 text-rose-600 shrink-0" />}
              <span>{userMsg.text}</span>
            </div>
          )}

          <form onSubmit={handleCreateUser} className="space-y-3.5 text-xs">
            <div>
              <label className="block font-semibold text-slate-700 mb-1">Логин*</label>
              <input
                id="admin-new-user"
                type="text"
                value={newUsername}
                onChange={(e) => setNewUsername(e.target.value)}
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
                onChange={(e) => setNewPassword(e.target.value)}
                placeholder="••••••••"
                className="w-full py-2 px-3 border border-slate-200 rounded-lg text-xs focus:ring-1 focus:ring-indigo-500"
                required
              />
            </div>

            <div>
              <label className="block font-semibold text-slate-700 mb-1">Роль доступа (RBAC)*</label>
              <select
                id="admin-new-role"
                value={newRole}
                onChange={(e) => setNewRole(e.target.value as any)}
                className="w-full py-2 px-3 border border-slate-200 rounded-lg text-xs focus:ring-1 focus:ring-indigo-500"
              >
                <option value="accountant">Бухгалтер (Сверка + Аналитика)</option>
                <option value="auditor">Аудитор (Только просмотр)</option>
                <option value="admin">Администратор (Полный доступ)</option>
              </select>
            </div>

            <button
              id="admin-create-user-btn"
              type="submit"
              className="w-full mt-2 py-2.5 px-4 bg-indigo-600 hover:bg-indigo-700 text-white font-semibold rounded-lg shadow-xs transition-colors cursor-pointer"
            >
              Добавить пользователя
            </button>
          </form>
        </div>

        {/* Users List */}
        <div className="lg:col-span-2 bg-white rounded-2xl border border-slate-200 p-6 shadow-xs space-y-4">
          <h2 className="text-sm font-bold text-slate-900 flex items-center gap-2">
            <Users className="w-4 h-4 text-indigo-600" />
            <span>Учётные записи системы ({users.length})</span>
          </h2>

          <div className="overflow-x-auto rounded-xl border border-slate-200 text-xs">
            <table className="min-w-full divide-y divide-slate-200">
              <thead className="bg-slate-50 font-bold text-slate-700">
                <tr>
                  <th 
                    onClick={() => toggleSort('username')}
                    className="px-3 py-2.5 text-left cursor-pointer hover:bg-slate-100 transition-colors select-none"
                  >
                    <div className="flex items-center gap-1.5">
                      <span>Логин</span>
                      {sortField === 'username' ? (
                        sortAsc ? <ArrowUp className="w-3.5 h-3.5 text-indigo-600" /> : <ArrowDown className="w-3.5 h-3.5 text-indigo-600" />
                      ) : (
                        <ArrowUpDown className="w-3.5 h-3.5 text-slate-400" />
                      )}
                    </div>
                  </th>
                  <th 
                    onClick={() => toggleSort('role')}
                    className="px-3 py-2.5 text-left cursor-pointer hover:bg-slate-100 transition-colors select-none"
                  >
                    <div className="flex items-center gap-1.5">
                      <span>Роль</span>
                      {sortField === 'role' ? (
                        sortAsc ? <ArrowUp className="w-3.5 h-3.5 text-indigo-600" /> : <ArrowDown className="w-3.5 h-3.5 text-indigo-600" />
                      ) : (
                        <ArrowUpDown className="w-3.5 h-3.5 text-slate-400" />
                      )}
                    </div>
                  </th>
                  <th className="px-3 py-2.5 text-left">Доступ к модулям</th>
                  <th className="px-3 py-2.5 text-right"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 bg-white">
                {usersLoading ? (
                  <tr><td colSpan={4} className="px-3 py-8 text-center text-slate-400">Загрузка пользователей…</td></tr>
                ) : usersError ? (
                  <tr><td colSpan={4} className="px-3 py-8 text-center text-rose-600">{usersError}</td></tr>
                ) : sortedUsers.map(u => (
                  <tr key={u.id} className="hover:bg-slate-50">
                    <td className="px-3 py-2.5 font-bold text-slate-900">{u.username}</td>
                    <td className="px-3 py-2.5">
                      <span className={`px-2 py-0.5 rounded-full text-[10px] font-semibold ${u.role === 'admin' ? 'bg-indigo-50 text-indigo-700 border border-indigo-200' : u.role === 'accountant' ? 'bg-emerald-50 text-emerald-700 border border-emerald-200' : 'bg-amber-50 text-amber-700 border border-amber-200'}`}>
                        {u.role === 'admin' ? 'Администратор' : u.role === 'accountant' ? 'Бухгалтер' : 'Аудитор'}
                      </span>
                    </td>
                    <td className="px-3 py-2.5 text-slate-600">
                      {u.role === 'admin' ? 'Все модули (Сверка, EPOS, Аналитика, Настройки)' : u.role === 'accountant' ? 'Сверка по RRN, Аналитика' : 'Просмотр аналитики и отчётов'}
                    </td>
                    <td className="px-3 py-2.5 text-right">
                      {u.username !== 'admin' && (
                        <button
                          onClick={() => handleDeleteUser(u.id, u.username)}
                          className="text-slate-400 hover:text-rose-600 p-1 cursor-pointer transition-colors"
                          title="Удалить"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* Global Parameters Settings */}
      <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-xs space-y-4">
        <div className="flex items-center justify-between border-b border-slate-100 pb-3">
          <h2 className="text-sm font-bold text-slate-900 flex items-center gap-2">
            <SettingsIcon className="w-4 h-4 text-indigo-600" />
            <span>Глобальные параметры сверки</span>
          </h2>
          {settingsSaved && (
            <span className="text-xs font-semibold text-emerald-600 flex items-center gap-1">
              <CheckCircle className="w-3.5 h-3.5" />
              <span>Параметры сохранены!</span>
            </span>
          )}
        </div>

        <form onSubmit={handleSaveSettings} className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs">
          <div>
            <label className="block font-semibold text-slate-700 mb-1">
              Допустимая погрешность расхождений (Tolerance)
            </label>
            <input
              type="number"
              step="0.01"
              min="0"
              value={tolerance}
              onChange={(e) => setTolerance(parseFloat(e.target.value) || 0)}
              className="w-full py-2 px-3 border border-slate-200 rounded-lg text-xs font-semibold"
            />
            <span className="text-[11px] text-slate-400 mt-0.5 block">
              Разницы меньше этого значения считаются успешно сошедшимися (по умолчанию: 0.01).
            </span>
          </div>

          <div>
            <label className="block font-semibold text-slate-700 mb-1">
              Основная расчётная валюта
            </label>
            <select
              value={currency}
              onChange={(e) => setCurrency(e.target.value)}
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
              className="w-full py-2.5 px-4 bg-slate-900 hover:bg-slate-800 text-white font-semibold rounded-lg shadow-xs transition-colors cursor-pointer"
            >
              Сохранить параметры
            </button>
          </div>
        </form>
      </div>

      {/* Audit Logs */}
      <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-xs space-y-4">
        <h2 className="text-sm font-bold text-slate-900 flex items-center gap-2">
          <History className="w-4 h-4 text-indigo-600" />
          <span>Журнал аудита действий (Audit Logs)</span>
        </h2>

        <div className="max-h-72 overflow-y-auto rounded-xl border border-slate-200 text-xs">
          <table className="min-w-full divide-y divide-slate-200">
            <thead className="bg-slate-50 font-bold text-slate-700 sticky top-0">
              <tr>
                <th className="px-3 py-2 text-left">Время</th>
                <th className="px-3 py-2 text-left">Пользователь</th>
                <th className="px-3 py-2 text-left">Действие</th>
                <th className="px-3 py-2 text-left">Подробности</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 bg-white">
              {auditLogs.map((log) => (
                <tr key={log.id} className="hover:bg-slate-50">
                  <td className="px-3 py-2 text-slate-500 whitespace-nowrap">
                    {new Date(log.timestamp).toLocaleString('ru-RU')}
                  </td>
                  <td className="px-3 py-2 font-semibold text-slate-900">{log.username}</td>
                  <td className="px-3 py-2 font-mono text-[11px] text-indigo-700">{log.action}</td>
                  <td className="px-3 py-2 text-slate-600">{log.details}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Confirm Modal */}
      <ConfirmModal
        isOpen={confirmState.isOpen}
        title={confirmState.title}
        message={confirmState.message}
        confirmText="Удалить"
        isDanger={true}
        onConfirm={confirmState.onConfirm}
        onClose={() => setConfirmState(prev => ({ ...prev, isOpen: false }))}
      />

      {/* Alert Modal */}
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
