import { RawRow, ReconciliationConfig, ReconciliationResult, DateSummaryRow, UnmatchedRow, AmountMismatchRow, EposTerminal, TerminalSummaryItem } from '../types';

export function cleanAmount(val: any): number {
  if (val === null || val === undefined || val === '') return 0.0;
  if (typeof val === 'number') return isNaN(val) ? 0.0 : val;
  
  let s = String(val).replace(/[^\d.,-]/g, '').trim();
  if (!s) return 0.0;

  const hasComma = s.includes(',');
  const hasDot = s.includes('.');

  if (hasComma && hasDot) {
    const lastComma = s.lastIndexOf(',');
    const lastDot = s.lastIndexOf('.');
    if (lastComma > lastDot) {
      // European format: "1.234,56" or "1.234.567,89" -> remove dots, replace comma with dot
      s = s.replace(/\./g, '').replace(',', '.');
    } else {
      // Standard/US format: "1,234.56" or "1,234,567.89" -> remove commas
      s = s.replace(/,/g, '');
    }
  } else if (hasComma && !hasDot) {
    // 1. Grouped by exactly 3 digits (thousands separator): "1,234" or "12,345,678" -> remove commas
    const isThousandsComma = /^-?\d{1,3}(,\d{3})+$/.test(s);
    // 2. Comma with 1 or 2 decimal digits: "1234,56" or "0,5" -> decimal point
    const isDecimalComma = /^-?\d+,\d{1,2}$/.test(s);
    // 3. Comma with 4+ digits: rare scientific/crypto decimal -> decimal point
    const isMicroDecimalComma = /^-?\d+,\d{4,}$/.test(s);

    if (isThousandsComma) {
      s = s.replace(/,/g, '');
    } else if (isDecimalComma || isMicroDecimalComma) {
      s = s.replace(',', '.');
    } else {
      // Multiple commas like "1,234,567" or general fallback
      const commaCount = (s.match(/,/g) || []).length;
      if (commaCount > 1) {
        s = s.replace(/,/g, '');
      } else {
        s = s.replace(',', '.');
      }
    }
  } else if (!hasComma && hasDot) {
    // Multiple dots used as thousands separators: "1.234.567"
    const dotCount = (s.match(/\./g) || []).length;
    if (dotCount > 1 && /^-?\d{1,3}(\.\d{3})+$/.test(s)) {
      s = s.replace(/\./g, '');
    }
  }

  const parsed = parseFloat(s);
  return isNaN(parsed) ? 0.0 : parsed;
}

export function cleanDate(val: any): { display: string; iso: string } {
  if (!val) return { display: '', iso: '' };

  if (val instanceof Date && !isNaN(val.getTime())) {
    const d = val;
    const day = String(d.getDate()).padStart(2, '0');
    const month = String(d.getMonth() + 1).padStart(2, '0');
    const year = d.getFullYear();
    return {
      display: `${day}.${month}.${year}`,
      iso: `${year}-${month}-${day}`
    };
  }

  const s = String(val).trim();
  
  // Try matching DD.MM.YYYY or DD/MM/YYYY or DD-MM-YYYY
  const dmyMatch = s.match(/^(\d{1,2})[./-](\d{1,2})[./-](\d{4})/);
  if (dmyMatch) {
    const day = dmyMatch[1].padStart(2, '0');
    const month = dmyMatch[2].padStart(2, '0');
    const year = dmyMatch[3];
    return { display: `${day}.${month}.${year}`, iso: `${year}-${month}-${day}` };
  }

  // Try matching YYYY-MM-DD or YYYY/MM/DD
  const ymdMatch = s.match(/^(\d{4})[./-](\d{1,2})[./-](\d{1,2})/);
  if (ymdMatch) {
    const year = ymdMatch[1];
    const month = ymdMatch[2].padStart(2, '0');
    const day = ymdMatch[3].padStart(2, '0');
    return { display: `${day}.${month}.${year}`, iso: `${year}-${month}-${day}` };
  }

  // Fallback Date parse
  const parsed = new Date(s);
  if (!isNaN(parsed.getTime())) {
    const day = String(parsed.getDate()).padStart(2, '0');
    const month = String(parsed.getMonth() + 1).padStart(2, '0');
    const year = parsed.getFullYear();
    return { display: `${day}.${month}.${year}`, iso: `${year}-${month}-${day}` };
  }

  return { display: s, iso: s };
}

export function cleanRrn(val: any, prefix: string, rowIndex: number): string {
  if (val === null || val === undefined) {
    return `_EMPTY_${prefix.toUpperCase()}_${rowIndex}`;
  }
  let s = String(val).trim().toUpperCase();
  s = s.replace(/\.0$/, ''); // strip Excel decimal suffix for integers
  if (['', 'NAN', 'NONE', 'NAT', 'NULL', 'UNDEFINED'].includes(s)) {
    return `_EMPTY_${prefix.toUpperCase()}_${rowIndex}`;
  }
  return s;
}

export function runReconciliation(
  rawOur: RawRow[],
  rawBank: RawRow[],
  cfg: ReconciliationConfig,
  eposList: EposTerminal[]
): ReconciliationResult {
  const eposInfoMap = new Map<string, EposTerminal>();
  eposList.forEach(t => {
    if (t.is_active) {
      eposInfoMap.set(String(t.terminal_id).trim().toUpperCase(), t);
    }
  });

  const revWords = cfg.rev_words.map(w => w.toLowerCase().trim()).filter(Boolean);

  // 1. Process OUR rows
  let ourRows = rawOur.map((row, idx) => {
    const dateRaw = row[cfg.our_date];
    const { display: dateStr, iso: dateIso } = cleanDate(dateRaw);
    const rrn = cleanRrn(row[cfg.our_rrn], 'our', idx);
    const amount = cfg.our_amt ? cleanAmount(row[cfg.our_amt]) : 0;
    const status = cfg.our_status ? String(row[cfg.our_status] || '').trim() : '';

    return {
      _idx: idx,
      date_str: dateStr,
      date_iso: dateIso,
      RRN: rrn,
      amount: amount,
      net_amount: amount,
      status: status,
      raw: row,
    };
  });

  // 2. Process BANK rows (сверка всегда по номинальным суммам, комиссия рассчитывается отдельно)
  let bankRows = rawBank.map((row, idx) => {
    const dateRaw = row[cfg.bank_date];
    const { display: dateStr, iso: dateIso } = cleanDate(dateRaw);
    const rrn = cleanRrn(row[cfg.bank_rrn], 'bank', idx);
    const amount = cfg.bank_amt ? cleanAmount(row[cfg.bank_amt]) : 0;
    const status = cfg.bank_status ? String(row[cfg.bank_status] || '').trim() : '';
    const tid = cfg.bank_tid ? String(row[cfg.bank_tid] || '').trim() : '';
    
    // Commission check from EPOS
    let commissionPct = 0;
    if (tid && eposInfoMap.has(tid.toUpperCase())) {
      commissionPct = Number(eposInfoMap.get(tid.toUpperCase())?.commission_pct) || 0;
    }

    return {
      _idx: idx,
      date_str: dateStr,
      date_iso: dateIso,
      RRN: rrn,
      raw_amount: amount,
      net_amount: amount, // Всегда номинал операции для сравнения с нашей суммой
      commission_pct: commissionPct,
      commission_amount: amount * (commissionPct / 100),
      terminal_id: tid,
      status: status,
      raw: row,
    };
  });

  // 3. Reversals
  const isReversal = (statusText: string) => {
    const s = statusText.toLowerCase();
    return revWords.some(w => s.includes(w));
  };

  const applyReversalsOur = (rows: typeof ourRows, action: string) => {
    if (!cfg.our_status) return rows;
    const act = (action || '').toLowerCase();
    if (act.includes('rrn') || act.includes('полностью') || act.includes('💥')) {
      const badRrns = new Set(rows.filter(r => isReversal(r.status)).map(r => r.RRN));
      return rows.filter(r => !badRrns.has(r.RRN));
    } else if (act.includes('удалить строку') || act.includes('строку') || act.includes('🗑')) {
      return rows.filter(r => !isReversal(r.status));
    } else if (act.includes('минусовать') || act.includes('минус') || act.includes('➖')) {
      return rows.map(r => ({
        ...r,
        amount: isReversal(r.status) ? -Math.abs(r.amount) : r.amount,
        net_amount: isReversal(r.status) ? -Math.abs(r.net_amount) : r.net_amount,
      }));
    }
    return rows;
  };

  const applyReversalsBank = (rows: typeof bankRows, action: string) => {
    if (!cfg.bank_status) return rows;
    const act = (action || '').toLowerCase();
    if (act.includes('rrn') || act.includes('полностью') || act.includes('💥')) {
      const badRrns = new Set(rows.filter(r => isReversal(r.status)).map(r => r.RRN));
      return rows.filter(r => !badRrns.has(r.RRN));
    } else if (act.includes('удалить строку') || act.includes('строку') || act.includes('🗑')) {
      return rows.filter(r => !isReversal(r.status));
    } else if (act.includes('минусовать') || act.includes('минус') || act.includes('➖')) {
      return rows.map(r => ({
        ...r,
        raw_amount: isReversal(r.status) ? -Math.abs(r.raw_amount) : r.raw_amount,
        net_amount: isReversal(r.status) ? -Math.abs(r.net_amount) : r.net_amount,
      }));
    }
    return rows;
  };

  ourRows = applyReversalsOur(ourRows, cfg.our_rev);
  bankRows = applyReversalsBank(bankRows, cfg.bank_rev);

  // 4. Duplicate handling
  const getDupMap = (rows: { RRN: string }[]) => {
    const counts = new Map<string, number>();
    rows.forEach(r => counts.set(r.RRN, (counts.get(r.RRN) || 0) + 1));
    return counts;
  };

  const ourDupCounts = getDupMap(ourRows);
  const bankDupCounts = getDupMap(bankRows);

  const dupsOur = ourRows.filter(r => (ourDupCounts.get(r.RRN) || 0) > 1);
  const dupsBank = bankRows.filter(r => (bankDupCounts.get(r.RRN) || 0) > 1);

  if (cfg.dup_action.includes('первую')) {
    const seenOur = new Set<string>();
    ourRows = ourRows.filter(r => {
      if (seenOur.has(r.RRN)) return false;
      seenOur.add(r.RRN);
      return true;
    });
    const seenBank = new Set<string>();
    bankRows = bankRows.filter(r => {
      if (seenBank.has(r.RRN)) return false;
      seenBank.add(r.RRN);
      return true;
    });
  } else if (cfg.dup_action.includes('последнюю')) {
    const seenOur = new Set<string>();
    ourRows = [...ourRows].reverse().filter(r => {
      if (seenOur.has(r.RRN)) return false;
      seenOur.add(r.RRN);
      return true;
    }).reverse();
    const seenBank = new Set<string>();
    bankRows = [...bankRows].reverse().filter(r => {
      if (seenBank.has(r.RRN)) return false;
      seenBank.add(r.RRN);
      return true;
    }).reverse();
  } else if (cfg.dup_action.includes('Удалить все')) {
    const badOur = new Set(dupsOur.map(d => d.RRN));
    const badBank = new Set(dupsBank.map(d => d.RRN));
    ourRows = ourRows.filter(r => !badOur.has(r.RRN));
    bankRows = bankRows.filter(r => !badBank.has(r.RRN));
  }

  // 5. Build lookup maps with duplicate occurrence indexing (matching Python cum_count().over("RRN"))
  const ourRrnCounts = new Map<string, number>();
  const ourRowsWithIdx = ourRows.map(r => {
    const idx = ourRrnCounts.get(r.RRN) || 0;
    ourRrnCounts.set(r.RRN, idx + 1);
    return { ...r, _dup_idx: idx };
  });

  const bankRrnCounts = new Map<string, number>();
  const bankRowsWithIdx = bankRows.map(r => {
    const idx = bankRrnCounts.get(r.RRN) || 0;
    bankRrnCounts.set(r.RRN, idx + 1);
    return { ...r, _dup_idx: idx };
  });

  const ourMap = new Map<string, typeof ourRowsWithIdx[0]>();
  ourRowsWithIdx.forEach(r => ourMap.set(`${r.RRN}___${r._dup_idx}`, r));

  const bankMap = new Map<string, typeof bankRowsWithIdx[0]>();
  bankRowsWithIdx.forEach(r => bankMap.set(`${r.RRN}___${r._dup_idx}`, r));

  const allKeys = Array.from(new Set([...ourMap.keys(), ...bankMap.keys()]));

  const onlyOur: UnmatchedRow[] = [];
  const onlyBank: UnmatchedRow[] = [];
  let amtMismatches: AmountMismatchRow[] = [];
  let matchedCount = 0;

  const mergedRows: ReconciliationResult['merged_rows'] = [];

  allKeys.forEach(key => {
    const o = ourMap.get(key);
    const b = bankMap.get(key);
    const rrn = o ? o.RRN : b!.RRN;

    if (o && b) {
      const delta = b.net_amount - o.net_amount;
      const isMismatch = Math.abs(delta) > cfg.tolerance;

      if (isMismatch) {
        if (cfg.unbind_mismatches) {
          // Unbind: Send o to only_our, b to only_bank
          onlyOur.push({
            checked: true,
            reason: '',
            date_str: o.date_str,
            RRN: rrn,
            amount: o.net_amount,
            status: o.status,
            raw: o.raw,
          });
          onlyBank.push({
            checked: true,
            reason: '',
            date_str: b.date_str,
            RRN: rrn,
            amount: b.net_amount,
            status: b.status,
            terminal_id: b.terminal_id,
            commission_pct: b.commission_pct,
            raw: b.raw,
          });
          mergedRows.push({
            date_str: o.date_str,
            RRN: rrn,
            type: 'left_only',
            net_amount_our: o.net_amount,
            status_our: o.status,
          });
          mergedRows.push({
            date_str: b.date_str,
            RRN: rrn,
            type: 'right_only',
            net_amount_bank: b.net_amount,
            status_bank: b.status,
          });
        } else {
          amtMismatches.push({
            RRN: rrn,
            date_our: o.date_str,
            date_bank: b.date_str,
            net_amount_our: o.net_amount,
            net_amount_bank: b.net_amount,
            'Δ сумма': delta,
            status_our: o.status,
            status_bank: b.status,
          });
          matchedCount++;
          mergedRows.push({
            date_str: o.date_str || b.date_str,
            RRN: rrn,
            type: 'both',
            net_amount_our: o.net_amount,
            net_amount_bank: b.net_amount,
            status_our: o.status,
            status_bank: b.status,
          });
        }
      } else {
        matchedCount++;
        mergedRows.push({
          date_str: o.date_str || b.date_str,
          RRN: rrn,
          type: 'both',
          net_amount_our: o.net_amount,
          net_amount_bank: b.net_amount,
          status_our: o.status,
          status_bank: b.status,
        });
      }
    } else if (o) {
      onlyOur.push({
        checked: true,
        reason: '',
        date_str: o.date_str,
        RRN: rrn,
        amount: o.net_amount,
        status: o.status,
        raw: o.raw,
      });
      mergedRows.push({
        date_str: o.date_str,
        RRN: rrn,
        type: 'left_only',
        net_amount_our: o.net_amount,
        status_our: o.status,
      });
    } else if (b) {
      onlyBank.push({
        checked: true,
        reason: '',
        date_str: b.date_str,
        RRN: rrn,
        amount: b.net_amount,
        status: b.status,
        terminal_id: b.terminal_id,
        commission_pct: b.commission_pct,
        raw: b.raw,
      });
      mergedRows.push({
        date_str: b.date_str,
        RRN: rrn,
        type: 'right_only',
        net_amount_bank: b.net_amount,
        status_bank: b.status,
      });
    }
  });

  // 6. Date Summary
  const dateMap = new Map<string, {
    date: string;
    our_count: number;
    our_sum: number;
    bank_count: number;
    bank_sum: number;
  }>();

  ourRows.forEach(r => {
    const d = r.date_str || 'Не указана';
    const entry = dateMap.get(d) || { date: d, our_count: 0, our_sum: 0, bank_count: 0, bank_sum: 0 };
    entry.our_count += 1;
    entry.our_sum += r.net_amount;
    dateMap.set(d, entry);
  });

  bankRows.forEach(r => {
    const d = r.date_str || 'Не указана';
    const entry = dateMap.get(d) || { date: d, our_count: 0, our_sum: 0, bank_count: 0, bank_sum: 0 };
    entry.bank_count += 1;
    entry.bank_sum += r.net_amount;
    dateMap.set(d, entry);
  });

  const summaryList: DateSummaryRow[] = Array.from(dateMap.values())
    .sort((a, b) => b.date.localeCompare(a.date))
    .map(entry => ({
      date: entry.date,
      Кол_во_у_нас: entry.our_count,
      Кол_во_в_банке: entry.bank_count,
      'Δ кол-во': entry.bank_count - entry.our_count,
      Сумма_у_нас: entry.our_sum,
      Сумма_в_банке: entry.bank_sum,
      'Δ суммы': entry.bank_sum - entry.our_sum,
    }));

  const totOurSum = summaryList.reduce((acc, row) => acc + row.Сумма_у_нас, 0);
  const totBankSum = summaryList.reduce((acc, row) => acc + row.Сумма_в_банке, 0);
  const totOurCount = summaryList.reduce((acc, row) => acc + row.Кол_во_у_нас, 0);
  const totBankCount = summaryList.reduce((acc, row) => acc + row.Кол_во_в_банке, 0);

  summaryList.push({
    date: '📊 ИТОГО (исходно)',
    Кол_во_у_нас: totOurCount,
    Кол_во_в_банке: totBankCount,
    'Δ кол-во': totBankCount - totOurCount,
    Сумма_у_нас: totOurSum,
    Сумма_в_банке: totBankSum,
    'Δ суммы': totBankSum - totOurSum,
  });

  // 7. Terminal Summary & Analytical Commission Calculation
  const termMap = new Map<string, {
    terminal_id: string;
    merchant_id?: string;
    bank_acquirer?: string;
    legal_entity?: string;
    tx_count: number;
    total_volume: number;
    commission_pct: number;
    commission_amount: number;
  }>();

  bankRows.forEach(b => {
    const tid = b.terminal_id ? b.terminal_id.trim() : '';
    const termKey = tid || '(Без TID)';
    const termInfo = tid ? eposInfoMap.get(tid.toUpperCase()) : undefined;
    const commPct = termInfo?.commission_pct ?? b.commission_pct ?? 0;
    const commAmt = b.raw_amount * (commPct / 100);

    const existing = termMap.get(termKey) || {
      terminal_id: termKey,
      merchant_id: termInfo?.merchant_id || '—',
      bank_acquirer: termInfo?.bank_acquirer || (tid ? 'EPOS' : '—'),
      legal_entity: termInfo?.legal_entity || '—',
      tx_count: 0,
      total_volume: 0,
      commission_pct: commPct,
      commission_amount: 0,
    };

    existing.tx_count += 1;
    existing.total_volume += b.raw_amount;
    existing.commission_amount += commAmt;
    termMap.set(termKey, existing);
  });

  const terminalSummary: TerminalSummaryItem[] = Array.from(termMap.values())
    .map(t => ({
      ...t,
      net_volume: t.total_volume - t.commission_amount,
    }))
    .sort((a, b) => b.total_volume - a.total_volume);

  const totalCommission = terminalSummary.reduce((acc, t) => acc + t.commission_amount, 0);
  const totalBankVolume = terminalSummary.reduce((acc, t) => acc + t.total_volume, 0);
  const effectiveCommissionRate = totalBankVolume > 0 ? (totalCommission / totalBankVolume) * 100 : 0;

  // Извлечение уникальных месяцев (формат YYYY-MM)
  const monthSet = new Set<string>();
  const addMonthFromIsoOrStr = (iso?: string, str?: string) => {
    if (iso && /^\d{4}-\d{2}/.test(iso)) {
      monthSet.add(iso.slice(0, 7));
    } else if (str) {
      // Поддержка формата DD.MM.YYYY
      const parts = str.split('.');
      if (parts.length === 3 && parts[2].length === 4) {
        monthSet.add(`${parts[2]}-${parts[1]}`);
      }
    }
  };

  ourRows.forEach(r => addMonthFromIsoOrStr(r.date_iso, r.date_str));
  bankRows.forEach(r => addMonthFromIsoOrStr(r.date_iso, r.date_str));
  if (monthSet.size === 0) {
    monthSet.add(new Date().toISOString().slice(0, 7));
  }
  const detectedMonths = Array.from(monthSet).sort().reverse();

  return {
    summary: summaryList,
    only_our: onlyOur,
    only_bank: onlyBank,
    amt_mismatches: amtMismatches,
    dups_our: dupsOur.map(d => d.raw),
    dups_bank: dupsBank.map(d => d.raw),
    dup_our_c: dupsOur.length,
    dup_bank_c: dupsBank.length,
    matched_count: matchedCount,
    mismatch_count: amtMismatches.length,
    terminal_summary: terminalSummary,
    total_commission: totalCommission,
    effective_commission_rate: effectiveCommissionRate,
    detected_months: detectedMonths,
    merged_rows: mergedRows,
    dup_action: cfg.dup_action,
  };
}
