import * as XLSX from 'xlsx';

type ParseMessage = {
  buffer: ArrayBuffer;
  fileName: string;
};

type ParsedFile = {
  fileName: string;
  rows: Record<string, any>[];
  columns: string[];
};

self.onmessage = (event: MessageEvent<ParseMessage>) => {
  try {
    const { buffer, fileName } = event.data;
    const workbook = XLSX.read(buffer, { type: 'array', cellDates: true });
    const firstSheetName = workbook.SheetNames[0];
    const worksheet = workbook.Sheets[firstSheetName];
    const rows: Record<string, any>[] = XLSX.utils.sheet_to_json(worksheet, { defval: '' });
    const columns = rows.length > 0 ? Object.keys(rows[0]) : [];

    const result: ParsedFile = { fileName, rows, columns };
    self.postMessage({ success: true, result });
  } catch (error: any) {
    self.postMessage({
      success: false,
      error: error?.message || String(error),
    });
  }
};
