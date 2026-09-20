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
  BuilderAmountTransform,
  BuilderComputedField,
  BuilderComputedOperation,
  BuilderFilterRule,
  BuilderKeyPair,
  BuilderKeyTransform,
  BuilderMatchingMode,
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
  key_pairs: [{
    left: '',
    right: '',
    mode: 'text',
    left_transform: 'none',
    right_transform: 'none',
  }],
  amount_a_col: '',
  amount_b_col: '',
  amount_tolerance: 0,
  amount_a_transform: 'as_is',
  amount_b_transform: 'as_is',
  matching_mode: 'one_to_one',
  filters: [],
  computed_fields: [],
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

  const effectiveColumnsA = useMemo(
    () => Array.from(new Set([
      ...columnsA,
      ...(config.computed_fields || [])
        .filter(field => field.side === 'a' && field.name.trim())
        .map(field => field.name.trim()),
    ])),
    [columnsA, config.computed_fields],
  );

  const effectiveColumnsB = useMemo(
    () => Array.from(new Set([
      ...columnsB,
      ...(config.computed_fields || [])
        .filter(field => field.side === 'b' && field.name.trim())
        .map(field => field.name.trim()),
    ])),
    [columnsB, config.computed_fields],
  );

  const computedSourceOptions = (side: 'a' | 'b', fieldIndex: number): string[] => {
    const base = side === 'a' ? columnsA : columnsB;
    const previous = (config.computed_fields || [])
      .slice(0, fieldIndex)
      .filter(field => field.side === side && field.name.trim())
      .map(field => field.name.trim());
    return Array.from(new Set([...base, ...previous]));
  };

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
      key_pairs: [
        ...current.key_pairs,
        {
          left: '',
          right: '',
          mode: 'text',
          left_transform: 'none',
          right_transform: 'none',
        },
      ],
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

  const addComputedField = () => {
    setConfig(current => ({
      ...current,
      computed_fields: [
        ...(current.computed_fields || []),
        {
          side: 'a',
          name: '',
          operation: 'normalize_text',
          sources: [''],
          text_mode: 'trim',
        },
      ],
    }));
  };

  const updateComputedField = (index: number, patch: Partial<BuilderComputedField>) => {
    setConfig(current => ({
      ...current,
      computed_fields: (current.computed_fields || []).map((field, fieldIndex) =>
        fieldIndex === index ? { ...field, ...patch } : field,
      ),
    }));
  };

  const updateComputedSource = (fieldIndex: number, sourceIndex: number, value: string) => {
    setConfig(current => ({
      ...current,
      computed_fields: (current.computed_fields || []).map((field, index) => {
        if (index !== fieldIndex) return field;
        const sources = [...(field.sources || [])];
        sources[sourceIndex] = value;
        return { ...field, sources };
      }),
    }));
  };

  const addComputedSource = (fieldIndex: number) => {
    setConfig(current => ({
      ...current,
      computed_fields: (current.computed_fields || []).map((field, index) =>
        index === fieldIndex
          ? { ...field, sources: [...(field.sources || []), ''] }
          : field,
      ),
    }));
  };

  const removeComputedSource = (fieldIndex: number, sourceIndex: number) => {
    setConfig(current => ({
      ...current,
      computed_fields: (current.computed_fields || []).map((field, index) => {
        if (index !== fieldIndex) return field;
        const sources = (field.sources || []).filter((_, sourceIdx) => sourceIdx !== sourceIndex);
        return { ...field, sources: sources.length ? sources : [''] };
      }),
    }));
  };

  const removeComputedField = (index: number) => {
    setConfig(current => ({
      ...current,
      computed_fields: (current.computed_fields || []).filter((_, fieldIndex) => fieldIndex !== index),
    }));
  };

  const addFilter = () => {
    setConfig(current => ({
      ...current,
      filters: [
        ...(current.filters || []),
        { side: 'a', column: '', operator: 'equals', value: '' },
      ],
    }));
  };

  const updateFilter = (index: number, patch: Partial<BuilderFilterRule>) => {
    setConfig(current => ({
      ...current,
      filters: (current.filters || []).map((rule, ruleIndex) =>
        ruleIndex === index ? { ...rule, ...patch } : rule,
      ),
    }));
  };

  const removeFilter = (index: number) => {
    setConfig(current => ({
      ...current,
      filters: (current.filters || []).filter((_, ruleIndex) => ruleIndex !== index),
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
    if ((config.matching_mode || 'one_to_one') !== 'one_to_one' && (!config.amount_a_col || !config.amount_b_col)) {
      return 'Для групповой сверки 1↔N / N↔1 обязательно выберите сумму в обоих источниках.';
    }
    const computedFields = config.computed_fields || [];
    const namesBySide = new Map<string, Set<string>>();
    for (const field of computedFields) {
      const name = field.name.trim();
      if (!name) return 'Укажите название каждого вычисляемого поля.';
      const sideNames = namesBySide.get(field.side) || new Set<string>();
      if (sideNames.has(name)) return `В источнике ${field.side.toUpperCase()} повторяется вычисляемое поле «${name}».`;
      sideNames.add(name);
      namesBySide.set(field.side, sideNames);

      if (!field.sources?.length || field.sources.some(source => !source)) {
        return `Выберите исходные колонки для вычисляемого поля «${name}».`;
      }
      if (field.operation === 'replace' && !(field.find || '').length) {
        return `Для поля «${name}» укажите, что заменить.`;
      }
    }

    const invalidFilter = (config.filters || []).find(rule => {
      if (!rule.column) return true;
      return !['empty', 'not_empty'].includes(rule.operator) && String(rule.value || '').trim() === '';
    });
    if (invalidFilter) {
      return 'Заполните колонку и значение во всех фильтрах.';
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
                V2: ключи, преобразования, фильтры, 1↔1 / 1↔N / N↔1, сумма и дата.
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
              <div className="mb-5 flex flex-col justify-between gap-3 lg:flex-row lg:items-start">
                <div className="flex items-center gap-2">
                  <Settings2 className="h-4 w-4 text-indigo-600" />
                  <div>
                    <h2 className="font-semibold text-slate-900">2. Правила сопоставления</h2>
                    <p className="text-xs text-slate-500">
                      Сначала подготовьте вычисляемые поля, затем ключи, сумму, дату, фильтры и стратегию matching.
                    </p>
                  </div>
                </div>

                <select
                  value={config.matching_mode || 'one_to_one'}
                  onChange={event => setConfig(current => ({
                    ...current,
                    matching_mode: event.target.value as BuilderMatchingMode,
                  }))}
                  className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-semibold text-slate-700"
                >
                  <option value="one_to_one">1 ↔ 1 · построчно</option>
                  <option value="one_to_many">1 ↔ N · одна строка A к группе B</option>
                  <option value="many_to_one">N ↔ 1 · группа A к одной строке B</option>
                </select>
              </div>

              {(config.matching_mode || 'one_to_one') !== 'one_to_one' && (
                <div className="mb-5 rounded-xl border border-indigo-100 bg-indigo-50 px-4 py-3 text-xs leading-5 text-indigo-700">
                  Групповая сверка объединяет оставшиеся строки с одинаковым ключом и сравнивает сумму группы.
                  Поэтому для 1↔N / N↔1 колонки суммы обязательны.
                </div>
              )}

              <div className="mb-5 rounded-xl border border-slate-200 p-4">
                <div className="mb-3 flex items-center justify-between gap-3">
                  <div>
                    <div className="text-sm font-semibold text-slate-900">Вычисляемые поля</div>
                    <div className="text-[11px] text-slate-500">
                      Создавайте временные колонки до сверки. Поля считаются сверху вниз и могут ссылаться на предыдущие.
                    </div>
                  </div>
                  <button
                    onClick={addComputedField}
                    className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 px-3 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-50"
                  >
                    <Plus className="h-3.5 w-3.5" />
                    Добавить поле
                  </button>
                </div>

                {(config.computed_fields || []).length === 0 ? (
                  <div className="rounded-lg bg-slate-50 px-3 py-3 text-xs text-slate-500">
                    Например: <span className="font-mono">Account + Document → MatchKey</span>,
                    удалить символы из RRN или привести дату к единому формату.
                  </div>
                ) : (
                  <div className="space-y-3">
                    {(config.computed_fields || []).map((field, fieldIndex) => {
                      const sourceOptions = computedSourceOptions(field.side, fieldIndex);
                      const isConcat = field.operation === 'concat';
                      const singleSource = field.sources?.[0] || '';

                      return (
                        <div key={fieldIndex} className="rounded-xl bg-slate-50 p-3">
                          <div className="grid grid-cols-1 gap-2 lg:grid-cols-[92px_1fr_190px_36px] lg:items-center">
                            <select
                              value={field.side}
                              onChange={event => updateComputedField(fieldIndex, {
                                side: event.target.value as BuilderComputedField['side'],
                                sources: [''],
                              })}
                              className="rounded-lg border border-slate-200 bg-white px-2.5 py-2 text-xs"
                            >
                              <option value="a">Источник A</option>
                              <option value="b">Источник B</option>
                            </select>

                            <input
                              value={field.name}
                              onChange={event => updateComputedField(fieldIndex, { name: event.target.value })}
                              placeholder="Имя нового поля, например MatchKey"
                              className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs"
                            />

                            <select
                              value={field.operation}
                              onChange={event => {
                                const operation = event.target.value as BuilderComputedOperation;
                                const currentSources = field.sources || [''];
                                updateComputedField(fieldIndex, {
                                  operation,
                                  sources: operation === 'concat'
                                    ? (currentSources.length >= 2 ? currentSources : [currentSources[0] || '', ''])
                                    : [currentSources[0] || ''],
                                });
                              }}
                              className="rounded-lg border border-slate-200 bg-white px-2.5 py-2 text-xs"
                            >
                              <option value="concat">CONCAT · объединить</option>
                              <option value="replace">REPLACE · заменить текст</option>
                              <option value="substring">SUBSTRING · взять часть</option>
                              <option value="normalize_text">TEXT · нормализовать</option>
                              <option value="normalize_date">DATE · нормализовать дату</option>
                            </select>

                            <button
                              onClick={() => removeComputedField(fieldIndex)}
                              className="flex h-9 w-9 items-center justify-center rounded-lg text-slate-400 hover:bg-rose-50 hover:text-rose-600"
                            >
                              <Trash2 className="h-4 w-4" />
                            </button>
                          </div>

                          <div className="mt-2 border-t border-slate-200 pt-2">
                            {isConcat ? (
                              <div className="space-y-2">
                                <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
                                  {(field.sources || []).map((source, sourceIndex) => (
                                    <div key={sourceIndex} className="flex gap-1.5">
                                      <select
                                        value={source}
                                        onChange={event => updateComputedSource(fieldIndex, sourceIndex, event.target.value)}
                                        className="min-w-0 flex-1 rounded-lg border border-slate-200 bg-white px-2.5 py-2 text-xs"
                                      >
                                        <option value="">Колонка {sourceIndex + 1}…</option>
                                        {sourceOptions.map(column => <option key={column} value={column}>{column}</option>)}
                                      </select>
                                      {(field.sources || []).length > 1 && (
                                        <button
                                          onClick={() => removeComputedSource(fieldIndex, sourceIndex)}
                                          className="rounded-lg px-2 text-slate-400 hover:bg-rose-50 hover:text-rose-600"
                                          title="Убрать колонку"
                                        >
                                          ×
                                        </button>
                                      )}
                                    </div>
                                  ))}
                                </div>
                                <div className="flex flex-wrap items-end gap-2">
                                  <button
                                    onClick={() => addComputedSource(fieldIndex)}
                                    className="rounded-lg border border-slate-200 bg-white px-2.5 py-2 text-[11px] font-semibold text-slate-600 hover:bg-slate-100"
                                  >
                                    + колонка
                                  </button>
                                  <label className="text-[11px] text-slate-500">
                                    Разделитель
                                    <input
                                      value={field.separator ?? ''}
                                      onChange={event => updateComputedField(fieldIndex, { separator: event.target.value })}
                                      placeholder="например -"
                                      className="ml-2 w-28 rounded-lg border border-slate-200 bg-white px-2.5 py-2 text-xs"
                                    />
                                  </label>
                                </div>
                              </div>
                            ) : (
                              <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
                                <select
                                  value={singleSource}
                                  onChange={event => updateComputedSource(fieldIndex, 0, event.target.value)}
                                  className="rounded-lg border border-slate-200 bg-white px-2.5 py-2 text-xs"
                                >
                                  <option value="">Исходная колонка…</option>
                                  {sourceOptions.map(column => <option key={column} value={column}>{column}</option>)}
                                </select>

                                {field.operation === 'replace' && (
                                  <div className="grid grid-cols-2 gap-2">
                                    <input
                                      value={field.find || ''}
                                      onChange={event => updateComputedField(fieldIndex, { find: event.target.value })}
                                      placeholder="Что заменить"
                                      className="rounded-lg border border-slate-200 bg-white px-2.5 py-2 text-xs"
                                    />
                                    <input
                                      value={field.replace_with || ''}
                                      onChange={event => updateComputedField(fieldIndex, { replace_with: event.target.value })}
                                      placeholder="На что"
                                      className="rounded-lg border border-slate-200 bg-white px-2.5 py-2 text-xs"
                                    />
                                  </div>
                                )}

                                {field.operation === 'substring' && (
                                  <div className="grid grid-cols-2 gap-2">
                                    <label className="text-[10px] text-slate-500">
                                      Старт
                                      <input
                                        type="number"
                                        value={field.start ?? 0}
                                        onChange={event => updateComputedField(fieldIndex, {
                                          start: Number(event.target.value) || 0,
                                        })}
                                        className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-2.5 py-2 text-xs"
                                      />
                                    </label>
                                    <label className="text-[10px] text-slate-500">
                                      Длина
                                      <input
                                        type="number"
                                        min="0"
                                        value={field.length ?? ''}
                                        onChange={event => updateComputedField(fieldIndex, {
                                          length: event.target.value === '' ? null : Math.max(0, Number(event.target.value) || 0),
                                        })}
                                        placeholder="до конца"
                                        className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-2.5 py-2 text-xs"
                                      />
                                    </label>
                                  </div>
                                )}

                                {field.operation === 'normalize_text' && (
                                  <select
                                    value={field.text_mode || 'trim'}
                                    onChange={event => updateComputedField(fieldIndex, {
                                      text_mode: event.target.value as BuilderComputedField['text_mode'],
                                    })}
                                    className="rounded-lg border border-slate-200 bg-white px-2.5 py-2 text-xs"
                                  >
                                    <option value="trim">TRIM · убрать края</option>
                                    <option value="collapse_spaces">Сжать повторные пробелы</option>
                                    <option value="lower">lowercase</option>
                                    <option value="upper">UPPERCASE</option>
                                    <option value="alnum">Только буквы и цифры</option>
                                  </select>
                                )}

                                {field.operation === 'normalize_date' && (
                                  <select
                                    value={field.date_format || 'iso'}
                                    onChange={event => updateComputedField(fieldIndex, {
                                      date_format: event.target.value as BuilderComputedField['date_format'],
                                    })}
                                    className="rounded-lg border border-slate-200 bg-white px-2.5 py-2 text-xs"
                                  >
                                    <option value="iso">YYYY-MM-DD</option>
                                    <option value="dmy">DD.MM.YYYY</option>
                                    <option value="compact">YYYYMMDD</option>
                                  </select>
                                )}
                              </div>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>

              <div className="mb-3 flex items-center justify-between gap-3">
                <div>
                  <div className="text-sm font-semibold text-slate-900">Ключи сопоставления</div>
                  <div className="text-[11px] text-slate-500">Можно использовать составной ключ из нескольких колонок.</div>
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
                  <div key={index} className="rounded-xl border border-slate-200 bg-slate-50 p-3">
                    <div className="grid grid-cols-1 gap-2 lg:grid-cols-[1fr_36px_1fr_180px_36px] lg:items-center">
                      <select
                        value={pair.left}
                        onChange={event => updatePair(index, { left: event.target.value })}
                        className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm"
                      >
                        <option value="">Колонка A…</option>
                        {effectiveColumnsA.map(column => <option key={column} value={column}>{column}</option>)}
                      </select>
                      <div className="text-center text-xs font-bold text-slate-400">↔</div>
                      <select
                        value={pair.right}
                        onChange={event => updatePair(index, { right: event.target.value })}
                        className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm"
                      >
                        <option value="">Колонка B…</option>
                        {effectiveColumnsB.map(column => <option key={column} value={column}>{column}</option>)}
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

                    <div className="mt-2 grid grid-cols-1 gap-2 border-t border-slate-200 pt-2 sm:grid-cols-2">
                      <label className="text-[11px] text-slate-500">
                        Преобразование ключа A
                        <select
                          value={pair.left_transform || 'none'}
                          onChange={event => updatePair(index, { left_transform: event.target.value as BuilderKeyTransform })}
                          className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-2.5 py-2 text-xs text-slate-700"
                        >
                          <option value="none">Без преобразования</option>
                          <option value="remove_spaces">Убрать все пробелы</option>
                          <option value="digits_only">Оставить только цифры</option>
                          <option value="strip_leading_zeros">Убрать ведущие нули</option>
                          <option value="alnum">Только буквы и цифры</option>
                        </select>
                      </label>

                      <label className="text-[11px] text-slate-500">
                        Преобразование ключа B
                        <select
                          value={pair.right_transform || 'none'}
                          onChange={event => updatePair(index, { right_transform: event.target.value as BuilderKeyTransform })}
                          className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-2.5 py-2 text-xs text-slate-700"
                        >
                          <option value="none">Без преобразования</option>
                          <option value="remove_spaces">Убрать все пробелы</option>
                          <option value="digits_only">Оставить только цифры</option>
                          <option value="strip_leading_zeros">Убрать ведущие нули</option>
                          <option value="alnum">Только буквы и цифры</option>
                        </select>
                      </label>
                    </div>
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
                      {effectiveColumnsA.map(column => <option key={column} value={column}>{column}</option>)}
                    </select>
                    <select
                      value={config.amount_b_col || ''}
                      onChange={event => setConfig(current => ({ ...current, amount_b_col: event.target.value }))}
                      className="rounded-lg border border-slate-200 px-3 py-2 text-sm"
                    >
                      <option value="">Не использовать B</option>
                      {effectiveColumnsB.map(column => <option key={column} value={column}>{column}</option>)}
                    </select>
                  </div>

                  <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
                    {[
                      ['A', 'amount_a_transform'] as const,
                      ['B', 'amount_b_transform'] as const,
                    ].map(([sideLabel, field]) => (
                      <label key={field} className="text-[11px] text-slate-500">
                        Значение {sideLabel}
                        <select
                          value={config[field] || 'as_is'}
                          onChange={event => setConfig(current => ({
                            ...current,
                            [field]: event.target.value as BuilderAmountTransform,
                          }))}
                          className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-2.5 py-2 text-xs"
                        >
                          <option value="as_is">Как в файле</option>
                          <option value="invert">Поменять знак × -1</option>
                          <option value="absolute">По модулю ABS()</option>
                        </select>
                      </label>
                    ))}
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
                      {effectiveColumnsA.map(column => <option key={column} value={column}>{column}</option>)}
                    </select>
                    <select
                      value={config.date_b_col || ''}
                      onChange={event => setConfig(current => ({ ...current, date_b_col: event.target.value }))}
                      className="rounded-lg border border-slate-200 px-3 py-2 text-sm"
                    >
                      <option value="">Не использовать B</option>
                      {effectiveColumnsB.map(column => <option key={column} value={column}>{column}</option>)}
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

              <div className="mt-5 rounded-xl border border-slate-200 p-4">
                <div className="mb-3 flex items-center justify-between gap-3">
                  <div>
                    <div className="text-sm font-semibold text-slate-900">Фильтры строк</div>
                    <div className="text-[11px] text-slate-500">
                      Отфильтруйте служебные статусы, нулевые суммы и другие строки до matching.
                    </div>
                  </div>
                  <button
                    onClick={addFilter}
                    className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 px-3 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-50"
                  >
                    <Plus className="h-3.5 w-3.5" />
                    Добавить фильтр
                  </button>
                </div>

                {(config.filters || []).length === 0 ? (
                  <div className="rounded-lg bg-slate-50 px-3 py-3 text-xs text-slate-500">
                    Фильтров нет — в сверку попадут все строки.
                  </div>
                ) : (
                  <div className="space-y-2">
                    {(config.filters || []).map((rule, index) => {
                      const sourceColumns = rule.side === 'a' ? effectiveColumnsA : effectiveColumnsB;
                      const needsValue = !['empty', 'not_empty'].includes(rule.operator);
                      return (
                        <div key={index} className="grid grid-cols-1 gap-2 rounded-lg bg-slate-50 p-2 lg:grid-cols-[90px_1fr_170px_1fr_36px] lg:items-center">
                          <select
                            value={rule.side}
                            onChange={event => updateFilter(index, {
                              side: event.target.value as BuilderFilterRule['side'],
                              column: '',
                            })}
                            className="rounded-lg border border-slate-200 bg-white px-2.5 py-2 text-xs"
                          >
                            <option value="a">Источник A</option>
                            <option value="b">Источник B</option>
                          </select>
                          <select
                            value={rule.column}
                            onChange={event => updateFilter(index, { column: event.target.value })}
                            className="rounded-lg border border-slate-200 bg-white px-2.5 py-2 text-xs"
                          >
                            <option value="">Колонка…</option>
                            {sourceColumns.map(column => <option key={column} value={column}>{column}</option>)}
                          </select>
                          <select
                            value={rule.operator}
                            onChange={event => updateFilter(index, {
                              operator: event.target.value as BuilderFilterRule['operator'],
                            })}
                            className="rounded-lg border border-slate-200 bg-white px-2.5 py-2 text-xs"
                          >
                            <option value="equals">Равно</option>
                            <option value="not_equals">Не равно</option>
                            <option value="contains">Содержит</option>
                            <option value="not_contains">Не содержит</option>
                            <option value="empty">Пусто</option>
                            <option value="not_empty">Не пусто</option>
                            <option value="gt">&gt;</option>
                            <option value="gte">≥</option>
                            <option value="lt">&lt;</option>
                            <option value="lte">≤</option>
                          </select>
                          <input
                            value={rule.value || ''}
                            onChange={event => updateFilter(index, { value: event.target.value })}
                            disabled={!needsValue}
                            placeholder={needsValue ? 'Значение' : 'Не требуется'}
                            className="rounded-lg border border-slate-200 bg-white px-2.5 py-2 text-xs disabled:bg-slate-100 disabled:text-slate-400"
                          />
                          <button
                            onClick={() => removeFilter(index)}
                            className="flex h-9 w-9 items-center justify-center rounded-lg text-slate-400 hover:bg-rose-50 hover:text-rose-600"
                          >
                            <Trash2 className="h-4 w-4" />
                          </button>
                        </div>
                      );
                    })}
                  </div>
                )}
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

                {metrics?.filter_stats && (
                  <div className="grid grid-cols-2 gap-2 border-b border-slate-100 bg-slate-50/60 px-5 py-3 text-[11px] text-slate-600 md:grid-cols-4">
                    <div>A до фильтров: <span className="font-bold text-slate-900">{metrics.filter_stats.source_a_before}</span></div>
                    <div>A после: <span className="font-bold text-slate-900">{metrics.filter_stats.source_a_after}</span></div>
                    <div>B до фильтров: <span className="font-bold text-slate-900">{metrics.filter_stats.source_b_before}</span></div>
                    <div>B после: <span className="font-bold text-slate-900">{metrics.filter_stats.source_b_after}</span></div>
                  </div>
                )}

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
                        {['Тип', 'Ключ', 'Строки A', 'Строки B', 'Сумма A', 'Сумма B', 'Δ суммы', 'Δ дней', 'Причина'].map(header => (
                          <th key={header} className="px-4 py-3 text-left text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                            {header}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {resultRows.slice(0, 300).map((row, index) => (
                        <tr key={`${row.key}-${row.row_a || 'x'}-${row.row_b || 'x'}-${index}`} className="hover:bg-slate-50">
                          <td className="px-4 py-3">
                            <span className="rounded-md bg-slate-100 px-2 py-1 text-[10px] font-bold text-slate-600">
                              {row.match_type || '1↔1'}
                            </span>
                          </td>
                          <td className="max-w-[260px] truncate px-4 py-3 font-mono text-xs" title={row.key}>{row.key || '—'}</td>
                          <td className="px-4 py-3 text-xs">
                            {row.grouped_rows_a?.length
                              ? row.grouped_rows_a.join(', ')
                              : (row.row_a ?? '—')}
                          </td>
                          <td className="px-4 py-3 text-xs">
                            {row.grouped_rows_b?.length
                              ? row.grouped_rows_b.join(', ')
                              : (row.row_b ?? '—')}
                          </td>
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
              <div className="mb-3 flex items-start justify-between gap-3">
                <div>
                  <div className="flex items-center gap-2">
                    <h2 className="text-sm font-bold text-slate-900">Шаблон сверки</h2>
                    <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${
                      selectedDefinitionId
                        ? 'bg-indigo-50 text-indigo-700'
                        : 'bg-slate-100 text-slate-600'
                    }`}>
                      {selectedDefinitionId ? 'Шаблон' : 'Разовая'}
                    </span>
                  </div>
                  <p className="mt-1 text-[11px] leading-4 text-slate-500">
                    Шаблон необязателен. Можно настроить правила и сразу запустить разовую сверку.
                  </p>
                </div>
                {selectedDefinitionId && (
                  <button
                    onClick={resetDefinition}
                    className="rounded-lg p-2 text-slate-400 hover:bg-slate-100"
                    title="Новый пустой шаблон"
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

              <div className="mt-3 grid grid-cols-1 gap-2">
                {selectedDefinitionId && (
                  <button
                    onClick={detachTemplateForOneOffRun}
                    className="flex w-full items-center justify-center gap-2 rounded-lg border border-indigo-200 bg-indigo-50 px-3 py-2.5 text-xs font-semibold text-indigo-700 hover:bg-indigo-100"
                  >
                    <Play className="h-3.5 w-3.5" />
                    Использовать правила разово
                  </button>
                )}

                {canManage && (
                  <button
                    onClick={() => void handleSaveTemplate()}
                    disabled={savingTemplate}
                    className="flex w-full items-center justify-center gap-2 rounded-lg bg-slate-900 px-3 py-2.5 text-xs font-semibold text-white hover:bg-slate-800 disabled:opacity-50"
                  >
                    {savingTemplate ? <LoaderCircle className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />}
                    {selectedDefinitionId ? 'Обновить шаблон' : 'Сохранить как шаблон'}
                  </button>
                )}
              </div>
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
              <div className="mb-3 flex items-center justify-between gap-3">
                <div className="flex items-center gap-2">
                  <History className="h-4 w-4 text-indigo-600" />
                  <div>
                    <h2 className="text-sm font-bold text-slate-900">История запусков</h2>
                    <p className="text-[10px] text-slate-400">Компактный архив конструктора</p>
                  </div>
                </div>
                {archive.length > 6 && (
                  <button
                    onClick={() => setShowAllRuns(value => !value)}
                    className="text-[11px] font-semibold text-indigo-600 hover:text-indigo-700"
                  >
                    {showAllRuns ? 'Свернуть' : `Все · ${archive.length}`}
                  </button>
                )}
              </div>

              <div className={`space-y-2 ${showAllRuns ? 'max-h-[560px] overflow-y-auto pr-1' : ''}`}>
                {(showAllRuns ? archive : archive.slice(0, 6)).map(item => {
                  const summary = item.summary || {};
                  const matchRate = Number(summary.match_percentage || 0);
                  const discrepancies = Number(summary.discrepancy_count || 0);
                  const createdBy = String(item.created_by || item.username || '—');
                  const timestamp = String(item.updated_at || item.timestamp || item.created_at || '');
                  const isCompleted = String(item.status || '').toUpperCase() === 'COMPLETED';
                  const title = item.definition_id
                    ? (item.definition_name || `Шаблон #${item.definition_id}`)
                    : 'Разовая сверка';

                  return (
                    <div
                      key={String(item.id)}
                      className="rounded-xl border border-slate-200 bg-slate-50/70 p-3"
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0">
                          <div className="flex items-center gap-1.5">
                            <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${
                              isCompleted ? 'bg-emerald-500' : 'bg-amber-500'
                            }`} />
                            <span className="truncate text-xs font-semibold text-slate-800" title={title}>
                              {title}
                            </span>
                          </div>
                          <div className="mt-1 flex items-center gap-1 text-[10px] text-slate-500">
                            <Clock3 className="h-3 w-3 shrink-0" />
                            <span>{formatDateTime(timestamp)}</span>
                            <span>·</span>
                            <span className="truncate" title={createdBy}>{createdBy}</span>
                          </div>
                        </div>

                        <div className="shrink-0 text-right">
                          <div className="text-xs font-bold text-indigo-700">{matchRate.toFixed(1)}%</div>
                          <div className="text-[9px] uppercase text-slate-400">match</div>
                        </div>
                      </div>

                      <div className="mt-2 grid grid-cols-[1fr_auto] gap-2 text-[10px] text-slate-500">
                        <div className="min-w-0 truncate" title={runSourceNames(item)}>
                          {runSourceNames(item)}
                        </div>
                        <div className="whitespace-nowrap">{formatMonth(item.period_month)}</div>
                      </div>

                      <div className="mt-2 flex items-center justify-between border-t border-slate-200/80 pt-2 text-[10px]">
                        <span className="font-mono text-slate-400">Run {item.run_id || '—'}</span>
                        <span className={discrepancies ? 'font-semibold text-amber-700' : 'font-semibold text-emerald-700'}>
                          {discrepancies ? `${discrepancies} расхожд.` : 'Без расхождений'}
                        </span>
                      </div>
                    </div>
                  );
                })}

                {archive.length === 0 && (
                  <div className="rounded-lg bg-slate-50 p-4 text-xs text-slate-500">
                    Запускайте сверки даже без шаблона — здесь появятся период, пользователь, время, файлы и результат.
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
