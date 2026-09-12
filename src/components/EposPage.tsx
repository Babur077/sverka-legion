import React, { useState } from 'react';
import { Smartphone, Plus, Trash2, CheckCircle, AlertCircle, Building2, Percent, Tag } from 'lucide-react';
import { EposTerminal, User } from '../types';
import { getStoredEpos, saveEposTerminal, deleteEposTerminal, toggleEposActive, logAction } from '../utils/storage';

interface EposPageProps {
  user: User;
}

export const EposPage: React.FC<EposPageProps> = ({ user }) => {
  const [terminals, setTerminals] = useState<EposTerminal[]>(getStoredEpos());

  const [tid, setTid] = useState('');
  const [mid, setMid] = useState('');
  const [bank, setBank] = useState('Kapital');
  const [entity, setEntity] = useState('');
  const [commPct, setCommPct] = useState<number>(1.2);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  const handleAddTerminal = (e: React.FormEvent) => {
    e.preventDefault();
    setMessage(null);

    const cleanTid = tid.trim();
    if (!cleanTid) {
      setMessage({ type: 'error', text: 'Поле TID обязательно для заполнения!' });
      return;
    }

    const newTerm: EposTerminal = {
      terminal_id: cleanTid,
      merchant_id: mid.trim() || `MID_${cleanTid}`,
      bank_acquirer: bank,
      legal_entity: entity.trim() || 'Основной филиал',
      commission_pct: commPct,
      is_active: true,
    };

    const res = saveEposTerminal(newTerm);
    if (res.success) {
      setTerminals(getStoredEpos());
      setMessage({ type: 'success', text: res.message });
      logAction(user.username, 'ADD_EPOS', `Добавлен терминал TID ${cleanTid} (${bank}, ${commPct}%)`);
      setTid('');
      setMid('');
      setEntity('');
    } else {
      setMessage({ type: 'error', text: res.message });
    }
  };

  const handleToggle = (terminalId: string) => {
    toggleEposActive(terminalId);
    setTerminals(getStoredEpos());
    logAction(user.username, 'TOGGLE_EPOS', `Изменен статус активности терминала ${terminalId}`);
  };

  const handleDelete = (terminalId: string) => {
    if (confirm(`Удалить терминал ${terminalId}?`)) {
      deleteEposTerminal(terminalId);
      setTerminals(getStoredEpos());
      logAction(user.username, 'DELETE_EPOS', `Удален терминал ${terminalId}`);
    }
  };

  return (
    <div className="p-8 max-w-7xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900 tracking-tight flex items-center gap-2">
          <span>Реестр EPOS терминалов</span>
        </h1>
        <p className="text-sm text-slate-500 mt-1">
          Справочник эквайринговых терминалов, привязка юрлиц и персональных комиссионных ставок для расчёта нетто-сумм.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Add Terminal Form */}
        <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-xs h-fit">
          <h2 className="text-sm font-bold text-slate-900 mb-4 flex items-center gap-2">
            <Plus className="w-4 h-4 text-indigo-600" />
            <span>Добавить терминал</span>
          </h2>

          {message && (
            <div className={`mb-4 p-3 rounded-lg text-xs flex items-center gap-2 ${message.type === 'success' ? 'bg-emerald-50 text-emerald-800 border border-emerald-200' : 'bg-rose-50 text-rose-800 border border-rose-200'}`}>
              {message.type === 'success' ? <CheckCircle className="w-4 h-4 text-emerald-600 shrink-0" /> : <AlertCircle className="w-4 h-4 text-rose-600 shrink-0" />}
              <span>{message.text}</span>
            </div>
          )}

          <form onSubmit={handleAddTerminal} className="space-y-3.5 text-xs">
            <div>
              <label className="block font-semibold text-slate-700 mb-1">Terminal ID (TID)*</label>
              <input
                id="epos-tid"
                type="text"
                placeholder="напр. 98234015"
                value={tid}
                onChange={(e) => setTid(e.target.value)}
                className="w-full py-2 px-3 border border-slate-200 rounded-lg text-xs font-mono focus:ring-1 focus:ring-indigo-500"
                required
              />
            </div>

            <div>
              <label className="block font-semibold text-slate-700 mb-1">Merchant ID (MID)</label>
              <input
                id="epos-mid"
                type="text"
                placeholder="напр. MERCH_LEGION_05"
                value={mid}
                onChange={(e) => setMid(e.target.value)}
                className="w-full py-2 px-3 border border-slate-200 rounded-lg text-xs font-mono focus:ring-1 focus:ring-indigo-500"
              />
            </div>

            <div>
              <label className="block font-semibold text-slate-700 mb-1">Банк-эквайер*</label>
              <select
                id="epos-bank"
                value={bank}
                onChange={(e) => setBank(e.target.value)}
                className="w-full py-2 px-3 border border-slate-200 rounded-lg text-xs focus:ring-1 focus:ring-indigo-500"
              >
                <option value="Kapital">Kapital Bank</option>
                <option value="Soliq">Soliq</option>
                <option value="NBU">NBU</option>
                <option value="Davr">Davr Bank</option>
                <option value="IpakYoli">Ipak Yoli</option>
                <option value="Другой">Другой</option>
              </select>
            </div>

            <div>
              <label className="block font-semibold text-slate-700 mb-1">Юр. лицо / Точка</label>
              <input
                id="epos-entity"
                type="text"
                placeholder="напр. ООО «Легион Трейд» филиал 2"
                value={entity}
                onChange={(e) => setEntity(e.target.value)}
                className="w-full py-2 px-3 border border-slate-200 rounded-lg text-xs focus:ring-1 focus:ring-indigo-500"
              />
            </div>

            <div>
              <label className="block font-semibold text-slate-700 mb-1">Комиссия (%)*</label>
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
              className="w-full mt-2 py-2.5 px-4 bg-indigo-600 hover:bg-indigo-700 text-white font-semibold rounded-lg shadow-xs transition-colors cursor-pointer"
            >
              Сохранить терминал
            </button>
          </form>
        </div>

        {/* Current Registry Table */}
        <div className="lg:col-span-2 bg-white rounded-2xl border border-slate-200 p-6 shadow-xs space-y-4">
          <div className="flex items-center justify-between border-b border-slate-100 pb-3">
            <h2 className="text-sm font-bold text-slate-900">
               Зарегистрированные терминалы ({terminals.length})
            </h2>
          </div>

          <div className="overflow-x-auto rounded-xl border border-slate-200 text-xs">
            <table className="min-w-full divide-y divide-slate-200">
              <thead className="bg-slate-50 font-bold text-slate-700">
                <tr>
                  <th className="px-3 py-2.5 text-left">TID</th>
                  <th className="px-3 py-2.5 text-left">MID</th>
                  <th className="px-3 py-2.5 text-left">Банк</th>
                  <th className="px-3 py-2.5 text-left">Юр. лицо</th>
                  <th className="px-3 py-2.5 text-right">Комиссия</th>
                  <th className="px-3 py-2.5 text-center">Активен</th>
                  <th className="px-3 py-2.5 text-right"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 bg-white">
                {terminals.map((t) => (
                  <tr key={t.terminal_id} className={`hover:bg-slate-50 ${t.is_active ? '' : 'opacity-60 bg-slate-50/50'}`}>
                    <td className="px-3 py-2.5 font-mono font-bold text-slate-900">{t.terminal_id}</td>
                    <td className="px-3 py-2.5 font-mono text-slate-600">{t.merchant_id}</td>
                    <td className="px-3 py-2.5 font-semibold text-indigo-700">{t.bank_acquirer}</td>
                    <td className="px-3 py-2.5 text-slate-700">{t.legal_entity}</td>
                    <td className="px-3 py-2.5 text-right font-bold text-slate-900">{t.commission_pct.toFixed(2)}%</td>
                    <td className="px-3 py-2.5 text-center">
                      <input
                        type="checkbox"
                        checked={t.is_active}
                        onChange={() => handleToggle(t.terminal_id)}
                        className="rounded text-indigo-600 cursor-pointer"
                      />
                    </td>
                    <td className="px-3 py-2.5 text-right">
                      <button
                        onClick={() => handleDelete(t.terminal_id)}
                        className="text-slate-400 hover:text-rose-600 transition-colors p-1"
                        title="Удалить"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
};
