import * as XLSX from 'xlsx';
import { RawRow } from '../types';
import { FileParseOptions, ParsedFileResult } from './fileParser';

interface WorkerRequest {
  buffer: ArrayBuffer;
  fileName: string;
  options?: FileParseOptions;
}

interface WorkerResponse {
  success: boolean;
  result?: ParsedFileResult;
  error?: string;
}

self.onmessage = (event: MessageEvent<WorkerRequest>) => {
  try {
    const { buffer, fileName, options = {} } = event.data;
    const workbook = XLSX.read(buffer, { type: 'array', cellDates: true, dense: true });
    const headerRow = Math.max(1, Math.min(200, Math.floor(Number(options.headerRow) || 1)));
    const isCsv = /\.csv$/i.test(fileName);
    const sheetNames = isCsv ? [] : workbook.SheetNames;
    const selectedSheet = (
      options.sheetName && workbook.SheetNames.includes(options.sheetName)
        ? options.sheetName
        : workbook.SheetNames[0]
    ) || '';
    const worksheet = workbook.Sheets[selectedSheet];

    if (!worksheet) {
      throw new Error('Не удалось найти выбранный лист Excel.');
    }

    const rows: RawRow[] = XLSX.utils.sheet_to_json(worksheet, {
      defval: '',
      range: headerRow - 1,
    });
    const columns = rows.length > 0 ? Object.keys(rows[0]) : [];

    const response: WorkerResponse = {
      success: true,
      result: {
        fileName,
        rows,
        columns,
        sheetNames,
        selectedSheet,
        headerRow,
        previewRows: rows.slice(0, 5),
      },
    };
    self.postMessage(response);
  } catch (error) {
    const response: WorkerResponse = {
      success: false,
      error: error instanceof Error ? error.message : String(error),
    };
    self.postMessage(response);
  }
};
