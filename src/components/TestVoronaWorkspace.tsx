import React, { useMemo, useState } from 'react';
import * as XLSX from 'xlsx';
import {
  AlertCircle,
  ArrowLeft,
  CheckCircle2,
  ChevronRight,
  Database,
  Download,
  FileSearch,
  FileSpreadsheet,
  FolderClock,
  LayoutDashboard,
  LoaderCircle,
  MessageSquareText,
  Play,
  RefreshCcw,
  Search,
  Settings,
  Upload,
  Users,
  X,
} from 'lucide-react';

import { User } from '../types';
import { FileDropZone } from './FileDropZone';
import { hasPermission } from '../utils/permissions';
import {
  runTestVorona,
  TestVoronaRow,
  TestVoronaRunResult,
  TestVoronaSourceRow,
} from '../utils/testVoronaApi';

interface Props {
  user: User;
  onBack: () => void;
}

type Tab = 'reconciliation' | 'database' | 'partners' | 'uploads';
type DatasetKey = 'sales' | 'bank' | 'faktura' | 'one_c' | 'opening_balances';

const DATASET_LABELS: Record<DatasetKey, string> = {
  sales: 'Продажи / комиссия',
  bank: 'Платежи',
  faktura: 'Фактуры',
  one_c: '1С',
  opening_balances: 'Сальдо',
};

const FILE_CARDS = [
  ['baza', 'VBAZA', 'Продажи, комиссия, Status, VID'],
  ['bank', 'VBANK', 'Дата, ИНН, партнёр, сумма, VID'],
  ['faktura', 'VFAKTURA', 'Фактуры по партнёрам'],
  ['vipp', 'VIPP', 'ИНН / ПИНФЛ → Vorona Code'],
  ['vorona', 'VORONA 2026', 'Сальдо начала года + лист 1С'],
] as const;

function money(value: number | null | undefined): string {
  const number = Number(value ?? 0);
  return Number.isFinite(number)
    ? number.toLocaleString('ru-RU', { maximumFractionDigits: 2 })
    : '—';
}

function statusClass(status: string): string {
  if (status === 'Без расхождений') return 'border-emerald-200 bg-emerald-50 text-emerald-700';
  if (status === 'Есть оба расхождения') return 'border-rose-200 bg-rose-50 text-rose-700';
  return 'border-amber-200 bg-amber-50 text-amber-700';
}

function statusDot(status: string): string {
  if (status === 'Без расхождений') return 'bg-emerald-500';
  if (status === 'Есть оба расхождения') return 'bg-rose-500';
  return 'bg-amber-500';
}

export const TestVoronaWorkspace: React.FC<Props> = ({ user, onBack }) => {
  const canRun = hasPermission(user, 'test_vorona.run');
  const canExport = hasPermission(user, 'test_vorona.export');

  const [tab, setTab] = useState<Tab>('reconciliation');
  const [year, setYear] = useState(2026);
  const [period, setPeriod] = useState('Янв–Сен');
  const [files, setFiles] = useState<{
    baza: File | null;
    bank: File | null;
    faktura: File | null;
    vipp: File | null;
    vorona: File | null;
  }>({ baza: null, bank: null, faktura: null, vipp: null, vorona: null });

  const [result, setResult] = useState<TestVoronaRunResult | null>(null);
  const [running, setRunning] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('Все');
  const [selected, setSelected] = useState<TestVoronaRow | null>(null);
  const [dataset, setDataset] = useState<DatasetKey>('sales');
  const [showUpload, setShowUpload] = useState(false);

  const metrics = result?.custom_metrics?.test_vorona;
  const rows = metrics?.rows || [];

  const filteredRows = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return rows.filter(row => {
      if (statusFilter !== 'Все' && row.status !== statusFilter) return false;
      if (!needle) return true;
      return [row.partner, row.inn, row.vid]
        .some(value => String(value || '').toLowerCase().includes(needle));
    });
  }, [rows, query, statusFilter]);

  const sourceRows = (metrics?.datasets?.[dataset] || []) as TestVoronaSourceRow[];
  const filteredSourceRows = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return sourceRows;
    return sourceRows.filter(row =>
      [row.partner, row.inn, row.vid, row.month, row.side]
        .some(value => String(value || '').toLowerCase().includes(needle)),
    );
  }, [sourceRows, query]);

  const partnerRows = (metrics?.datasets?.partners || []) as TestVoronaSourceRow[];
  const filteredPartners = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return partnerRows;
    return partnerRows.filter(row =>
      [row.partner, row.inn, row.vid]
        .some(value => String(value || '').toLowerCase().includes(needle)),
    );
  }, [partnerRows, query]);

  const ready = Object.values(files).every(Boolean);

  const handleRun = async () => {
    if (!canRun || !ready || running) {
      if (!ready) setShowUpload(true);
      return;
    }

    setRunning(true);
    setMessage(null);
    try {
      const next = await runTestVorona({
        baza: files.baza!,
        bank: files.bank!,
        faktura: files.faktura!,
        vipp: files.vipp!,
        vorona: files.vorona!,
      }, year);
      setResult(next);
      setSelected(null);
      setTab('reconciliation');
      setShowUpload(false);
      setMessage(`Сверка завершена · Run ${next.run_id}`);
    } catch (error: any) {
      setMessage(error?.message || 'Не удалось выполнить сверку.');
    } finally {
      setRunning(false);
    }
  };

  const exportResult = () => {
    if (!result || !rows.length) return;
    const workbook = XLSX.utils.book_new();
    const summary = rows.map(row => ({
      Partner: row.partner,
      INN: row.inn,
      VID: row.vid,
      Payment: row.payment,
      Bank: row.bank,
      Faktura: row.faktura,
      Komissiya: row.komissiya,
      Saldo: row.saldo,
      '1C': row.one_c,
      Difference: row.difference,
      'Difference 1C': row.difference_1c,
      Status: row.status,
    }));
    XLSX.utils.book_append_sheet(workbook, XLSX.utils.json_to_sheet(summary), 'Сверка');
    XLSX.writeFile(workbook, `Тестовая_ворона_${year}.xlsx`);
  };

  const navItems: Array<{ id: Tab; label: string; icon: React.ElementType; subtitle: string }> = [
    { id: 'reconciliation', label: 'Сверка', icon: LayoutDashboard, subtitle: 'Главный контроль' },
    { id: 'database', label: 'База данных', icon: Database, subtitle: 'Исходные операции' },
    { id: 'partners', label: 'Партнёры', icon: Users, subtitle: 'ИНН / ПИНФЛ / VID' },
    { id: 'uploads', label: 'Загрузки', icon: Upload, subtitle: 'Excel-источники' },
  ];

  const statuses = ['Все', 'Есть Difference', 'Есть Difference 1C', 'Без расхождений'];

  const detailOperations = selected
    ? [
        {
          label: 'Продажи / Payment',
          value: selected.payment,
          ok: true,
        },
        {
          label: 'Комиссия / Faktura',
          value: selected.difference,
          ok: Math.abs(selected.difference) <= 1,
        },
        {
          label: 'Контроль 1C',
          value: selected.difference_1c,
          ok: Math.abs(selected.difference_1c) <= 1,
        },
      ]
    : [];

  return (
    <div className="flex min-h-full bg-[#f6f8fb] text-slate-900">
      <aside className="sticky top-0 h-screen w-[238px] shrink-0 border-r border-slate-200 bg-white">
        <div className="flex h-full flex-col">
          <div className="border-b border-slate-100 px-5 py-5">
            <button
              type="button"
              onClick={onBack}
              className="flex items-center gap-2 text-left"
              title="Все модули"
            >
              <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-indigo-600 text-white shadow-sm">
                <FileSearch className="h-4 w-4" />
              </div>
              <div>
                <div className="text-[15px] font-black tracking-tight text-slate-900">ReconcileHub</div>
                <div className="text-[10px] font-semibold text-slate-400">Тестовая ворона</div>
              </div>
            </button>
          </div>

          <nav className="flex-1 space-y-1 px-3 py-4">
            {navItems.map(item => {
              const Icon = item.icon;
              const active = tab === item.id;
              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => {
                    setTab(item.id);
                    if (item.id === 'uploads') setShowUpload(false);
                  }}
                  className={`flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left transition-all ${
                    active
                      ? 'bg-indigo-600 text-white shadow-sm'
                      : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900'
                  }`}
                >
                  <Icon className={`h-4 w-4 shrink-0 ${active ? 'text-white' : 'text-slate-400'}`} />
                  <div className="min-w-0">
                    <div className="truncate text-xs font-bold">{item.label}</div>
                    <div className={`mt-0.5 truncate text-[9px] ${active ? 'text-indigo-100' : 'text-slate-400'}`}>
                      {item.subtitle}
                    </div>
                  </div>
                </button>
              );
            })}

            <div className="my-3 border-t border-slate-100" />

            <button
              type="button"
              onClick={onBack}
              className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left text-slate-600 hover:bg-slate-50"
            >
              <ArrowLeft className="h-4 w-4 text-slate-400" />
              <div>
                <div className="text-xs font-bold">Все модули</div>
                <div className="mt-0.5 text-[9px] text-slate-400">Вернуться в ReconcileHub</div>
              </div>
            </button>
          </nav>

          <div className="border-t border-slate-100 p-4">
            <div className="flex items-center gap-3 rounded-xl bg-slate-50 p-3">
              <div className="flex h-8 w-8 items-center justify-center rounded-full bg-indigo-100 text-[10px] font-black text-indigo-700">
                {user.username.slice(0, 2).toUpperCase()}
              </div>
              <div className="min-w-0">
                <div className="truncate text-[11px] font-bold text-slate-800">{user.username}</div>
                <div className="truncate text-[9px] text-slate-400">{user.role}</div>
              </div>
              <Settings className="ml-auto h-3.5 w-3.5 text-slate-400" />
            </div>
          </div>
        </div>
      </aside>

      <main className="min-w-0 flex-1">
        <div className="border-b border-slate-200 bg-white">
          <div className="px-6 py-5 xl:px-8">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <div className="flex items-center gap-2">
                  <h1 className="text-[22px] font-black tracking-tight text-slate-900">Взаиморасчёты с партнёрами</h1>
                  <span className="rounded-full border border-indigo-200 bg-indigo-50 px-2 py-0.5 text-[9px] font-bold text-indigo-700">
                    Тестовая ворона
                  </span>
                </div>
                <p className="mt-1 text-xs text-slate-500">
                  Контроль взаиморасчётов, фактур, оплат и данных 1С
                </p>
              </div>

              <div className="flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  onClick={() => setShowUpload(true)}
                  className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-[11px] font-bold text-slate-700 shadow-sm hover:bg-slate-50"
                >
                  <Upload className="h-3.5 w-3.5" />
                  Загрузить Excel
                </button>
                <button
                  type="button"
                  onClick={() => void handleRun()}
                  disabled={!canRun || running}
                  className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-[11px] font-bold text-slate-700 shadow-sm hover:bg-slate-50 disabled:opacity-40"
                >
                  {running ? <LoaderCircle className="h-3.5 w-3.5 animate-spin" /> : <RefreshCcw className="h-3.5 w-3.5" />}
                  Обновить сверку
                </button>
                <button
                  type="button"
                  onClick={exportResult}
                  disabled={!result || !canExport}
                  className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-3 py-2 text-[11px] font-bold text-white shadow-sm hover:bg-indigo-700 disabled:opacity-40"
                >
                  <Download className="h-3.5 w-3.5" />
                  Экспорт
                </button>
              </div>
            </div>
          </div>
        </div>

        <div className="space-y-4 px-6 py-5 xl:px-8">
          {message && (
            <div className="flex items-center justify-between rounded-xl border border-indigo-100 bg-indigo-50 px-4 py-2.5 text-[11px] font-semibold text-indigo-700">
              <span>{message}</span>
              <button type="button" onClick={() => setMessage(null)}>
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
          )}

          {tab === 'reconciliation' && (
            <>
              <section className="rounded-xl border border-slate-200 bg-white p-3 shadow-xs">
                <div className="flex flex-wrap items-center gap-2">
                  <label className="relative min-w-[320px] flex-1">
                    <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                    <input
                      value={query}
                      onChange={event => setQuery(event.target.value)}
                      placeholder="Поиск по ИНН / ПИНФЛ / VID / партнёру"
                      className="w-full rounded-lg border border-slate-200 bg-slate-50 py-2.5 pl-9 pr-3 text-xs outline-none focus:border-indigo-300 focus:bg-white focus:ring-2 focus:ring-indigo-100"
                    />
                  </label>

                  <label className="flex items-center gap-2 rounded-lg border border-slate-200 px-3 py-2.5 text-[11px] font-semibold text-slate-600">
                    Год:
                    <input
                      type="number"
                      value={year}
                      onChange={event => setYear(Number(event.target.value) || 2026)}
                      className="w-14 bg-transparent font-bold text-slate-900 outline-none"
                    />
                  </label>

                  <select
                    value={period}
                    onChange={event => setPeriod(event.target.value)}
                    className="rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-[11px] font-semibold text-slate-600 outline-none"
                  >
                    <option>Янв–Сен</option>
                    <option>Янв–Дек</option>
                    <option>Текущий месяц</option>
                  </select>

                  <select
                    value={statusFilter}
                    onChange={event => setStatusFilter(event.target.value)}
                    className="rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-[11px] font-semibold text-slate-600 outline-none"
                  >
                    <option value="Все">Статус: Все</option>
                    <option value="Есть Difference">Есть Difference</option>
                    <option value="Есть Difference 1C">Есть Difference 1C</option>
                    <option value="Без расхождений">Без расхождений</option>
                  </select>
                </div>

                <div className="mt-3 flex flex-wrap gap-2">
                  {statuses.map(status => (
                    <button
                      key={status}
                      type="button"
                      onClick={() => setStatusFilter(status)}
                      className={`inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-[10px] font-bold ${
                        statusFilter === status
                          ? 'border-indigo-200 bg-indigo-50 text-indigo-700'
                          : 'border-slate-200 bg-white text-slate-500 hover:bg-slate-50'
                      }`}
                    >
                      {status !== 'Все' && (
                        <span className={`h-1.5 w-1.5 rounded-full ${
                          status === 'Без расхождений' ? 'bg-emerald-500' : status === 'Есть Difference' ? 'bg-rose-500' : 'bg-amber-500'
                        }`} />
                      )}
                      {status}
                    </button>
                  ))}
                </div>
              </section>

              <section className="grid grid-cols-2 gap-3 xl:grid-cols-4">
                <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-xs">
                  <div className="flex items-start justify-between">
                    <div>
                      <div className="text-[10px] font-bold uppercase tracking-wide text-slate-400">Партнёров</div>
                      <div className="mt-2 text-2xl font-black text-slate-900">{rows.length || '—'}</div>
                    </div>
                    <div className="rounded-lg bg-indigo-50 p-2 text-indigo-600"><Users className="h-4 w-4" /></div>
                  </div>
                  <div className="mt-2 text-[9px] text-slate-400">в текущей сверке</div>
                </div>

                <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-xs">
                  <div className="flex items-start justify-between">
                    <div>
                      <div className="text-[10px] font-bold uppercase tracking-wide text-slate-400">С расхождениями</div>
                      <div className="mt-2 text-2xl font-black text-rose-600">{result?.summary.discrepancy_count ?? '—'}</div>
                    </div>
                    <div className="rounded-lg bg-rose-50 p-2 text-rose-600"><AlertCircle className="h-4 w-4" /></div>
                  </div>
                  <div className="mt-2 text-[9px] text-slate-400">требуют проверки</div>
                </div>

                <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-xs">
                  <div className="flex items-start justify-between">
                    <div>
                      <div className="text-[10px] font-bold uppercase tracking-wide text-slate-400">Difference</div>
                      <div className="mt-2 text-xl font-black text-rose-600">{result ? money(metrics?.totals?.difference) : '—'}</div>
                    </div>
                    <div className="rounded-lg bg-rose-50 p-2 text-rose-600"><Database className="h-4 w-4" /></div>
                  </div>
                  <div className="mt-2 text-[9px] text-slate-400">Faktura − Komissiya</div>
                </div>

                <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-xs">
                  <div className="flex items-start justify-between">
                    <div>
                      <div className="text-[10px] font-bold uppercase tracking-wide text-slate-400">Difference 1C</div>
                      <div className="mt-2 text-xl font-black text-amber-600">{result ? money(metrics?.totals?.difference_1c) : '—'}</div>
                    </div>
                    <div className="rounded-lg bg-amber-50 p-2 text-amber-600"><FileSpreadsheet className="h-4 w-4" /></div>
                  </div>
                  <div className="mt-2 text-[9px] text-slate-400">Saldo − 1C</div>
                </div>
              </section>

              <section className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-xs">
                <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3">
                  <div>
                    <h2 className="text-xs font-black text-slate-900">Контроль взаиморасчётов</h2>
                    <p className="mt-0.5 text-[9px] text-slate-400">Нажмите на партнёра, чтобы открыть детали справа</p>
                  </div>
                  {!result && (
                    <button
                      type="button"
                      onClick={() => setShowUpload(true)}
                      className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-3 py-2 text-[10px] font-bold text-white"
                    >
                      <Upload className="h-3.5 w-3.5" />
                      Начать
                    </button>
                  )}
                </div>

                <div className="overflow-x-auto">
                  <table className="min-w-[1450px] w-full text-[11px]">
                    <thead className="bg-[#f8fafc] text-[9px] uppercase tracking-wide text-slate-400">
                      <tr>
                        {['Партнёр','ИНН','VID','Payment','Bank','Faktura','Komissiya','Saldo','1C','Difference','Difference 1C','Статус'].map(header => (
                          <th key={header} className="px-3 py-3 text-left font-bold">{header}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {filteredRows.map(row => (
                        <tr
                          key={row.vid}
                          onClick={() => setSelected(row)}
                          className={`cursor-pointer transition-colors hover:bg-indigo-50/40 ${selected?.vid === row.vid ? 'bg-indigo-50/60' : ''}`}
                        >
                          <td className="max-w-[250px] truncate px-3 py-3 font-bold text-slate-800" title={row.partner}>{row.partner}</td>
                          <td className="px-3 py-3 text-slate-500">{row.inn || '—'}</td>
                          <td className="px-3 py-3 font-bold text-indigo-700">{row.vid}</td>
                          <td className="px-3 py-3 text-right tabular-nums">{money(row.payment)}</td>
                          <td className="px-3 py-3 text-right tabular-nums">{money(row.bank)}</td>
                          <td className="px-3 py-3 text-right tabular-nums">{money(row.faktura)}</td>
                          <td className="px-3 py-3 text-right tabular-nums">{money(row.komissiya)}</td>
                          <td className="px-3 py-3 text-right font-semibold tabular-nums">{money(row.saldo)}</td>
                          <td className="px-3 py-3 text-right tabular-nums">{money(row.one_c)}</td>
                          <td className={`px-3 py-3 text-right font-black tabular-nums ${Math.abs(row.difference) > 1 ? 'bg-rose-50 text-rose-700' : 'text-emerald-700'}`}>
                            {money(row.difference)}
                          </td>
                          <td className={`px-3 py-3 text-right font-black tabular-nums ${Math.abs(row.difference_1c) > 1 ? 'bg-amber-50 text-amber-700' : 'text-emerald-700'}`}>
                            {money(row.difference_1c)}
                          </td>
                          <td className="px-3 py-3">
                            <span className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border px-2 py-1 text-[9px] font-bold ${statusClass(row.status)}`}>
                              <span className={`h-1.5 w-1.5 rounded-full ${statusDot(row.status)}`} />
                              {row.status}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>

                  {!result && (
                    <div className="flex min-h-52 flex-col items-center justify-center px-6 py-10 text-center">
                      <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-indigo-50 text-indigo-600">
                        <FileSpreadsheet className="h-5 w-5" />
                      </div>
                      <div className="mt-3 text-sm font-black text-slate-800">Сверка ещё не запущена</div>
                      <div className="mt-1 max-w-md text-xs text-slate-400">
                        Загрузите пять Excel-файлов, после чего таблица будет собрана автоматически.
                      </div>
                    </div>
                  )}
                </div>
              </section>

              {selected && (
                <section className="rounded-xl border border-slate-200 bg-white shadow-xs">
                  <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3">
                    <div>
                      <h2 className="text-xs font-black text-slate-900">Последние операции / детали расхождений</h2>
                      <p className="mt-0.5 text-[9px] text-slate-400">{selected.partner} · {selected.vid}</p>
                    </div>
                    <button
                      type="button"
                      onClick={() => {
                        setQuery(selected.vid);
                        setDataset('sales');
                        setTab('database');
                      }}
                      className="inline-flex items-center gap-1 text-[10px] font-bold text-indigo-600 hover:text-indigo-700"
                    >
                      Все операции партнёра
                      <ChevronRight className="h-3 w-3" />
                    </button>
                  </div>

                  <div className="grid grid-cols-1 divide-y divide-slate-100 lg:grid-cols-3 lg:divide-x lg:divide-y-0">
                    {detailOperations.map(item => (
                      <div key={item.label} className="flex items-center gap-3 px-4 py-4">
                        <div className={`flex h-8 w-8 items-center justify-center rounded-lg ${item.ok ? 'bg-emerald-50 text-emerald-600' : 'bg-rose-50 text-rose-600'}`}>
                          {item.ok ? <CheckCircle2 className="h-4 w-4" /> : <AlertCircle className="h-4 w-4" />}
                        </div>
                        <div>
                          <div className="text-[10px] font-bold text-slate-500">{item.label}</div>
                          <div className={`mt-0.5 text-sm font-black ${item.ok ? 'text-slate-900' : 'text-rose-700'}`}>
                            {money(item.value)}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </section>
              )}
            </>
          )}

          {tab === 'database' && result && (
            <section className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-xs">
              <div className="flex flex-col gap-3 border-b border-slate-100 p-4 xl:flex-row xl:items-center xl:justify-between">
                <div>
                  <h2 className="text-sm font-black text-slate-900">База данных</h2>
                  <p className="mt-1 text-[10px] text-slate-400">Проверка строк, из которых собрана сверка</p>
                </div>
                <label className="relative min-w-[320px]">
                  <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                  <input
                    value={query}
                    onChange={event => setQuery(event.target.value)}
                    placeholder="Партнёр / ИНН / VID"
                    className="w-full rounded-lg border border-slate-200 py-2 pl-9 pr-3 text-xs outline-none"
                  />
                </label>
              </div>

              <div className="flex flex-wrap gap-2 border-b border-slate-100 px-4 py-3">
                {(Object.keys(DATASET_LABELS) as DatasetKey[]).map(key => (
                  <button
                    key={key}
                    type="button"
                    onClick={() => setDataset(key)}
                    className={`rounded-lg border px-3 py-1.5 text-[10px] font-bold ${
                      dataset === key
                        ? 'border-indigo-600 bg-indigo-600 text-white'
                        : 'border-slate-200 text-slate-500 hover:bg-slate-50'
                    }`}
                  >
                    {DATASET_LABELS[key]} · {metrics?.source_counts?.[key] ?? 0}
                  </button>
                ))}
              </div>

              <div className="overflow-x-auto">
                <table className="min-w-[950px] w-full text-[11px]">
                  <thead className="bg-slate-50 text-[9px] uppercase tracking-wide text-slate-400">
                    <tr>
                      <th className="px-4 py-3 text-left">Месяц / сторона</th>
                      <th className="px-4 py-3 text-left">Дата</th>
                      <th className="px-4 py-3 text-left">Партнёр</th>
                      <th className="px-4 py-3 text-left">ИНН / ПИНФЛ</th>
                      <th className="px-4 py-3 text-left">VID</th>
                      <th className="px-4 py-3 text-right">Сумма</th>
                      {dataset === 'sales' && <th className="px-4 py-3 text-right">Комиссия</th>}
                      {dataset === 'sales' && <th className="px-4 py-3 text-left">Status</th>}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {filteredSourceRows.slice(0, 1000).map((row, index) => (
                      <tr key={index} className="hover:bg-slate-50">
                        <td className="px-4 py-3">{row.month || row.side || '—'}</td>
                        <td className="px-4 py-3 text-slate-500">{row.date ? String(row.date).slice(0, 10) : '—'}</td>
                        <td className="max-w-[320px] truncate px-4 py-3 font-semibold text-slate-800" title={row.partner}>{row.partner || '—'}</td>
                        <td className="px-4 py-3">{row.inn || '—'}</td>
                        <td className="px-4 py-3 font-bold text-indigo-700">{row.vid || '—'}</td>
                        <td className="px-4 py-3 text-right tabular-nums">{money(row.amount)}</td>
                        {dataset === 'sales' && <td className="px-4 py-3 text-right tabular-nums">{money(row.commission)}</td>}
                        {dataset === 'sales' && <td className="px-4 py-3">{row.Status || '—'}</td>}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}

          {tab === 'database' && !result && (
            <section className="rounded-xl border border-slate-200 bg-white p-12 text-center shadow-xs">
              <Database className="mx-auto h-7 w-7 text-slate-300" />
              <div className="mt-3 text-sm font-black text-slate-800">База появится после запуска сверки</div>
              <button type="button" onClick={() => setShowUpload(true)} className="mt-4 rounded-lg bg-indigo-600 px-4 py-2 text-[10px] font-bold text-white">
                Загрузить Excel
              </button>
            </section>
          )}

          {tab === 'partners' && result && (
            <section className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-xs">
              <div className="flex items-center justify-between border-b border-slate-100 p-4">
                <div>
                  <h2 className="text-sm font-black text-slate-900">Справочник партнёров</h2>
                  <p className="mt-1 text-[10px] text-slate-400">VIPP · ИНН / ПИНФЛ → Vorona Code</p>
                </div>
                <label className="relative min-w-[320px]">
                  <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                  <input
                    value={query}
                    onChange={event => setQuery(event.target.value)}
                    placeholder="Поиск по партнёру / ИНН / VID"
                    className="w-full rounded-lg border border-slate-200 py-2 pl-9 pr-3 text-xs outline-none"
                  />
                </label>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full min-w-[800px] text-[11px]">
                  <thead className="bg-slate-50 text-[9px] uppercase tracking-wide text-slate-400">
                    <tr>
                      <th className="px-4 py-3 text-left">VID</th>
                      <th className="px-4 py-3 text-left">Партнёр</th>
                      <th className="px-4 py-3 text-left">ИНН / ПИНФЛ</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {filteredPartners.slice(0, 2000).map((row, index) => (
                      <tr key={index} className="hover:bg-slate-50">
                        <td className="px-4 py-3 font-bold text-indigo-700">{row.vid}</td>
                        <td className="px-4 py-3 font-semibold text-slate-800">{row.partner}</td>
                        <td className="px-4 py-3 text-slate-600">{row.inn}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}

          {tab === 'partners' && !result && (
            <section className="rounded-xl border border-slate-200 bg-white p-12 text-center shadow-xs">
              <Users className="mx-auto h-7 w-7 text-slate-300" />
              <div className="mt-3 text-sm font-black text-slate-800">Справочник загрузится из VIPP</div>
              <button type="button" onClick={() => setShowUpload(true)} className="mt-4 rounded-lg bg-indigo-600 px-4 py-2 text-[10px] font-bold text-white">
                Загрузить Excel
              </button>
            </section>
          )}

          {tab === 'uploads' && (
            <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-xs">
              <div className="mb-4 flex items-center justify-between">
                <div>
                  <h2 className="text-sm font-black text-slate-900">Исходные файлы</h2>
                  <p className="mt-1 text-[10px] text-slate-400">Пять источников для расчёта «Тестовой вороны»</p>
                </div>
                {ready && (
                  <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-200 bg-emerald-50 px-2.5 py-1 text-[9px] font-bold text-emerald-700">
                    <CheckCircle2 className="h-3 w-3" />
                    Все файлы готовы
                  </span>
                )}
              </div>

              <div className="grid grid-cols-1 gap-3 xl:grid-cols-5">
                {FILE_CARDS.map(([key, title, subtitle]) => (
                  <div key={key} className="rounded-xl border border-slate-200 p-3">
                    <div className="mb-2 flex items-center gap-2">
                      <FileSpreadsheet className="h-4 w-4 text-indigo-600" />
                      <div className="text-xs font-black text-slate-800">{title}</div>
                    </div>
                    <FileDropZone
                      accept=".xlsx,.xls"
                      onFile={file => setFiles(current => ({ ...current, [key]: file }))}
                      className="flex min-h-28 cursor-pointer flex-col items-center justify-center rounded-lg border border-dashed border-slate-300 bg-slate-50 p-3 text-center hover:bg-slate-100"
                      activeClassName="border-indigo-400 bg-indigo-50 ring-2 ring-indigo-100"
                    >
                      {isDragging => (
                        <>
                          <Upload className="mb-2 h-5 w-5 text-indigo-500" />
                          <div className="max-w-full truncate text-[10px] font-bold text-slate-700">
                            {files[key]?.name || (isDragging ? 'Отпустите файл' : 'Перетащите или выберите')}
                          </div>
                          <div className="mt-1 text-[8px] leading-4 text-slate-400">{subtitle}</div>
                        </>
                      )}
                    </FileDropZone>
                  </div>
                ))}
              </div>

              <div className="mt-5 flex items-center gap-3">
                <button
                  type="button"
                  onClick={() => void handleRun()}
                  disabled={!canRun || !ready || running}
                  className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2.5 text-xs font-bold text-white hover:bg-indigo-700 disabled:opacity-40"
                >
                  {running ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4 fill-current" />}
                  Запустить сверку
                </button>
                <div className="text-[10px] text-slate-400">Год расчёта: {year}</div>
              </div>
            </section>
          )}
        </div>
      </main>

      {selected && tab === 'reconciliation' && (
        <div className="fixed inset-y-0 right-0 z-50 w-full max-w-[390px] border-l border-slate-200 bg-white shadow-2xl">
          <div className="flex items-start justify-between border-b border-slate-100 p-5">
            <div className="min-w-0">
              <div className="truncate text-sm font-black text-slate-900">{selected.partner}</div>
              <div className="mt-1 text-[10px] text-slate-500">ИНН: {selected.inn || '—'} · VID: {selected.vid}</div>
              <span className={`mt-2 inline-flex rounded-full border px-2 py-1 text-[9px] font-bold ${statusClass(selected.status)}`}>
                {selected.status}
              </span>
            </div>
            <button type="button" onClick={() => setSelected(null)} className="rounded-lg p-2 text-slate-400 hover:bg-slate-50">
              <X className="h-4 w-4" />
            </button>
          </div>

          <div className="space-y-4 overflow-y-auto p-5">
            <div className="space-y-2">
              {[
                ['Начальное сальдо', selected.opening_balance],
                ['Продажи / Payment', selected.payment],
                ['Комиссия', selected.komissiya],
                ['Платежи / Bank', selected.bank],
                ['Фактуры', selected.faktura],
                ['Данные 1С', selected.one_c],
                ['Расчётное Saldo', selected.saldo],
              ].map(([label, value]) => (
                <div key={String(label)} className="flex items-center justify-between rounded-lg border border-slate-100 bg-slate-50/70 px-3 py-2.5">
                  <span className="text-[10px] font-semibold text-slate-500">{label}</span>
                  <span className="text-[11px] font-black tabular-nums text-slate-900">{money(Number(value))}</span>
                </div>
              ))}
            </div>

            <div className="grid grid-cols-2 gap-2">
              <div className={`rounded-xl border p-3 ${Math.abs(selected.difference) > 1 ? 'border-rose-200 bg-rose-50' : 'border-emerald-200 bg-emerald-50'}`}>
                <div className="text-[9px] font-bold uppercase text-slate-400">Difference</div>
                <div className={`mt-1 text-lg font-black ${Math.abs(selected.difference) > 1 ? 'text-rose-700' : 'text-emerald-700'}`}>
                  {money(selected.difference)}
                </div>
              </div>
              <div className={`rounded-xl border p-3 ${Math.abs(selected.difference_1c) > 1 ? 'border-amber-200 bg-amber-50' : 'border-emerald-200 bg-emerald-50'}`}>
                <div className="text-[9px] font-bold uppercase text-slate-400">Difference 1C</div>
                <div className={`mt-1 text-lg font-black ${Math.abs(selected.difference_1c) > 1 ? 'text-amber-700' : 'text-emerald-700'}`}>
                  {money(selected.difference_1c)}
                </div>
              </div>
            </div>

            <div className="rounded-xl border border-slate-200 p-4">
              <div className="flex items-center gap-2">
                <AlertCircle className="h-4 w-4 text-rose-500" />
                <div className="text-[11px] font-black text-slate-800">Причины расхождения</div>
              </div>
              <div className="mt-3 space-y-2 text-[10px]">
                {Math.abs(selected.difference) > 1 ? (
                  <div className="flex items-start gap-2 text-rose-700">
                    <span className="mt-1 h-1.5 w-1.5 rounded-full bg-rose-500" />
                    <span>Faktura отличается от Komissiya на {money(Math.abs(selected.difference))}</span>
                  </div>
                ) : (
                  <div className="flex items-start gap-2 text-emerald-700">
                    <span className="mt-1 h-1.5 w-1.5 rounded-full bg-emerald-500" />
                    <span>Фактуры и комиссия совпадают</span>
                  </div>
                )}

                {Math.abs(selected.difference_1c) > 1 ? (
                  <div className="flex items-start gap-2 text-amber-700">
                    <span className="mt-1 h-1.5 w-1.5 rounded-full bg-amber-500" />
                    <span>Расчётное Saldo отличается от 1С на {money(Math.abs(selected.difference_1c))}</span>
                  </div>
                ) : (
                  <div className="flex items-start gap-2 text-emerald-700">
                    <span className="mt-1 h-1.5 w-1.5 rounded-full bg-emerald-500" />
                    <span>Данные 1С совпадают</span>
                  </div>
                )}
              </div>
            </div>

            <div className="space-y-2">
              <button
                type="button"
                onClick={() => {
                  setQuery(selected.vid);
                  setDataset('sales');
                  setTab('database');
                  setSelected(null);
                }}
                className="w-full rounded-xl bg-indigo-600 px-4 py-3 text-[11px] font-bold text-white hover:bg-indigo-700"
              >
                Показать операции
              </button>
              <button
                type="button"
                className="inline-flex w-full items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-3 text-[11px] font-bold text-slate-700 hover:bg-slate-50"
              >
                <MessageSquareText className="h-3.5 w-3.5" />
                Добавить комментарий
              </button>
            </div>
          </div>
        </div>
      )}

      {showUpload && (
        <div className="fixed inset-0 z-[70] flex items-center justify-center bg-slate-950/30 p-4 backdrop-blur-[2px]">
          <div className="w-full max-w-5xl rounded-2xl border border-slate-200 bg-white shadow-2xl">
            <div className="flex items-start justify-between border-b border-slate-100 px-5 py-4">
              <div>
                <h2 className="text-sm font-black text-slate-900">Загрузить данные для «Тестовой вороны»</h2>
                <p className="mt-1 text-[10px] text-slate-400">Можно перетащить файлы прямо в соответствующие блоки.</p>
              </div>
              <button type="button" onClick={() => setShowUpload(false)} className="rounded-lg p-2 text-slate-400 hover:bg-slate-50">
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="grid grid-cols-1 gap-3 p-5 md:grid-cols-2 xl:grid-cols-5">
              {FILE_CARDS.map(([key, title, subtitle]) => (
                <div key={key} className="rounded-xl border border-slate-200 p-3">
                  <div className="mb-2 flex items-center gap-2">
                    <FileSpreadsheet className="h-4 w-4 text-indigo-600" />
                    <div className="text-xs font-black text-slate-800">{title}</div>
                  </div>
                  <FileDropZone
                    accept=".xlsx,.xls"
                    onFile={file => setFiles(current => ({ ...current, [key]: file }))}
                    className="flex min-h-32 cursor-pointer flex-col items-center justify-center rounded-lg border border-dashed border-slate-300 bg-slate-50 p-3 text-center hover:bg-slate-100"
                    activeClassName="border-indigo-400 bg-indigo-50 ring-2 ring-indigo-100"
                  >
                    {isDragging => (
                      <>
                        {files[key] ? (
                          <CheckCircle2 className="mb-2 h-5 w-5 text-emerald-500" />
                        ) : (
                          <Upload className="mb-2 h-5 w-5 text-indigo-500" />
                        )}
                        <div className="max-w-full truncate text-[10px] font-bold text-slate-700">
                          {files[key]?.name || (isDragging ? 'Отпустите файл' : 'Перетащите или выберите')}
                        </div>
                        <div className="mt-1 text-[8px] leading-4 text-slate-400">{subtitle}</div>
                      </>
                    )}
                  </FileDropZone>
                </div>
              ))}
            </div>

            <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 px-5 py-4">
              <div className="flex items-center gap-2 text-[10px] text-slate-500">
                <FolderClock className="h-3.5 w-3.5" />
                {ready ? 'Все 5 файлов выбраны' : `Выбрано ${Object.values(files).filter(Boolean).length} из 5 файлов`}
              </div>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => setShowUpload(false)}
                  className="rounded-lg border border-slate-200 px-4 py-2 text-[10px] font-bold text-slate-600 hover:bg-slate-50"
                >
                  Закрыть
                </button>
                <button
                  type="button"
                  onClick={() => void handleRun()}
                  disabled={!canRun || !ready || running}
                  className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-[10px] font-bold text-white hover:bg-indigo-700 disabled:opacity-40"
                >
                  {running ? <LoaderCircle className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5 fill-current" />}
                  Запустить сверку
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
