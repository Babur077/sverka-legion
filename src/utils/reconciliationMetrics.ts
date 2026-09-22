export interface ReconciliationQuality {
  rrnMatched: number;
  exactMatched: number;
  amountMismatches: number;
  detectedAmountMismatches: number;
  unboundMismatches: number;
  onlyOur: number;
  onlyBank: number;
  unmatched: number;
  scope: number;
  issueCount: number;
  rrnMatchRate: number;
  exactMatchRate: number;
}

export interface ReconciliationQualityBasis {
  rrnFoundCount?: number;
  amountMismatchCountBeforeUnbind?: number;
  onlyOurCountBeforeUnbind?: number;
  onlyBankCountBeforeUnbind?: number;
  unboundMismatchCount?: number;
}

export function getReconciliationQuality(
  matchedCount: number,
  mismatchCount: number,
  onlyOurCount: number,
  onlyBankCount: number,
  basis?: ReconciliationQualityBasis,
): ReconciliationQuality {
  const activeMatched = Math.max(0, Number(matchedCount) || 0);
  const activeAmountMismatches = Math.max(
    0,
    Math.min(activeMatched, Number(mismatchCount) || 0),
  );
  const onlyOur = Math.max(0, Number(onlyOurCount) || 0);
  const onlyBank = Math.max(0, Number(onlyBankCount) || 0);
  const unmatched = onlyOur + onlyBank;

  const rrnMatched = Math.max(
    0,
    Number(basis?.rrnFoundCount ?? activeMatched) || 0,
  );
  const detectedAmountMismatches = Math.max(
    0,
    Math.min(
      rrnMatched,
      Number(
        basis?.amountMismatchCountBeforeUnbind
        ?? activeAmountMismatches,
      ) || 0,
    ),
  );
  const exactMatched = Math.max(0, rrnMatched - detectedAmountMismatches);

  const scopeOnlyOur = Math.max(
    0,
    Number(basis?.onlyOurCountBeforeUnbind ?? onlyOur) || 0,
  );
  const scopeOnlyBank = Math.max(
    0,
    Number(basis?.onlyBankCountBeforeUnbind ?? onlyBank) || 0,
  );
  const scope = rrnMatched + scopeOnlyOur + scopeOnlyBank;

  return {
    rrnMatched,
    exactMatched,
    amountMismatches: activeAmountMismatches,
    detectedAmountMismatches,
    unboundMismatches: Math.max(
      0,
      Number(basis?.unboundMismatchCount ?? 0) || 0,
    ),
    onlyOur,
    onlyBank,
    unmatched,
    scope,
    issueCount: activeAmountMismatches + unmatched,
    rrnMatchRate: scope ? (rrnMatched / scope) * 100 : 0,
    exactMatchRate: scope ? (exactMatched / scope) * 100 : 0,
  };
}
