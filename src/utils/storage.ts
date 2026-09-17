import { User, EposTerminal, AuditLog, ReconciliationArchive, SystemSettings } from '../types';

const USERS_KEY = 'reconcile_users';
const EPOS_KEY = 'reconcile_epos_banks_v2';
const BANKS_KEY = 'reconcile_available_banks_v2';
const LOGS_KEY = 'reconcile_logs';
const ARCHIVE_KEY = 'reconcile_archive';
const SETTINGS_KEY = 'reconcile_settings';

/**
 * Computes a secure SHA-256 hex digest for password storage.
 */
function sha256Hex(ascii: string): string {
  function rightRotate(value: number, amount: number) {
    return (value >>> amount) | (value << (32 - amount));
  }
  let i: number, j: number;
  let result = '';

  const words: number[] = [];
  const asciiBitLength = ascii.length * 8;
  
  const hash = [
    0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53f,
    0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19
  ];
  
  const k = [
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
    0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x59f1111f, 0xe49b69c1, 0x988c2c6a, 0x3c7a47b7,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd192e819, 0xa3e79b3f, 0x4f2c5d9c,
    0x06ca6351, 0x14292967, 0x27b70a85, 0x3d6ef8e0, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da, 0x81c2c92e,
    0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967, 0x27b70a85,
    0x3d6ef8e0, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da, 0x81c2c92e, 0xa831c66d, 0xb00327c8, 0xbf597fc7,
    0xc6e00bf3, 0xd192e819, 0xa3e79b3f, 0x6f067aa2, 0xd2078f57, 0x4d9a0e9b, 0x1f83d9ab, 0x5be0cd19,
    0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x92322d85, 0xa2bfe8a1, 0x816d807f,
    0x650a7354, 0x766a0abb, 0x92722c85, 0xa2bfe8a1, 0xa81a664b, 0xc76c51a3, 0xd192e819, 0xf40e3585
  ];

  for (i = 0; i < ascii.length; i++) {
    const j2 = ascii.charCodeAt(i);
    words[i >> 2] |= j2 << ((3 - (i % 4)) * 8);
  }

  words[asciiBitLength >> 5] |= 0x80 << (24 - (asciiBitLength % 32));
  words[(((asciiBitLength + 64) >> 9) << 4) + 15] = asciiBitLength;

  for (i = 0; i < words.length; i += 16) {
    const w = words.slice(i, i + 16);
    const oldHash = [...hash];

    for (j = 0; j < 64; j++) {
      let s0: number, s1: number, ch: number, temp1: number, temp2: number, maj: number;
      if (j >= 16) {
        const gamma0 = rightRotate(w[j - 15], 7) ^ rightRotate(w[j - 15], 18) ^ (w[j - 15] >>> 3);
        const gamma1 = rightRotate(w[j - 2], 17) ^ rightRotate(w[j - 2], 19) ^ (w[j - 2] >>> 10);
        w[j] = (w[j - 16] + gamma0 + w[j - 7] + gamma1) | 0;
      }

      s1 = rightRotate(hash[4], 6) ^ rightRotate(hash[4], 11) ^ rightRotate(hash[4], 25);
      ch = (hash[4] & hash[5]) ^ (~hash[4] & hash[6]);
      temp1 = (hash[7] + s1 + ch + k[j] + (w[j] | 0)) | 0;
      s0 = rightRotate(hash[0], 2) ^ rightRotate(hash[0], 13) ^ rightRotate(hash[0], 22);
      maj = (hash[0] & hash[1]) ^ (hash[0] & hash[2]) ^ (hash[1] & hash[2]);
      temp2 = (s0 + maj) | 0;

      hash[7] = hash[6];
      hash[6] = hash[5];
      hash[5] = hash[4];
      hash[4] = (hash[3] + temp1) | 0;
      hash[3] = hash[2];
      hash[2] = hash[1];
      hash[1] = hash[0];
      hash[0] = (temp1 + temp2) | 0;
    }

    for (j = 0; j < 8; j++) {
      hash[j] = (hash[j] + oldHash[j]) | 0;
    }
  }

  for (i = 0; i < 8; i++) {
    for (j = 3; j >= 0; j--) {
      const b = (hash[i] >> (8 * j)) & 255;
      result += (b < 16 ? '0' : '') + b.toString(16);
    }
  }
  return result;
}

const PASSWORD_SALT = 'reconcile_sec_salt_v2';

export function hashPassword(plain: string): string {
  return 'sha256:' + sha256Hex(PASSWORD_SALT + ':' + plain.trim());
}

export const DEFAULT_BANKS: string[] = [
  'Aloqa Bank',
  'Open Bank',
  'Saderat Bank',
  'Davr Bank',
  'Hamkor Bank',
];

const DEFAULT_USERS: Array<User & { passwordHash: string }> = [
  { id: 1, username: 'admin', role: 'admin', passwordHash: hashPassword('admin123') },
  { id: 2, username: 'accountant', role: 'accountant', passwordHash: hashPassword('acc123') },
  { id: 3, username: 'auditor', role: 'auditor', passwordHash: hashPassword('audit123') },
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
    const parsed: Array<User & { passwordHash: string }> = JSON.parse(raw);
    let migrated = false;
    parsed.forEach(u => {
      if (u.passwordHash && !u.passwordHash.startsWith('sha256:')) {
        u.passwordHash = hashPassword(u.passwordHash);
        migrated = true;
      }
    });
    if (migrated) {
      localStorage.setItem(USERS_KEY, JSON.stringify(parsed));
    }
    return parsed;
  } catch {
    return DEFAULT_USERS;
  }
}

export function verifyUser(username: string, password: string): User | null {
  const users = getStoredUsers();
  const cleanPass = password.trim();
  const hashedInput = hashPassword(cleanPass);

  let userUpdated = false;
  const found = users.find(u => {
    if (u.username.toLowerCase() !== username.trim().toLowerCase()) {
      return false;
    }
    if (u.passwordHash === hashedInput) {
      return true;
    }
    if (u.passwordHash === cleanPass) {
      u.passwordHash = hashedInput;
      userUpdated = true;
      return true;
    }
    return false;
  });

  if (userUpdated) {
    try {
      localStorage.setItem(USERS_KEY, JSON.stringify(users));
    } catch {}
  }

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
    passwordHash: hashPassword(password.trim()),
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
    return false;
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
  }
  terminals.push(terminal);
  localStorage.setItem(EPOS_KEY, JSON.stringify(terminals));
  return { success: true, message: `Терминал ${terminal.terminal_id} успешно добавлен!` };
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
  only_bank_count: number,
  period_month?: string,
  total_commission?: number,
  terminals_summary?: import('../types').TerminalSummaryItem[]
): { success: boolean; message: string } {
  try {
    const raw = localStorage.getItem(ARCHIVE_KEY);
    const archive: ReconciliationArchive[] = raw ? JSON.parse(raw) : [];
    const nowIso = new Date().toISOString();
    const resolvedMonth = period_month || nowIso.slice(0, 7);
    const normalizedTerminals = (terminals_summary || []).map(t => ({ ...t, terminal_id: String(t.terminal_id || '').trim() || '(Без TID)' }));
    const terminalCommission = normalizedTerminals.reduce((sum, t) => sum + (Number(t.commission_amount) || 0), 0);
    const newEntry: ReconciliationArchive = {
      id: Date.now(),
      timestamp: nowIso,
      username,
      bank_name,
      total_our,
      total_bank,
      difference,
      matched_count,
      mismatch_count,
      only_our_count,
      only_bank_count,
      period_month: resolvedMonth,
      total_commission: normalizedTerminals.length > 0 ? terminalCommission : (total_commission || 0),
      terminals_summary: normalizedTerminals,
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
      const initial: ReconciliationArchive[] = [
        {
          id: 1,
          timestamp: new Date(Date.now() - 86400000 * 2).toISOString(),
          username: 'admin',
          bank_name: 'Aloqa Bank',
          total_our: 145000000,
          total_bank: 145000000,
          difference: 0,
          matched_count: 342,
          mismatch_count: 0,
          only_our_count: 0,
          only_bank_count: 0,
          period_month: '2026-09',
          total_commission: 841000,
          terminals_summary: [
            { terminal_id: '97008516', bank_acquirer: 'Aloqa Bank', merchant_id: 'MID_ALOQA_01', legal_entity: 'ООО Retail Plus', tx_count: 180, total_volume: 85000000, commission_pct: 0.58, commission_amount: 493000, net_volume: 84507000 },
            { terminal_id: '1963301C', bank_acquirer: 'Aloqa Bank', merchant_id: 'MID_ALOQA_02', legal_entity: 'ООО Retail Plus', tx_count: 162, total_volume: 60000000, commission_pct: 0.58, commission_amount: 348000, net_volume: 59652000 },
          ]
        },
        {
          id: 2,
          timestamp: new Date(Date.now() - 86400000 * 15).toISOString(),
          username: 'accountant',
          bank_name: 'Hamkor Bank',
          total_our: 89400000,
          total_bank: 89400000,
          difference: 0,
          matched_count: 215,
          mismatch_count: 0,
          only_our_count: 0,
          only_bank_count: 0,
          period_month: '2026-08',
          total_commission: 670500,
          terminals_summary: [
            { terminal_id: '91500844', bank_acquirer: 'Hamkor Bank', merchant_id: 'MID_HAMKOR_01', legal_entity: 'ООО Торг Мастер', tx_count: 120, total_volume: 49400000, commission_pct: 0.75, commission_amount: 370500, net_volume: 49029500 },
            { terminal_id: '91500845', bank_acquirer: 'Hamkor Bank', merchant_id: 'MID_HAMKOR_02', legal_entity: 'ООО Торг Мастер', tx_count: 95, total_volume: 40000000, commission_pct: 0.75, commission_amount: 300000, net_volume: 39700000 },
          ]
        }
      ];
      localStorage.setItem(ARCHIVE_KEY, JSON.stringify(initial));
      return initial;
    }
    const parsed: ReconciliationArchive[] = JSON.parse(raw);
    return parsed.map(item => ({
      ...item,
      period_month: item.period_month || item.timestamp.slice(0, 7),
      total_commission: item.total_commission || 0,
      terminals_summary: item.terminals_summary || [],
    }));
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

const DRAFT_KEY = 'reconcile_active_draft_v2';
const LEGACY_DRAFT_KEY = 'reconcile_active_draft_v1';

export function saveActiveDraft(draft: any): void {
  try {
    const fileMeta = {
      our: draft?.ourFile
        ? {
            name: draft.ourFile.name,
            columns: draft.ourFile.columns || [],
            rowCount: Array.isArray(draft.ourFile.rows) ? draft.ourFile.rows.length : (draft.ourFile.rowCount || 0),
          }
        : null,
      bank: draft?.bankFile
        ? {
            name: draft.bankFile.name,
            columns: draft.bankFile.columns || [],
            rowCount: Array.isArray(draft.bankFile.rows) ? draft.bankFile.rows.length : (draft.bankFile.rowCount || 0),
          }
        : null,
    };

    const payload = {
      ...draft,
      version: 2,
      ourFile: null,
      bankFile: null,
      fileMeta,
    };

    localStorage.setItem(DRAFT_KEY, JSON.stringify(payload));
  } catch (e) {
    console.warn('Failed to save draft to localStorage:', e);
  }
}

export function getStoredDraft(): any | null {
  try {
    const raw = localStorage.getItem(DRAFT_KEY);
    if (raw) return JSON.parse(raw);

    // Legacy v1 could contain the entire imported tables. Remove it without JSON.parse
    // so a previously saved 200 MB file does not block app startup.
    localStorage.removeItem(LEGACY_DRAFT_KEY);
    return null;
  } catch {
    return null;
  }
}

export function clearActiveDraft(): void {
  try {
    localStorage.removeItem(DRAFT_KEY);
    localStorage.removeItem(LEGACY_DRAFT_KEY);
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
