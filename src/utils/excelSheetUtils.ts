import type * as XLSX from 'xlsx';

export interface ResolvedWorkbookSheet {
  selectedSheet: string;
  worksheet: XLSX.WorkSheet;
  readableSheetNames: string[];
}

function normalizeSheetName(value: string): string {
  return String(value || '')
    .replace(/\u00a0/g, ' ')
    .trim()
    .toLocaleLowerCase();
}

export function resolveReadableWorkbookSheet(
  workbook: XLSX.WorkBook,
  requestedSheet?: string,
): ResolvedWorkbookSheet {
  const sheets = workbook.Sheets || {};
  const declaredNames = Array.isArray(workbook.SheetNames)
    ? workbook.SheetNames
    : [];

  const readableSheetNames: string[] = [];
  const seen = new Set<string>();

  const addIfReadable = (name: string) => {
    if (!name || seen.has(name) || !sheets[name]) return;
    seen.add(name);
    readableSheetNames.push(name);
  };

  // Preserve the workbook's declared order, but skip service/chart entries
  // that do not resolve to an actual worksheet object.
  declaredNames.forEach(addIfReadable);

  // Some exports expose a readable sheet in Sheets but omit/inconsistently
  // populate SheetNames. Keep those usable as a fallback too.
  Object.keys(sheets).forEach(addIfReadable);

  if (!readableSheetNames.length) {
    const declared = declaredNames.length
      ? ` Объявленные листы: ${declaredNames.join(', ')}.`
      : '';
    throw new Error(
      `В книге Excel не найдено ни одного читаемого листа.${declared}`,
    );
  }

  let selectedSheet = '';
  if (requestedSheet) {
    if (readableSheetNames.includes(requestedSheet)) {
      selectedSheet = requestedSheet;
    } else {
      const normalizedRequested = normalizeSheetName(requestedSheet);
      selectedSheet = readableSheetNames.find(
        name => normalizeSheetName(name) === normalizedRequested,
      ) || '';
    }
  }

  if (!selectedSheet) {
    selectedSheet = readableSheetNames[0];
  }

  const worksheet = sheets[selectedSheet];
  if (!worksheet) {
    // Defensive guard: this should be impossible after filtering above.
    throw new Error(
      `Не удалось открыть лист Excel «${selectedSheet}». Доступные листы: ${readableSheetNames.join(', ')}.`,
    );
  }

  return {
    selectedSheet,
    worksheet,
    readableSheetNames,
  };
}
