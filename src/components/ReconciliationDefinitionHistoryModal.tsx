import React, { useEffect, useMemo, useState } from 'react';
import {
  ArrowRight,
  History,
  LoaderCircle,
  RotateCcw,
  UserRound,
  X,
} from 'lucide-react';

import {
  ReconciliationBuilderConfig,
  ReconciliationDefinition,
  ReconciliationDefinitionVersion,
  getReconciliationDefinitionVersions,
  restoreReconciliationDefinitionVersion,
} from '../utils/reconciliationBuilderApi';

interface Props {
  definition: ReconciliationDefinition;
  canManage: boolean;
  onClose: () => void;
  onRestored: (definition: ReconciliationDefinition, message: string) => void;
}

interface DiffRow {
  label: string;
  from: string;
  to: string;
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

function compact(value: any): string {
  if (value == null || value === '') return '—';
  if (typeof value === 'boolean') return value ? 'Да' : 'Нет';
  if (Array.isArray(value) || typeof value === 'object') {
    const text = JSON.stringify(value);
    return text.length > 180 ? text.slice(0, 177) + '…' : text;
  }
  return String(value);
}

function same(a: any, b: any): boolean {
  return JSON.stringify(a ?? null) === JSON.stringify(b ?? null);
}

function configDiff(
  historical: ReconciliationBuilderConfig,
  current: ReconciliationBuilderConfig,
): DiffRow[] {
  const fields: Array<[string, keyof ReconciliationBuilderConfig]> = [
    ['Режим matching', 'matching_mode'],
    ['Ключи', 'key_pairs'],
    ['Вычисляемые поля', 'computed_fields'],
    ['Фильтры', 'filters'],
    ['Колонка суммы A', 'amount_a_col'],
    ['Колонка суммы B', 'amount_b_col'],
    ['Преобразование суммы A', 'amount_a_transform'],
    ['Преобразование суммы B', 'amount_b_transform'],
    ['Допуск суммы', 'amount_tolerance'],
    ['Колонка даты A', 'date_a_col'],
    ['Колонка даты B', 'date_b_col'],
    ['Допуск даты', 'date_tolerance_days'],
    ['Пустой ключ = исключение', 'ignore_empty_keys'],
    ['Day first', 'dayfirst'],
    ['Колонки результата A', 'result_columns_a'],
    ['Колонки результата B', 'result_columns_b'],
  ];

  return fields
    .filter(([, key]) => !same(historical[key], current[key]))
    .map(([label, key]) => ({
      label,
      from: compact(historical[key]),
      to: compact(current[key]),
    }));
}

export const ReconciliationDefinitionHistoryModal: React.FC<Props> = ({
  definition,
  canManage,
  onClose,
  onRestored,
}) => {
  const [versions, setVersions] = useState<ReconciliationDefinitionVersion[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(definition.active_version_id || null);
  const [loading, setLoading] = useState(true);
  const [restoring, setRestoring] = useState(false);
  const [changeNote, setChangeNote] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    let disposed = false;
    setLoading(true);
    setError('');

    getReconciliationDefinitionVersions(definition.id)
      .then(items => {
        if (disposed) return;
        setVersions(items);
        const preferred = items.find(item => item.id === definition.active_version_id) || items[0];
        setSelectedId(preferred?.id || null);
      })
      .catch((err: any) => {
        if (!disposed) setError(err?.message || 'Не удалось загрузить историю версий.');
      })
      .finally(() => {
        if (!disposed) setLoading(false);
      });

    return () => {
      disposed = true;
    };
  }, [definition.id, definition.active_version_id]);

  const selected = versions.find(item => item.id === selectedId) || null;
  const active = versions.find(item => item.id === definition.active_version_id)
    || versions.find(item => item.status === 'ACTIVE')
    || null;

  const differences = useMemo(() => {
    if (!selected || !active) return [];
    const rows: DiffRow[] = [];

    if (selected.name_snapshot !== active.name_snapshot) {
      rows.push({
        label: 'Название',
        from: selected.name_snapshot,
        to: active.name_snapshot,
      });
    }
    if (selected.description_snapshot !== active.description_snapshot) {
      rows.push({
        label: 'Описание',
        from: selected.description_snapshot || '—',
        to: active.description_snapshot || '—',
      });
    }

    return [...rows, ...configDiff(selected.config, active.config)];
  }, [selected, active]);

  const handleRestore = async () => {
    if (!selected || selected.id === definition.active_version_id || !canManage) return;
    const nextVersion = (definition.current_version_number || 0) + 1;
    const confirmed = window.confirm(
      'Восстановить v' + selected.version_number
      + '? Старая версия не будет перезаписана — система создаст новую v'
      + nextVersion + '.',
    );
    if (!confirmed) return;

    setRestoring(true);
    setError('');
    try {
      const response = await restoreReconciliationDefinitionVersion(
        definition.id,
        selected.id,
        changeNote.trim(),
      );
      onRestored(response.definition, response.message);
    } catch (err: any) {
      setError(err?.message || 'Не удалось восстановить версию.');
    } finally {
      setRestoring(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[90] flex items-center justify-center bg-slate-950/40 p-3 backdrop-blur-[1px]">
      <div className="flex max-h-[92vh] w-full max-w-5xl flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl">
        <div className="flex items-start justify-between gap-4 border-b border-slate-200 px-5 py-4">
          <div>
            <div className="flex items-center gap-2">
              <History className="h-5 w-5 text-indigo-600" />
              <h2 className="text-lg font-bold text-slate-900">История версий</h2>
            </div>
            <div className="mt-1 text-xs text-slate-500">
              {definition.name} · активная v{definition.current_version_number || 1}
            </div>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg border border-slate-200 p-2 text-slate-500 hover:bg-slate-50"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {error && (
          <div className="border-b border-rose-100 bg-rose-50 px-5 py-2 text-xs text-rose-700">
            {error}
          </div>
        )}

        {loading ? (
          <div className="flex min-h-[360px] items-center justify-center gap-2 text-sm text-slate-500">
            <LoaderCircle className="h-4 w-4 animate-spin" />
            Загружаем версии…
          </div>
        ) : (
          <div className="grid min-h-0 flex-1 grid-cols-1 md:grid-cols-[300px_1fr]">
            <div className="min-h-0 overflow-y-auto border-r border-slate-200 bg-slate-50/60 p-3">
              <div className="space-y-2">
                {versions.map(version => {
                  const isActive = version.id === definition.active_version_id || version.status === 'ACTIVE';
                  return (
                    <button
                      key={version.id}
                      onClick={() => setSelectedId(version.id)}
                      className={'w-full rounded-xl border p-3 text-left transition '
                        + (selectedId === version.id
                          ? 'border-indigo-300 bg-white shadow-sm'
                          : 'border-slate-200 bg-white/70 hover:border-slate-300')}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <div className="text-sm font-bold text-slate-900">v{version.version_number}</div>
                        <span className={'rounded-full px-2 py-0.5 text-[9px] font-semibold '
                          + (isActive
                            ? 'bg-emerald-50 text-emerald-700'
                            : 'bg-slate-100 text-slate-500')}
                        >
                          {isActive ? 'ACTIVE' : 'ARCHIVED'}
                        </span>
                      </div>
                      <div className="mt-1 flex items-center gap-1 text-[10px] text-slate-500">
                        <UserRound className="h-3 w-3" />
                        <span className="truncate">{version.created_by || '—'}</span>
                      </div>
                      <div className="mt-1 text-[10px] text-slate-400">
                        {formatDateTime(version.created_at)}
                      </div>
                      {version.change_note && (
                        <div className="mt-2 line-clamp-2 text-[10px] leading-4 text-slate-600">
                          {version.change_note}
                        </div>
                      )}
                      {version.restored_from_version_id && (
                        <div className="mt-2 text-[9px] font-semibold text-indigo-600">
                          восстановленная версия
                        </div>
                      )}
                    </button>
                  );
                })}
              </div>
            </div>

            <div className="min-h-0 overflow-y-auto p-5">
              {!selected ? (
                <div className="text-sm text-slate-500">Версия не выбрана.</div>
              ) : (
                <div className="space-y-5">
                  <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-start">
                    <div>
                      <div className="flex items-center gap-2">
                        <h3 className="text-xl font-bold text-slate-900">v{selected.version_number}</h3>
                        {selected.id === definition.active_version_id && (
                          <span className="rounded-full bg-emerald-50 px-2 py-1 text-[10px] font-semibold text-emerald-700">
                            текущая
                          </span>
                        )}
                      </div>
                      <div className="mt-1 text-sm font-semibold text-slate-700">
                        {selected.name_snapshot}
                      </div>
                      <div className="mt-1 text-xs text-slate-500">
                        {selected.description_snapshot || 'Без описания'}
                      </div>
                    </div>

                    <div className="text-right text-[11px] text-slate-500">
                      <div>{selected.created_by || '—'}</div>
                      <div className="mt-1">{formatDateTime(selected.created_at)}</div>
                    </div>
                  </div>

                  <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
                    <div className="text-xs font-bold uppercase tracking-wider text-slate-400">
                      Комментарий к версии
                    </div>
                    <div className="mt-2 text-sm text-slate-700">
                      {selected.change_note || 'Комментарий не указан.'}
                    </div>
                  </div>

                  <div>
                    <div className="mb-2 flex items-center gap-2">
                      <div className="text-sm font-bold text-slate-900">
                        Сравнение с текущей v{active?.version_number || definition.current_version_number || 1}
                      </div>
                      {selected.id !== definition.active_version_id && (
                        <ArrowRight className="h-4 w-4 text-slate-400" />
                      )}
                    </div>

                    {selected.id === definition.active_version_id ? (
                      <div className="rounded-xl bg-emerald-50 p-4 text-xs text-emerald-700">
                        Это текущая активная версия шаблона.
                      </div>
                    ) : differences.length === 0 ? (
                      <div className="rounded-xl bg-slate-50 p-4 text-xs text-slate-500">
                        Конфигурация совпадает с текущей версией.
                      </div>
                    ) : (
                      <div className="overflow-hidden rounded-xl border border-slate-200">
                        <table className="min-w-full text-xs">
                          <thead className="bg-slate-50">
                            <tr>
                              <th className="px-3 py-2 text-left text-[10px] uppercase text-slate-400">Параметр</th>
                              <th className="px-3 py-2 text-left text-[10px] uppercase text-slate-400">v{selected.version_number}</th>
                              <th className="px-3 py-2 text-left text-[10px] uppercase text-slate-400">Сейчас</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-slate-100">
                            {differences.map((row, index) => (
                              <tr key={row.label + '-' + index}>
                                <td className="px-3 py-2 font-semibold text-slate-700">{row.label}</td>
                                <td className="max-w-[260px] px-3 py-2 text-slate-600">
                                  <div className="break-words">{row.from}</div>
                                </td>
                                <td className="max-w-[260px] px-3 py-2 text-slate-600">
                                  <div className="break-words">{row.to}</div>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>

                  {canManage && selected.id !== definition.active_version_id && (
                    <div className="rounded-xl border border-indigo-100 bg-indigo-50/50 p-4">
                      <div className="text-sm font-semibold text-slate-900">
                        Восстановить v{selected.version_number}
                      </div>
                      <div className="mt-1 text-xs leading-5 text-slate-500">
                        История не переписывается. Будет создана новая v{(definition.current_version_number || 0) + 1}
                        {' '}с правилами выбранной версии.
                      </div>
                      <input
                        value={changeNote}
                        onChange={event => setChangeNote(event.target.value)}
                        placeholder={'Комментарий, например: откат к v' + selected.version_number}
                        className="mt-3 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs"
                      />
                      <button
                        onClick={() => void handleRestore()}
                        disabled={restoring}
                        className="mt-3 inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2.5 text-xs font-semibold text-white hover:bg-indigo-700 disabled:opacity-50"
                      >
                        {restoring
                          ? <LoaderCircle className="h-4 w-4 animate-spin" />
                          : <RotateCcw className="h-4 w-4" />}
                        Создать новую версию из v{selected.version_number}
                      </button>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
