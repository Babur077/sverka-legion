import React, { useEffect, useMemo, useState } from 'react';
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  BarChart3,
  CheckCircle2,
  Clock3,
  FileSearch,
  Layers3,
  LoaderCircle,
  RefreshCcw,
} from 'lucide-react';
import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import {
  DashboardData,
  DashboardJob,
  DashboardRecentRun,
  getDashboardData,
} from '../utils/dashboardApi';

interface Props {
  onOpenModule: (moduleId: string) => void;
}

function formatMonth(value: string): string {
  const [year, month] = value.split('-').map(Number);
  if (!year || !month) return value;
  return new Date(year, month - 1, 1).toLocaleDateString('ru-RU', {
    month: 'short',
    year: '2-digit',
  });
}

function formatDateTime(value?: string | null): string {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function runTitle(run: DashboardRecentRun): string {
  if (run.definition_name) {
    return run.definition_name
      + (run.definition_version_number ? ` · v${run.definition_version_number}` : '');
  }
  if (run.bank_name) return String(run.bank_name);
  return run.module_name;
}

function statusClass(status: string): string {
  const normalized = status.toUpperCase();
  if (normalized === 'COMPLETED') return 'bg-emerald-50 text-emerald-700 border-emerald-200';
  if (normalized === 'FAILED') return 'bg-rose-50 text-rose-700 border-rose-200';
  if (normalized === 'CANCELLED') return 'bg-slate-100 text-slate-500 border-slate-200';
  if (normalized === 'RUNNING') return 'bg-indigo-50 text-indigo-700 border-indigo-200';
  if (normalized === 'QUEUED') return 'bg-amber-50 text-amber-700 border-amber-200';
  return 'bg-amber-50 text-amber-700 border-amber-200';
}

function jobStatusLabel(job: DashboardJob): string {
  if (job.status === 'RUNNING') return job.stage || 'Выполняется';
  if (job.status === 'QUEUED') return 'В очереди';
  if (job.status === 'COMPLETED') return 'Готово';
  if (job.status === 'FAILED') return 'Ошибка';
  if (job.status === 'CANCELLED') return 'Отменено';
  return job.status;
}

export const DashboardPage: React.FC<Props> = ({ onOpenModule }) => {
  const [months, setMonths] = useState(6);
  const [moduleId, setModuleId] = useState('');
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = async () => {
    setLoading(true);
    setError('');
    try {
      setData(await getDashboardData(months, moduleId || undefined));
    } catch (err: any) {
      setError(err?.message || 'Не удалось загрузить Dashboard.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, [months, moduleId]);

  const activeJobs = useMemo(
    () => (data?.jobs || []).filter(job => job.status === 'RUNNING' || job.status === 'QUEUED'),
    [data?.jobs],
  );

  const failedJobs = useMemo(
    () => (data?.jobs || []).filter(job => job.status === 'FAILED').slice(0, 3),
    [data?.jobs],
  );

  const chartData = useMemo(
    () => (data?.trend || []).map(item => ({
      ...item,
      label: formatMonth(item.month),
    })),
    [data?.trend],
  );

  if (loading && !data) {
    return (
      <div className="flex min-h-full items-center justify-center bg-slate-50">
        <div className="flex items-center gap-2 text-sm text-slate-500">
          <LoaderCircle className="h-4 w-4 animate-spin" />
          Загружаем Dashboard…
        </div>
      </div>
    );
  }

  const summary = data?.summary || {
    runs: 0,
    completed_runs: 0,
    failed_runs: 0,
    problem_runs: 0,
    average_match_percentage: 0,
    discrepancies: 0,
    running_jobs: 0,
    queued_jobs: 0,
    failed_jobs: 0,
  };

  return (
    <div className="min-h-full bg-slate-50">
      <div className="border-b border-slate-200 bg-white px-5 py-4">
        <div className="mx-auto flex max-w-[1800px] flex-col justify-between gap-4 lg:flex-row lg:items-center">
          <div>
            <h1 className="text-xl font-bold text-slate-900">Dashboard</h1>
            <p className="mt-1 text-xs text-slate-500">
              Общая картина по сверкам, качеству результатов и фоновым задачам.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <select
              value={months}
              onChange={event => setMonths(Number(event.target.value))}
              className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-700"
            >
              <option value={3}>3 месяца</option>
              <option value={6}>6 месяцев</option>
              <option value={12}>12 месяцев</option>
            </select>

            <select
              value={moduleId}
              onChange={event => setModuleId(event.target.value)}
              className="min-w-[190px] rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-700"
            >
              <option value="">Все модули</option>
              {(data?.filters.available_modules || []).map(module => (
                <option key={module.id} value={module.id}>{module.name}</option>
              ))}
            </select>

            <button
              onClick={() => void load()}
              disabled={loading}
              className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-50 disabled:opacity-50"
            >
              <RefreshCcw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
              Обновить
            </button>
          </div>
        </div>
      </div>

      <div className="mx-auto max-w-[1800px] space-y-5 p-5 xl:p-7">
        {error && (
          <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
            {error}
          </div>
        )}

        <section className="grid grid-cols-2 gap-3 xl:grid-cols-6">
          {[
            {
              label: 'Сверок',
              value: summary.runs.toLocaleString('ru-RU'),
              helper: `${summary.completed_runs} завершено`,
              icon: Layers3,
              className: 'bg-indigo-50 text-indigo-700',
            },
            {
              label: 'Средняя сходимость',
              value: `${summary.average_match_percentage.toFixed(1)}%`,
              helper: 'по Run за период',
              icon: CheckCircle2,
              className: 'bg-emerald-50 text-emerald-700',
            },
            {
              label: 'Run с расхождениями',
              value: summary.problem_runs.toLocaleString('ru-RU'),
              helper: `${summary.discrepancies.toLocaleString('ru-RU')} строк проблем`,
              icon: AlertTriangle,
              className: 'bg-amber-50 text-amber-700',
            },
            {
              label: 'Выполняется',
              value: summary.running_jobs.toLocaleString('ru-RU'),
              helper: `${summary.queued_jobs} в очереди`,
              icon: Activity,
              className: 'bg-violet-50 text-violet-700',
            },
            {
              label: 'Ошибок Run',
              value: summary.failed_runs.toLocaleString('ru-RU'),
              helper: 'за выбранный период',
              icon: FileSearch,
              className: 'bg-rose-50 text-rose-700',
            },
            {
              label: 'Ошибок Jobs',
              value: summary.failed_jobs.toLocaleString('ru-RU'),
              helper: 'в последних задачах',
              icon: Clock3,
              className: 'bg-slate-100 text-slate-700',
            },
          ].map(card => {
            const Icon = card.icon;
            return (
              <div key={card.label} className="rounded-xl border border-slate-200 bg-white p-4 shadow-xs">
                <div className={`flex h-8 w-8 items-center justify-center rounded-lg ${card.className}`}>
                  <Icon className="h-4 w-4" />
                </div>
                <div className="mt-3 text-2xl font-black tracking-tight text-slate-900">{card.value}</div>
                <div className="mt-1 text-[11px] font-semibold text-slate-600">{card.label}</div>
                <div className="mt-0.5 text-[10px] text-slate-400">{card.helper}</div>
              </div>
            );
          })}
        </section>

        <section className="grid grid-cols-1 gap-5 2xl:grid-cols-[1.5fr_1fr]">
          <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-xs">
            <div className="mb-4 flex items-start justify-between gap-3">
              <div>
                <div className="flex items-center gap-2">
                  <BarChart3 className="h-4 w-4 text-indigo-600" />
                  <h2 className="font-bold text-slate-900">Динамика сверок</h2>
                </div>
                <p className="mt-1 text-[11px] text-slate-500">
                  Столбцы — количество Run, линия — средняя доля совпадений за месяц.
                </p>
              </div>
            </div>

            <div className="h-[310px]">
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={chartData} margin={{ top: 10, right: 12, bottom: 0, left: -12 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="label" tick={{ fontSize: 11 }} />
                  <YAxis yAxisId="runs" allowDecimals={false} tick={{ fontSize: 10 }} />
                  <YAxis
                    yAxisId="match"
                    orientation="right"
                    domain={[0, 100]}
                    tickFormatter={value => `${value}%`}
                    tick={{ fontSize: 10 }}
                  />
                  <Tooltip
                    formatter={(value: any, name: any) => (
                      name === 'Сходимость'
                        ? [`${Number(value).toFixed(1)}%`, name]
                        : [Number(value).toLocaleString('ru-RU'), name]
                    )}
                  />
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                  <Bar yAxisId="runs" dataKey="runs" name="Run" fill="#4f46e5" radius={[4, 4, 0, 0]} />
                  <Line
                    yAxisId="match"
                    type="monotone"
                    dataKey="average_match_percentage"
                    name="Сходимость"
                    stroke="#059669"
                    strokeWidth={2}
                    dot={{ r: 3 }}
                    connectNulls
                  />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-xs">
            <div>
              <h2 className="font-bold text-slate-900">По модулям</h2>
              <p className="mt-1 text-[11px] text-slate-500">Сводка по доступным вам типам сверок.</p>
            </div>

            <div className="mt-4 overflow-x-auto">
              <table className="min-w-full text-xs">
                <thead>
                  <tr className="border-b border-slate-100 text-[10px] uppercase tracking-wider text-slate-400">
                    <th className="px-2 py-2 text-left">Модуль</th>
                    <th className="px-2 py-2 text-right">Run</th>
                    <th className="px-2 py-2 text-right">Match</th>
                    <th className="px-2 py-2 text-right">Пробл.</th>
                    <th className="w-8" />
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {(data?.modules || []).map(module => (
                    <tr key={module.module_id} className="hover:bg-slate-50">
                      <td className="max-w-[260px] px-2 py-3 font-semibold text-slate-800">
                        <div className="truncate" title={module.module_name}>{module.module_name}</div>
                      </td>
                      <td className="px-2 py-3 text-right tabular-nums">{module.runs}</td>
                      <td className="px-2 py-3 text-right font-semibold tabular-nums">
                        {module.runs ? `${module.average_match_percentage.toFixed(1)}%` : '—'}
                      </td>
                      <td className="px-2 py-3 text-right tabular-nums">{module.problem_runs}</td>
                      <td className="px-1 py-3">
                        <button
                          onClick={() => onOpenModule(module.module_id)}
                          className="rounded p-1 text-slate-400 hover:bg-indigo-50 hover:text-indigo-600"
                          title="Открыть модуль"
                        >
                          <ArrowRight className="h-3.5 w-3.5" />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>

              {(data?.modules || []).length === 0 && (
                <div className="py-8 text-center text-xs text-slate-500">
                  Нет доступных модулей или данных за выбранный период.
                </div>
              )}
            </div>
          </div>
        </section>

        <section className="grid grid-cols-1 gap-5 2xl:grid-cols-[1.4fr_1fr]">
          <div className="rounded-xl border border-slate-200 bg-white shadow-xs">
            <div className="border-b border-slate-100 px-5 py-4">
              <h2 className="font-bold text-slate-900">Последние Run</h2>
              <p className="mt-1 text-[11px] text-slate-500">
                Последние сохранённые результаты из общего журнала ReconciliationRun.
              </p>
            </div>

            <div className="overflow-x-auto">
              <table className="min-w-full text-xs">
                <thead className="bg-slate-50">
                  <tr className="text-[10px] uppercase tracking-wider text-slate-400">
                    <th className="px-4 py-3 text-left">Сверка</th>
                    <th className="px-4 py-3 text-left">Пользователь</th>
                    <th className="px-4 py-3 text-left">Время</th>
                    <th className="px-4 py-3 text-right">Match</th>
                    <th className="px-4 py-3 text-right">Расх.</th>
                    <th className="px-4 py-3 text-left">Статус</th>
                    <th className="w-10" />
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {(data?.recent_runs || []).map(run => (
                    <tr key={run.id} className="hover:bg-slate-50">
                      <td className="max-w-[300px] px-4 py-3">
                        <div className="truncate font-semibold text-slate-800" title={runTitle(run)}>
                          {runTitle(run)}
                        </div>
                        <div className="mt-0.5 truncate font-mono text-[9px] text-slate-400">
                          {run.module_name} · {run.run_id || '—'}
                        </div>
                      </td>
                      <td className="px-4 py-3 text-slate-600">{run.created_by || '—'}</td>
                      <td className="px-4 py-3 whitespace-nowrap text-slate-500">
                        {formatDateTime(run.updated_at || run.created_at)}
                      </td>
                      <td className="px-4 py-3 text-right font-bold tabular-nums text-slate-800">
                        {run.match_percentage.toFixed(1)}%
                      </td>
                      <td className="px-4 py-3 text-right tabular-nums text-slate-700">
                        {run.discrepancy_count}
                      </td>
                      <td className="px-4 py-3">
                        <span className={`rounded-full border px-2 py-1 text-[9px] font-semibold ${statusClass(run.status)}`}>
                          {run.status}
                        </span>
                      </td>
                      <td className="px-2 py-3">
                        <button
                          onClick={() => onOpenModule(run.module_id)}
                          className="rounded p-1.5 text-slate-400 hover:bg-indigo-50 hover:text-indigo-600"
                          title="Открыть"
                        >
                          <ArrowRight className="h-3.5 w-3.5" />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>

              {(data?.recent_runs || []).length === 0 && (
                <div className="py-10 text-center text-sm text-slate-500">
                  За выбранный период Run пока нет.
                </div>
              )}
            </div>
          </div>

          <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-xs">
            <div className="flex items-start justify-between gap-3">
              <div>
                <h2 className="font-bold text-slate-900">Фоновые задачи</h2>
                <p className="mt-1 text-[11px] text-slate-500">
                  Текущая очередь и последние ошибки worker.
                </p>
              </div>
              {(activeJobs.length > 0) && (
                <span className="rounded-full bg-indigo-50 px-2 py-1 text-[10px] font-bold text-indigo-700">
                  {activeJobs.length} активн.
                </span>
              )}
            </div>

            <div className="mt-4 space-y-2">
              {activeJobs.slice(0, 5).map(job => (
                <div key={job.id} className="rounded-xl border border-slate-200 bg-slate-50/70 p-3">
                  <div className="flex items-center justify-between gap-3">
                    <div className="min-w-0">
                      <div className="truncate text-xs font-semibold text-slate-800">
                        #{job.id} · {jobStatusLabel(job)}
                      </div>
                      <div className="mt-1 text-[10px] text-slate-400">
                        {job.created_by} · {formatDateTime(job.created_at)}
                      </div>
                    </div>
                    <span className={`rounded-full border px-2 py-1 text-[9px] font-bold ${statusClass(job.status)}`}>
                      {job.status === 'RUNNING' || job.status === 'QUEUED'
                        ? `${job.progress}%`
                        : job.status}
                    </span>
                  </div>
                  <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-white">
                    <div
                      className="h-full rounded-full bg-indigo-600 transition-[width]"
                      style={{ width: `${Math.max(3, Math.min(100, job.progress || 0))}%` }}
                    />
                  </div>
                </div>
              ))}

              {activeJobs.length === 0 && (
                <div className="rounded-xl bg-slate-50 p-4 text-xs text-slate-500">
                  Сейчас фоновые задачи не выполняются.
                </div>
              )}

              {failedJobs.length > 0 && (
                <div className="pt-2">
                  <div className="mb-2 text-[10px] font-bold uppercase tracking-wider text-slate-400">
                    Последние ошибки
                  </div>
                  <div className="space-y-2">
                    {failedJobs.map(job => (
                      <div key={job.id} className="rounded-lg border border-rose-100 bg-rose-50/60 p-3">
                        <div className="flex items-center justify-between gap-2 text-[10px]">
                          <span className="font-semibold text-rose-700">#{job.id} · {job.module_id}</span>
                          <span className="text-rose-400">{formatDateTime(job.updated_at)}</span>
                        </div>
                        <div className="mt-1 line-clamp-2 text-[10px] text-rose-600" title={job.error || ''}>
                          {job.error || 'Ошибка без описания'}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        </section>
      </div>
    </div>
  );
};
