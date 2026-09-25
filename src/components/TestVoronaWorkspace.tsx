import React, { useMemo, useState } from 'react';
import {
  AlertCircle,
  ArrowLeft,
  CheckCircle2,
  Database,
  FileSpreadsheet,
  LoaderCircle,
  Play,
  Search,
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

type Tab = 'reconciliation' | 'database' | 'partners';
type DatasetKey = 'sales' | 'bank' | 'faktura' | 'one_c' | 'opening_balances';

const DATASET_LABELS: Record<DatasetKey, string> = {
  sales: 'Продажи / комиссия',
  bank: 'Платежи',
  faktura: 'Фактуры',
  one_c: '1С',
  opening_balances: 'Сальдо',
};

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

export const TestVoronaWorkspace: React.FC<Props> = ({ user, onBack }) => {
  const canRun = hasPermission(user, 'test_vorona.run');

  const [tab, setTab] = useState<Tab>('reconciliation');
  const [year, setYear] = useState(2026);
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
    if (!canRun || !ready || running) return;
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
      setMessage(`Сверка завершена. Run ${next.run_id}.`);
    } catch (error: any) {
      setMessage(error?.message || 'Не удалось выполнить сверку.');
    } finally {
      setRunning(false);
    }
  };

  const fileCards = [
    ['baza', 'VBAZA', 'Продажи, комиссия, Status, VID'],
    ['bank', 'VBANK', 'Дата, ИНН, партнёр, сумма, VID'],
    ['faktura', 'VFAKTURA', 'Фактуры по партнёрам'],
    ['vipp', 'VIPP', 'ИНН / ПИНФЛ → Vorona Code'],
    ['vorona', 'VORONA 2026', 'Сальдо начала года + лист 1С'],
  ] as const;

  const statuses = ['Все', 'Без расхождений', 'Есть Difference', 'Есть Difference 1C', 'Есть оба расхождения'];

  return (
    <div className="min-h-full bg-slate-50">
      <div className="sticky top-0 z-30 border-b border-slate-200 bg-white/95 backdrop-blur">
        <div className="mx-auto max-w-[1900px] px-5 py-4">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <button
                type="button"
                onClick={onBack}
                className="rounded-lg border border-slate-200 bg-white p-2 text-slate-500 hover:bg-slate-50"
              >
                <ArrowLeft className="h-4 w-4" />
              </button>
              <div>
                <h1 className="text-lg font-black text-slate-900">Тестовая ворона</h1>
                <p className="text-xs text-slate-500">Контроль взаиморасчётов с партнёрами</p>
              </div>
            </div>

            <div className="flex items-center gap-2">
              <label className="flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-600">
                Год
                <input
                  type="number"
                  value={year}
                  onChange={event => setYear(Number(event.target.value) || 2026)}
                  className="w-16 bg-transparent text-right font-bold text-slate-900 outline-none"
                />
              </label>
              <button
                type="button"
                onClick={() => void handleRun()}
                disabled={!canRun || !ready || running}
                className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-xs font-bold text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-40"
              >
                {running ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4 fill-current" />}
                {running ? 'Считаем…' : 'Запустить сверку'}
              </button>
            </div>
          </div>

          <div className="mt-4 flex gap-1 border-t border-slate-100 pt-3">
            {[
              ['reconciliation', 'Сверка'],
              ['database', 'База данных'],
              ['partners', 'Справочник партнёров'],
            ].map(([key, label]) => (
              <button
                key={key}
                type="button"
                onClick={() => setTab(key as Tab)}
                className={`rounded-lg px-3 py-2 text-xs font-bold ${tab === key ? 'bg-indigo-50 text-indigo-700' : 'text-slate-500 hover:bg-slate-50'}`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="mx-auto max-w-[1900px] space-y-5 p-5">
        {!result && (
          <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-xs">
            <div className="mb-4">
              <h2 className="text-sm font-black text-slate-900">Исходные файлы</h2>
              <p className="mt-1 text-xs text-slate-500">Для первого MVP загружаем те же 5 Excel, из которых сейчас собирается VORONA.</p>
            </div>

            <div className="grid grid-cols-1 gap-3 xl:grid-cols-5">
              {fileCards.map(([key, title, subtitle]) => (
                <div key={key} className="rounded-xl border border-slate-200 p-3">
                  <div className="mb-2 flex items-center gap-2">
                    <FileSpreadsheet className="h-4 w-4 text-indigo-600" />
                    <div className="text-xs font-bold text-slate-800">{title}</div>
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
                        <div className="max-w-full truncate text-[11px] font-semibold text-slate-700">
                          {files[key]?.name || (isDragging ? 'Отпустите файл' : 'Перетащите или выберите')}
                        </div>
                        <div className="mt-1 text-[9px] leading-4 text-slate-400">{subtitle}</div>
                      </>
                    )}
                  </FileDropZone>
                </div>
              ))}
            </div>
          </section>
        )}

        {message && (
          <div className="rounded-xl border border-indigo-200 bg-indigo-50 px-4 py-3 text-xs font-semibold text-indigo-700">
            {message}
          </div>
        )}

        {result && tab === 'reconciliation' && (
          <>
            <section className="grid grid-cols-2 gap-3 xl:grid-cols-4">
              {[
                ['Партнёров', rows.length, Users],
                ['С расхождениями', result.summary.discrepancy_count, AlertCircle],
                ['Difference', money(metrics?.totals?.difference), Database],
                ['Difference 1C', money(metrics?.totals?.difference_1c), FileSpreadsheet],
              ].map(([label, value, Icon]: any) => (
                <div key={label} className="rounded-2xl border border-slate-200 bg-white p-4 shadow-xs">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="text-xl font-black text-slate-900">{value}</div>
                      <div className="mt-1 text-[10px] font-bold uppercase tracking-wide text-slate-400">{label}</div>
                    </div>
                    <div className="rounded-lg bg-slate-50 p-2 text-slate-500"><Icon className="h-4 w-4" /></div>
                  </div>
                </div>
              ))}
            </section>

            <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-xs">
              <div className="flex flex-col gap-3 border-b border-slate-100 p-4 xl:flex-row xl:items-center xl:justify-between">
                <div className="flex flex-wrap gap-2">
                  {statuses.map(status => (
                    <button
                      key={status}
                      type="button"
                      onClick={() => setStatusFilter(status)}
                      className={`rounded-lg border px-3 py-1.5 text-[11px] font-semibold ${statusFilter === status ? 'border-indigo-600 bg-indigo-600 text-white' : 'border-slate-200 text-slate-600 hover:bg-slate-50'}`}
                    >
                      {status}
                    </button>
                  ))}
                </div>
                <label className="relative min-w-[320px]">
                  <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                  <input
                    value={query}
                    onChange={event => setQuery(event.target.value)}
                    placeholder="ИНН / ПИНФЛ / VID / партнёр"
                    className="w-full rounded-lg border border-slate-200 py-2 pl-9 pr-3 text-xs outline-none focus:border-indigo-300 focus:ring-2 focus:ring-indigo-100"
                  />
                </label>
              </div>

              <div className="overflow-x-auto">
                <table className="min-w-[1450px] w-full text-xs">
                  <thead className="bg-slate-50 text-[10px] uppercase tracking-wide text-slate-400">
                    <tr>
                      {['Партнёр','ИНН / ПИНФЛ','VID','Payment','Bank','Faktura','Komissiya','Saldo','1C','Difference','Difference 1C','Статус'].map(header => (
                        <th key={header} className="px-3 py-3 text-left">{header}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {filteredRows.map(row => (
                      <tr
                        key={row.vid}
                        onClick={() => setSelected(row)}
                        className="cursor-pointer hover:bg-slate-50"
                      >
                        <td className="max-w-[280px] truncate px-3 py-3 font-semibold text-slate-800" title={row.partner}>{row.partner}</td>
                        <td className="px-3 py-3 text-slate-600">{row.inn || '—'}</td>
                        <td className="px-3 py-3 font-bold text-indigo-700">{row.vid}</td>
                        <td className="px-3 py-3 text-right tabular-nums">{money(row.payment)}</td>
                        <td className="px-3 py-3 text-right tabular-nums">{money(row.bank)}</td>
                        <td className="px-3 py-3 text-right tabular-nums">{money(row.faktura)}</td>
                        <td className="px-3 py-3 text-right tabular-nums">{money(row.komissiya)}</td>
                        <td className="px-3 py-3 text-right font-semibold tabular-nums">{money(row.saldo)}</td>
                        <td className="px-3 py-3 text-right tabular-nums">{money(row.one_c)}</td>
                        <td className={`px-3 py-3 text-right font-bold tabular-nums ${Math.abs(row.difference) > 1 ? 'bg-rose-50 text-rose-700' : 'text-emerald-700'}`}>{money(row.difference)}</td>
                        <td className={`px-3 py-3 text-right font-bold tabular-nums ${Math.abs(row.difference_1c) > 1 ? 'bg-amber-50 text-amber-700' : 'text-emerald-700'}`}>{money(row.difference_1c)}</td>
                        <td className="px-3 py-3">
                          <span className={`inline-flex rounded-full border px-2 py-1 text-[10px] font-bold ${statusClass(row.status)}`}>{row.status}</span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {filteredRows.length === 0 && (
                  <div className="px-5 py-12 text-center text-sm text-slate-500">Строки не найдены.</div>
                )}
              </div>
            </section>
          </>
        )}

        {result && tab === 'database' && (
          <section className="rounded-2xl border border-slate-200 bg-white shadow-xs">
            <div className="flex flex-col gap-3 border-b border-slate-100 p-4 xl:flex-row xl:items-center xl:justify-between">
              <div className="flex flex-wrap gap-2">
                {(Object.keys(DATASET_LABELS) as DatasetKey[]).map(key => (
                  <button
                    key={key}
                    type="button"
                    onClick={() => setDataset(key)}
                    className={`rounded-lg border px-3 py-1.5 text-[11px] font-semibold ${dataset === key ? 'border-indigo-600 bg-indigo-600 text-white' : 'border-slate-200 text-slate-600 hover:bg-slate-50'}`}
                  >
                    {DATASET_LABELS[key]} · {metrics?.source_counts?.[key] ?? 0}
                  </button>
                ))}
              </div>
              <label className="relative min-w-[320px]">
                <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                <input
                  value={query}
                  onChange={event => setQuery(event.target.value)}
                  placeholder="Фильтр по партнёру / ИНН / VID"
                  className="w-full rounded-lg border border-slate-200 py-2 pl-9 pr-3 text-xs outline-none"
                />
              </label>
            </div>

            <div className="overflow-x-auto">
              <table className="min-w-[900px] w-full text-xs">
                <thead className="bg-slate-50 text-[10px] uppercase tracking-wide text-slate-400">
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

        {result && tab === 'partners' && (
          <section className="rounded-2xl border border-slate-200 bg-white shadow-xs">
            <div className="flex items-center justify-between border-b border-slate-100 p-4">
              <div>
                <h2 className="text-sm font-black text-slate-900">Справочник партнёров</h2>
                <p className="mt-1 text-xs text-slate-500">Данные из VIPP: ИНН / ПИНФЛ → Vorona Code.</p>
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
              <table className="w-full min-w-[800px] text-xs">
                <thead className="bg-slate-50 text-[10px] uppercase tracking-wide text-slate-400">
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
      </div>

      {selected && (
        <div className="fixed inset-y-0 right-0 z-50 w-full max-w-md border-l border-slate-200 bg-white shadow-2xl">
          <div className="flex items-start justify-between border-b border-slate-100 p-5">
            <div className="min-w-0">
              <div className="truncate text-base font-black text-slate-900">{selected.partner}</div>
              <div className="mt-1 text-xs text-slate-500">ИНН: {selected.inn || '—'} · VID: {selected.vid}</div>
            </div>
            <button type="button" onClick={() => setSelected(null)} className="rounded-lg p-2 text-slate-400 hover:bg-slate-50">
              <X className="h-4 w-4" />
            </button>
          </div>

          <div className="space-y-4 p-5">
            <div className="grid grid-cols-2 gap-3">
              {[
                ['Начальное сальдо', selected.opening_balance],
                ['Payment', selected.payment],
                ['Bank', selected.bank],
                ['Faktura', selected.faktura],
                ['Komissiya', selected.komissiya],
                ['Saldo', selected.saldo],
                ['1C', selected.one_c],
              ].map(([label, value]) => (
                <div key={String(label)} className="rounded-xl border border-slate-200 p-3">
                  <div className="text-sm font-black text-slate-900">{money(Number(value))}</div>
                  <div className="mt-1 text-[10px] font-bold uppercase text-slate-400">{label}</div>
                </div>
              ))}
            </div>

            <div className="rounded-xl border border-rose-200 bg-rose-50 p-4">
              <div className="text-[10px] font-bold uppercase text-rose-500">Difference</div>
              <div className="mt-1 text-xl font-black text-rose-700">{money(selected.difference)}</div>
              <div className="mt-3 border-t border-rose-200 pt-3 text-[10px] font-bold uppercase text-amber-600">Difference 1C</div>
              <div className="mt-1 text-xl font-black text-amber-700">{money(selected.difference_1c)}</div>
            </div>

            <button
              type="button"
              onClick={() => {
                setQuery(selected.vid);
                setDataset('sales');
                setTab('database');
                setSelected(null);
              }}
              className="w-full rounded-xl bg-slate-900 px-4 py-3 text-xs font-bold text-white hover:bg-slate-800"
            >
              Показать исходные операции
            </button>
          </div>
        </div>
      )}
    </div>
  );
};
