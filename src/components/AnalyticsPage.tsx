import React, { useState, useMemo } from 'react';
import { BarChart3, TrendingUp, Calendar, Filter, Archive, CheckCircle, AlertCircle, Download, Trash2, ArrowUpDown, ArrowUp, ArrowDown, FolderOpen } from 'lucide-react';
import { ResponsiveContainer, BarChart, Bar, LineChart, Line, XAxis, YAxis, Tooltip, Legend, CartesianGrid } from 'recharts';
import * as XLSX from 'xlsx';
import { ReconciliationArchive, User } from '../types';
import { getArchiveData, deleteArchiveRecord, logAction } from '../utils/storage';
import { ConfirmModal } from './Modal';

interface AnalyticsPageProps {
  user: User;
}

type SortField = 'timestamp' | 'username' | 'bank_name' | 'total_our' | 'total_bank' | 'difference' | 'matched_count';

export const AnalyticsPage: React.FC<AnalyticsPageProps> = ({ user }) => {
  const [archive, setArchive] = useState<ReconciliationArchive[]>(getArchiveData());
  const [bankFilter, setBankFilter] = useState<string>('(Все)');

  // Sorting state
  const [sortField, setSortField] = useState<SortField>('timestamp');
  const [sortAsc, setSortAsc] = useState<boolean>(false); // default newest first

  // Delete modal state
  const [deleteConfirm, setDeleteConfirm] = useState<{
    isOpen: boolean;
    id: number;
    bankName: string;
    timestamp: string;
  }>({
    isOpen: false,
    id: 0,
    bankName: '',
    timestamp: '',
  });

  const banks = Array.from(new Set(archive.map(a => a.bank_name)));

  const filtered = useMemo(() => {
    return archive.filter(a => {
      if (bankFilter !== '(Все)' && a.bank_name !== bankFilter) return false;
      return true;
    });
  }, [archive, bankFilter]);

  const sortedFiltered = useMemo(() => {
    return [...filtered].sort((a, b) => {
      let res = 0;
      if (sortField === 'timestamp') {
        res = new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime();
      } else if (['total_our', 'total_bank', 'difference', 'matched_count'].includes(sortField)) {
        res = (a[sortField] as number) - (b[sortField] as number);
      } else {
        res = String(a[sortField] || '').localeCompare(String(b[sortField] || ''));
      }
      return sortAsc ? res : -res;
    });
  }, [filtered, sortField, sortAsc]);

  const totalOurVolume = filtered.reduce((acc, curr) => acc + curr.total_our, 0);
  const totalBankVolume = filtered.reduce((acc, curr) => acc + curr.total_bank, 0);
  const totalDifference = filtered.reduce((acc, curr) => acc + curr.difference, 0);
  const totalMatchedTxns = filtered.reduce((acc, curr) => acc + curr.matched_count, 0);

  const chartData = filtered.map(item => ({
    date: item.timestamp.slice(0, 10),
    bank: item.bank_name,
    our_vol: item.total_our,
    bank_vol: item.total_bank,
    diff: item.difference,
  })).reverse();

  const fmt = (n: number) => n.toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

  const toggleSort = (field: SortField) => {
    if (sortField === field) {
      setSortAsc(!sortAsc);
    } else {
      setSortField(field);
      setSortAsc(false); // default descending when switching
    }
  };

  const handleDeleteArchive = (item: ReconciliationArchive) => {
    setDeleteConfirm({
      isOpen: true,
      id: item.id,
      bankName: item.bank_name,
      timestamp: new Date(item.timestamp).toLocaleString('ru-RU'),
    });
  };

  const confirmDeleteArchive = () => {
    const { id, bankName, timestamp } = deleteConfirm;
    if (id) {
      deleteArchiveRecord(id);
      const updated = getArchiveData();
      setArchive(updated);
      logAction(user.username, 'DELETE_ARCHIVE', `Удалена запись сверки ${bankName} от ${timestamp}`);
    }
    setDeleteConfirm({ isOpen: false, id: 0, bankName: '', timestamp: '' });
  };

  const exportArchiveExcel = () => {
    const ws = XLSX.utils.json_to_sheet(sortedFiltered.map(f => ({
      'ID': f.id,
      'Дата и время': f.timestamp,
      'Оператор': f.username,
      'Банк': f.bank_name,
      'Сумма у нас': f.total_our,
      'Сумма банка': f.total_bank,
      'Разница': f.difference,
      'Совпадений': f.matched_count,
      'Расхождений сумм': f.mismatch_count,
      'Только у нас': f.only_our_count,
      'Только в банке': f.only_bank_count,
    })));
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, 'Архив_сверок');
    XLSX.writeFile(wb, `Архив_сверок_${new Date().toISOString().slice(0, 10)}.xlsx`);
  };

  return (
    <div className="p-8 max-w-7xl mx-auto space-y-6">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold text-slate-900 tracking-tight flex items-center gap-2">
            <span>Аналитика и архив сверок</span>
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            История завершённых сверок, тренды расхождений и финансовая динамика.
          </p>
        </div>

        {archive.length > 0 && (
          <button
            onClick={exportArchiveExcel}
            className="inline-flex items-center gap-2 px-3.5 py-2 bg-white hover:bg-slate-50 text-slate-700 text-xs font-semibold rounded-xl border border-slate-200 transition-colors cursor-pointer shadow-xs"
          >
            <Download className="w-3.5 h-3.5 text-emerald-600" />
            <span>Экспорт архива в Excel</span>
          </button>
        )}
      </div>

      {archive.length === 0 ? (
        /* Empty State when no reconciliation records exist */
        <div className="bg-white rounded-2xl border border-slate-200 p-12 text-center shadow-xs space-y-4 max-w-xl mx-auto my-12">
          <div className="w-14 h-14 bg-indigo-50 text-indigo-600 rounded-2xl flex items-center justify-center mx-auto">
            <Archive className="w-7 h-7" />
          </div>
          <div className="space-y-1.5">
            <h3 className="text-base font-bold text-slate-900">В архиве пока нет проведённых сверок</h3>
            <p className="text-xs text-slate-500 max-w-md mx-auto leading-relaxed">
              Загрузите реестры и выписку во вкладке «Сверка по RRN», нажмите «Запустить сверку транзакций» и сохраните результат в архив. Здесь появятся графики и детальный журнал.
            </p>
          </div>
        </div>
      ) : (
        <>
          {/* Filter Bar */}
          <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-xs flex items-center justify-between gap-4">
            <div className="flex items-center gap-4">
              <div className="flex items-center gap-2 text-xs font-semibold text-slate-700">
                <Filter className="w-4 h-4 text-slate-400" />
                <span>Фильтр по банку:</span>
              </div>
              <select
                value={bankFilter}
                onChange={(e) => setBankFilter(e.target.value)}
                className="py-1.5 px-3 bg-slate-50 border border-slate-200 rounded-lg text-xs font-medium text-slate-800"
              >
                <option value="(Все)">(Все банки)</option>
                {banks.map(b => <option key={b} value={b}>{b}</option>)}
              </select>
            </div>
            {bankFilter !== '(Все)' && (
              <button
                onClick={() => setBankFilter('(Все)')}
                className="text-xs text-slate-500 hover:text-slate-800 font-medium"
              >
                Сбросить фильтр
              </button>
            )}
          </div>

          {filtered.length === 0 ? (
            <div className="bg-white rounded-2xl border border-slate-200 p-8 text-center text-xs text-slate-500 space-y-2">
              <FolderOpen className="w-8 h-8 text-slate-300 mx-auto" />
              <p>По банку «{bankFilter}» не найдено сохранённых сверок.</p>
              <button
                onClick={() => setBankFilter('(Все)')}
                className="text-indigo-600 font-semibold hover:underline"
              >
                Показать все банки
              </button>
            </div>
          ) : (
            <>
              {/* Metric Cards */}
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                <div className="min-w-0 bg-white rounded-2xl border border-slate-200 p-5 shadow-xs">
                  <div className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">Всего сверок</div>
                  <div className="text-xl font-bold text-slate-900 mt-1 break-words tabular-nums">{filtered.length}</div>
                  <div className="text-[11px] text-slate-400 mt-1">в базе данных</div>
                </div>

                <div className="min-w-0 bg-white rounded-2xl border border-slate-200 p-5 shadow-xs">
                  <div className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">Объём (Наши данные)</div>
                  <div className="text-xl font-bold text-indigo-600 mt-1 break-words tabular-nums">{fmt(totalOurVolume)}</div>
                  <div className="text-[11px] text-slate-400 mt-1">UZS</div>
                </div>

                <div className="min-w-0 bg-white rounded-2xl border border-slate-200 p-5 shadow-xs">
                  <div className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">Объём (Банк)</div>
                  <div className="text-xl font-bold text-emerald-600 mt-1 break-words tabular-nums">{fmt(totalBankVolume)}</div>
                  <div className="text-[11px] text-slate-400 mt-1">UZS</div>
                </div>

                <div className="min-w-0 bg-white rounded-2xl border border-slate-200 p-5 shadow-xs">
                  <div className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">Суммарная разница (Δ)</div>
                  <div className={`text-xl font-bold mt-1 break-words tabular-nums ${Math.abs(totalDifference) < 1 ? 'text-emerald-600' : 'text-rose-600'}`}>
                    {totalDifference > 0 ? `+${fmt(totalDifference)}` : fmt(totalDifference)}
                  </div>
                  <div className="text-[11px] text-slate-400 mt-1">UZS</div>
                </div>
              </div>

              {/* Historical Charts */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-xs">
                  <h2 className="text-sm font-bold text-slate-900 mb-4">
                    <div className="flex items-center gap-1.5"><BarChart3 className="w-4 h-4 text-indigo-600"/> Динамика сведённых объёмов</div>
                  </h2>
                  <div className="h-64">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={chartData} margin={{ top: 10, right: 10, left: 10, bottom: 20 }}>
                        <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
                        <XAxis dataKey="date" tick={{ fontSize: 10 }} />
                        <YAxis tick={{ fontSize: 10 }} />
                        <Tooltip formatter={(v: number) => fmt(v)} />
                        <Legend wrapperStyle={{ fontSize: 11 }} />
                        <Bar dataKey="our_vol" name="Наши данные" fill="#4f46e5" radius={[4, 4, 0, 0]} />
                        <Bar dataKey="bank_vol" name="Банк" fill="#059669" radius={[4, 4, 0, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                </div>

                <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-xs">
                  <h2 className="text-sm font-bold text-slate-900 mb-4">
                    <div className="flex items-center gap-1.5"><TrendingUp className="w-4 h-4 text-rose-600"/> Тренд расхождений (Δ)</div>
                  </h2>
                  <div className="h-64">
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={chartData} margin={{ top: 10, right: 10, left: 10, bottom: 20 }}>
                        <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
                        <XAxis dataKey="date" tick={{ fontSize: 10 }} />
                        <YAxis tick={{ fontSize: 10 }} />
                        <Tooltip formatter={(v: number) => fmt(v)} />
                        <Legend wrapperStyle={{ fontSize: 11 }} />
                        <Line type="monotone" dataKey="diff" name="Разница (Банк - Мы)" stroke="#e11d48" strokeWidth={2} dot={{ r: 4 }} />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                </div>
              </div>

              {/* Archive Records Table */}
              <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-xs space-y-4">
                <h2 className="text-sm font-bold text-slate-900">
                  <div className="flex items-center gap-1.5"><Archive className="w-4 h-4 text-emerald-600"/> Журнал проведённых сверок</div>
                </h2>

                <div className="overflow-x-auto rounded-xl border border-slate-200 text-xs">
                  <table className="min-w-full divide-y divide-slate-200">
                    <thead className="bg-slate-50 font-bold text-slate-700 select-none">
                      <tr>
                        <th 
                          onClick={() => toggleSort('timestamp')}
                          className="px-3 py-2.5 text-left cursor-pointer hover:bg-slate-100 transition-colors"
                        >
                          <div className="flex items-center gap-1">
                            <span>Дата / Время</span>
                            {sortField === 'timestamp' ? (
                              sortAsc ? <ArrowUp className="w-3.5 h-3.5 text-indigo-600" /> : <ArrowDown className="w-3.5 h-3.5 text-indigo-600" />
                            ) : <ArrowUpDown className="w-3.5 h-3.5 text-slate-400" />}
                          </div>
                        </th>
                        <th 
                          onClick={() => toggleSort('username')}
                          className="px-3 py-2.5 text-left cursor-pointer hover:bg-slate-100 transition-colors"
                        >
                          <div className="flex items-center gap-1">
                            <span>Оператор</span>
                            {sortField === 'username' ? (
                              sortAsc ? <ArrowUp className="w-3.5 h-3.5 text-indigo-600" /> : <ArrowDown className="w-3.5 h-3.5 text-indigo-600" />
                            ) : <ArrowUpDown className="w-3.5 h-3.5 text-slate-400" />}
                          </div>
                        </th>
                        <th 
                          onClick={() => toggleSort('bank_name')}
                          className="px-3 py-2.5 text-left cursor-pointer hover:bg-slate-100 transition-colors"
                        >
                          <div className="flex items-center gap-1">
                            <span>Банк</span>
                            {sortField === 'bank_name' ? (
                              sortAsc ? <ArrowUp className="w-3.5 h-3.5 text-indigo-600" /> : <ArrowDown className="w-3.5 h-3.5 text-indigo-600" />
                            ) : <ArrowUpDown className="w-3.5 h-3.5 text-slate-400" />}
                          </div>
                        </th>
                        <th 
                          onClick={() => toggleSort('total_our')}
                          className="px-3 py-2.5 text-right cursor-pointer hover:bg-slate-100 transition-colors"
                        >
                          <div className="flex items-center justify-end gap-1">
                            <span>Сумма (Мы)</span>
                            {sortField === 'total_our' ? (
                              sortAsc ? <ArrowUp className="w-3.5 h-3.5 text-indigo-600" /> : <ArrowDown className="w-3.5 h-3.5 text-indigo-600" />
                            ) : <ArrowUpDown className="w-3.5 h-3.5 text-slate-400" />}
                          </div>
                        </th>
                        <th 
                          onClick={() => toggleSort('total_bank')}
                          className="px-3 py-2.5 text-right cursor-pointer hover:bg-slate-100 transition-colors"
                        >
                          <div className="flex items-center justify-end gap-1">
                            <span>Сумма (Банк)</span>
                            {sortField === 'total_bank' ? (
                              sortAsc ? <ArrowUp className="w-3.5 h-3.5 text-indigo-600" /> : <ArrowDown className="w-3.5 h-3.5 text-indigo-600" />
                            ) : <ArrowUpDown className="w-3.5 h-3.5 text-slate-400" />}
                          </div>
                        </th>
                        <th 
                          onClick={() => toggleSort('difference')}
                          className="px-3 py-2.5 text-right cursor-pointer hover:bg-slate-100 transition-colors"
                        >
                          <div className="flex items-center justify-end gap-1">
                            <span>Разница (Δ)</span>
                            {sortField === 'difference' ? (
                              sortAsc ? <ArrowUp className="w-3.5 h-3.5 text-indigo-600" /> : <ArrowDown className="w-3.5 h-3.5 text-indigo-600" />
                            ) : <ArrowUpDown className="w-3.5 h-3.5 text-slate-400" />}
                          </div>
                        </th>
                        <th 
                          onClick={() => toggleSort('matched_count')}
                          className="px-3 py-2.5 text-center cursor-pointer hover:bg-slate-100 transition-colors"
                        >
                          <div className="flex items-center justify-center gap-1">
                            <span>Совпало</span>
                            {sortField === 'matched_count' ? (
                              sortAsc ? <ArrowUp className="w-3.5 h-3.5 text-indigo-600" /> : <ArrowDown className="w-3.5 h-3.5 text-indigo-600" />
                            ) : <ArrowUpDown className="w-3.5 h-3.5 text-slate-400" />}
                          </div>
                        </th>
                        <th className="px-3 py-2.5 text-center">Расхожд.</th>
                        {user.role !== 'auditor' && <th className="px-3 py-2.5 text-right"></th>}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100 bg-white">
                      {sortedFiltered.map((item) => (
                        <tr key={item.id} className="hover:bg-slate-50 transition-colors">
                          <td className="px-3 py-2.5 text-slate-700 whitespace-nowrap">
                            {new Date(item.timestamp).toLocaleString('ru-RU')}
                          </td>
                          <td className="px-3 py-2.5 font-medium text-slate-900">{item.username}</td>
                          <td className="px-3 py-2.5 font-semibold text-indigo-700">{item.bank_name}</td>
                          <td className="px-3 py-2.5 text-right text-slate-800 tabular-nums tracking-tight whitespace-nowrap">{fmt(item.total_our)}</td>
                          <td className="px-3 py-2.5 text-right text-slate-800 tabular-nums tracking-tight whitespace-nowrap">{fmt(item.total_bank)}</td>
                          <td className={`px-3 py-2.5 text-right font-bold ${Math.abs(item.difference) < 1 ? 'text-emerald-600' : 'text-rose-600'}`}>
                            {item.difference > 0 ? `+${fmt(item.difference)}` : fmt(item.difference)}
                          </td>
                          <td className="px-3 py-2.5 text-center text-emerald-700 font-semibold">{item.matched_count}</td>
                          <td className="px-3 py-2.5 text-center text-amber-700 font-semibold">{item.mismatch_count + item.only_our_count + item.only_bank_count}</td>
                          {user.role !== 'auditor' && (
                            <td className="px-3 py-2.5 text-right">
                              <button
                                onClick={() => handleDeleteArchive(item)}
                                className="text-slate-400 hover:text-rose-600 transition-colors p-1 cursor-pointer"
                                title="Удалить запись из архива"
                              >
                                <Trash2 className="w-3.5 h-3.5" />
                              </button>
                            </td>
                          )}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </>
          )}
        </>
      )}

      {/* Delete Confirmation Modal */}
      <ConfirmModal
        isOpen={deleteConfirm.isOpen}
        title="Удаление записи из архива"
        message={`Удалить запись сверки банка «${deleteConfirm.bankName}» от ${deleteConfirm.timestamp}? Данные будут стёрты из архива.`}
        confirmText="Удалить"
        isDanger={true}
        onConfirm={confirmDeleteArchive}
        onClose={() => setDeleteConfirm({ isOpen: false, id: 0, bankName: '', timestamp: '' })}
      />
    </div>
  );
};
