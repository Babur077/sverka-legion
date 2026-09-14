import { User, EposTerminal, AuditLog, ReconciliationArchive, SystemSettings } from '../types';

const USERS_KEY = 'reconcile_users';
const EPOS_KEY = 'reconcile_epos_banks_v2';
const BANKS_KEY = 'reconcile_available_banks_v2';
const LOGS_KEY = 'reconcile_logs';
const ARCHIVE_KEY = 'reconcile_archive';
const SETTINGS_KEY = 'reconcile_settings';

export const DEFAULT_BANKS: string[] = [
  'Aloqa Bank',
  'Open Bank',
  'Saderat Bank',
  'Davr Bank',
  'Hamkor Bank',
];

const DEFAULT_USERS: Array<User & { passwordHash: string }> = [
  { id: 1, username: 'admin', role: 'admin', passwordHash: 'admin123' },
  { id: 2, username: 'accountant', role: 'accountant', passwordHash: 'acc123' },
  { id: 3, username: 'auditor', role: 'auditor', passwordHash: 'audit123' },
];

const DEFAULT_EPOS: EposTerminal[] = [
  { terminal_id: '98234001', merchant_id: 'MID_ALOQA_01', bank_acquirer: 'Aloqa Bank', commission_pct: 1.2, is_active: true },
  { terminal_id: '98234002', merchant_id: 'MID_OPEN_01', bank_acquirer: 'Open Bank', commission_pct: 1.0, is_active: true },
  { terminal_id: '98234003', merchant_id: 'MID_SADERAT_01', bank_acquirer: 'Saderat Bank', commission_pct: 1.5, is_active: true },
  { terminal_id: '98234004', merchant_id: 'MID_DAVR_01', bank_acquirer: 'Davr Bank', commission_pct: 1.0, is_active: true },
  { terminal_id: '98234005', merchant_id: 'MID_HAMKOR_01', bank_acquirer: 'Hamkor Bank', commission_pct: 1.2, is_active: true },
];

const DEFAULT_SETTINGS: SystemSettings = {
  amount_tolerance: 0.01,
  currency: 'UZS',
  dayfirst: true,
};

export function getStoredUsers(): Array<User & { passwordHash: string }> {
  try {
    const raw = localStorage.getItem(USERS_KEY);
    if (!raw) {
      localStorage.setItem(USERS_KEY, JSON.stringify(DEFAULT_USERS));
      return DEFAULT_USERS;
    }
    return JSON.parse(raw);
  } catch {
    return DEFAULT_USERS;
  }
}

export function verifyUser(username: string, password: string):User | null {
  const users = getStoredUsers();
  const found = users.find(u => u.username.toLowerCase() === username.trim().toLowerCase() && u.passwordHash === password.trim());
  if (found) {
    return { id: found.id, username: found.username, role: found.role };
  }
  return null;
}

export function addUser(username: string, password: string, role: 'admin' | 'accountant' | 'auditor'): { success: boolean; message: string } {
  const users = getStoredUsers();
  const cleanUser = username.trim();
  if (users.some(u => u.username.toLowerCase() === cleanUser.toLowerCase())) {
    return { success: false, message: `Пользователь с логином «${cleanUser}» уже существует!` };
  }
  const newUser = {
    id: Date.now(),
    username: cleanUser,
    passwordHash: password.trim(),
    role,
  };
  users.push(newUser);
  localStorage.setItem(USERS_KEY, JSON.stringify(users));
  return { success: true, message: 'Пользователь успешно создан!' };
}

export function deleteUser(id: number): boolean {
  let users = getStoredUsers();
  const toDelete = users.find(u => u.id === id);
  if (toDelete && toDelete.username === 'admin') {
    return false; // Prevent deleting master admin
  }
  users = users.filter(u => u.id !== id);
  localStorage.setItem(USERS_KEY, JSON.stringify(users));
  return true;
}

export function getStoredBanks(): string[] {
  try {
    const raw = localStorage.getItem(BANKS_KEY);
    if (!raw) {
      localStorage.setItem(BANKS_KEY, JSON.stringify(DEFAULT_BANKS));
      return DEFAULT_BANKS;
    }
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed) && parsed.length > 0) {
      // Ensure the 5 primary banks are always included
      const merged = Array.from(new Set([...DEFAULT_BANKS, ...parsed]));
      return merged;
    }
    return DEFAULT_BANKS;
  } catch {
    return DEFAULT_BANKS;
  }
}

export function addStoredBank(bankName: string): boolean {
  const clean = bankName.trim();
  if (!clean) return false;
  const banks = getStoredBanks();
  if (!banks.some(b => b.toLowerCase() === clean.toLowerCase())) {
    banks.push(clean);
    localStorage.setItem(BANKS_KEY, JSON.stringify(banks));
    return true;
  }
  return false;
}

export function getStoredEpos(): EposTerminal[] {
  try {
    const raw = localStorage.getItem(EPOS_KEY);
    if (!raw) {
      localStorage.setItem(EPOS_KEY, JSON.stringify(DEFAULT_EPOS));
      return DEFAULT_EPOS;
    }
    return JSON.parse(raw);
  } catch {
    return DEFAULT_EPOS;
  }
}

export function saveEposTerminal(terminal: EposTerminal): { success: boolean; message: string } {
  const terminals = getStoredEpos();
  const existsIndex = terminals.findIndex(t => t.terminal_id === terminal.terminal_id);
  if (existsIndex >= 0) {
    terminals[existsIndex] = terminal;
    localStorage.setItem(EPOS_KEY, JSON.stringify(terminals));
    return { success: true, message: `Терминал ${terminal.terminal_id} успешно обновлен!` };
  } else {
    terminals.push(terminal);
    localStorage.setItem(EPOS_KEY, JSON.stringify(terminals));
    return { success: true, message: `Терминал ${terminal.terminal_id} успешно добавлен!` };
  }
}

export function deleteEposTerminal(tid: string): void {
  const terminals = getStoredEpos().filter(t => t.terminal_id !== tid);
  localStorage.setItem(EPOS_KEY, JSON.stringify(terminals));
}

export function toggleEposActive(tid: string): void {
  const terminals = getStoredEpos();
  const t = terminals.find(x => x.terminal_id === tid);
  if (t) {
    t.is_active = !t.is_active;
    localStorage.setItem(EPOS_KEY, JSON.stringify(terminals));
  }
}

export function logAction(username: string, action: string, details: string = ''): void {
  try {
    const raw = localStorage.getItem(LOGS_KEY);
    const logs: AuditLog[] = raw ? JSON.parse(raw) : [];
    const newLog: AuditLog = {
      id: Date.now(),
      timestamp: new Date().toISOString(),
      username,
      action,
      details,
    };
    logs.unshift(newLog);
    if (logs.length > 200) logs.pop();
    localStorage.setItem(LOGS_KEY, JSON.stringify(logs));
  } catch (e) {
    console.error('Failed to log action', e);
  }
}

export function getAuditLogs(): AuditLog[] {
  try {
    const raw = localStorage.getItem(LOGS_KEY);
    if (!raw) {
      // Seed a couple initial logs
      const initial: AuditLog[] = [
        { id: 1, timestamp: new Date(Date.now() - 3600000).toISOString(), username: 'system', action: 'INIT', details: 'Система инициализирована. База данных готова к работе.' }
      ];
      localStorage.setItem(LOGS_KEY, JSON.stringify(initial));
      return initial;
    }
    return JSON.parse(raw);
  } catch {
    return [];
  }
}

export function saveReconciliation(
  username: string,
  bank_name: string,
  total_our: number,
  total_bank: number,
  difference: number,
  matched_count: number,
  mismatch_count: number,
  only_our_count: number,
  only_bank_count: number
): { success: boolean; message: string } {
  try {
    const raw = localStorage.getItem(ARCHIVE_KEY);
    const archive: ReconciliationArchive[] = raw ? JSON.parse(raw) : [];
    const newEntry: ReconciliationArchive = {
      id: Date.now(),
      timestamp: new Date().toISOString(),
      username,
      bank_name,
      total_our,
      total_bank,
      difference,
      matched_count,
      mismatch_count,
      only_our_count,
      only_bank_count,
    };
    archive.unshift(newEntry);
    localStorage.setItem(ARCHIVE_KEY, JSON.stringify(archive));
    return { success: true, message: 'Сверка успешно сохранена в системный архив!' };
  } catch (e: any) {
    return { success: false, message: `Ошибка при сохранении: ${e?.message || e}` };
  }
}

export function getArchiveData(): ReconciliationArchive[] {
  try {
    const raw = localStorage.getItem(ARCHIVE_KEY);
    if (!raw) {
      // Seed realistic archive entries for sample demonstration
      const initial: ReconciliationArchive[] = [
        {
          id: 1,
          timestamp: new Date(Date.now() - 86400000 * 2).toISOString(),
          username: 'admin',
          bank_name: 'Kapital Bank',
          total_our: 145000000,
          total_bank: 145000000,
          difference: 0,
          matched_count: 342,
          mismatch_count: 0,
          only_our_count: 0,
          only_bank_count: 0,
        },
        {
          id: 2,
          timestamp: new Date(Date.now() - 86400000).toISOString(),
          username: 'accountant',
          bank_name: 'Soliq',
          total_our: 89400000,
          total_bank: 89350000,
          difference: -50000,
          matched_count: 215,
          mismatch_count: 1,
          only_our_count: 2,
          only_bank_count: 0,
        }
      ];
      localStorage.setItem(ARCHIVE_KEY, JSON.stringify(initial));
      return initial;
    }
    return JSON.parse(raw);
  } catch {
    return [];
  }
}

export function deleteArchiveRecord(id: number): boolean {
  try {
    const raw = localStorage.getItem(ARCHIVE_KEY);
    if (!raw) return false;
    const archive: ReconciliationArchive[] = JSON.parse(raw);
    const updated = archive.filter(a => a.id !== id);
    localStorage.setItem(ARCHIVE_KEY, JSON.stringify(updated));
    return true;
  } catch {
    return false;
  }
}

const DRAFT_KEY = 'reconcile_active_draft_v1';

export function saveActiveDraft(draft: any): void {
  try {
    localStorage.setItem(DRAFT_KEY, JSON.stringify(draft));
  } catch (e) {
    console.warn('Failed to save draft to localStorage:', e);
  }
}

export function getStoredDraft(): any | null {
  try {
    const raw = localStorage.getItem(DRAFT_KEY);
    if (!raw) return null;
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

export function clearActiveDraft(): void {
  try {
    localStorage.removeItem(DRAFT_KEY);
  } catch {}
}

export function getStoredSettings(): SystemSettings {
  try {
    const raw = localStorage.getItem(SETTINGS_KEY);
    if (!raw) {
      localStorage.setItem(SETTINGS_KEY, JSON.stringify(DEFAULT_SETTINGS));
      return DEFAULT_SETTINGS;
    }
    return { ...DEFAULT_SETTINGS, ...JSON.parse(raw) };
  } catch {
    return DEFAULT_SETTINGS;
  }
}

export function saveSettings(settings: SystemSettings): void {
  localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings));
}
