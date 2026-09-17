import * as XLSX from 'xlsx';
import { RawRow } from '../types';

interface WorkerRequest {
  buffer: ArrayBuffer;
  fileName: string;
}

interface WorkerResponse {
  success: boolean;
  result?: {
    fileName: string;
    rows: RawRow[];
    columns: string[];
  };
  error?: string;
}

self.onmessage = (event: MessageEvent<WorkerRequest>) => {
  try {
    const { buffer, fileName } = event.data;
    const workbook = XLSX.read(buffer, { type: 'array', cellDates: true, dense: true });
    const firstSheetName = workbook.SheetNames[0];
    const worksheet = workbook.Sheets[firstSheetName];
    const rows: RawRow[] = XLSX.utils.sheet_to_json(worksheet, { defval: '' });
    const columns = rows.length > 0 ? Object.keys(rows[0]) : [];

    const response: WorkerResponse = {
      success: true,
      result: { fileName, rows, columns },
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
