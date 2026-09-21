import * as XLSX from 'xlsx';

import {
  BuilderResultRow,
  BuilderRunResult,
  ReconciliationBuilderConfig,
} from './reconciliationBuilderApi';

export interface BuilderArchiveRecord {
  id: number;
  run_id?: string;
  status?: string;
  period_month?: string;
  created_at?: string;
  updated_at?: string;
  created_by?: string;
  username?: string;
  source_a_name?: string;
  source_b_name?: string;
  source_files?: string[];
  definition_id?: number | null;
  definition_name?: string;
  definition_version_id?: number | null;
  definition_version_number?: number | null;
  summary?: BuilderRunResult['summary'];
  config?: ReconciliationBuilderConfig;
  config_snapshot?: ReconciliationBuilderConfig;
  result_snapshot?: BuilderRunResult;
  archive_schema_version?: number;
  [key: string]: any;
}

function safeCell(value: any): any {
  if (value == null) return '';
  if (typeof value === 'number' || typeof value === 'boolean') return value;
  if (value instanceof Date) return value;
  const text = String(value);
  return /^[=+\-@]/.test(text) ? `'${text}` : text;
}

function sourceRows(row: BuilderResultRow, side: 'a' | 'b'): Record<string, any>[] {
  const source = side === 'a' ? row.source_a : row.source_b;
  if (!source || typeof source !== 'object') return [];
  if (Array.isArray((source as any).rows)) {
    return (source as any).rows.filter((item: any) => item && typeof item === 'object');
  }
  return [source as Record<string, any>];
}

function collectColumns(rows: BuilderResultRow[], side: 'a' | 'b'): string[] {
  const columns: string[] = [];
  const seen = new Set<string>();
  for (const row of rows) {
    for (const source of sourceRows(row, side)) {
      for (const key of Object.keys(source)) {
        if (!seen.has(key)) {
          seen.add(key);
          columns.push(key);
        }
      }
    }
  }
  return columns;
}

function aggregateSourceValue(
  row: BuilderResultRow,
  side: 'a' | 'b',
  column: string,
): any {
  const values = sourceRows(row, side)
    .map(source => source[column])
    .filter(value => value != null && value !== '');

  if (values.length === 0) return '';

  const normalized = values.map(value => safeCell(value));
  const unique = Array.from(new Set(normalized.map(value => String(value))));
  if (unique.length === 1) {
    const raw = values[0];
    return typeof raw === 'number' ? raw : safeCell(raw);
  }
  return unique.join(' | ');
}

function flattenRows(rows: BuilderResultRow[]): Record<string, any>[] {
  const columnsA = collectColumns(rows, 'a');
  const columnsB = collectColumns(rows, 'b');

  return rows.map(row => {
    const flat: Record<string, any> = {
      'Тип': row.match_type || '1↔1',
      'Ключ': safeCell(row.key || ''),
      'Строки A': (row.grouped_rows_a?.length
        ? row.grouped_rows_a
        : row.row_a != null
          ? [row.row_a]
          : []).join(', '),
      'Строки B': (row.grouped_rows_b?.length
        ? row.grouped_rows_b
        : row.row_b != null
          ? [row.row_b]
          : []).join(', '),
      'Сумма A': row.amount_a ?? '',
      'Сумма B': row.amount_b ?? '',
      'Δ суммы': row.amount_delta ?? '',
      'Дата A': safeCell(row.date_a || ''),
      'Дата B': safeCell(row.date_b || ''),
      'Δ дней': row.date_delta_days ?? '',
      'Причина': safeCell(row.reason || ''),
    };

    for (const column of columnsA) {
      flat[`A · ${column}`] = aggregateSourceValue(row, 'a', column);
    }
    for (const column of columnsB) {
      flat[`B · ${column}`] = aggregateSourceValue(row, 'b', column);
    }
    return flat;
  });
}

function appendJsonSheet(
  workbook: XLSX.WorkBook,
  name: string,
  rows: Record<string, any>[],
): void {
  const data = rows.length ? rows : [{ 'Статус': 'Нет данных' }];
  XLSX.utils.book_append_sheet(
    workbook,
    XLSX.utils.json_to_sheet(data),
    name,
  );
}

function rulesSheet(config: ReconciliationBuilderConfig): XLSX.WorkSheet {
  const rows: any[][] = [
    ['Раздел', 'Параметр', 'Значение'],
    ['Основное', 'Matching mode', config.matching_mode || 'one_to_one'],
    ['Основное', 'Пустой ключ = исключение', config.ignore_empty_keys ? 'Да' : 'Нет'],
    ['Основное', 'Day first', config.dayfirst ? 'Да' : 'Нет'],
    ['Сумма', 'Колонка A', config.amount_a_col || ''],
    ['Сумма', 'Колонка B', config.amount_b_col || ''],
    ['Сумма', 'Допуск', config.amount_tolerance ?? 0],
    ['Сумма', 'Transform A', config.amount_a_transform || 'as_is'],
    ['Сумма', 'Transform B', config.amount_b_transform || 'as_is'],
    ['Дата', 'Колонка A', config.date_a_col || ''],
    ['Дата', 'Колонка B', config.date_b_col || ''],
    ['Дата', 'Допуск, дней', config.date_tolerance_days ?? 0],
    [],
    ['Ключи', 'A', 'B', 'Режим', 'Transform A', 'Transform B'],
  ];

  for (const pair of config.key_pairs || []) {
    rows.push([
      'Ключ',
      pair.left,
      pair.right,
      pair.mode,
      pair.left_transform || 'none',
      pair.right_transform || 'none',
    ]);
  }

  rows.push([], ['Фильтры', 'Источник', 'Колонка', 'Оператор', 'Значение']);
  for (const filter of config.filters || []) {
    rows.push([
      'Фильтр',
      filter.side.toUpperCase(),
      filter.column,
      filter.operator,
      filter.value || '',
    ]);
  }

  rows.push([], ['Вычисляемые поля', 'Источник', 'Имя', 'Операция', 'Источники', 'Параметры']);
  for (const field of config.computed_fields || []) {
    const params = {
      separator: field.separator,
      find: field.find,
      replace_with: field.replace_with,
      start: field.start,
      length: field.length,
      text_mode: field.text_mode,
      date_format: field.date_format,
    };
    rows.push([
      'Поле',
      field.side.toUpperCase(),
      field.name,
      field.operation,
      (field.sources || []).join(' + '),
      Object.entries(params)
        .filter(([, value]) => value != null && value !== '')
        .map(([key, value]) => `${key}=${value}`)
        .join('; '),
    ]);
  }

  return XLSX.utils.aoa_to_sheet(rows);
}

export function exportBuilderArchiveRun(record: BuilderArchiveRecord): void {
  const result = record.result_snapshot;
  if (!result) {
    throw new Error('Для этой старой записи полный snapshot результата не сохранён.');
  }

  const config = record.config_snapshot || record.config || {
    key_pairs: [],
    amount_tolerance: 0,
    date_tolerance_days: 0,
    ignore_empty_keys: true,
    dayfirst: true,
  };

  const generic = result.custom_metrics?.generic;
  const workbook = XLSX.utils.book_new();

  const summaryRows = [
    { 'Параметр': 'Run ID', 'Значение': record.run_id || result.run_id || '' },
    { 'Параметр': 'Шаблон', 'Значение': record.definition_name || 'Разовая сверка' },
    { 'Параметр': 'Версия шаблона', 'Значение': record.definition_version_number ? 'v' + record.definition_version_number : '' },
    { 'Параметр': 'Период', 'Значение': record.period_month || '' },
    { 'Параметр': 'Пользователь', 'Значение': record.created_by || record.username || '' },
    { 'Параметр': 'Создано', 'Значение': record.created_at || record.updated_at || '' },
    { 'Параметр': 'Статус', 'Значение': record.status || result.status || '' },
    { 'Параметр': 'Источник A', 'Значение': record.source_a_name || record.source_files?.[0] || '' },
    { 'Параметр': 'Источник B', 'Значение': record.source_b_name || record.source_files?.[1] || '' },
    { 'Параметр': 'Записей A', 'Значение': result.summary.total_records_a },
    { 'Параметр': 'Записей B', 'Значение': result.summary.total_records_b },
    { 'Параметр': 'Сумма A', 'Значение': result.summary.total_sum_a },
    { 'Параметр': 'Сумма B', 'Значение': result.summary.total_sum_b },
    { 'Параметр': 'Совпало', 'Значение': result.summary.matched_count },
    { 'Параметр': 'Расхождений', 'Значение': result.summary.discrepancy_count },
    { 'Параметр': 'Сходимость, %', 'Значение': result.summary.match_percentage },
    { 'Параметр': 'Δ суммы', 'Значение': result.summary.diff_sum },
    { 'Параметр': 'Время выполнения, мс', 'Значение': result.summary.execution_time_ms },
  ];

  XLSX.utils.book_append_sheet(
    workbook,
    XLSX.utils.json_to_sheet(summaryRows),
    'Summary',
  );
  XLSX.utils.book_append_sheet(workbook, rulesSheet(config), 'Rules');

  appendJsonSheet(workbook, 'Matched', flattenRows(generic?.matched || []));
  appendJsonSheet(workbook, 'Mismatches', flattenRows(generic?.mismatches || []));
  appendJsonSheet(workbook, 'Only_A', flattenRows(generic?.only_a || []));
  appendJsonSheet(workbook, 'Only_B', flattenRows(generic?.only_b || []));

  const runId = String(record.run_id || result.run_id || 'run').replace(/[^\w-]+/g, '_');
  const period = String(record.period_month || 'period').replace(/[^\w-]+/g, '_');
  XLSX.writeFile(workbook, `ReconcileHub_${period}_${runId}.xlsx`);
}
