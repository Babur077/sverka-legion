import React, { useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle,
  ArrowLeft,
  BarChart3,
  CheckCircle2,
  FileSpreadsheet,
  History,
  LayoutDashboard,
  Play,
  Receipt,
  RefreshCw,
  Save,
  Trash2,
  Upload,
} from 'lucide-react';
import { SystemSettings, User } from '../types';
import { guessCol, parseFile } from '../utils/fileParser';
import {
  deletePaynetArchive,
  getPaynetArchive,
  PaynetArchiveRecord,
  PaynetRunResult,
  runPaynetViaApi,
  savePaynetArchive,
} from '../utils/paynetApi';

type PaynetSection = 'overview' | 'workspace' | 'analytics' | 'archive';

interface PaynetWorkspaceProps {
  user: User;
  settings: SystemSettings;
  onBack: () => void;
}

interface ParsedFileState {
  file: File;
  name: string;
  columns: string[];
  rows: number;
}

const fmt = (value: number) =>
  Number(value || 0).toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export const PaynetWorkspace: React.FC<PaynetWorkspaceProps> = ({ user, settings, onBack }) => {
  const canRun = user.role === 'admin' || user.permissions?.includes('paynet.run') || false;
  const [section, setSection] = useState<PaynetSection>('overview');
  const [archive, setArchive] = useState<PaynetArchiveRecord[]>([]);
  const [archiveError, setArchiveError] = useState<string | null>(null);
  const [archiveLoading, setArchiveLoading] = useState(false);

  const [billing, setBilling] = useState<ParsedFileState | null>(null);
  const [agent, setAgent] = useState<ParsedFileState | null>(null);
  const [billingIdCol, setBillingIdCol] = useState('');
  const [billingAmountCol, setBillingAmountCol] = useState('');
  const [billingStatusCol, setBillingStatusCol] = useState('');
  const [agentIdCol, setAgentIdCol] = useState('');
  const [agentAmountCol, setAgentAmountCol] = useState('');
  const [agentStatusCol, setAgentStatusCol] = useState('');
  const [agentCommissionCol, setAgentCommissionCol] = useState('');
  const [providerName, setProviderName] = useState('Paynet');
  const [result, setResult] = useState<PaynetRunResult | null>(null);
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);

  const loadArchive = async () => {
    setArchiveLoading(true);
    setArchiveError(null);
    try {
      setArchive(await getPaynetArchive(user.username));
    } catch (error: any) {
      setArchiveError(error?.message || 'Не удалось загрузить архив Paynet.');
    } finally {
      setArchiveLoading(false);
    }
  };

  useEffect(() => {
    void loadArchive();
  }, [user.username]);

  const handleFile = async (file: File, side: 'billing' | 'agent') => {
    const parsed = await parseFile(file);
    const state: ParsedFileState = {
      file,
      name: parsed.fileName,
      columns: parsed.columns,
      rows: parsed.rows.length,
    };

    if (side === 'billing') {
      setBilling(state);
      setBillingIdCol(guessCol(parsed.columns, ['transaction', 'txn', 'order', 'id', 'номер']) || parsed.columns[0] || '');
      setBillingAmountCol(guessCol(parsed.columns, ['amount', 'сумма', 'sum']) || parsed.columns[1] || '');
      setBillingStatusCol(guessCol(parsed.columns, ['status', 'статус']) || '');
    } else {
      setAgent(state);
      setAgentIdCol(guessCol(parsed.columns, ['transaction', 'txn', 'order', 'id', 'номер']) || parsed.columns[0] || '');
      setAgentAmountCol(guessCol(parsed.columns, ['amount', 'сумма', 'sum']) || parsed.columns[1] || '');
      setAgentStatusCol(guessCol(parsed.columns, ['status', 'статус']) || '');
      setAgentCommissionCol(guessCol(parsed.columns, ['commission', 'комисс']) || '');
    }
    setResult(null);
    setRunError(null);
    setSaveMessage(null);
  };

  const run = async () => {
    if (!billing || !agent || !billingIdCol || !billingAmountCol || !agentIdCol || !agentAmountCol) {
      setRunError('Загрузите оба файла и выберите Transaction ID и сумму с обеих сторон.');
      return;
    }

    setRunning(true);
    setRunError(null);
    setSaveMessage(null);
    try {
      const data = await runPaynetViaApi(user.username, billing.file, agent.file, {
        billingIdCol,
        billingAmountCol,
        billingStatusCol,
        agentIdCol,
        agentAmountCol,
        agentStatusCol,
        agentCommissionCol,
        providerName,
        tolerance: settings.amount_tolerance || 0.01,
      });
      setResult(data);
    } catch (error: any) {
      setRunError(error?.message || 'Не удалось выполнить сверку Paynet.');
    } finally {
      setRunning(false);
    }
  };

  const saveResult = async () => {
    if (!result) return;
    setSaveMessage(null);
    try {
      await savePaynetArchive(user.username, result, providerName);
      setSaveMessage('Результат сохранён в серверный архив.');
      await loadArchive();
    } catch (error: any) {
      setSaveMessage(error?.message || 'Не удалось сохранить результат.');
    }
  };

  const deleteArchive = async (id: number) => {
    try {
      await deletePaynetArchive(user.username, id);
      await loadArchive();
    } catch (error: any) {
      setArchiveError(error?.message || 'Не удалось удалить запись.');
    }
  };

  const paynetMetrics = result?.custom_metrics?.paynet;
  const totalArchivedBilling = archive.reduce((sum, item) => sum + Number(item.total_our || 0), 0);
  const totalArchivedAgent = archive.reduce((sum, item) => sum + Number(item.total_bank || 0), 0);
  const totalArchivedCommission = archive.reduce((sum, item) => sum + Number(item.total_commission || 0), 0);
  const avgMatch = archive.length
    ? archive.reduce((sum, item) => sum + Number(item.extra?.match_percentage || 0), 0) / archive.length
    : 0;

  const recent = archive.slice(0, 5);
  const providerStats = useMemo(() => {
    const map = new Map<string, { provider: string; runs: number; volume: number; commission: number; issues: number }>();
    archive.forEach(item => {
      const provider = String(item.extra?.provider_name || item.bank_name || 'Не указан');
      const current = map.get(provider) || { provider, runs: 0, volume: 0, commission: 0, issues: 0 };
      current.runs += 1;
      current.volume += Number(item.total_bank || 0);
      current.commission += Number(item.total_commission || 0);
      current.issues += Number(item.mismatch_count || 0) + Number(item.only_our_count || 0) + Number(item.only_bank_count || 0);
      map.set(provider, current);
    });
    return Array.from(map.values()).sort((a, b) => b.volume - a.volume);
  }, [archive]);

  const menu: Array<{ id: PaynetSection; label: string; icon: React.ElementType; requiresRun?: boolean }> = [
    { id: 'overview', label: 'Обзор', icon: LayoutDashboard },
    { id: 'workspace', label: 'Новая сверка', icon: Play, requiresRun: true },
    { id: 'analytics', label: 'Аналитика', icon: BarChart3 },
    { id: 'archive', label: 'Архив', icon: History },
  ];

  return (
    <div className="min-h-full bg-slate-50">
      <div className="border-b border-slate-200 bg-white">
        <div className="w-full max-w-[1800px] mx-auto px-6 xl:px-8 py-4 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3 min-w-0">
            <button onClick={onBack} className="p-2 rounded-lg border border-slate-200 text-slate-500 hover:bg-slate-50" title="К модулям">
              <ArrowLeft className="w-4 h-4" />
            </button>
            <div className="w-10 h-10 rounded-xl bg-cyan-50 border border-cyan-100 text-cyan-700 flex items-center justify-center">
              <Receipt className="w-5 h-5" />
            </div>
            <div className="min-w-0">
              <h1 className="text-lg font-bold text-slate-900">Paynet / Payme</h1>
              <p className="text-xs text-slate-500">Transaction ID · суммы · статусы · комиссии</p>
            </div>
          </div>
          {canRun && (
            <button onClick={() => setSection('workspace')} className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-indigo-600 text-white text-sm font-semibold hover:bg-indigo-700">
              <Play className="w-3.5 h-3.5 fill-white" />
              Новая сверка
            </button>
          )}
        </div>
      </div>

      <div className="w-full max-w-[1800px] mx-auto px-6 xl:px-8 py-6 grid grid-cols-1 lg:grid-cols-[230px_minmax(0,1fr)] gap-6">
        <aside className="bg-white border border-slate-200 rounded-xl p-2 h-fit shadow-xs">
          <div className="px-3 py-2 text-[10px] font-bold uppercase tracking-wider text-slate-400">Paynet workspace</div>
          <nav className="space-y-1">
            {menu.filter(item => !item.requiresRun || canRun).map(item => {
              const Icon = item.icon;
              const active = section === item.id;
              return (
                <button
                  key={item.id}
                  onClick={() => setSection(item.id)}
                  className={`w-full flex items-center gap-2.5 px-3 py-2.5 rounded-lg text-sm text-left transition-colors ${active ? 'bg-indigo-50 text-indigo-700 font-semibold' : 'text-slate-600 hover:bg-slate-50'}`}
                >
                  <Icon className="w-4 h-4" />
                  {item.label}
                </button>
              );
            })}
          </nav>
        </aside>

        <div className="min-w-0 space-y-5">
          {archiveError && (
            <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-xs text-rose-700">{archiveError}</div>
          )}

          {section === 'overview' && (
            <>
              <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-xs flex items-center justify-between gap-4">
                <div>
                  <div className="text-xs text-slate-500">Модуль платежных систем</div>
                  <h2 className="text-xl font-bold text-slate-900 mt-1">Состояние сверок Paynet / Payme</h2>
                  <p className="text-sm text-slate-500 mt-1">Краткая статистика сохранённых запусков и последние результаты.</p>
                </div>
                {canRun && <button onClick={() => setSection('workspace')} className="px-4 py-2.5 rounded-lg bg-indigo-600 text-white text-sm font-semibold">Запустить сверку</button>}
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
                {[
                  ['Сохранённых запусков', archive.length.toLocaleString('ru-RU')],
                  ['Средний Match', archive.length ? `${avgMatch.toFixed(2)}%` : '—'],
                  ['Оборот провайдера', `${fmt(totalArchivedAgent)} ${settings.currency}`],
                  ['Комиссия', `${fmt(totalArchivedCommission)} ${settings.currency}`],
                ].map(([label, value]) => (
                  <div key={label} className="bg-white border border-slate-200 rounded-xl p-4 shadow-xs">
                    <div className="text-xs text-slate-500">{label}</div>
                    <div className="text-xl font-bold text-slate-900 mt-1 break-words">{value}</div>
                  </div>
                ))}
              </div>

              <div className="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-xs">
                <div className="px-5 py-4 border-b border-slate-100 flex items-center justify-between">
                  <div><h3 className="font-semibold text-slate-900">Последние запуски</h3><p className="text-xs text-slate-500">Серверный архив Paynet</p></div>
                  <button onClick={() => void loadArchive()} className="p-2 rounded-lg text-slate-500 hover:bg-slate-50"><RefreshCw className={`w-4 h-4 ${archiveLoading ? 'animate-spin' : ''}`} /></button>
                </div>
                {recent.length === 0 ? (
                  <div className="p-10 text-center text-sm text-slate-500">Сохранённых запусков пока нет.</div>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="min-w-full text-xs">
                      <thead className="bg-slate-50 text-slate-500"><tr>{['Дата','Провайдер','Биллинг','Провайдер','Match','Проблемы'].map(h => <th key={h} className="px-4 py-2.5 text-left font-semibold">{h}</th>)}</tr></thead>
                      <tbody className="divide-y divide-slate-100">
                        {recent.map(item => (
                          <tr key={item.id}>
                            <td className="px-4 py-3 whitespace-nowrap">{new Date(item.timestamp).toLocaleString('ru-RU')}</td>
                            <td className="px-4 py-3 font-semibold">{item.extra?.provider_name || item.bank_name}</td>
                            <td className="px-4 py-3">{fmt(item.total_our)}</td>
                            <td className="px-4 py-3">{fmt(item.total_bank)}</td>
                            <td className="px-4 py-3 font-semibold">{Number(item.extra?.match_percentage || 0).toFixed(2)}%</td>
                            <td className="px-4 py-3">{item.mismatch_count + item.only_our_count + item.only_bank_count}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </>
          )}

          {section === 'workspace' && canRun && (
            <>
              <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-xs">
                <h2 className="text-lg font-bold text-slate-900">Новая сверка Paynet / Payme</h2>
                <p className="text-sm text-slate-500 mt-1">Загрузите внутренний биллинг и реестр провайдера. Максимальный размер файла наследует общий лимит платформы.</p>
              </div>

              <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
                {([
                  ['billing', 'Внутренний биллинг / Orders', billing],
                  ['agent', 'Реестр провайдера', agent],
                ] as const).map(([side, label, fileState]) => (
                  <label key={side} className="bg-white border border-slate-200 rounded-xl p-5 shadow-xs cursor-pointer hover:border-indigo-300 transition-colors">
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center"><Upload className="w-4 h-4" /></div>
                      <div>
                        <div className="text-sm font-semibold text-slate-900">{label}</div>
                        <div className="text-xs text-slate-500 mt-0.5">{fileState ? `${fileState.name} · ${fileState.rows.toLocaleString('ru-RU')} строк` : 'Excel / CSV'}</div>
                      </div>
                    </div>
                    <input type="file" accept=".xlsx,.xls,.csv,.txt" className="hidden" onChange={e => { const file = e.target.files?.[0]; if (file) void handleFile(file, side); }} />
                  </label>
                ))}
              </div>

              <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-xs space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-3">
                  <ColumnSelect label="Transaction ID — биллинг" value={billingIdCol} onChange={setBillingIdCol} columns={billing?.columns || []} required />
                  <ColumnSelect label="Сумма — биллинг" value={billingAmountCol} onChange={setBillingAmountCol} columns={billing?.columns || []} required />
                  <ColumnSelect label="Статус — биллинг" value={billingStatusCol} onChange={setBillingStatusCol} columns={billing?.columns || []} />
                  <div>
                    <label className="block text-[11px] font-semibold text-slate-600 mb-1">Провайдер</label>
                    <input value={providerName} onChange={e => setProviderName(e.target.value)} className="w-full border border-slate-200 rounded-lg px-3 py-2 text-xs" placeholder="Paynet" />
                  </div>
                  <ColumnSelect label="Transaction ID — провайдер" value={agentIdCol} onChange={setAgentIdCol} columns={agent?.columns || []} required />
                  <ColumnSelect label="Сумма — провайдер" value={agentAmountCol} onChange={setAgentAmountCol} columns={agent?.columns || []} required />
                  <ColumnSelect label="Статус — провайдер" value={agentStatusCol} onChange={setAgentStatusCol} columns={agent?.columns || []} />
                  <ColumnSelect label="Комиссия — провайдер" value={agentCommissionCol} onChange={setAgentCommissionCol} columns={agent?.columns || []} />
                </div>

                {runError && <div className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-xs text-rose-700">{runError}</div>}

                <button disabled={running} onClick={() => void run()} className="w-full flex items-center justify-center gap-2 rounded-xl bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-300 text-white py-3 text-sm font-semibold">
                  {running ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4 fill-white" />}
                  {running ? 'Выполняется сверка…' : 'Запустить сверку'}
                </button>
              </div>

              {result && (
                <>
                  <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
                    {[
                      ['Match', `${result.summary.match_percentage.toFixed(2)}%`],
                      ['Совпало', result.summary.matched_count.toLocaleString('ru-RU')],
                      ['Расхождений', result.summary.discrepancy_count.toLocaleString('ru-RU')],
                      ['Δ суммы', `${fmt(result.summary.diff_sum)} ${settings.currency}`],
                    ].map(([label, value]) => (
                      <div key={label} className="bg-white border border-slate-200 rounded-xl p-4 shadow-xs">
                        <div className="text-xs text-slate-500">{label}</div>
                        <div className="text-xl font-bold text-slate-900 mt-1">{value}</div>
                      </div>
                    ))}
                  </div>

                  <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-xs">
                    <div className="flex items-center justify-between gap-4 mb-4">
                      <div>
                        <h3 className="font-semibold text-slate-900">Расхождения</h3>
                        <p className="text-xs text-slate-500 mt-0.5">Суммы и статусы по совпавшим Transaction ID</p>
                      </div>
                      <div className="text-xs text-slate-500">
                        Только биллинг: <b>{paynetMetrics?.only_billing?.length || 0}</b> · Только провайдер: <b>{paynetMetrics?.only_agent?.length || 0}</b>
                      </div>
                    </div>
                    {result.discrepancies.length === 0 ? (
                      <div className="rounded-lg bg-emerald-50 border border-emerald-100 p-4 text-xs text-emerald-700 flex items-center gap-2"><CheckCircle2 className="w-4 h-4" /> Расхождений нет.</div>
                    ) : (
                      <div className="max-h-[420px] overflow-auto border border-slate-200 rounded-xl">
                        <table className="min-w-full text-xs">
                          <thead className="sticky top-0 bg-slate-50 text-slate-600"><tr>{['Transaction ID','Биллинг','Провайдер','Δ','Статус биллинга','Статус провайдера','Причина'].map(h => <th key={h} className="px-3 py-2 text-left font-semibold">{h}</th>)}</tr></thead>
                          <tbody className="divide-y divide-slate-100">
                            {result.discrepancies.slice(0, 500).map((row, idx) => (
                              <tr key={idx}>
                                <td className="px-3 py-2 font-mono font-semibold">{String(row.transaction_id || '—')}</td>
                                <td className="px-3 py-2">{fmt(Number(row.billing_amount || 0))}</td>
                                <td className="px-3 py-2">{fmt(Number(row.agent_amount || 0))}</td>
                                <td className="px-3 py-2 font-semibold">{fmt(Number(row.amount_diff || 0))}</td>
                                <td className="px-3 py-2">{String(row.billing_status || '—')}</td>
                                <td className="px-3 py-2">{String(row.agent_status || '—')}</td>
                                <td className="px-3 py-2 text-amber-700">{String(row.reason || 'Расхождение')}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>

                  <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-xs flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                    <div>
                      <h3 className="font-semibold text-slate-900">Фиксация результата</h3>
                      <p className="text-xs text-slate-500 mt-1">Комиссия провайдера: {fmt(paynetMetrics?.total_commission || 0)} {settings.currency}</p>
                      {saveMessage && <p className="text-xs text-indigo-600 mt-1">{saveMessage}</p>}
                    </div>
                    <button onClick={() => void saveResult()} className="inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-indigo-600 text-white text-sm font-semibold"><Save className="w-4 h-4" /> Записать в Архив БД</button>
                  </div>
                </>
              )}
            </>
          )}

          {section === 'analytics' && (
            <>
              <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-xs">
                <h2 className="text-lg font-bold text-slate-900">Аналитика Paynet / Payme</h2>
                <p className="text-sm text-slate-500 mt-1">Метрики строятся только по сохранённым серверным результатам.</p>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
                {[
                  ['Оборот биллинга', `${fmt(totalArchivedBilling)} ${settings.currency}`],
                  ['Оборот провайдера', `${fmt(totalArchivedAgent)} ${settings.currency}`],
                  ['Комиссия провайдера', `${fmt(totalArchivedCommission)} ${settings.currency}`],
                  ['Средний Match', archive.length ? `${avgMatch.toFixed(2)}%` : '—'],
                ].map(([label, value]) => <div key={label} className="bg-white border border-slate-200 rounded-xl p-4 shadow-xs"><div className="text-xs text-slate-500">{label}</div><div className="text-xl font-bold text-slate-900 mt-1 break-words">{value}</div></div>)}
              </div>
              <div className="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-xs">
                <div className="px-5 py-4 border-b border-slate-100"><h3 className="font-semibold text-slate-900">По провайдерам</h3></div>
                {providerStats.length === 0 ? <div className="p-10 text-center text-sm text-slate-500">Недостаточно данных.</div> : (
                  <div className="overflow-x-auto"><table className="min-w-full text-xs"><thead className="bg-slate-50 text-slate-500"><tr>{['Провайдер','Запусков','Оборот','Комиссия','Проблемы'].map(h => <th key={h} className="px-4 py-2.5 text-left font-semibold">{h}</th>)}</tr></thead><tbody className="divide-y divide-slate-100">{providerStats.map(p => <tr key={p.provider}><td className="px-4 py-3 font-semibold">{p.provider}</td><td className="px-4 py-3">{p.runs}</td><td className="px-4 py-3">{fmt(p.volume)}</td><td className="px-4 py-3">{fmt(p.commission)}</td><td className="px-4 py-3">{p.issues}</td></tr>)}</tbody></table></div>
                )}
              </div>
            </>
          )}

          {section === 'archive' && (
            <div className="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-xs">
              <div className="px-5 py-4 border-b border-slate-100 flex items-center justify-between">
                <div><h2 className="font-semibold text-slate-900">Архив Paynet / Payme</h2><p className="text-xs text-slate-500 mt-0.5">Сохранённые результаты этого модуля</p></div>
                <button onClick={() => void loadArchive()} className="p-2 rounded-lg text-slate-500 hover:bg-slate-50"><RefreshCw className={`w-4 h-4 ${archiveLoading ? 'animate-spin' : ''}`} /></button>
              </div>
              {archive.length === 0 ? <div className="p-10 text-center text-sm text-slate-500">Архив пуст.</div> : (
                <div className="overflow-x-auto"><table className="min-w-full text-xs"><thead className="bg-slate-50 text-slate-500"><tr>{['Дата','Провайдер','Биллинг','Провайдер','Δ','Match','Комиссия',''].map(h => <th key={h || 'actions'} className="px-4 py-2.5 text-left font-semibold">{h}</th>)}</tr></thead><tbody className="divide-y divide-slate-100">{archive.map(item => <tr key={item.id}><td className="px-4 py-3 whitespace-nowrap">{new Date(item.timestamp).toLocaleString('ru-RU')}</td><td className="px-4 py-3 font-semibold">{item.extra?.provider_name || item.bank_name}</td><td className="px-4 py-3">{fmt(item.total_our)}</td><td className="px-4 py-3">{fmt(item.total_bank)}</td><td className="px-4 py-3">{fmt(item.difference)}</td><td className="px-4 py-3">{Number(item.extra?.match_percentage || 0).toFixed(2)}%</td><td className="px-4 py-3">{fmt(item.total_commission || 0)}</td><td className="px-4 py-3 text-right">{canRun && <button onClick={() => void deleteArchive(item.id)} className="p-1.5 text-slate-400 hover:text-rose-600"><Trash2 className="w-4 h-4" /></button>}</td></tr>)}</tbody></table></div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

const ColumnSelect: React.FC<{
  label: string;
  value: string;
  onChange: (value: string) => void;
  columns: string[];
  required?: boolean;
}> = ({ label, value, onChange, columns, required }) => (
  <div>
    <label className="block text-[11px] font-semibold text-slate-600 mb-1">{label}{required ? ' *' : ''}</label>
    <div className="relative">
      <FileSpreadsheet className="absolute left-2.5 top-2.5 w-3.5 h-3.5 text-slate-400" />
      <select value={value} onChange={e => onChange(e.target.value)} className="w-full border border-slate-200 rounded-lg pl-8 pr-3 py-2 text-xs bg-white">
        <option value="">— не выбрано —</option>
        {columns.map(column => <option key={column} value={column}>{column}</option>)}
      </select>
    </div>
  </div>
);
