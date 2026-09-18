import React, { useEffect, useState, useMemo } from 'react';
import { Building2, Plus, Trash2, CheckCircle, AlertCircle, RotateCcw, Landmark, Check, ArrowUpDown, ArrowUp, ArrowDown } from 'lucide-react';
import { EposTerminal, User } from '../types';
import { hasPermission } from '../utils/permissions';
import { getEposViaApi, createEposViaApi, updateEposViaApi, deleteEposViaApi } from '../utils/eposApi';
import { DEFAULT_BANKS, getBanksViaApi } from '../utils/banksApi';
import { ConfirmModal } from './Modal';

interface EposPageProps {
  user: User;
}

export const EposPage: React.FC<EposPageProps> = ({ user }) => {
  const canManage = hasPermission(user, 'epos.manage');
  const [terminals, setTerminals] = useState<EposTerminal[]>([]);
  const [availableBanks, setAvailableBanks] = useState<string[]>(DEFAULT_BANKS);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  const refreshTerminals = async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const data = await getEposViaApi(user.username);
      setTerminals(data);
      if (data.length) setAvailableBanks(prev => Array.from(new Set([...prev, ...data.map(t => t.bank_acquirer).filter(Boolean)])));
    } catch (error: any) {
      setLoadError(error?.message || 'Не удалось загрузить реестр EPOS.');
    } finally { setLoading(false); }
  };

  useEffect(() => {
    void refreshTerminals();
    void getBanksViaApi()
      .then(setAvailableBanks)
      .catch(() => {});
  }, [user.username]);

  const [selectedBank, setSelectedBank] = useState<string>('Aloqa Bank');
  const [showAddBankInput, setShowAddBankInput] = useState<boolean>(false);
  const [customBankName, setCustomBankName] = useState<string>('');

  const [tid, setTid] = useState('');
  const [mid, setMid] = useState('');
  const [commPct, setCommPct] = useState<number>(1.2);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  // Sorting
  const [sortField, setSortField] = useState<'bank_acquirer' | 'terminal_id' | 'commission_pct'>('bank_acquirer');
  const [sortAsc, setSortAsc] = useState<boolean>(true);

  // Modal confirmation
  const [deleteConfirm, setDeleteConfirm] = useState<{
    isOpen: boolean;
    terminalId: string;
    bankName: string;
  }>({
    isOpen: false,
    terminalId: '',
    bankName: '',
  });

  // Quick select bank handler
  const handleSelectBank = (bankName: string) => {
    setSelectedBank(bankName);
    // Auto-suggest commission if terminal with this bank already exists
    const existing = terminals.find(t => t.bank_acquirer.toLowerCase() === bankName.toLowerCase());
    if (existing) {
      setCommPct(existing.commission_pct);
    }
  };

  // Add custom bank to list
  const handleCreateNewBank = (e: React.FormEvent) => {
    e.preventDefault();
    if (!canManage) return;
    const clean = customBankName.trim();
    if (!clean) return;

    setAvailableBanks(prev => Array.from(new Set([...prev, clean])));
    setSelectedBank(clean);
    setCustomBankName('');
    setShowAddBankInput(false);
    setMessage({ type: 'success', text: `Банк «${clean}» выбран. Сохраните терминал, чтобы закрепить его в серверном реестре.` });
  };

  const handleAddTerminal = async (e: React.FormEvent) => {
    e.preventDefault();
    setMessage(null);
    if (!canManage) {
      setMessage({ type: 'error', text: 'Нет права epos.manage для изменения реестра.' });
      return;
    }

    const bankName = selectedBank.trim();
    if (!bankName) {
      setMessage({ type: 'error', text: 'Пожалуйста, выберите или укажите банк-эквайер!' });
      return;
    }

    // If TID is left blank, auto-generate standard TID based on bank name
    const cleanTid = tid.trim() || `TID_${bankName.replace(/\s+/g, '_').toUpperCase()}_${Date.now().toString().slice(-4)}`;
    const cleanMid = mid.trim() || `MID_${bankName.replace(/\s+/g, '_').toUpperCase()}`;

    const newTerm: EposTerminal = {
      terminal_id: cleanTid,
      merchant_id: cleanMid,
      bank_acquirer: bankName,
      commission_pct: commPct,
      is_active: true,
    };

    setSaving(true);
    try {
      await createEposViaApi(user.username, newTerm);
      await refreshTerminals();
      setMessage({ type: 'success', text: `Банк ${bankName} (TID: ${cleanTid}) успешно сохранен в реестр!` });
      setTid(''); setMid('');
    } catch (error: any) {
      setMessage({ type: 'error', text: error?.message || 'Не удалось сохранить терминал.' });
    } finally { setSaving(false); }
  };

  const handleToggle = async (terminal: EposTerminal) => {
    if (!canManage) return;
    setSaving(true);
    try {
      await updateEposViaApi(user.username, { ...terminal, is_active: !terminal.is_active });
      await refreshTerminals();
    } catch (error: any) {
      setMessage({ type: 'error', text: error?.message || 'Не удалось изменить статус терминала.' });
    } finally { setSaving(false); }
  };

  const handleDelete = (terminalId: string, bankName: string) => {
    if (!canManage) return;
    setDeleteConfirm({
      isOpen: true,
      terminalId,
      bankName,
    });
  };

  const confirmDeleteTerminal = async () => {
    const { terminalId, bankName } = deleteConfirm;
    if (terminalId) {
      setSaving(true);
      try {
        await deleteEposViaApi(user.username, terminalId);
        await refreshTerminals();
      } catch (error: any) {
        setMessage({ type: 'error', text: error?.message || 'Не удалось удалить терминал.' });
      } finally { setSaving(false); }
    }
    setDeleteConfirm({ isOpen: false, terminalId: '', bankName: '' });
  };

  const sortedTerminals = useMemo(() => {
    return [...terminals].sort((a, b) => {
      let res = 0;
      if (sortField === 'commission_pct') {
        res = a.commission_pct - b.commission_pct;
      } else {
        const valA = a[sortField] || '';
        const valB = b[sortField] || '';
        res = valA.localeCompare(valB);
      }
      return sortAsc ? res : -res;
    });
  }, [terminals, sortField, sortAsc]);

  const toggleSort = (field: 'bank_acquirer' | 'terminal_id' | 'commission_pct') => {
    if (sortField === field) {
      setSortAsc(!sortAsc);
    } else {
      setSortField(field);
      setSortAsc(true);
    }
  };

  return (
    <div className="p-8 max-w-7xl mx-auto space-y-6">
      {/* Page Header */}
      <div>
        <h1 className="text-2xl font-bold text-slate-900 tracking-tight flex items-center gap-2.5">
          <Building2 className="w-6 h-6 text-indigo-600" />
          <span>Реестр банков-эквайеров</span>
          {!canManage && (
            <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-slate-100 text-slate-600 border border-slate-200">
              Только просмотр
            </span>
          )}
        </h1>
        <p className="text-sm text-slate-500 mt-1">
          Справочник банков-эквайеров и персональных комиссионных ставок для расчёта нетто-сумм при сверке.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Form: Add Bank / Terminal */}
        <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-xs h-fit space-y-4">
          <div className="flex items-center justify-between pb-2 border-b border-slate-100">
            <h2 className="text-sm font-bold text-slate-900 flex items-center gap-2">
              <Plus className="w-4 h-4 text-indigo-600" />
              <span>Добавить банк в реестр</span>
            </h2>
          </div>

          {message && (
            <div className={`p-3 rounded-lg text-xs flex items-center gap-2 ${message.type === 'success' ? 'bg-emerald-50 text-emerald-800 border border-emerald-200' : 'bg-rose-50 text-rose-800 border border-rose-200'}`}>
              {message.type === 'success' ? <CheckCircle className="w-4 h-4 text-emerald-600 shrink-0" /> : <AlertCircle className="w-4 h-4 text-rose-600 shrink-0" />}
              <span>{message.text}</span>
            </div>
          )}

          {/* Quick select bank chips */}
          <div>
            <label className="block text-[11px] font-bold text-slate-500 uppercase tracking-wider mb-2">
              Быстрый набор банков:
            </label>
            <div className="flex flex-wrap gap-1.5 mb-2">
              {availableBanks.map((b) => {
                const isSelected = selectedBank.toLowerCase() === b.toLowerCase();
                return (
                  <button
                    key={b}
                    type="button"
                    onClick={() => handleSelectBank(b)}
                    className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all flex items-center gap-1.5 cursor-pointer border ${
                      isSelected
                        ? 'bg-indigo-600 text-white border-indigo-600 shadow-xs ring-2 ring-indigo-200'
                        : 'bg-slate-50 hover:bg-slate-100 text-slate-700 border-slate-200'
                    }`}
                  >
                    {isSelected ? <Check className="w-3.5 h-3.5" /> : <Landmark className="w-3 h-3 text-slate-400" />}
                    <span>{b}</span>
                  </button>
                );
              })}

              <button
                type="button"
                disabled={!canManage}
                onClick={() => setShowAddBankInput(!showAddBankInput)}
                className="px-2.5 py-1.5 rounded-lg text-xs font-semibold text-indigo-600 hover:text-indigo-700 bg-indigo-50/70 hover:bg-indigo-100/70 border border-indigo-200/80 transition-colors flex items-center gap-1 cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
              >
                <Plus className="w-3.5 h-3.5" />
                <span>Добавить банк</span>
              </button>
            </div>

            {showAddBankInput && (
              <form onSubmit={handleCreateNewBank} className="mt-2.5 p-3 bg-slate-50 rounded-xl border border-slate-200 space-y-2">
                <span className="text-[11px] font-semibold text-slate-600 block">Новый банк в быстрый набор:</span>
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={customBankName}
                    onChange={(e) => setCustomBankName(e.target.value)}
                    placeholder="напр. Agrobank"
                    className="flex-1 py-1.5 px-2.5 bg-white border border-slate-300 rounded-lg text-xs focus:ring-1 focus:ring-indigo-500"
                    autoFocus
                  />
                  <button
                    type="submit"
                    className="px-3 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold rounded-lg shadow-xs transition-colors shrink-0 cursor-pointer"
                  >
                    Добавить
                  </button>
                </div>
              </form>
            )}
          </div>

          <form onSubmit={handleAddTerminal} className="space-y-3.5 text-xs pt-2">
            <div>
              <label className="block font-semibold text-slate-700 mb-1">Банк-эквайер*</label>
              <select
                id="epos-bank"
                value={selectedBank}
                onChange={(e) => handleSelectBank(e.target.value)}
                className="w-full py-2 px-3 border border-slate-200 rounded-lg text-xs font-medium focus:ring-1 focus:ring-indigo-500 bg-white"
              >
                {availableBanks.map((b) => (
                  <option key={b} value={b}>{b}</option>
                ))}
              </select>
            </div>

            <div>
              <label className="block font-semibold text-slate-700 mb-1">
                Terminal ID (TID)
                <span className="text-slate-400 font-normal ml-1">(код терминала)</span>
              </label>
              <input
                id="epos-tid"
                type="text"
                placeholder="напр. 98234015 (или оставьте пустым для автогенерации)"
                value={tid}
                onChange={(e) => setTid(e.target.value)}
                className="w-full py-2 px-3 border border-slate-200 rounded-lg text-xs font-mono focus:ring-1 focus:ring-indigo-500"
              />
            </div>

            <div>
              <label className="block font-semibold text-slate-700 mb-1">
                Merchant ID (MID)
                <span className="text-slate-400 font-normal ml-1">(опционально)</span>
              </label>
              <input
                id="epos-mid"
                type="text"
                placeholder="напр. MID_ALOQA_01"
                value={mid}
                onChange={(e) => setMid(e.target.value)}
                className="w-full py-2 px-3 border border-slate-200 rounded-lg text-xs font-mono focus:ring-1 focus:ring-indigo-500"
              />
            </div>

            <div>
              <label className="block font-semibold text-slate-700 mb-1">Комиссия банка (%)*</label>
              <div className="relative">
                <input
                  id="epos-commission"
                  type="number"
                  step="0.05"
                  min="0"
                  max="100"
                  value={commPct}
                  onChange={(e) => setCommPct(parseFloat(e.target.value) || 0)}
                  className="w-full py-2 px-3 border border-slate-200 rounded-lg text-xs focus:ring-1 focus:ring-indigo-500 font-semibold"
                  required
                />
                <span className="absolute right-3 top-2 text-slate-400 font-semibold">%</span>
              </div>
            </div>

            <button
              id="epos-submit-button"
              type="submit"
              disabled={!canManage || saving}
              className="w-full mt-2 py-2.5 px-4 bg-indigo-600 hover:bg-indigo-700 disabled:bg-slate-300 disabled:text-slate-500 text-white font-semibold rounded-lg shadow-xs transition-colors cursor-pointer disabled:cursor-not-allowed flex items-center justify-center gap-1.5"
            >
              <Plus className="w-4 h-4" />
              <span>Сохранить банк в реестр</span>
            </button>
          </form>
        </div>

        {/* Right Table: Current Registered Banks */}
        <div className="lg:col-span-2 bg-white rounded-2xl border border-slate-200 p-6 shadow-xs space-y-4">
          <div className="flex items-center justify-between border-b border-slate-100 pb-3">
            <div>
              <h2 className="text-sm font-bold text-slate-900">
                Зарегистрированные банки-эквайеры ({terminals.length})
              </h2>
              <p className="text-xs text-slate-500 mt-0.5">
                Реестр банков для автоматического применения комиссии и сверки
              </p>
            </div>
          </div>

          {loadError && <div className="p-3 rounded-lg bg-rose-50 text-rose-800 border border-rose-200 text-xs">{loadError}</div>}

          <div className="overflow-x-auto rounded-xl border border-slate-200 text-xs">
            <table className="min-w-full divide-y divide-slate-200">
              <thead className="bg-slate-50 font-bold text-slate-700">
                <tr>
                  <th 
                    onClick={() => toggleSort('bank_acquirer')}
                    className="px-3 py-2.5 text-left cursor-pointer hover:bg-slate-100 transition-colors select-none"
                  >
                    <div className="flex items-center gap-1.5">
                      <span>Банк-эквайер</span>
                      {sortField === 'bank_acquirer' ? (
                        sortAsc ? <ArrowUp className="w-3.5 h-3.5 text-indigo-600" /> : <ArrowDown className="w-3.5 h-3.5 text-indigo-600" />
                      ) : (
                        <ArrowUpDown className="w-3.5 h-3.5 text-slate-400" />
                      )}
                    </div>
                  </th>
                  <th 
                    onClick={() => toggleSort('terminal_id')}
                    className="px-3 py-2.5 text-left cursor-pointer hover:bg-slate-100 transition-colors select-none"
                  >
                    <div className="flex items-center gap-1.5">
                      <span>TID</span>
                      {sortField === 'terminal_id' ? (
                        sortAsc ? <ArrowUp className="w-3.5 h-3.5 text-indigo-600" /> : <ArrowDown className="w-3.5 h-3.5 text-indigo-600" />
                      ) : (
                        <ArrowUpDown className="w-3.5 h-3.5 text-slate-400" />
                      )}
                    </div>
                  </th>
                  <th className="px-3 py-2.5 text-left">MID</th>
                  <th 
                    onClick={() => toggleSort('commission_pct')}
                    className="px-3 py-2.5 text-right cursor-pointer hover:bg-slate-100 transition-colors select-none"
                  >
                    <div className="flex items-center justify-end gap-1.5">
                      <span>Комиссия</span>
                      {sortField === 'commission_pct' ? (
                        sortAsc ? <ArrowUp className="w-3.5 h-3.5 text-indigo-600" /> : <ArrowDown className="w-3.5 h-3.5 text-indigo-600" />
                      ) : (
                        <ArrowUpDown className="w-3.5 h-3.5 text-slate-400" />
                      )}
                    </div>
                  </th>
                  <th className="px-3 py-2.5 text-center">Активен</th>
                  <th className="px-3 py-2.5 text-right"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 bg-white">
                {loading ? (
                  <tr><td colSpan={6} className="px-4 py-8 text-center text-slate-400">Загрузка реестра…</td></tr>
                ) : sortedTerminals.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="px-4 py-8 text-center text-slate-400">
                      В реестре пока нет записей. Выберите банк слева и сохраните его.
                    </td>
                  </tr>
                ) : (
                  sortedTerminals.map((t) => (
                    <tr key={t.terminal_id} className={`hover:bg-slate-50 transition-colors ${t.is_active ? '' : 'opacity-60 bg-slate-50/50'}`}>
                      <td className="px-3 py-2.5 font-semibold text-indigo-700 flex items-center gap-2">
                        <div className="w-6 h-6 rounded-md bg-indigo-50 text-indigo-600 flex items-center justify-center shrink-0">
                          <Landmark className="w-3.5 h-3.5" />
                        </div>
                        <span className="font-bold text-slate-900">{t.bank_acquirer}</span>
                      </td>
                      <td className="px-3 py-2.5 font-mono font-bold text-slate-700">{t.terminal_id}</td>
                      <td className="px-3 py-2.5 font-mono text-slate-500">{t.merchant_id || '—'}</td>
                      <td className="px-3 py-2.5 text-right font-bold text-slate-900 tabular-nums">
                        {t.commission_pct.toFixed(2)}%
                      </td>
                      <td className="px-3 py-2.5 text-center">
                        <input
                          type="checkbox"
                          checked={t.is_active}
                          disabled={!canManage}
                          onChange={() => void handleToggle(t)}
                          className="rounded text-indigo-600 cursor-pointer disabled:cursor-not-allowed disabled:opacity-50"
                        />
                      </td>
                      <td className="px-3 py-2.5 text-right">
                        {canManage && (
                          <button
                            onClick={() => handleDelete(t.terminal_id, t.bank_acquirer)}
                            className="text-slate-400 hover:text-rose-600 transition-colors p-1 cursor-pointer"
                            title="Удалить"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        )}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* Delete Confirmation Modal */}
      <ConfirmModal
        isOpen={deleteConfirm.isOpen}
        title="Удаление банка из реестра"
        message={`Удалить запись банка «${deleteConfirm.bankName}» (TID: ${deleteConfirm.terminalId}) из реестра?`}
        confirmText="Удалить"
        isDanger={true}
        onConfirm={confirmDeleteTerminal}
        onClose={() => setDeleteConfirm({ isOpen: false, terminalId: '', bankName: '' })}
      />
    </div>
  );
};
