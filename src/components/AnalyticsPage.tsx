import React, { useEffect, useState, useMemo } from 'react';
import {
  BarChart3, TrendingUp, Calendar, Filter, Archive, CheckCircle, AlertCircle,
  Download, Trash2, ArrowUpDown, ArrowUp, ArrowDown, FolderOpen, Building2,
  Percent, Coins, Layers, Eye, Search, X
} from 'lucide-react';
import {
  ResponsiveContainer, BarChart, Bar, LineChart, Line, XAxis, YAxis,
  Tooltip, Legend, CartesianGrid, Cell
} from 'recharts';
import * as XLSX from 'xlsx';
import { ReconciliationArchive, TerminalSummaryItem, User } from '../types';
import { deleteBankRrnArchive, getBankRrnArchive } from '../utils/archiveApi';
import { ConfirmModal } from './Modal';

interface AnalyticsPageProps {
  user: User;
}

type SortField = 'timestamp' | 'username' | 'bank_name' | 'period_month' | 'total_our' | 'total_bank' | 'difference' | 'matched_count' | 'total_commission';

interface FlatTerminalRecord extends TerminalSummaryItem {
  archive_id: number;
  archive_timestamp: string;
  archive_bank: string;
  period_month: string;
}

export const AnalyticsPage: React.FC<AnalyticsPageProps> = ({ user }) => {
  const [archive, setArchive] = useState<ReconciliationArchive[]>([]);
  const [archiveError, setArchiveError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'banks' | 'terminals'>('banks');

  const refreshArchive = async () => {
    setArchiveError(null);
    try {
      setArchive(await getBankRrnArchive(user.username));
    } catch (error: any) {
      setArchiveError(error?.message || 'Не удалось загрузить серверный архив.');
    }
  };

  useEffect(() => {
    void refreshArchive();
  }, [user.username]);

  // Filters
  const [bankFilter, setBankFilter] = useState<string>('(Все)');
  const [monthFilter, setMonthFilter] = useState<string>('(Все)');
  const [terminalFilter, setTerminalFilter] = useState<string>('(Все)');
  const [searchTidQuery, setSearchTidQuery] = useState<string>('');

  // Sorting state for recons
  const [sortField, setSortField] = useState<SortField>('timestamp');
  const [sortAsc, setSortAsc] = useState<boolean>(false); // default newest first

  // Selected archive record for detailed terminal inspection modal
  const [inspectRecord, setInspectRecord] = useState<ReconciliationArchive | null>(null);

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

  // Extract unique filter options
  const banks = useMemo(() => {
    return Array.from(new Set(archive.map(a => a.bank_name).filter(Boolean))).sort();
  }, [archive]);

  const months = useMemo(() => {
    const list = new Set<string>();
    archive.forEach(a => {
      if (a.period_month) {
        list.add(a.period_month);
      } else if (a.timestamp) {
        list.add(a.timestamp.slice(0, 7));
      }
    });
    return Array.from(list).sort().reverse();
  }, [archive]);

  // Flatten all terminal items from all archive records
  const allTerminalRecords = useMemo<FlatTerminalRecord[]>(() => {
    const list: FlatTerminalRecord[] = [];
    archive.forEach(rec => {
      const pMonth = rec.period_month || (rec.timestamp ? rec.timestamp.slice(0, 7) : '—');
      if (rec.terminals_summary && Array.isArray(rec.terminals_summary)) {
        rec.terminals_summary.forEach(term => {
          list.push({
            ...term,
            archive_id: rec.id,
            archive_timestamp: rec.timestamp,
            archive_bank: rec.bank_name,
            period_month: pMonth,
          });
        });
      }
    });
    return list;
  }, [archive]);

  const availableTids = useMemo(() => {
    return Array.from(new Set(allTerminalRecords.map(t => t.terminal_id))).sort();
  }, [allTerminalRecords]);

  // Filtered Archive Records
  const filteredArchive = useMemo(() => {
    return archive.filter(a => {
      if (bankFilter !== '(Все)' && a.bank_name !== bankFilter) return false;
      const recMonth = a.period_month || (a.timestamp ? a.timestamp.slice(0, 7) : '');
      if (monthFilter !== '(Все)' && recMonth !== monthFilter) return false;
      if (terminalFilter !== '(Все)') {
        const hasTid = a.terminals_summary?.some(t => t.terminal_id === terminalFilter);
        if (!hasTid) return false;
      }
      return true;
    });
  }, [archive, bankFilter, monthFilter, terminalFilter]);

  // Sorted Archive
  const sortedArchive = useMemo(() => {
    return [...filteredArchive].sort((a, b) => {
      let res = 0;
      if (sortField === 'timestamp') {
        res = new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime();
      } else if (sortField === 'period_month') {
        res = String(a.period_month || '').localeCompare(String(b.period_month || ''));
      } else if (['total_our', 'total_bank', 'difference', 'matched_count', 'total_commission'].includes(sortField)) {
        const valA = (a[sortField] as number) || 0;
        const valB = (b[sortField] as number) || 0;
        res = valA - valB;
      } else {
        res = String(a[sortField] || '').localeCompare(String(b[sortField] || ''));
      }
      return sortAsc ? res : -res;
    });
  }, [filteredArchive, sortField, sortAsc]);

  // Filtered Terminal Records
  const filteredTerminals = useMemo(() => {
    return allTerminalRecords.filter(t => {
      if (bankFilter !== '(Все)' && t.archive_bank !== bankFilter && t.bank_acquirer !== bankFilter) return false;
      if (monthFilter !== '(Все)' && t.period_month !== monthFilter) return false;
      if (terminalFilter !== '(Все)' && t.terminal_id !== terminalFilter) return false;
      if (searchTidQuery.trim()) {
        const q = searchTidQuery.toLowerCase().trim();
        const matchesTid = t.terminal_id.toLowerCase().includes(q);
        const matchesLegal = (t.legal_entity || '').toLowerCase().includes(q);
        const matchesMerchant = (t.merchant_id || '').toLowerCase().includes(q);
        if (!matchesTid && !matchesLegal && !matchesMerchant) return false;
      }
      return true;
    });
  }, [allTerminalRecords, bankFilter, monthFilter, terminalFilter, searchTidQuery]);

  // Aggregate stats
  const totalOurVolume = filteredArchive.reduce((acc, curr) => acc + curr.total_our, 0);
  const totalBankVolume = filteredArchive.reduce((acc, curr) => acc + curr.total_bank, 0);
  const totalDifference = filteredArchive.reduce((acc, curr) => acc + curr.difference, 0);
  const totalCommissionArchive = filteredArchive.reduce((acc, curr) => acc + (curr.total_commission || 0), 0);

  // Terminals aggregate stats
  const totalTerminalVolume = filteredTerminals.reduce((acc, curr) => acc + curr.total_volume, 0);
  const totalTerminalCommission = filteredTerminals.reduce((acc, curr) => acc + curr.commission_amount, 0);
  const totalTerminalNetVolume = filteredTerminals.reduce((acc, curr) => acc + curr.net_volume, 0);
  const totalTerminalTxCount = filteredTerminals.reduce((acc, curr) => acc + curr.tx_count, 0);
  const avgEffectiveRate = totalTerminalVolume > 0 ? (totalTerminalCommission / totalTerminalVolume) * 100 : 0;

  // Chart data for banks
  const chartData = filteredArchive.map(item => ({
    date: item.period_month || item.timestamp.slice(0, 10),
    bank: item.bank_name,
    our_vol: item.total_our,
    bank_vol: item.total_bank,
    commission: item.total_commission || 0,
    diff: item.difference,
  })).reverse();

  // Top 10 terminals chart data
  const topTerminalsChartData = useMemo(() => {
    const grouped = new Map<string, { tid: string; volume: number; commission: number; net: number }>();
    filteredTerminals.forEach(t => {
      const cur = grouped.get(t.terminal_id) || { tid: t.terminal_id, volume: 0, commission: 0, net: 0 };
      cur.volume += t.total_volume;
      cur.commission += t.commission_amount;
      cur.net += t.net_volume;
      grouped.set(t.terminal_id, cur);
    });
    return Array.from(grouped.values())
      .sort((a, b) => b.volume - a.volume)
      .slice(0, 10);
  }, [filteredTerminals]);

  const fmt = (n: number) => n.toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

  const toggleSort = (field: SortField) => {
    if (sortField === field) {
      setSortAsc(!sortAsc);
    } else {
      setSortField(field);
      setSortAsc(false);
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

  const confirmDeleteArchive = async () => {
    const { id } = deleteConfirm;
    if (id) {
      try {
        await deleteBankRrnArchive(user.username, id);
        await refreshArchive();
      } catch (error: any) {
        setArchiveError(error?.message || 'Не удалось удалить запись архива.');
      }
    }
    setDeleteConfirm({ isOpen: false, id: 0, bankName: '', timestamp: '' });
  };

  const resetAllFilters = () => {
    setBankFilter('(Все)');
    setMonthFilter('(Все)');
    setTerminalFilter('(Все)');
    setSearchTidQuery('');
  };

  const hasActiveFilters = bankFilter !== '(Все)' || monthFilter !== '(Все)' || terminalFilter !== '(Все)' || searchTidQuery.trim() !== '';

  const exportArchiveExcel = () => {
    const wb = XLSX.utils.book_new();

    // Sheet 1: Сводка_сверок
    const cleanArchive = sortedArchive.map(f => ({
      'ID': f.id,
      'Дата и время': f.timestamp,
      'Отчётный месяц': f.period_month || '',
      'Оператор': f.username,
      'Банк': f.bank_name,
      'Сумма у нас': f.total_our,
      'Сумма банка': f.total_bank,
      'Разница (Δ)': f.difference,
      'Комиссия EPOS': f.total_commission || 0,
      'Совпадений': f.matched_count,
      'Расхождений сумм': f.mismatch_count,
      'Только у нас': f.only_our_count,
      'Только в банке': f.only_bank_count,
      'Терминалов в записи': f.terminals_summary?.length || 0,
    }));
    const wsArchive = XLSX.utils.json_to_sheet(cleanArchive.length ? cleanArchive : [{ 'Статус': 'Нет данных' }]);
    XLSX.utils.book_append_sheet(wb, wsArchive, 'Сводка_сверок');

    // Sheet 2: Аналитика_по_терминалам
    if (filteredTerminals.length > 0) {
      const cleanTerminals = filteredTerminals.map(t => ({
        'TID Терминала': t.terminal_id,
        'Банк-эквайер': t.bank_acquirer || t.archive_bank,
        'Мерчант / MID': t.merchant_id || '',
        'Юр. лицо / Точка': t.legal_entity || '',
        'Отчётный месяц': t.period_month,
        'Транзакций': t.tx_count,
        'Оборот (UZS)': t.total_volume,
        'Ставка комиссии (%)': t.commission_pct,
        'Сумма комиссии (UZS)': t.commission_amount,
        'К зачислению нетто (UZS)': t.net_volume,
        'Дата фиксации': t.archive_timestamp,
      }));
      const wsTerm = XLSX.utils.json_to_sheet(cleanTerminals);
      XLSX.utils.book_append_sheet(wb, wsTerm, 'Аналитика_терминалов');
    }

    XLSX.writeFile(wb, `Аналитика_сверок_и_терминалов_${new Date().toISOString().slice(0, 10)}.xlsx`);
  };

  return (
    <div className="p-8 max-w-7xl mx-auto space-y-6">
      {archiveError && (
        <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-xs text-rose-700">
          {archiveError}
        </div>
      )}
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold text-slate-900 tracking-tight flex items-center gap-2">
            <span>Аналитика и архив сверок</span>
            <span className="text-xs font-semibold px-2.5 py-0.5 rounded-full bg-indigo-50 text-indigo-700 border border-indigo-200">
              EPOS Analytics
            </span>
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            История завершённых сверок, детализация по месяцам, аналитика комиссий и оборота в разрезе терминалов.
          </p>
        </div>

        {archive.length > 0 && (
          <button
            onClick={exportArchiveExcel}
            className="inline-flex items-center gap-2 px-4 py-2.5 bg-white hover:bg-slate-50 text-slate-700 text-xs font-semibold rounded-xl border border-slate-200 transition-colors cursor-pointer shadow-xs"
          >
            <Download className="w-4 h-4 text-emerald-600" />
            <span>Экспорт в Excel со всеми вкладками</span>
          </button>
        )}
      </div>

      {archive.length === 0 ? (
        /* Empty State */
        <div className="bg-white rounded-2xl border border-slate-200 p-12 text-center shadow-xs space-y-4 max-w-xl mx-auto my-12">
          <div className="w-14 h-14 bg-indigo-50 text-indigo-600 rounded-2xl flex items-center justify-center mx-auto">
            <Archive className="w-7 h-7" />
          </div>
          <div className="space-y-1.5">
            <h3 className="text-base font-bold text-slate-900">В архиве пока нет проведённых сверок</h3>
            <p className="text-xs text-slate-500 max-w-md mx-auto leading-relaxed">
              Загрузите реестры во вкладке «Сверка по RRN», нажмите «Запустить сверку транзакций» и запишите результат в архив базы данных с выбором месяца. Здесь появится полный финансовый анализ.
            </p>
          </div>
        </div>
      ) : (
        <>
          {/* ─── FILTERS BAR ─── */}
          <div className="bg-white rounded-2xl border border-slate-200 p-4 shadow-xs flex flex-wrap items-center justify-between gap-4">
            <div className="flex flex-wrap items-center gap-3">
              <div className="flex items-center gap-1.5 text-xs font-bold text-slate-700">
                <Filter className="w-4 h-4 text-indigo-600" />
                <span>Фильтры:</span>
              </div>

              {/* Month Selector */}
              <div className="flex items-center gap-1.5 bg-slate-50 border border-slate-200 rounded-xl px-2.5 py-1 text-xs">
                <Calendar className="w-3.5 h-3.5 text-slate-500" />
                <span className="text-slate-500 font-medium">Месяц:</span>
                <select
                  value={monthFilter}
                  onChange={(e) => setMonthFilter(e.target.value)}
                  className="bg-transparent font-semibold text-slate-800 focus:outline-none cursor-pointer"
                >
                  <option value="(Все)">(Все месяцы)</option>
                  {months.map(m => (
                    <option key={m} value={m}>{m}</option>
                  ))}
                </select>
              </div>

              {/* Bank Selector */}
              <div className="flex items-center gap-1.5 bg-slate-50 border border-slate-200 rounded-xl px-2.5 py-1 text-xs">
                <Building2 className="w-3.5 h-3.5 text-slate-500" />
                <span className="text-slate-500 font-medium">Банк:</span>
                <select
                  value={bankFilter}
                  onChange={(e) => setBankFilter(e.target.value)}
                  className="bg-transparent font-semibold text-slate-800 focus:outline-none cursor-pointer"
                >
                  <option value="(Все)">(Все банки)</option>
                  {banks.map(b => (
                    <option key={b} value={b}>{b}</option>
                  ))}
                </select>
              </div>

              {/* Terminal Selector */}
              <div className="flex items-center gap-1.5 bg-slate-50 border border-slate-200 rounded-xl px-2.5 py-1 text-xs">
                <Layers className="w-3.5 h-3.5 text-slate-500" />
                <span className="text-slate-500 font-medium">Терминал (TID):</span>
                <select
                  value={terminalFilter}
                  onChange={(e) => setTerminalFilter(e.target.value)}
                  className="bg-transparent font-semibold text-slate-800 focus:outline-none cursor-pointer"
                >
                  <option value="(Все)">(Все терминалы)</option>
                  {availableTids.map(t => (
                    <option key={t} value={t}>{t}</option>
                  ))}
                </select>
              </div>
            </div>

            {hasActiveFilters && (
              <button
                type="button"
                onClick={resetAllFilters}
                className="text-xs font-semibold text-rose-600 hover:text-rose-800 transition-colors flex items-center gap-1 cursor-pointer"
              >
                <X className="w-3.5 h-3.5" />
                <span>Сбросить фильтры</span>
              </button>
            )}
          </div>

          {/* ─── TAB NAVIGATION ─── */}
          <div className="flex border-b border-slate-200 gap-2 overflow-x-auto">
            <button
              onClick={() => setActiveTab('banks')}
              className={`pb-3 px-3 text-xs font-semibold border-b-2 transition-all whitespace-nowrap cursor-pointer ${
                activeTab === 'banks' ? 'border-indigo-600 text-indigo-700' : 'border-transparent text-slate-500 hover:text-slate-800'
              }`}
            >
              <div className="flex items-center gap-1.5">
                <BarChart3 className="w-4 h-4" />
                <span>Сводка по банкам и сверкам ({filteredArchive.length})</span>
              </div>
            </button>

            <button
              onClick={() => setActiveTab('terminals')}
              className={`pb-3 px-3 text-xs font-semibold border-b-2 transition-all whitespace-nowrap cursor-pointer ${
                activeTab === 'terminals' ? 'border-indigo-600 text-indigo-700' : 'border-transparent text-slate-500 hover:text-slate-800'
              }`}
            >
              <div className="flex items-center gap-1.5">
                <Building2 className="w-4 h-4" />
                <span>Аналитика по терминалам и комиссии EPOS ({filteredTerminals.length})</span>
              </div>
            </button>
          </div>

          {/* ─── VIEW 1: BANKS & RECONCILIATIONS ─── */}
          {activeTab === 'banks' && (
            <div className="space-y-6">
              {filteredArchive.length === 0 ? (
                <div className="bg-white rounded-2xl border border-slate-200 p-8 text-center text-xs text-slate-500 space-y-2">
                  <FolderOpen className="w-8 h-8 text-slate-300 mx-auto" />
                  <p>По выбранным фильтрам не найдено сохранённых сверок.</p>
                  <button
                    onClick={resetAllFilters}
                    className="text-indigo-600 font-semibold hover:underline"
                  >
                    Сбросить фильтры
                  </button>
                </div>
              ) : (
                <>
                  {/* Metric Cards */}
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                    <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-xs">
                      <div className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">Всего сверок</div>
                      <div className="text-xl font-bold text-slate-900 mt-1 tabular-nums">{filteredArchive.length}</div>
                      <div className="text-[11px] text-slate-400 mt-0.5">В текущей выборке</div>
                    </div>

                    <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-xs">
                      <div className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">Объём (Наши данные)</div>
                      <div className="text-lg font-bold text-indigo-600 mt-1 break-words tabular-nums">{fmt(totalOurVolume)} UZS</div>
                      <div className="text-[11px] text-slate-400 mt-0.5">По реестру 1C / учету</div>
                    </div>

                    <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-xs">
                      <div className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">Объём (Банк)</div>
                      <div className="text-lg font-bold text-emerald-600 mt-1 break-words tabular-nums">{fmt(totalBankVolume)} UZS</div>
                      <div className="text-[11px] text-slate-400 mt-0.5">Номинальная сумма операций</div>
                    </div>

                    <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-xs">
                      <div className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">Комиссия EPOS (в архиве)</div>
                      <div className="text-lg font-bold text-rose-600 mt-1 break-words tabular-nums">{fmt(totalCommissionArchive)} UZS</div>
                      <div className="text-[11px] text-slate-400 mt-0.5">
                        Разница (Δ): <span className={Math.abs(totalDifference) < 1 ? 'text-emerald-600 font-semibold' : 'text-rose-600 font-semibold'}>{fmt(totalDifference)} UZS</span>
                      </div>
                    </div>
                  </div>

                  {/* Historical Charts */}
                  <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                    <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-xs">
                      <h2 className="text-sm font-bold text-slate-900 mb-4 flex items-center gap-1.5">
                        <BarChart3 className="w-4 h-4 text-indigo-600" />
                        <span>Динамика сведённых объёмов (Мы vs Банк)</span>
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
                      <h2 className="text-sm font-bold text-slate-900 mb-4 flex items-center gap-1.5">
                        <TrendingUp className="w-4 h-4 text-rose-600" />
                        <span>Тренд расхождений (Δ = Банк - Мы)</span>
                      </h2>
                      <div className="h-64">
                        <ResponsiveContainer width="100%" height="100%">
                          <LineChart data={chartData} margin={{ top: 10, right: 10, left: 10, bottom: 20 }}>
                            <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
                            <XAxis dataKey="date" tick={{ fontSize: 10 }} />
                            <YAxis tick={{ fontSize: 10 }} />
                            <Tooltip formatter={(v: number) => fmt(v)} />
                            <Legend wrapperStyle={{ fontSize: 11 }} />
                            <Line type="monotone" dataKey="diff" name="Разница (Δ)" stroke="#e11d48" strokeWidth={2} dot={{ r: 4 }} />
                          </LineChart>
                        </ResponsiveContainer>
                      </div>
                    </div>
                  </div>

                  {/* Archive Table */}
                  <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-xs space-y-4">
                    <div className="flex items-center justify-between">
                      <h2 className="text-sm font-bold text-slate-900 flex items-center gap-1.5">
                        <Archive className="w-4 h-4 text-emerald-600" />
                        <span>Журнал проведённых сверок</span>
                      </h2>
                      <span className="text-xs text-slate-500">
                        Отображено записей: {sortedArchive.length}
                      </span>
                    </div>

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
                              onClick={() => toggleSort('period_month')}
                              className="px-3 py-2.5 text-left cursor-pointer hover:bg-slate-100 transition-colors"
                            >
                              <div className="flex items-center gap-1">
                                <span>Месяц</span>
                                {sortField === 'period_month' ? (
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
                              onClick={() => toggleSort('total_commission')}
                              className="px-3 py-2.5 text-right cursor-pointer hover:bg-slate-100 transition-colors"
                            >
                              <div className="flex items-center justify-end gap-1">
                                <span>Комиссия EPOS</span>
                                {sortField === 'total_commission' ? (
                                  sortAsc ? <ArrowUp className="w-3.5 h-3.5 text-indigo-600" /> : <ArrowDown className="w-3.5 h-3.5 text-indigo-600" />
                                ) : <ArrowUpDown className="w-3.5 h-3.5 text-slate-400" />}
                              </div>
                            </th>
                            <th className="px-3 py-2.5 text-center">Терминалы</th>
                            <th className="px-3 py-2.5 text-center">Совпало</th>
                            <th className="px-3 py-2.5 text-center">Расхожд.</th>
                            {user.role !== 'auditor' && <th className="px-3 py-2.5 text-right"></th>}
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100 bg-white">
                          {sortedArchive.map((item) => {
                            const termCount = item.terminals_summary?.length || 0;
                            return (
                              <tr key={item.id} className="hover:bg-slate-50 transition-colors">
                                <td className="px-3 py-2.5 text-slate-700 whitespace-nowrap">
                                  {new Date(item.timestamp).toLocaleString('ru-RU')}
                                </td>
                                <td className="px-3 py-2.5 font-mono font-medium text-slate-800">
                                  {item.period_month || item.timestamp.slice(0, 7)}
                                </td>
                                <td className="px-3 py-2.5 font-semibold text-indigo-700">{item.bank_name}</td>
                                <td className="px-3 py-2.5 text-right text-slate-800 tabular-nums tracking-tight whitespace-nowrap">{fmt(item.total_our)}</td>
                                <td className="px-3 py-2.5 text-right text-slate-800 tabular-nums tracking-tight whitespace-nowrap">{fmt(item.total_bank)}</td>
                                <td className={`px-3 py-2.5 text-right font-bold ${Math.abs(item.difference) < 1 ? 'text-emerald-600' : 'text-rose-600'}`}>
                                  {item.difference > 0 ? `+${fmt(item.difference)}` : fmt(item.difference)}
                                </td>
                                <td className="px-3 py-2.5 text-right font-semibold text-rose-600 tabular-nums whitespace-nowrap">
                                  {item.total_commission ? fmt(item.total_commission) : '0,00'}
                                </td>
                                <td className="px-3 py-2.5 text-center">
                                  {termCount > 0 ? (
                                    <button
                                      type="button"
                                      onClick={() => setInspectRecord(item)}
                                      className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-indigo-50 hover:bg-indigo-100 text-indigo-700 font-semibold text-[11px] transition-colors cursor-pointer"
                                      title="Посмотреть список терминалов этой сверки"
                                    >
                                      <Building2 className="w-3 h-3" />
                                      <span>{termCount} шт.</span>
                                    </button>
                                  ) : (
                                    <span className="text-slate-400">—</span>
                                  )}
                                </td>
                                <td className="px-3 py-2.5 text-center text-emerald-700 font-semibold">{item.matched_count}</td>
                                <td className="px-3 py-2.5 text-center text-amber-700 font-semibold">
                                  {item.mismatch_count + item.only_our_count + item.only_bank_count}
                                </td>
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
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </>
              )}
            </div>
          )}

          {/* ─── VIEW 2: TERMINALS & EPOS COMMISSION ANALYSIS ─── */}
          {activeTab === 'terminals' && (
            <div className="space-y-6">
              {filteredTerminals.length === 0 ? (
                <div className="bg-white rounded-2xl border border-slate-200 p-8 text-center text-xs text-slate-500 space-y-2">
                  <FolderOpen className="w-8 h-8 text-slate-300 mx-auto" />
                  <p>По выбранным фильтрам терминалы не найдены.</p>
                  <button
                    onClick={resetAllFilters}
                    className="text-indigo-600 font-semibold hover:underline"
                  >
                    Сбросить фильтры
                  </button>
                </div>
              ) : (
                <>
                  {/* Metric Cards */}
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                    <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-xs">
                      <div className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">Всего терминалов (TID)</div>
                      <div className="text-xl font-bold text-slate-900 mt-1 tabular-nums">
                        {new Set(filteredTerminals.map(t => t.terminal_id)).size}
                      </div>
                      <div className="text-[11px] text-slate-400 mt-0.5">
                        Транзакций: <strong className="text-slate-700">{totalTerminalTxCount}</strong>
                      </div>
                    </div>

                    <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-xs">
                      <div className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">Совокупный оборот терминалов</div>
                      <div className="text-lg font-bold text-slate-900 mt-1 break-words tabular-nums">{fmt(totalTerminalVolume)} UZS</div>
                      <div className="text-[11px] text-slate-400 mt-0.5">Номинальная сумма операций</div>
                    </div>

                    <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-xs">
                      <div className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">Начислено комиссии эквайринга</div>
                      <div className="text-lg font-bold text-rose-600 mt-1 break-words tabular-nums">{fmt(totalTerminalCommission)} UZS</div>
                      <div className="text-[11px] text-slate-500 mt-0.5">
                        Средняя ставка: <strong className="text-slate-800">{avgEffectiveRate.toFixed(2)}%</strong>
                      </div>
                    </div>

                    <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-xs">
                      <div className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">К перечислению (нетто)</div>
                      <div className="text-lg font-bold text-emerald-600 mt-1 break-words tabular-nums">{fmt(totalTerminalNetVolume)} UZS</div>
                      <div className="text-[11px] text-emerald-700 mt-0.5">Оборот минус комиссия банка</div>
                    </div>
                  </div>

                  {/* Terminal Charts */}
                  <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-xs">
                    <h2 className="text-sm font-bold text-slate-900 mb-4 flex items-center gap-1.5">
                      <BarChart3 className="w-4 h-4 text-indigo-600" />
                      <span>Топ-10 терминалов по обороту и удержанной комиссии (UZS)</span>
                    </h2>
                    <div className="h-64">
                      <ResponsiveContainer width="100%" height="100%">
                        <BarChart data={topTerminalsChartData} margin={{ top: 10, right: 10, left: 10, bottom: 20 }}>
                          <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
                          <XAxis dataKey="tid" tick={{ fontSize: 10 }} />
                          <YAxis tick={{ fontSize: 10 }} />
                          <Tooltip formatter={(v: number) => fmt(v)} />
                          <Legend wrapperStyle={{ fontSize: 11 }} />
                          <Bar dataKey="volume" name="Оборот терминала" fill="#4f46e5" radius={[4, 4, 0, 0]} />
                          <Bar dataKey="commission" name="Комиссия банка" fill="#e11d48" radius={[4, 4, 0, 0]} />
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  </div>

                  {/* Terminals Table with live search */}
                  <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-xs space-y-4">
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                      <div>
                        <h2 className="text-sm font-bold text-slate-900 flex items-center gap-1.5">
                          <Building2 className="w-4 h-4 text-indigo-600" />
                          <span>Детализированный реестр по терминалам</span>
                        </h2>
                        <p className="text-xs text-slate-500 mt-0.5">
                          Показывает фактический оборот, процент комиссии и сумму к зачислению по каждому терминалу.
                        </p>
                      </div>

                      {/* Quick Search */}
                      <div className="relative w-full sm:w-64">
                        <Search className="w-3.5 h-3.5 text-slate-400 absolute left-3 top-2.5" />
                        <input
                          type="text"
                          placeholder="Поиск по TID / Мерчанту..."
                          value={searchTidQuery}
                          onChange={(e) => setSearchTidQuery(e.target.value)}
                          className="w-full pl-8 pr-3 py-1.5 bg-slate-50 border border-slate-200 rounded-xl text-xs focus:bg-white focus:outline-none focus:ring-1 focus:ring-indigo-500"
                        />
                        {searchTidQuery && (
                          <button
                            type="button"
                            onClick={() => setSearchTidQuery('')}
                            className="absolute right-2.5 top-2 text-slate-400 hover:text-slate-600"
                          >
                            <X className="w-3.5 h-3.5" />
                          </button>
                        )}
                      </div>
                    </div>

                    <div className="overflow-x-auto rounded-xl border border-slate-200 text-xs">
                      <table className="min-w-full divide-y divide-slate-200">
                        <thead className="bg-slate-50 font-bold text-slate-700 select-none">
                          <tr>
                            <th className="px-3 py-2.5 text-left">TID Терминала</th>
                            <th className="px-3 py-2.5 text-left">Банк-эквайер</th>
                            <th className="px-3 py-2.5 text-left">Мерчант / Точка</th>
                            <th className="px-3 py-2.5 text-center">Месяц</th>
                            <th className="px-3 py-2.5 text-right">Сделок</th>
                            <th className="px-3 py-2.5 text-right">Оборот (UZS)</th>
                            <th className="px-3 py-2.5 text-right">Ставка %</th>
                            <th className="px-3 py-2.5 text-right">Комиссия (UZS)</th>
                            <th className="px-3 py-2.5 text-right">К зачислению (нетто)</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100 bg-white">
                          {filteredTerminals.map((t, idx) => (
                            <tr key={`${t.archive_id}-${t.terminal_id}-${idx}`} className="hover:bg-slate-50 transition-colors">
                              <td className="px-3 py-2.5 font-mono font-bold text-slate-900">{t.terminal_id}</td>
                              <td className="px-3 py-2.5 text-slate-700">{t.bank_acquirer || t.archive_bank}</td>
                              <td className="px-3 py-2.5 text-slate-600">{t.legal_entity || t.merchant_id || '—'}</td>
                              <td className="px-3 py-2.5 text-center font-mono font-medium text-slate-700">{t.period_month}</td>
                              <td className="px-3 py-2.5 text-right font-medium text-slate-700">{t.tx_count}</td>
                              <td className="px-3 py-2.5 text-right font-semibold text-slate-900 tabular-nums">{fmt(t.total_volume)}</td>
                              <td className="px-3 py-2.5 text-right font-bold text-indigo-600">{t.commission_pct}%</td>
                              <td className="px-3 py-2.5 text-right font-semibold text-rose-600 tabular-nums">{fmt(t.commission_amount)}</td>
                              <td className="px-3 py-2.5 text-right font-bold text-emerald-600 tabular-nums">{fmt(t.net_volume)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </>
              )}
            </div>
          )}
        </>
      )}

      {/* Inspect Single Archive Record Terminals Modal */}
      {inspectRecord && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 backdrop-blur-xs p-4">
          <div className="bg-white rounded-2xl shadow-xl border border-slate-200 max-w-4xl w-full p-6 space-y-4 max-h-[90vh] flex flex-col">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <div>
                <h3 className="text-base font-bold text-slate-900 flex items-center gap-2">
                  <Building2 className="w-5 h-5 text-indigo-600" />
                  <span>Терминалы сверки: {inspectRecord.bank_name}</span>
                </h3>
                <p className="text-xs text-slate-500 mt-0.5">
                  Месяц: <strong className="text-slate-800">{inspectRecord.period_month || inspectRecord.timestamp.slice(0, 7)}</strong> | Дата фиксации: {new Date(inspectRecord.timestamp).toLocaleString('ru-RU')}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setInspectRecord(null)}
                className="text-slate-400 hover:text-slate-600 p-1.5 rounded-lg hover:bg-slate-100 transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="overflow-y-auto flex-1">
              <table className="min-w-full text-xs text-left divide-y divide-slate-200">
                <thead className="bg-slate-50 font-bold text-slate-700">
                  <tr>
                    <th className="py-2.5 px-3">TID</th>
                    <th className="py-2.5 px-3">Банк-эквайер</th>
                    <th className="py-2.5 px-3">Мерчант</th>
                    <th className="py-2.5 px-3 text-right">Сделок</th>
                    <th className="py-2.5 px-3 text-right">Оборот (UZS)</th>
                    <th className="py-2.5 px-3 text-right">Ставка %</th>
                    <th className="py-2.5 px-3 text-right">Комиссия (UZS)</th>
                    <th className="py-2.5 px-3 text-right">К зачислению (UZS)</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {inspectRecord.terminals_summary && inspectRecord.terminals_summary.length > 0 ? (
                    inspectRecord.terminals_summary.map((t, i) => (
                      <tr key={i} className="hover:bg-slate-50">
                        <td className="py-2 px-3 font-mono font-bold text-slate-900">{t.terminal_id}</td>
                        <td className="py-2 px-3 text-slate-700">{t.bank_acquirer || inspectRecord.bank_name}</td>
                        <td className="py-2 px-3 text-slate-600">{t.legal_entity || t.merchant_id || '—'}</td>
                        <td className="py-2 px-3 text-right text-slate-700">{t.tx_count}</td>
                        <td className="py-2 px-3 text-right font-semibold text-slate-900 tabular-nums">{fmt(t.total_volume)}</td>
                        <td className="py-2 px-3 text-right font-medium text-indigo-600">{t.commission_pct}%</td>
                        <td className="py-2 px-3 text-right font-semibold text-rose-600 tabular-nums">{fmt(t.commission_amount)}</td>
                        <td className="py-2 px-3 text-right font-bold text-emerald-600 tabular-nums">{fmt(t.net_volume)}</td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan={8} className="py-6 text-center text-slate-400">
                        В этой записи нет детализации по терминалам.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>

            <div className="pt-3 border-t border-slate-100 flex justify-end">
              <button
                type="button"
                onClick={() => setInspectRecord(null)}
                className="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-semibold rounded-xl transition-colors cursor-pointer"
              >
                Закрыть
              </button>
            </div>
          </div>
        </div>
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
