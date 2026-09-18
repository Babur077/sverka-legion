export interface ReconciliationQuality {
  rrnMatched: number;
  exactMatched: number;
  amountMismatches: number;
  onlyOur: number;
  onlyBank: number;
  unmatched: number;
  scope: number;
  issueCount: number;
  rrnMatchRate: number;
  exactMatchRate: number;
}

export function getReconciliationQuality(
  matchedCount: number,
  mismatchCount: number,
  onlyOurCount: number,
  onlyBankCount: number,
): ReconciliationQuality {
  const rrnMatched = Math.max(0, Number(matchedCount) || 0);
  const amountMismatches = Math.max(0, Math.min(rrnMatched, Number(mismatchCount) || 0));
  const onlyOur = Math.max(0, Number(onlyOurCount) || 0);
  const onlyBank = Math.max(0, Number(onlyBankCount) || 0);
  const unmatched = onlyOur + onlyBank;
  const exactMatched = Math.max(0, rrnMatched - amountMismatches);
  // Amount mismatches are already a subset of RRN-matched rows, so they must
  // never be added to the denominator a second time.
  const scope = rrnMatched + unmatched;

  return {
    rrnMatched,
    exactMatched,
    amountMismatches,
    onlyOur,
    onlyBank,
    unmatched,
    scope,
    issueCount: amountMismatches + unmatched,
    rrnMatchRate: scope ? (rrnMatched / scope) * 100 : 0,
    exactMatchRate: scope ? (exactMatched / scope) * 100 : 0,
  };
}
