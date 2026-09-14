import { runReconciliation } from './reconEngine';
import { RawRow, ReconciliationConfig, EposTerminal } from '../types';

self.onmessage = (e: MessageEvent<{ ourRows: RawRow[]; bankRows: RawRow[]; cfg: ReconciliationConfig; eposList: EposTerminal[] }>) => {
  const { ourRows, bankRows, cfg, eposList } = e.data;
  try {
    const result = runReconciliation(ourRows, bankRows, cfg, eposList);
    self.postMessage({ success: true, result });
  } catch (error: any) {
    self.postMessage({ success: false, error: error?.message || String(error) });
  }
};
