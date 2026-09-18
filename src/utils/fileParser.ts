import * as XLSX from 'xlsx';
import { RawRow, DateSummaryRow, UnmatchedRow, AmountMismatchRow, TerminalSummaryItem } from '../types';

export function guessCol(cols: string[], keywords: string[]): string | null {
  if (!cols || cols.length === 0) return null;
  for (const col of cols) {
    const colLower = String(col).toLowerCase().trim();
    if (keywords.some(kw => colLower.includes(kw))) {
      return col;
    }
  }
  return null;
}

type FileParseProgressStatus = 'loading' | 'success' | 'error';
type FileParseProgressStage = 'reading' | 'parsing' | 'ready' | 'error';

interface FileParseProgressDetail {
  status: FileParseProgressStatus;
  stage: FileParseProgressStage;
  fileName: string;
  progress?: number;
  rows?: number;
  columns?: number;
  error?: string;
  sizeBytes?: number;
  elapsedMs?: number;
}

const FILE_PARSE_PROGRESS_EVENT = 'reconcile:file-parse-progress';
export const MAX_FILE_SIZE_BYTES = 200 * 1024 * 1024;

function emitFileParseProgress(detail: FileParseProgressDetail): void {
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent<FileParseProgressDetail>(FILE_PARSE_PROGRESS_EVENT, { detail }));
  }
}

function parseWorkbook(data: ArrayBuffer | string, fileName: string): { fileName: string; rows: RawRow[]; columns: string[] } {
  const workbook = XLSX.read(data, {
    type: typeof data === 'string' ? 'binary' : 'array',
    cellDates: true,
    dense: true,
  });
  const firstSheetName = workbook.SheetNames[0];
  const worksheet = workbook.Sheets[firstSheetName];
  const jsonRows: RawRow[] = XLSX.utils.sheet_to_json(worksheet, { defval: '' });

  if (jsonRows.length === 0) {
    return { fileName, rows: [], columns: [] };
  }

  return {
    fileName,
    rows: jsonRows,
    columns: Object.keys(jsonRows[0]),
  };
}

export async function parseFile(file: File): Promise<{ fileName: string; rows: RawRow[]; columns: string[] }> {
  const startedAt = performance.now();
  const fileSize = file.size;

  if (fileSize > MAX_FILE_SIZE_BYTES) {
    const sizeMb = (fileSize / 1024 / 1024).toFixed(1);
    const error = `Файл слишком большой: ${sizeMb} МБ. Максимальный размер — 200 МБ.`;
    emitFileParseProgress({
      status: 'error',
      stage: 'error',
      fileName: file.name,
      sizeBytes: fileSize,
      elapsedMs: 0,
      error,
    });
    throw new Error(error);
  }

  emitFileParseProgress({
    status: 'loading',
    stage: 'reading',
    fileName: file.name,
    progress: 0,
    sizeBytes: fileSize,
    elapsedMs: 0,
  });

  return new Promise((resolve, reject) => {
    const reader = new FileReader();

    reader.onprogress = (e) => {
      if (!e.lengthComputable) return;
      const progress = Math.min(80, Math.round((e.loaded / e.total) * 80));
      emitFileParseProgress({
        status: 'loading',
        stage: 'reading',
        fileName: file.name,
        progress,
        sizeBytes: fileSize,
        elapsedMs: performance.now() - startedAt,
      });
    };

    reader.onload = (e) => {
      const data = e.target?.result;
      if (!(data instanceof ArrayBuffer)) {
        const error = 'Не удалось получить содержимое файла.';
        emitFileParseProgress({
          status: 'error',
          stage: 'error',
          fileName: file.name,
          sizeBytes: fileSize,
          elapsedMs: performance.now() - startedAt,
          error,
        });
        reject(new Error(error));
        return;
      }

      emitFileParseProgress({
        status: 'loading',
        stage: 'parsing',
        fileName: file.name,
        progress: 80,
        sizeBytes: fileSize,
        elapsedMs: performance.now() - startedAt,
      });

      if (typeof Worker === 'undefined') {
        try {
          const result = parseWorkbook(data, file.name);
          emitFileParseProgress({
            status: 'success',
            stage: 'ready',
            fileName: file.name,
            progress: 100,
            rows: result.rows.length,
            columns: result.columns.length,
            sizeBytes: fileSize,
            elapsedMs: performance.now() - startedAt,
          });
          resolve(result);
        } catch (err) {
          const message = err instanceof Error ? err.message : String(err);
          emitFileParseProgress({
            status: 'error',
            stage: 'error',
            fileName: file.name,
            sizeBytes: fileSize,
            elapsedMs: performance.now() - startedAt,
            error: message,
          });
          reject(err);
        }
        return;
      }

      let worker: Worker | null = null;
      try {
        worker = new Worker(new URL('./fileParseWorker.ts', import.meta.url), { type: 'module' });

        worker.onmessage = (event: MessageEvent<{ success: boolean; result?: { fileName: string; rows: RawRow[]; columns: string[] }; error?: string }>) => {
          worker?.terminate();
          worker = null;

          if (event.data.success && event.data.result) {
            const result = event.data.result;
            emitFileParseProgress({
              status: 'success',
              stage: 'ready',
              fileName: file.name,
              progress: 100,
              rows: result.rows.length,
              columns: result.columns.length,
              sizeBytes: fileSize,
              elapsedMs: performance.now() - startedAt,
            });
            resolve(result);
            return;
          }

          const message = event.data.error || 'Не удалось обработать файл.';
          emitFileParseProgress({
            status: 'error',
            stage: 'error',
            fileName: file.name,
            sizeBytes: fileSize,
            elapsedMs: performance.now() - startedAt,
            error: message,
          });
          reject(new Error(message));
        };

        worker.onerror = (event) => {
          worker?.terminate();
          worker = null;
          const message = event.message || 'Ошибка Web Worker при обработке файла.';
          emitFileParseProgress({
            status: 'error',
            stage: 'error',
            fileName: file.name,
            sizeBytes: fileSize,
            elapsedMs: performance.now() - startedAt,
            error: message,
          });
          reject(new Error(message));
        };

        worker.postMessage({ buffer: data, fileName: file.name }, [data]);
      } catch (err) {
        worker?.terminate();
        worker = null;
        try {
          const result = parseWorkbook(data, file.name);
          emitFileParseProgress({
            status: 'success',
            stage: 'ready',
            fileName: file.name,
            progress: 100,
            rows: result.rows.length,
            columns: result.columns.length,
            sizeBytes: fileSize,
            elapsedMs: performance.now() - startedAt,
          });
          resolve(result);
        } catch (fallbackErr) {
          const message = fallbackErr instanceof Error ? fallbackErr.message : String(fallbackErr);
          emitFileParseProgress({
            status: 'error',
            stage: 'error',
            fileName: file.name,
            sizeBytes: fileSize,
            elapsedMs: performance.now() - startedAt,
            error: message,
          });
          reject(fallbackErr);
        }
      }
    };

    reader.onerror = () => {
      const message = 'Не удалось прочитать файл.';
      emitFileParseProgress({
        status: 'error',
        stage: 'error',
        fileName: file.name,
        sizeBytes: fileSize,
        elapsedMs: performance.now() - startedAt,
        error: message,
      });
      reject(new Error(message));
    };

    reader.readAsArrayBuffer(file);
  });
}

export function exportReconciliationToExcel(
  summaryRows: DateSummaryRow[],
  onlyOurRows: UnmatchedRow[],
  onlyBankRows: UnmatchedRow[],
  mismatchRows: AmountMismatchRow[],
  dupsOur: RawRow[],
  dupsBank: RawRow[],
  terminalSummary?: TerminalSummaryItem[]
): void {
  const wb = XLSX.utils.book_new();

  // Sheet 1: Сводка_по_датам
  const wsSummary = XLSX.utils.json_to_sheet(summaryRows);
  XLSX.utils.book_append_sheet(wb, wsSummary, 'Сводка_по_датам');

  // Sheet 2: Терминалы_и_Комиссия (если есть данные)
  if (terminalSummary && terminalSummary.length > 0) {
    const cleanTerminals = terminalSummary.map(t => ({
      'TID Терминала': t.terminal_id,
      'Банк-эквайер': t.bank_acquirer || '',
      'Мерчант': t.merchant_id || '',
      'Юр. лицо': t.legal_entity || '',
      'Кол-во транзакций': t.tx_count,
      'Оборот (UZS)': t.total_volume,
      'Ставка комиссии (%)': t.commission_pct,
      'Комиссия эквайринга (UZS)': t.commission_amount,
      'К зачислению нетто (UZS)': t.net_volume,
    }));
    const wsTerm = XLSX.utils.json_to_sheet(cleanTerminals);
    XLSX.utils.book_append_sheet(wb, wsTerm, 'Терминалы_и_Комиссия');
  }

  // Sheet 3: Нет_в_банке
  const cleanOnlyOur = onlyOurRows.map(r => ({
    'Вкл.': r.checked ? 'Да' : 'Нет',
    'Дата': r.date_str,
    'RRN': r.RRN,
    'Сумма': r.amount,
    'Статус': r.status || '',
    'Причина': r.reason || '',
  }));
  const wsOur = XLSX.utils.json_to_sheet(cleanOnlyOur.length ? cleanOnlyOur : [{ 'Статус': 'Нет данных' }]);
  XLSX.utils.book_append_sheet(wb, wsOur, 'Нет_в_банке');

  // Sheet 4: Лишнее_от_банка
  const cleanOnlyBank = onlyBankRows.map(r => ({
    'Вкл.': r.checked ? 'Да' : 'Нет',
    'Дата': r.date_str,
    'RRN': r.RRN,
    'Сумма': r.amount,
    'Статус': r.status || '',
    'TID': r.terminal_id || '',
    'Комиссия (%)': r.commission_pct || 0,
    'Причина': r.reason || '',
  }));
  const wsBank = XLSX.utils.json_to_sheet(cleanOnlyBank.length ? cleanOnlyBank : [{ 'Статус': 'Нет данных' }]);
  XLSX.utils.book_append_sheet(wb, wsBank, 'Лишнее_от_банка');

  // Sheet 5: Расхождения_сумм
  if (mismatchRows.length > 0) {
    const cleanMismatch = mismatchRows.map(r => ({
      'RRN': r.RRN,
      'Дата (Мы)': r.date_our,
      'Дата (Банк)': r.date_bank,
      'Сумма (Мы)': r.net_amount_our,
      'Сумма (Банк)': r.net_amount_bank,
      'Δ Разница': r['Δ сумма'],
      'Причина': r.amount_issue || 'Расхождение суммы',
    }));
    const wsMismatch = XLSX.utils.json_to_sheet(cleanMismatch);
    XLSX.utils.book_append_sheet(wb, wsMismatch, 'Расхождения_сумм');
  }

  // Sheet 6 & 7: Дубликаты
  if (dupsOur.length > 0) {
    const wsDupOur = XLSX.utils.json_to_sheet(dupsOur);
    XLSX.utils.book_append_sheet(wb, wsDupOur, 'Дубликаты_наши');
  }
  if (dupsBank.length > 0) {
    const wsDupBank = XLSX.utils.json_to_sheet(dupsBank);
    XLSX.utils.book_append_sheet(wb, wsDupBank, 'Дубликаты_банк');
  }

  const now = new Date();
  const dateStr = `${now.getFullYear()}${String(now.getMonth() + 1).padStart(2, '0')}${String(now.getDate()).padStart(2, '0')}_${String(now.getHours()).padStart(2, '0')}${String(now.getMinutes()).padStart(2, '0')}`;
  XLSX.writeFile(wb, `Сверка_${dateStr}.xlsx`);
}
