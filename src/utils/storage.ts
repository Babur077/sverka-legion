const DRAFT_KEY = 'reconcile_active_draft_v2';
const LEGACY_DRAFT_KEY = 'reconcile_active_draft_v1';

export function saveActiveDraft(draft: any): void {
  try {
    const fileMeta = {
      our: draft?.ourFile
        ? {
            name: draft.ourFile.name,
            columns: draft.ourFile.columns || [],
            rowCount: Array.isArray(draft.ourFile.rows) ? draft.ourFile.rows.length : (draft.ourFile.rowCount || 0),
          }
        : null,
      bank: draft?.bankFile
        ? {
            name: draft.bankFile.name,
            columns: draft.bankFile.columns || [],
            rowCount: Array.isArray(draft.bankFile.rows) ? draft.bankFile.rows.length : (draft.bankFile.rowCount || 0),
          }
        : null,
    };

    localStorage.setItem(
      DRAFT_KEY,
      JSON.stringify({ ...draft, version: 2, ourFile: null, bankFile: null, fileMeta }),
    );
  } catch (error) {
    console.warn('Failed to save draft to localStorage:', error);
  }
}

export function getStoredDraft(): any | null {
  try {
    const raw = localStorage.getItem(DRAFT_KEY);
    localStorage.removeItem(LEGACY_DRAFT_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export function clearActiveDraft(): void {
  try {
    localStorage.removeItem(DRAFT_KEY);
    localStorage.removeItem(LEGACY_DRAFT_KEY);
  } catch {}
}
