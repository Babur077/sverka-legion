import React, { useEffect, useMemo, useState } from 'react';
import {
  ArrowLeft,
  CheckCircle2,
  Copy,
  FileSpreadsheet,
  Clock3,
  History,
  LoaderCircle,
  Plus,
  Play,
  Save,
  Settings2,
  Trash2,
  Wrench,
  XCircle,
} from 'lucide-react';
import { User } from '../types';
import { parseFile } from '../utils/fileParser';
import { getModuleArchive, saveModuleArchive } from '../utils/archiveApi';
import { hasPermission } from '../utils/permissions';
import {
  BuilderKeyPair,
  BuilderResultRow,
  BuilderRunResult,
  ReconciliationBuilderConfig,
  ReconciliationDefinition,
  createReconciliationDefinition,
  deleteReconciliationDefinition,
  getReconciliationDefinitions,
  runReconciliationBuilder,
  updateReconciliationDefinition,
} from '../utils/reconciliationBuilderApi';

interface Props {
  user: User;
  onBack: () => void;
}

type ResultTab = 'matched' | 'mismatches' | 'only_a' | 'only_b';

const emptyConfig = (): ReconciliationBuilderConfig => ({
  key_pairs: [{ left: '', right: '', mode: 'text' }],
  amount_a_col: '',
  amount_b_col: '',
  amount_tolerance: 0,
  date_a_col: '',
  date_b_col: '',
  date_tolerance_days: 0,
  ignore_empty_keys: true,
  dayfirst: true,
});

const money = (value: number) =>
  value.toLocaleString('ru-RU', { maximumFractionDigits: 2 });

function currentMonth(): string {
  return new Date().toISOString().slice(0, 7);
}

function formatMonth(value?: string): string {
  if (!value) return '—';
  const [year, month] = value.split('-').map(Number);
  if (!year || !month) return value;
  return new Date(year, month - 1, 1).toLocaleDateString('ru-RU', {
    month: 'long',
    year: 'numeric',
  });
}

function formatDateTime(value?: string): string {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    year: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function runSourceNames(item: Record<string, any>): string {
  const sourceFiles = Array.isArray(item.source_files) ? item.source_files : [];
  const names = sourceFiles.length
    ? sourceFiles
    : [item.source_a_name, item.source_b_name].filter(Boolean);
  return names.length ? names.join(' ↔ ') : 'Источники не указаны';
}

export const ReconciliationBuilderWorkspace: React.FC<Props> = ({ user, onBack }) => {
  const [sourceA, setSourceA] = useState<File | null>(null);
  const [sourceB, setSourceB] = useState<File | null>(null);
  const [columnsA, setColumnsA] = useState<string[]>([]);
  const [columnsB, setColumnsB] = useState<string[]>([]);
  const [rowsA, setRowsA] = useState(0);
  const [rowsB, setRowsB] = useState(0);
  const [config, setConfig] = useState<ReconciliationBuilderConfig>(emptyConfig);
  const [definitions, setDefinitions] = useState<ReconciliationDefinition[]>([]);
  const [selectedDefinitionId, setSelectedDefinitionId] = useState<number | null>(null);
  const [templateName, setTemplateName] = useState('');
  const [templateDescription, setTemplateDescription] = useState('');
  const [periodMonth, setPeriodMonth] = useState(currentMonth());
  const [result, setResult] = useState<BuilderRunResult | null>(null);
  const [resultTab, setResultTab] = useState<ResultTab>('matched');
  const [archive, setArchive] = useState<Array<Record<string, any>>>([]);
  const [loadingFile, setLoadingFile] = useState<'a' | 'b' | null>(null);
  const [running, setRunning] = useState(false);
  const [savingTemplate, setSavingTemplate] = useState(false);
  const [showAllRuns, setShowAllRuns] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error' | 'info'; text: string } | null>(null);

  const canRun = hasPermission(user, 'reconciliation_builder.run');
  const canManage = hasPermission(user, 'reconciliation_builder.manage');

  const loadDefinitions = async () => {
    try {
      setDefinitions(await getReconciliationDefinitions());
    } catch (error: any) {
      setMessage({ type: 'error', text: error?.message || 'Не удалось загрузить шаблоны.' });
    }
  };

  const loadArchive = async () => {
    try {
      setArchive(await getModuleArchive<Record<string, any>>(user.username, 'reconciliation_builder'));
    } catch {
      setArchive([]);
    }
  };

  useEffect(() => {
    void loadDefinitions();
    void loadArchive();
  }, [user.username]);

  const handleFile = async (side: 'a' | 'b', file: File | null) => {
    if (!file) return;
    setMessage(null);
    setLoadingFile(side);
    try {
      const parsed = await parseFile(file);
      if (side === 'a') {
        setSourceA(file);
        setColumnsA(parsed.columns);
        setRowsA(parsed.rows.length);
      } else {
        setSourceB(file);
        setColumnsB(parsed.columns);
        setRowsB(parsed.rows.length);
      }
      setResult(null);
    } catch (error: any) {
      setMessage({
        type: 'error',
        text: error?.message || 'Не удалось прочитать файл.',
      });
    } finally {
      setLoadingFile(null);
    }
  };

  const updatePair = (index: number, patch: Partial<BuilderKeyPair>) => {
    setConfig(current => ({
      ...current,
      key_pairs: current.key_pairs.map((pair, pairIndex) =>
        pairIndex === index ? { ...pair, ...patch } : pair,
      ),
    }));
  };

  const addPair = () => {
    setConfig(current => ({
      ...current,
      key_pairs: [...current.key_pairs, { left: '', right: '', mode: 'text' }],
    }));
  };

  const removePair = (index: number) => {
    setConfig(current => ({
      ...current,
      key_pairs: current.key_pairs.length === 1
        ? current.key_pairs
        : current.key_pairs.filter((_, pairIndex) => pairIndex !== index),
    }));
  };

  const loadDefinition = (definition: ReconciliationDefinition) => {
    setSelectedDefinitionId(definition.id);
    setTemplateName(definition.name);
    setTemplateDescription(definition.description || '');
    setConfig({
      ...emptyConfig(),
      ...definition.config,
      key_pairs: definition.config.key_pairs?.length
        ? definition.config.key_pairs
        : emptyConfig().key_pairs,
    });
    setResult(null);
    setMessage({
      type: 'info',
      text: `Шаблон «${definition.name}» загружен. Подставьте файлы и проверьте выбранные колонки.`,
    });
  };

  const resetDefinition = () => {
    setSelectedDefinitionId(null);
    setTemplateName('');
    setTemplateDescription('');
    setConfig(emptyConfig());
    setResult(null);
  };

  const detachTemplateForOneOffRun = () => {
    const previousName = templateName.trim();
    setSelectedDefinitionId(null);
    setTemplateName('');
    setTemplateDescription('');
    setResult(null);
    setMessage({
      type: 'info',
      text: previousName
        ? `Правила шаблона «${previousName}» оставлены в форме, но следующий запуск будет разовым и не изменит шаблон.`
        : 'Разовый режим включён. Шаблон сохранять не нужно — настройте правила и запускайте сверку.',
    });
  };

  const validateConfig = (): string | null => {
    if (!sourceA || !sourceB) return 'Загрузите оба источника.';
    if (!config.key_pairs.length) return 'Добавьте хотя бы один ключ.';
    const invalidPair = config.key_pairs.some(pair => !pair.left || !pair.right);
    if (invalidPair) return 'Для каждого ключа выберите колонку в источнике A и B.';
    if (!!config.amount_a_col !== !!config.amount_b_col) {
      return 'Для проверки суммы нужно выбрать колонки с обеих сторон.';
    }
    if (!!config.date_a_col !== !!config.date_b_col) {
      return 'Для проверки даты нужно выбрать колонки с обеих сторон.';
    }
    return null;
  };

  const handleSaveTemplate = async () => {
    if (!canManage) return;
    if (!templateName.trim()) {
      setMessage({ type: 'error', text: 'Введите название шаблона.' });
      return;
    }
    const invalid = config.key_pairs.some(pair => !pair.left || !pair.right);
    if (invalid) {
      setMessage({ type: 'error', text: 'Заполните все пары ключевых колонок.' });
      return;
    }

    setSavingTemplate(true);
    setMessage(null);
    try {
      if (selectedDefinitionId) {
        const saved = await updateReconciliationDefinition(
          selectedDefinitionId,
          templateName.trim(),
          templateDescription.trim(),
          config,
        );
        setMessage({ type: 'success', text: saved.message });
      } else {
        const saved = await createReconciliationDefinition(
          templateName.trim(),
          templateDescription.trim(),
          config,
        );
        setSelectedDefinitionId(saved.id);
        setMessage({ type: 'success', text: saved.message });
      }
      await loadDefinitions();
    } catch (error: any) {
      setMessage({ type: 'error', text: error?.message || 'Не удалось сохранить шаблон.' });
    } finally {
      setSavingTemplate(false);
    }
  };

  const handleDeleteTemplate = async (definition: ReconciliationDefinition) => {
    if (!canManage) return;
    if (!window.confirm(`Удалить шаблон «${definition.name}»?`)) return;
    try {
      await deleteReconciliationDefinition(definition.id);
      if (selectedDefinitionId === definition.id) resetDefinition();
      await loadDefinitions();
      setMessage({ type: 'success', text: 'Шаблон удалён.' });
    } catch (error: any) {
      setMessage({ type: 'error', text: error?.message || 'Не удалось удалить шаблон.' });
    }
  };

  const handleRun = async () => {
    if (!canRun) return;
    const validationError = validateConfig();
    if (validationError) {
      setMessage({ type: 'error', text: validationError });
      return;
    }

    setRunning(true);
    setMessage(null);
    setResult(null);
    try {
      const runResult = await runReconciliationBuilder(
        sourceA!,
        sourceB!,
        config,
        selectedDefinitionId
          ? {
              id: selectedDefinitionId,
              name: templateName.trim() || undefined,
            }
          : undefined,
      );
      setResult(runResult);
      setResultTab('matched');

      await saveModuleArchive(user.username, 'reconciliation_builder', {
        run_id: runResult.run_id,
        status: runResult.status,
        period_month: periodMonth,
        definition_id: selectedDefinitionId,
        definition_name: selectedDefinitionId
          ? (templateName.trim() || `Шаблон #${selectedDefinitionId}`)
          : 'Разовая сверка',
        source_a_name: sourceA!.name,
        source_b_name: sourceB!.name,
        source_files: [sourceA!.name, sourceB!.name],
        summary: runResult.summary,
        config,
      });

      await loadArchive();
      setMessage({
        type: 'success',
        text: `Сверка выполнена и сохранена в журнал. Run ID: ${runResult.run_id}`,
      });
    } catch (error: any) {
      setMessage({
        type: 'error',
        text: error?.message || 'Не удалось выполнить универсальную сверку.',
      });
    } finally {
      setRunning(false);
    }
  };

  const metrics = result?.custom_metrics?.generic;
  const resultRows = useMemo<BuilderResultRow[]>(() => {
    if (!metrics) return [];
    if (resultTab === 'matched') return metrics.matched || [];
    if (resultTab === 'mismatches') return metrics.mismatches || [];
    if (resultTab === 'only_a') return metrics.only_a || [];
    return metrics.only_b || [];
  }, [metrics, resultTab]);

  const resultTabs: Array<{ id: ResultTab; label: string; count: number }> = [
    { id: 'matched', label: 'Совпало', count: metrics?.matched?.length || 0 },
    { id: 'mismatches', label: 'Расхождения', count: metrics?.mismatches?.length || 0 },
    { id: 'only_a', label: 'Только A', count: metrics?.only_a?.length || 0 },
    { id: 'only_b', label: 'Только B', count: metrics?.only_b?.length || 0 },
  ];

  return (
    <div className="min-h-full bg-slate-50">
      <div className="border-b border-slate-200 bg-white px-5 py-4">
        <div className="mx-auto flex max-w-[1800px] items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <button
              onClick={onBack}
              className="rounded-lg border border-slate-200 p-2 text-slate-500 hover:bg-slate-50"
              title="Назад к модулям"
            >
              <ArrowLeft className="h-4 w-4" />
            </button>
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-indigo-50 text-indigo-600">
              <Wrench className="h-5 w-5" />
            </div>
            <div>
              <h1 className="text-xl font-bold text-slate-900">Конструктор сверок</h1>
              <p className="text-xs text-slate-500">
                Детерминированные правила: ключи → сумма → дата → результат.
              </p>
            </div>
          </div>

          <button
            onClick={handleRun}
            disabled={!canRun || running}
            className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {running ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4 fill-white" />}
            {running ? 'Сверка…' : 'Запустить сверку'}
          </button>
        </div>
      </div>

      <div className="mx-auto max-w-[1800px] space-y-5 p-5 xl:p-7">
        {message && (
          <div className={`rounded-xl border px-4 py-3 text-sm ${
            message.type === 'error'
              ? 'border-rose-200 bg-rose-50 text-rose-700'
              : message.type === 'success'
                ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
                : 'border-indigo-200 bg-indigo-50 text-indigo-700'
          }`}>
            {message.text}
          </div>
        )}

        <div className="grid grid-cols-1 gap-5 2xl:grid-cols-[1fr_360px]">
          <div className="space-y-5">
            <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-xs">
              <div className="mb-4 flex items-center gap-2">
                <FileSpreadsheet className="h-4 w-4 text-indigo-600" />
                <h2 className="font-semibold text-slate-900">1. Источники данных</h2>
              </div>

              <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
                {[
                  { side: 'a' as const, label: 'Источник A', file: sourceA, rows: rowsA, columns: columnsA },
                  { side: 'b' as const, label: 'Источник B', file: sourceB, rows: rowsB, columns: columnsB },
                ].map(item => (
                  <label
                    key={item.side}
                    className="cursor-pointer rounded-xl border border-dashed border-slate-300 bg-slate-50 p-5 transition hover:border-indigo-300 hover:bg-indigo-50/30"
                  >
                    <div className="text-xs font-bold uppercase tracking-wider text-slate-400">{item.label}</div>
                    <div className="mt-2 font-semibold text-slate-900">
                      {item.file?.name || 'Выберите Excel / CSV'}
                    </div>
                    <div className="mt-1 text-xs text-slate-500">
                      {loadingFile === item.side
                        ? 'Чтение файла…'
                        : item.file
                          ? `${item.rows.toLocaleString('ru-RU')} строк · ${item.columns.length} колонок`
                          : 'После загрузки колонки появятся в конструкторе.'}
                    </div>
                    <input
                      type="file"
                      accept=".xlsx,.xls,.csv"
                      className="hidden"
                      onChange={event => void handleFile(item.side, event.target.files?.[0] || null)}
                    />
                  </label>
                ))}
              </div>
            </section>

            <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-xs">
              <div className="mb-4 flex items-center justify-between gap-3">
                <div className="flex items-center gap-2">
                  <Settings2 className="h-4 w-4 text-indigo-600" />
                  <div>
                    <h2 className="font-semibold text-slate-900">2. Правила сопоставления</h2>
                    <p className="text-xs text-slate-500">Ключи обязательны. Сумма и дата — дополнительные проверки.</p>
                  </div>
                </div>
                <button
                  onClick={addPair}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 px-3 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-50"
                >
                  <Plus className="h-3.5 w-3.5" />
                  Добавить ключ
                </button>
              </div>

              <div className="space-y-3">
                {config.key_pairs.map((pair, index) => (
                  <div key={index} className="grid grid-cols-1 gap-2 rounded-xl border border-slate-200 bg-slate-50 p-3 lg:grid-cols-[1fr_36px_1fr_170px_36px] lg:items-center">
                    <select
                      value={pair.left}
                      onChange={event => updatePair(index, { left: event.target.value })}
                      className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm"
                    >
                      <option value="">Колонка A…</option>
                      {columnsA.map(column => <option key={column} value={column}>{column}</option>)}
                    </select>
                    <div className="text-center text-xs font-bold text-slate-400">↔</div>
                    <select
                      value={pair.right}
                      onChange={event => updatePair(index, { right: event.target.value })}
                      className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm"
                    >
                      <option value="">Колонка B…</option>
                      {columnsB.map(column => <option key={column} value={column}>{column}</option>)}
                    </select>
                    <select
                      value={pair.mode}
                      onChange={event => updatePair(index, { mode: event.target.value as BuilderKeyPair['mode'] })}
                      className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm"
                    >
                      <option value="text">Текст нормализованный</option>
                      <option value="exact">Точное значение</option>
                      <option value="numeric">Числовой ключ</option>
                    </select>
                    <button
                      onClick={() => removePair(index)}
                      disabled={config.key_pairs.length === 1}
                      className="flex h-9 w-9 items-center justify-center rounded-lg text-slate-400 hover:bg-rose-50 hover:text-rose-600 disabled:opacity-30"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                ))}
              </div>

              <div className="mt-5 grid grid-cols-1 gap-4 xl:grid-cols-2">
                <div className="rounded-xl border border-slate-200 p-4">
                  <div className="text-sm font-semibold text-slate-900">Проверка суммы</div>
                  <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2">
                    <select
                      value={config.amount_a_col || ''}
                      onChange={event => setConfig(current => ({ ...current, amount_a_col: event.target.value }))}
                      className="rounded-lg border border-slate-200 px-3 py-2 text-sm"
                    >
                      <option value="">Не использовать A</option>
                      {columnsA.map(column => <option key={column} value={column}>{column}</option>)}
                    </select>
                    <select
                      value={config.amount_b_col || ''}
                      onChange={event => setConfig(current => ({ ...current, amount_b_col: event.target.value }))}
                      className="rounded-lg border border-slate-200 px-3 py-2 text-sm"
                    >
                      <option value="">Не использовать B</option>
                      {columnsB.map(column => <option key={column} value={column}>{column}</option>)}
                    </select>
                  </div>
                  <label className="mt-3 block text-xs text-slate-500">
                    Допуск по сумме
                    <input
                      type="number"
                      min="0"
                      step="0.01"
                      value={config.amount_tolerance}
                      onChange={event => setConfig(current => ({
                        ...current,
                        amount_tolerance: Math.max(0, Number(event.target.value) || 0),
                      }))}
                      className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
                    />
                  </label>
                </div>

                <div className="rounded-xl border border-slate-200 p-4">
                  <div className="text-sm font-semibold text-slate-900">Проверка даты</div>
                  <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2">
                    <select
                      value={config.date_a_col || ''}
                      onChange={event => setConfig(current => ({ ...current, date_a_col: event.target.value }))}
                      className="rounded-lg border border-slate-200 px-3 py-2 text-sm"
                    >
                      <option value="">Не использовать A</option>
                      {columnsA.map(column => <option key={column} value={column}>{column}</option>)}
                    </select>
                    <select
                      value={config.date_b_col || ''}
                      onChange={event => setConfig(current => ({ ...current, date_b_col: event.target.value }))}
                      className="rounded-lg border border-slate-200 px-3 py-2 text-sm"
                    >
                      <option value="">Не использовать B</option>
                      {columnsB.map(column => <option key={column} value={column}>{column}</option>)}
                    </select>
                  </div>
                  <label className="mt-3 block text-xs text-slate-500">
                    Допуск, дней
                    <input
                      type="number"
                      min="0"
                      step="1"
                      value={config.date_tolerance_days}
                      onChange={event => setConfig(current => ({
                        ...current,
                        date_tolerance_days: Math.max(0, Math.floor(Number(event.target.value) || 0)),
                      }))}
                      className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
                    />
                  </label>
                </div>
              </div>

              <div className="mt-4 flex flex-wrap gap-4 rounded-xl bg-slate-50 p-3 text-xs text-slate-600">
                <label className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={config.ignore_empty_keys}
                    onChange={event => setConfig(current => ({ ...current, ignore_empty_keys: event.target.checked }))}
                  />
                  Пустой ключ считать исключением
                </label>
                <label className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={config.dayfirst}
                    onChange={event => setConfig(current => ({ ...current, dayfirst: event.target.checked }))}
                  />
                  Даты в формате день/месяц/год
                </label>
                <label className="flex items-center gap-2">
                  Период журнала:
                  <input
                    type="month"
                    value={periodMonth}
                    onChange={event => setPeriodMonth(event.target.value)}
                    className="rounded border border-slate-200 bg-white px-2 py-1"
                  />
                </label>
              </div>
            </section>

            {result && (
              <section className="rounded-xl border border-slate-200 bg-white shadow-xs">
                <div className="border-b border-slate-100 p-5">
                  <div className="flex flex-col justify-between gap-3 xl:flex-row xl:items-center">
                    <div>
                      <div className="flex items-center gap-2">
                        {result.status === 'COMPLETED'
                          ? <CheckCircle2 className="h-5 w-5 text-emerald-600" />
                          : <XCircle className="h-5 w-5 text-amber-500" />}
                        <h2 className="font-bold text-slate-900">Результат сверки</h2>
                      </div>
                      <p className="mt-1 text-xs text-slate-500">
                        Run {result.run_id} · {result.summary.execution_time_ms.toLocaleString('ru-RU')} мс
                      </p>
                    </div>

                    <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
                      <div className="rounded-lg bg-emerald-50 px-3 py-2">
                        <div className="text-[10px] uppercase text-emerald-600">Совпало</div>
                        <div className="font-bold text-emerald-800">{result.summary.matched_count}</div>
                      </div>
                      <div className="rounded-lg bg-amber-50 px-3 py-2">
                        <div className="text-[10px] uppercase text-amber-600">Проблем</div>
                        <div className="font-bold text-amber-800">{result.summary.discrepancy_count}</div>
                      </div>
                      <div className="rounded-lg bg-indigo-50 px-3 py-2">
                        <div className="text-[10px] uppercase text-indigo-600">Сходимость</div>
                        <div className="font-bold text-indigo-800">{result.summary.match_percentage.toFixed(2)}%</div>
                      </div>
                      <div className="rounded-lg bg-slate-100 px-3 py-2">
                        <div className="text-[10px] uppercase text-slate-500">Δ суммы</div>
                        <div className="font-bold text-slate-800">{money(result.summary.diff_sum)}</div>
                      </div>
                    </div>
                  </div>
                </div>

                <div className="flex gap-1 overflow-x-auto border-b border-slate-100 px-5 py-3">
                  {resultTabs.map(tab => (
                    <button
                      key={tab.id}
                      onClick={() => setResultTab(tab.id)}
                      className={`rounded-lg px-3 py-2 text-xs font-semibold ${
                        resultTab === tab.id
                          ? 'bg-indigo-600 text-white'
                          : 'text-slate-600 hover:bg-slate-100'
                      }`}
                    >
                      {tab.label} · {tab.count}
                    </button>
                  ))}
                </div>

                <div className="overflow-x-auto">
                  <table className="min-w-full text-sm">
                    <thead className="bg-slate-50">
                      <tr>
                        {['Ключ', 'Строка A', 'Строка B', 'Сумма A', 'Сумма B', 'Δ суммы', 'Δ дней', 'Причина'].map(header => (
                          <th key={header} className="px-4 py-3 text-left text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                            {header}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {resultRows.slice(0, 300).map((row, index) => (
                        <tr key={`${row.key}-${row.row_a || 'x'}-${row.row_b || 'x'}-${index}`} className="hover:bg-slate-50">
                          <td className="max-w-[260px] truncate px-4 py-3 font-mono text-xs" title={row.key}>{row.key || '—'}</td>
                          <td className="px-4 py-3">{row.row_a ?? '—'}</td>
                          <td className="px-4 py-3">{row.row_b ?? '—'}</td>
                          <td className="px-4 py-3">{row.amount_a == null ? '—' : money(row.amount_a)}</td>
                          <td className="px-4 py-3">{row.amount_b == null ? '—' : money(row.amount_b)}</td>
                          <td className="px-4 py-3">{row.amount_delta == null ? '—' : money(row.amount_delta)}</td>
                          <td className="px-4 py-3">{row.date_delta_days ?? '—'}</td>
                          <td className="px-4 py-3 text-slate-600">{row.reason || '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {resultRows.length > 300 && (
                    <div className="border-t border-slate-100 px-4 py-3 text-xs text-slate-500">
                      Показаны первые 300 из {resultRows.length.toLocaleString('ru-RU')} строк.
                    </div>
                  )}
                </div>
              </section>
            )}
          </div>

          <aside className="space-y-5">
            <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-xs">
              <div className="mb-3 flex items-center justify-between">
                <div>
                  <h2 className="text-sm font-bold text-slate-900">Шаблон сверки</h2>
                  <p className="text-[11px] text-slate-500">Сохраните правила и используйте их в следующем месяце.</p>
                </div>
                {selectedDefinitionId && (
                  <button
                    onClick={resetDefinition}
                    className="rounded-lg p-2 text-slate-400 hover:bg-slate-100"
                    title="Новый шаблон"
                  >
                    <Plus className="h-4 w-4" />
                  </button>
                )}
              </div>

              <input
                value={templateName}
                onChange={event => setTemplateName(event.target.value)}
                placeholder="Например: 1C ↔ Aloqa"
                className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
              />
              <textarea
                value={templateDescription}
                onChange={event => setTemplateDescription(event.target.value)}
                placeholder="Краткое описание"
                rows={2}
                className="mt-2 w-full resize-none rounded-lg border border-slate-200 px-3 py-2 text-sm"
              />

              {canManage && (
                <button
                  onClick={() => void handleSaveTemplate()}
                  disabled={savingTemplate}
                  className="mt-3 flex w-full items-center justify-center gap-2 rounded-lg bg-slate-900 px-3 py-2.5 text-xs font-semibold text-white hover:bg-slate-800 disabled:opacity-50"
                >
                  {savingTemplate ? <LoaderCircle className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />}
                  {selectedDefinitionId ? 'Обновить шаблон' : 'Сохранить шаблон'}
                </button>
              )}
            </section>

            <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-xs">
              <div className="mb-3 flex items-center gap-2">
                <Copy className="h-4 w-4 text-indigo-600" />
                <h2 className="text-sm font-bold text-slate-900">Сохранённые шаблоны</h2>
              </div>

              <div className="max-h-[360px] space-y-2 overflow-y-auto">
                {definitions.length === 0 ? (
                  <div className="rounded-lg bg-slate-50 p-4 text-xs text-slate-500">
                    Шаблонов пока нет.
                  </div>
                ) : definitions.map(definition => (
                  <div
                    key={definition.id}
                    className={`rounded-lg border p-3 ${
                      selectedDefinitionId === definition.id
                        ? 'border-indigo-300 bg-indigo-50'
                        : 'border-slate-200'
                    }`}
                  >
                    <button
                      onClick={() => loadDefinition(definition)}
                      className="w-full text-left"
                    >
                      <div className="text-sm font-semibold text-slate-900">{definition.name}</div>
                      <div className="mt-1 line-clamp-2 text-[11px] text-slate-500">
                        {definition.description || `${definition.config.key_pairs?.length || 0} ключ(а)`}
                      </div>
                    </button>
                    {canManage && (
                      <div className="mt-2 flex justify-end">
                        <button
                          onClick={() => void handleDeleteTemplate(definition)}
                          className="rounded p-1.5 text-slate-400 hover:bg-rose-50 hover:text-rose-600"
                          title="Удалить шаблон"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </section>

            <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-xs">
              <div className="mb-3 flex items-center gap-2">
                <History className="h-4 w-4 text-indigo-600" />
                <h2 className="text-sm font-bold text-slate-900">Последние запуски</h2>
              </div>
              <div className="space-y-2">
                {archive.slice(0, 8).map(item => (
                  <div key={String(item.id)} className="rounded-lg bg-slate-50 p-3">
                    <div className="flex items-center justify-between gap-2">
                      <span className="truncate text-xs font-semibold text-slate-800">
                        {item.definition_name || 'Без шаблона'}
                      </span>
                      <span className="text-[10px] text-slate-400">{formatMonth(item.period_month)}</span>
                    </div>
                    <div className="mt-1 flex items-center justify-between text-[11px] text-slate-500">
                      <span>{item.run_id || '—'}</span>
                      <span>{Number(item.summary?.match_percentage || 0).toFixed(1)}%</span>
                    </div>
                  </div>
                ))}
                {archive.length === 0 && (
                  <div className="rounded-lg bg-slate-50 p-4 text-xs text-slate-500">
                    Здесь появятся сохранённые запуски конструктора.
                  </div>
                )}
              </div>
            </section>
          </aside>
        </div>
      </div>
    </div>
  );
};
