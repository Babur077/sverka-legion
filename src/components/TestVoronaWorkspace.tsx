import React, { useEffect, useMemo, useState } from 'react';
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
  History,
  LayoutDashboard,
  LoaderCircle,
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
  getTestVoronaImports,
  runStoredTestVorona,
  TestVoronaImportBatch,
  TestVoronaImportConflictError,
  TestVoronaRow,
  TestVoronaRunResult,
  TestVoronaSourceRow,
  TestVoronaSourceType,
  uploadTestVoronaSource,
} from '../utils/testVoronaApi';

interface Props {
  user: User;
  onBack: () => void;
}

type Tab = 'reconciliation' | 'database' | 'partners' | 'uploads';
type DatasetKey = 'sales' | 'bank' | 'faktura' | 'one_c' | 'opening_balances';

const MONTHS = [
  'Январь',
  'Февраль',
  'Март',
  'Апрель',
  'Май',
  'Июнь',
  'Июль',
  'Август',
  'Сентябрь',
  'Октябрь',
  'Ноябрь',
  'Декабрь',
];

const DATASET_LABELS: Record<DatasetKey, string> = {
  sales: 'Продажи / комиссия',
  bank: 'Платежи',
  faktura: 'Фактуры',
  one_c: '1С',
  opening_balances: 'Начальное сальдо',
};

const SOURCE_CARDS: Array<{
  key: TestVoronaSourceType;
  title: string;
  description: string;
  monthly: boolean;
}> = [
  {
    key: 'sales',
    title: 'Продажи',
    description: 'VBAZA · Sales / Komissiya / Status',
    monthly: true,
  },
  {
    key: 'bank',
    title: 'Оплаты',
    description: 'VBANK · банковские оплаты',
    monthly: true,
  },
  {
    key: 'faktura',
    title: 'Фактуры',
    description: 'VFAKTURA · выставленные с/ф',
    monthly: true,
  },
  {
    key: 'one_c',
    title: '1С',
    description: 'Сальдо / проводки 4890–4010 и 6990–6310',
    monthly: true,
  },
  {
    key: 'partners',
    title: 'Справочник',
    description: 'VIPP · ИНН / ПИНФЛ → VID',
    monthly: false,
  },
  {
    key: 'opening_balances',
    title: 'Начальное сальдо',
    description: 'Загружается один раз на год',
    monthly: false,
  },
];

function money(value: number | null | undefined): string {
  const number = Number(value ?? 0);
  return Number.isFinite(number)
    ? number.toLocaleString('ru-RU', { maximumFractionDigits: 2 })
    : '—';
}

function statusClass(status: string): string {
  if (status === 'Без расхождений') {
    return 'border-emerald-200 bg-emerald-50 text-emerald-700';
  }
  if (status === 'Есть оба расхождения') {
    return 'border-rose-200 bg-rose-50 text-rose-700';
  }
  return 'border-amber-200 bg-amber-50 text-amber-700';
}

function formatDateTime(value?: string): string {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export const TestVoronaWorkspace: React.FC<Props> = ({ user, onBack }) => {
  const canRun = hasPermission(user, 'test_vorona.run');
  const canExport = hasPermission(user, 'test_vorona.export');

  const today = new Date();
  const [year, setYear] = useState(today.getFullYear());
  const [month, setMonth] = useState(today.getMonth() + 1);
  const [tab, setTab] = useState<Tab>('reconciliation');
  const [result, setResult] = useState<TestVoronaRunResult | null>(null);
  const [imports, setImports] = useState<TestVoronaImportBatch[]>([]);
  const [importsLoading, setImportsLoading] = useState(false);
  const [running, setRunning] = useState(false);
  const [uploadingSource, setUploadingSource] = useState<TestVoronaSourceType | null>(null);
  const [showUpload, setShowUpload] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error' | 'info'; text: string } | null>(null);
  const [query, setQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('Все');
  const [selected, setSelected] = useState<TestVoronaRow | null>(null);
  const [dataset, setDataset] = useState<DatasetKey>('sales');

  const metrics = result?.custom_metrics?.test_vorona;
  const rows = metrics?.rows || [];

  const loadImports = async () => {
    setImportsLoading(true);
    try {
      setImports(await getTestVoronaImports(year, undefined, true));
    } catch (error: any) {
      setMessage({
        type: 'error',
        text: error?.message || 'Не удалось загрузить историю данных.',
      });
    } finally {
      setImportsLoading(false);
    }
  };

  useEffect(() => {
    void loadImports();
  }, [year]);

  const activeBatch = (sourceType: TestVoronaSourceType): TestVoronaImportBatch | undefined => {
    const source = SOURCE_CARDS.find(item => item.key === sourceType);
    return imports.find(item => {
      if (item.source_type !== sourceType || !Boolean(item.is_active)) return false;
      if (source?.monthly) {
        return Number(item.year) === year && Number(item.month) === month;
      }
      if (sourceType === 'opening_balances') {
        return Number(item.year) === year;
      }
      return sourceType === 'partners';
    });
  };

  const monthlyReadyCount = ['sales', 'bank', 'faktura', 'one_c']
    .filter(source => activeBatch(source as TestVoronaSourceType))
    .length;

  const handleUpload = async (
    sourceType: TestVoronaSourceType,
    file: File,
    replaceExisting = false,
  ) => {
    if (!canRun || uploadingSource) return;
    const source = SOURCE_CARDS.find(item => item.key === sourceType);
    if (!source) return;

    setUploadingSource(sourceType);
    setMessage(null);

    try {
      const response = await uploadTestVoronaSource(sourceType, file, {
        year: sourceType === 'partners' ? undefined : year,
        month: source.monthly ? month : undefined,
        replaceExisting,
      });

      setMessage({
        type: response.state === 'duplicate' ? 'info' : 'success',
        text: response.message,
      });
      await loadImports();
    } catch (error: any) {
      if (error instanceof TestVoronaImportConflictError && !replaceExisting) {
        const oldName = error.batch?.filename || 'текущий файл';
        const confirmed = window.confirm(
          `${SOURCE_CARDS.find(item => item.key === sourceType)?.title}: данные за выбранный период уже загружены (${oldName}).\n\nЗаменить их новым файлом ${file.name}?\n\nСтарая версия останется в истории.`,
        );
        if (confirmed) {
          setUploadingSource(null);
          await handleUpload(sourceType, file, true);
          return;
        }
      } else {
        setMessage({
          type: 'error',
          text: error?.message || 'Не удалось сохранить файл в базу.',
        });
      }
    } finally {
      setUploadingSource(null);
    }
  };

  const handleRun = async () => {
    if (!canRun || running) return;
    setRunning(true);
    setMessage(null);
    setSelected(null);

    try {
      const next = await runStoredTestVorona(year, month);
      setResult(next);
      setTab('reconciliation');
      setShowUpload(false);
      setMessage({
        type: 'success',
        text: `Сверка пересчитана по базе за январь–${MONTHS[month - 1].toLowerCase()}. Run ${next.run_id}.`,
      });
    } catch (error: any) {
      setMessage({
        type: 'error',
        text: error?.message || 'Не удалось выполнить сверку по базе.',
      });
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

    XLSX.utils.book_append_sheet(
      workbook,
      XLSX.utils.json_to_sheet(summary),
      'Сверка',
    );
    XLSX.writeFile(
      workbook,
      `Тестовая_ворона_${year}_${String(month).padStart(2, '0')}.xlsx`,
    );
  };

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

  const navItems: Array<{
    id: Tab;
    label: string;
    icon: React.ElementType;
    subtitle: string;
  }> = [
    { id: 'reconciliation', label: 'Сверка', icon: LayoutDashboard, subtitle: 'Главный контроль' },
    { id: 'database', label: 'База данных', icon: Database, subtitle: 'Накопленные операции' },
    { id: 'partners', label: 'Партнёры', icon: Users, subtitle: 'ИНН / ПИНФЛ / VID' },
    { id: 'uploads', label: 'Загрузки', icon: History, subtitle: 'История версий' },
  ];

  const statuses = [
    'Все',
    'Есть Difference',
    'Есть Difference 1C',
    'Есть оба расхождения',
    'Без расхождений',
  ];

  return (
    <div className="flex min-h-full bg-[#f6f8fb] text-slate-900">
      <aside className="sticky top-0 h-screen w-[238px] shrink-0 border-r border-slate-200 bg-white">
        <div className="flex h-full flex-col">
          <div className="border-b border-slate-100 px-5 py-5">
            <button type="button" onClick={onBack} className="flex items-center gap-2 text-left">
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
                  onClick={() => setTab(item.id)}
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
                  <h1 className="text-[22px] font-black tracking-tight text-slate-900">
                    Взаиморасчёты с партнёрами
                  </h1>
                  <span className="rounded-full border border-indigo-200 bg-indigo-50 px-2 py-0.5 text-[9px] font-bold text-indigo-700">
                    Тестовая ворона
                  </span>
                </div>
                <p className="mt-1 text-xs text-slate-500">
                  Накопительная база · ежемесячная дозагрузка · контроль Difference и 1С
                </p>
              </div>

              <div className="flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  onClick={() => setShowUpload(true)}
                  className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-[11px] font-bold text-slate-700 shadow-sm hover:bg-slate-50"
                >
                  <Upload className="h-3.5 w-3.5" />
                  Добавить данные
                </button>

                <button
                  type="button"
                  onClick={() => void handleRun()}
                  disabled={!canRun || running}
                  className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-3 py-2 text-[11px] font-bold text-white shadow-sm hover:bg-indigo-700 disabled:opacity-40"
                >
                  {running
                    ? <LoaderCircle className="h-3.5 w-3.5 animate-spin" />
                    : <RefreshCcw className="h-3.5 w-3.5" />}
                  Пересчитать
                </button>

                <button
                  type="button"
                  onClick={exportResult}
                  disabled={!result || !canExport}
                  className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-[11px] font-bold text-slate-700 shadow-sm hover:bg-slate-50 disabled:opacity-40"
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
            <div className={`flex items-center justify-between rounded-xl border px-4 py-2.5 text-[11px] font-semibold ${
              message.type === 'error'
                ? 'border-rose-200 bg-rose-50 text-rose-700'
                : message.type === 'success'
                  ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
                  : 'border-indigo-200 bg-indigo-50 text-indigo-700'
            }`}>
              <span>{message.text}</span>
              <button type="button" onClick={() => setMessage(null)}>
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
          )}

          <section className="rounded-xl border border-slate-200 bg-white p-3 shadow-xs">
            <div className="flex flex-wrap items-center gap-2">
              <label className="flex items-center gap-2 rounded-lg border border-slate-200 px-3 py-2.5 text-[11px] font-semibold text-slate-600">
                Год
                <input
                  type="number"
                  value={year}
                  onChange={event => setYear(Number(event.target.value) || today.getFullYear())}
                  className="w-16 bg-transparent text-right font-bold text-slate-900 outline-none"
                />
              </label>

              <select
                value={month}
                onChange={event => {
                  setMonth(Number(event.target.value));
                  setResult(null);
                  setSelected(null);
                }}
                className="rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-[11px] font-semibold text-slate-600 outline-none"
              >
                {MONTHS.map((name, index) => (
                  <option key={name} value={index + 1}>{name}</option>
                ))}
              </select>

              <div className="ml-1 text-[10px] text-slate-400">
                Расчёт идёт накопительно: январь–{MONTHS[month - 1].toLowerCase()}
              </div>

              <div className="ml-auto flex items-center gap-2">
                <span className={`rounded-full border px-2.5 py-1 text-[9px] font-bold ${
                  monthlyReadyCount >= 3
                    ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
                    : 'border-amber-200 bg-amber-50 text-amber-700'
                }`}>
                  {monthlyReadyCount}/4 месячных источника
                </span>
                {activeBatch('partners') && (
                  <span className="rounded-full border border-emerald-200 bg-emerald-50 px-2.5 py-1 text-[9px] font-bold text-emerald-700">
                    Справочник загружен
                  </span>
                )}
              </div>
            </div>
          </section>

          {tab === 'reconciliation' && (
            <>
              <section className="grid grid-cols-2 gap-3 xl:grid-cols-4">
                <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-xs">
                  <div className="text-[10px] font-bold uppercase tracking-wide text-slate-400">Партнёров</div>
                  <div className="mt-2 text-2xl font-black text-slate-900">{rows.length || '—'}</div>
                  <div className="mt-2 text-[9px] text-slate-400">в расчёте</div>
                </div>
                <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-xs">
                  <div className="text-[10px] font-bold uppercase tracking-wide text-slate-400">С расхождениями</div>
                  <div className="mt-2 text-2xl font-black text-rose-600">{result?.summary.discrepancy_count ?? '—'}</div>
                  <div className="mt-2 text-[9px] text-slate-400">требуют разбора</div>
                </div>
                <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-xs">
                  <div className="text-[10px] font-bold uppercase tracking-wide text-slate-400">Difference</div>
                  <div className="mt-2 text-xl font-black text-rose-600">{result ? money(metrics?.totals?.difference) : '—'}</div>
                  <div className="mt-2 text-[9px] text-slate-400">Faktura − Komissiya</div>
                </div>
                <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-xs">
                  <div className="text-[10px] font-bold uppercase tracking-wide text-slate-400">Difference 1C</div>
                  <div className="mt-2 text-xl font-black text-amber-600">{result ? money(metrics?.totals?.difference_1c) : '—'}</div>
                  <div className="mt-2 text-[9px] text-slate-400">Saldo − 1C</div>
                </div>
              </section>

              <section className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-xs">
                <div className="flex flex-col gap-3 border-b border-slate-100 p-4 xl:flex-row xl:items-center xl:justify-between">
                  <div>
                    <h2 className="text-xs font-black text-slate-900">Контроль взаиморасчётов</h2>
                    <p className="mt-0.5 text-[9px] text-slate-400">
                      Период: январь–{MONTHS[month - 1].toLowerCase()} {year}
                    </p>
                  </div>

                  <div className="flex flex-wrap items-center gap-2">
                    <select
                      value={statusFilter}
                      onChange={event => setStatusFilter(event.target.value)}
                      className="rounded-lg border border-slate-200 px-3 py-2 text-[10px] font-semibold text-slate-600 outline-none"
                    >
                      {statuses.map(status => (
                        <option key={status} value={status}>{status}</option>
                      ))}
                    </select>

                    <label className="relative min-w-[300px]">
                      <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                      <input
                        value={query}
                        onChange={event => setQuery(event.target.value)}
                        placeholder="ИНН / ПИНФЛ / VID / партнёр"
                        className="w-full rounded-lg border border-slate-200 bg-slate-50 py-2 pl-9 pr-3 text-xs outline-none focus:bg-white"
                      />
                    </label>
                  </div>
                </div>

                <div className="overflow-x-auto">
                  <table className="min-w-[1450px] w-full text-[11px]">
                    <thead className="bg-slate-50 text-[9px] uppercase tracking-wide text-slate-400">
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
                          className="cursor-pointer hover:bg-indigo-50/40"
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
                            <span className={`inline-flex whitespace-nowrap rounded-full border px-2 py-1 text-[9px] font-bold ${statusClass(row.status)}`}>
                              {row.status}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>

                  {!result && (
                    <div className="flex min-h-52 flex-col items-center justify-center px-6 py-10 text-center">
                      <Database className="h-7 w-7 text-slate-300" />
                      <div className="mt-3 text-sm font-black text-slate-800">Данные теперь хранятся в базе</div>
                      <div className="mt-1 max-w-lg text-xs text-slate-400">
                        Загрузите текущий месяц один раз. Затем нажмите «Пересчитать» — прошлые месяцы подтянутся автоматически.
                      </div>
                      <button
                        type="button"
                        onClick={() => setShowUpload(true)}
                        className="mt-4 rounded-lg bg-indigo-600 px-4 py-2 text-[10px] font-bold text-white"
                      >
                        Добавить данные за {MONTHS[month - 1].toLowerCase()}
                      </button>
                    </div>
                  )}
                </div>
              </section>
            </>
          )}

          {tab === 'database' && (
            <section className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-xs">
              <div className="flex flex-col gap-3 border-b border-slate-100 p-4 xl:flex-row xl:items-center xl:justify-between">
                <div>
                  <h2 className="text-sm font-black text-slate-900">База данных</h2>
                  <p className="mt-1 text-[10px] text-slate-400">
                    Активные данные, попавшие в последний расчёт
                  </p>
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

              {result ? (
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
                      {filteredSourceRows.slice(0, 1500).map((row, index) => (
                        <tr key={index} className="hover:bg-slate-50">
                          <td className="px-4 py-3">
                            {row.side || (typeof row.month === 'number' ? MONTHS[row.month - 1] : row.month) || '—'}
                          </td>
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
              ) : (
                <div className="p-12 text-center text-xs text-slate-400">
                  Нажмите «Пересчитать», чтобы открыть активные строки базы.
                </div>
              )}
            </section>
          )}

          {tab === 'partners' && (
            <section className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-xs">
              <div className="flex items-center justify-between border-b border-slate-100 p-4">
                <div>
                  <h2 className="text-sm font-black text-slate-900">Справочник партнёров</h2>
                  <p className="mt-1 text-[10px] text-slate-400">VIPP хранится постоянно и не требует ежемесячной загрузки</p>
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

              {result ? (
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
                      {filteredPartners.slice(0, 2500).map((row, index) => (
                        <tr key={index} className="hover:bg-slate-50">
                          <td className="px-4 py-3 font-bold text-indigo-700">{row.vid}</td>
                          <td className="px-4 py-3 font-semibold text-slate-800">{row.partner}</td>
                          <td className="px-4 py-3 text-slate-600">{row.inn}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="p-12 text-center text-xs text-slate-400">
                  Справочник уже может быть в базе. Нажмите «Пересчитать», чтобы отобразить его здесь.
                </div>
              )}
            </section>
          )}

          {tab === 'uploads' && (
            <section className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-xs">
              <div className="flex items-center justify-between border-b border-slate-100 p-4">
                <div>
                  <h2 className="text-sm font-black text-slate-900">История загрузок</h2>
                  <p className="mt-1 text-[10px] text-slate-400">
                    Старые версии не участвуют в расчёте, но остаются для контроля
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => void loadImports()}
                  disabled={importsLoading}
                  className="inline-flex items-center gap-2 rounded-lg border border-slate-200 px-3 py-2 text-[10px] font-bold text-slate-600 hover:bg-slate-50 disabled:opacity-40"
                >
                  <RefreshCcw className={`h-3.5 w-3.5 ${importsLoading ? 'animate-spin' : ''}`} />
                  Обновить
                </button>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full min-w-[900px] text-[11px]">
                  <thead className="bg-slate-50 text-[9px] uppercase tracking-wide text-slate-400">
                    <tr>
                      <th className="px-4 py-3 text-left">Дата</th>
                      <th className="px-4 py-3 text-left">Источник</th>
                      <th className="px-4 py-3 text-left">Период</th>
                      <th className="px-4 py-3 text-left">Файл</th>
                      <th className="px-4 py-3 text-right">Строк</th>
                      <th className="px-4 py-3 text-left">Статус</th>
                      <th className="px-4 py-3 text-left">Пользователь</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {imports.map(item => (
                      <tr key={item.id} className={Boolean(item.is_active) ? 'hover:bg-slate-50' : 'bg-slate-50/50 text-slate-400'}>
                        <td className="px-4 py-3">{formatDateTime(item.uploaded_at)}</td>
                        <td className="px-4 py-3 font-semibold">
                          {SOURCE_CARDS.find(source => source.key === item.source_type)?.title || item.source_type}
                        </td>
                        <td className="px-4 py-3">{item.period_key}</td>
                        <td className="max-w-[300px] truncate px-4 py-3" title={item.filename}>{item.filename}</td>
                        <td className="px-4 py-3 text-right tabular-nums">{item.rows_count}</td>
                        <td className="px-4 py-3">
                          <span className={`rounded-full border px-2 py-1 text-[9px] font-bold ${
                            Boolean(item.is_active)
                              ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
                              : 'border-slate-200 bg-slate-100 text-slate-500'
                          }`}>
                            {Boolean(item.is_active) ? 'Активная' : 'Заменена'}
                          </span>
                        </td>
                        <td className="px-4 py-3">{item.uploaded_by}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {!importsLoading && imports.length === 0 && (
                  <div className="p-12 text-center text-xs text-slate-400">Загрузок пока нет.</div>
                )}
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
                ['Оплаты / Bank', selected.bank],
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
          </div>
        </div>
      )}

      {showUpload && (
        <div className="fixed inset-0 z-[70] flex items-center justify-center bg-slate-950/30 p-4 backdrop-blur-[2px]">
          <div className="w-full max-w-6xl rounded-2xl border border-slate-200 bg-white shadow-2xl">
            <div className="flex items-start justify-between border-b border-slate-100 px-5 py-4">
              <div>
                <h2 className="text-sm font-black text-slate-900">Добавить данные в базу</h2>
                <p className="mt-1 text-[10px] text-slate-400">
                  {MONTHS[month - 1]} {year} · загружай только новые данные за закрытый месяц
                </p>
              </div>
              <button type="button" onClick={() => setShowUpload(false)} className="rounded-lg p-2 text-slate-400 hover:bg-slate-50">
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="grid grid-cols-1 gap-3 p-5 md:grid-cols-2 xl:grid-cols-3">
              {SOURCE_CARDS.map(source => {
                const batch = activeBatch(source.key);
                const uploading = uploadingSource === source.key;

                return (
                  <div key={source.key} className="rounded-xl border border-slate-200 p-4">
                    <div className="mb-3 flex items-start justify-between gap-2">
                      <div>
                        <div className="text-xs font-black text-slate-800">{source.title}</div>
                        <div className="mt-1 text-[9px] leading-4 text-slate-400">{source.description}</div>
                      </div>
                      {batch && (
                        <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-500" />
                      )}
                    </div>

                    {batch && (
                      <div className="mb-3 rounded-lg border border-emerald-100 bg-emerald-50 px-3 py-2">
                        <div className="truncate text-[9px] font-bold text-emerald-700" title={batch.filename}>
                          {batch.filename}
                        </div>
                        <div className="mt-1 text-[8px] text-emerald-600">
                          {batch.rows_count} строк · {formatDateTime(batch.uploaded_at)}
                        </div>
                      </div>
                    )}

                    <FileDropZone
                      accept=".xlsx,.xls"
                      onFile={file => void handleUpload(source.key, file)}
                      className="flex min-h-24 cursor-pointer flex-col items-center justify-center rounded-lg border border-dashed border-slate-300 bg-slate-50 p-3 text-center hover:bg-slate-100"
                      activeClassName="border-indigo-400 bg-indigo-50 ring-2 ring-indigo-100"
                    >
                      {isDragging => (
                        <>
                          {uploading
                            ? <LoaderCircle className="mb-2 h-5 w-5 animate-spin text-indigo-500" />
                            : <Upload className="mb-2 h-5 w-5 text-indigo-500" />}
                          <div className="text-[9px] font-bold text-slate-700">
                            {uploading
                              ? 'Сохраняем…'
                              : batch
                                ? 'Перетащите новый файл для замены'
                                : isDragging
                                  ? 'Отпустите файл'
                                  : 'Перетащите или выберите файл'}
                          </div>
                        </>
                      )}
                    </FileDropZone>

                    <div className="mt-2 text-[8px] text-slate-400">
                      {source.monthly
                        ? `Период: ${MONTHS[month - 1]} ${year}`
                        : source.key === 'partners'
                          ? 'Общий справочник — действует для всех месяцев'
                          : `Начальное сальдо на ${year} год`}
                    </div>
                  </div>
                );
              })}
            </div>

            <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 px-5 py-4">
              <div className="text-[10px] text-slate-500">
                Повторный файл не загрузится. При замене старая версия останется в истории.
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
                  disabled={!canRun || running}
                  className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-[10px] font-bold text-white hover:bg-indigo-700 disabled:opacity-40"
                >
                  {running ? <LoaderCircle className="h-3.5 w-3.5 animate-spin" /> : <RefreshCcw className="h-3.5 w-3.5" />}
                  Пересчитать
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
