import React, { useMemo, useState } from 'react';
import {
  BarChart3,
  TrendingUp,
  Coins,
  CheckCircle2,
  Building2,
  Terminal,
  WalletCards,
  ReceiptText,
  ArrowUpRight,
  ArrowDownRight,
} from 'lucide-react';
import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { ReconciliationArchive, TerminalSummaryItem, User } from '../types';
import { getBankRrnArchive } from '../utils/archiveApi';
import { getReconciliationQuality } from '../utils/reconciliationMetrics';

interface Props {
  user: User;
}

const money = (n: number) => n.toLocaleString('ru-RU', { maximumFractionDigits: 0 });
const pct = (n: number) => `${n.toFixed(2)}%`;

type TerminalAnalyticsRow = TerminalSummaryItem & { bank: string; runs: number };

type TerminalPeriodAnalyticsRow = TerminalSummaryItem & {
  bank: string;
  period: string;
  periodLabel: string;
  runs: number;
};

interface BankHistoryRow {
  period: string;
  label: string;
  volume: number;
  net: number;
  commission: number;
  tx: number;
  terminals: number;
  effectiveCommission: number;
  growth: number | null;
}

interface TerminalHistoryRow {
  period: string;
  label: string;
  volume: number;
  net: number;
  commission: number;
  tx: number;
  avgTicket: number;
  effectiveCommission: number;
  bankVolume: number;
  shareOfBank: number;
  runs: number;
}

function periodOf(record: ReconciliationArchive): string {
  return record.period_month || record.timestamp.slice(0, 7);
}

function formatPeriodLabel(period: string): string {
  const [year, month] = period.split('-').map(Number);
  if (!year || !month) return period;
  return new Date(year, month - 1, 1).toLocaleDateString('ru-RU', {
    month: 'short',
    year: '2-digit',
  });
}

function terminalSnapshotsForRecord(record: ReconciliationArchive): TerminalSummaryItem[] {
  const assignedTerminalId = String(record.assigned_terminal_id || '').trim();

  if (assignedTerminalId) {
    const matching = (record.terminals_summary || []).find(
      item => String(item.terminal_id || '').trim() === assignedTerminalId,
    );

    if (matching) {
      return [{
        ...matching,
        terminal_id: assignedTerminalId,
        bank_acquirer: matching.bank_acquirer || record.bank_name,
      }];
    }

    const volume = Number(record.total_bank || 0);
    const commission = Number(record.total_commission || 0);
    const txCount = Math.max(
      0,
      Number(record.matched_count || 0) + Number(record.only_bank_count || 0),
    );

    return [{
      terminal_id: assignedTerminalId,
      bank_acquirer: record.bank_name,
      tx_count: txCount,
      total_volume: volume,
      commission_pct: volume ? commission / volume * 100 : 0,
      commission_amount: commission,
      net_volume: volume - commission,
    }];
  }

  return (record.terminals_summary || []).map(item => ({
    ...item,
    terminal_id: String(item.terminal_id || '(Без TID)'),
    bank_acquirer: item.bank_acquirer || record.bank_name,
  }));
}

function latestTerminalSnapshots(
  records: ReconciliationArchive[],
): Array<{ record: ReconciliationArchive; terminal: TerminalSummaryItem }> {
  const latest = new Map<string, { record: ReconciliationArchive; terminal: TerminalSummaryItem }>();

  records.forEach(record => {
    terminalSnapshotsForRecord(record).forEach(terminal => {
      const terminalId = String(terminal.terminal_id || '(Без TID)').trim();
      const key = `${periodOf(record)}::${record.bank_name}::${terminalId}`;
      const current = latest.get(key);

      if (!current || new Date(record.timestamp).getTime() > new Date(current.record.timestamp).getTime()) {
        latest.set(key, { record, terminal: { ...terminal, terminal_id: terminalId } });
      }
    });
  });

  return Array.from(latest.values());
}

function aggregateTerminals(records: ReconciliationArchive[]): TerminalAnalyticsRow[] {
  const map = new Map<string, TerminalAnalyticsRow>();

  latestTerminalSnapshots(records).forEach(({ record, terminal: item }) => {
    const tid = String(item.terminal_id || '(Без TID)');
    const current = map.get(tid);

    if (!current) {
      map.set(tid, {
        ...item,
        terminal_id: tid,
        bank: item.bank_acquirer || record.bank_name,
        merchant_id: item.merchant_id,
        tx_count: item.tx_count || 0,
        total_volume: item.total_volume || 0,
        commission_pct: item.commission_pct || 0,
        commission_amount: item.commission_amount || 0,
        net_volume: item.net_volume || 0,
        runs: 1,
      });
      return;
    }

    current.tx_count += item.tx_count || 0;
    current.total_volume += item.total_volume || 0;
    current.commission_amount += item.commission_amount || 0;
    current.net_volume += item.net_volume || 0;
    current.commission_pct = current.total_volume
      ? current.commission_amount / current.total_volume * 100
      : current.commission_pct;
    current.runs += 1;

    if (!current.merchant_id && item.merchant_id) current.merchant_id = item.merchant_id;
  });

  return Array.from(map.values()).sort((a, b) => b.total_volume - a.total_volume);
}

function latestSnapshotsForTerminal(
  records: ReconciliationArchive[],
  terminalId: string,
): Array<{ record: ReconciliationArchive; terminal: TerminalSummaryItem }> {
  return latestTerminalSnapshots(records).filter(
    ({ terminal }) => String(terminal.terminal_id || '').trim() === terminalId,
  );
}

export const BankRrnAnalytics: React.FC<Props> = ({ user }) => {
  const [archive, setArchive] = useState<ReconciliationArchive[]>([]);

  React.useEffect(() => {
    getBankRrnArchive(user.username).then(setArchive).catch(error => console.error(error));
  }, [user.username]);

  const [bank, setBank] = useState('(Все)');
  const [month, setMonth] = useState('(Все)');
  const [terminal, setTerminal] = useState('(Все)');

  const banks = useMemo(
    () => Array.from(new Set(archive.map(a => a.bank_name))).sort(),
    [archive],
  );

  const months = useMemo(
    () => Array.from(new Set(archive.map(periodOf))).sort().reverse(),
    [archive],
  );

  const bankFiltered = useMemo(
    () => archive.filter(a => bank === '(Все)' || a.bank_name === bank),
    [archive, bank],
  );

  const filtered = useMemo(
    () => bankFiltered.filter(a => month === '(Все)' || periodOf(a) === month),
    [bankFiltered, month],
  );

  const bankHistory = useMemo<BankHistoryRow[]>(() => {
    const byPeriod = new Map<string, {
      volume: number;
      net: number;
      commission: number;
      tx: number;
      terminals: Set<string>;
    }>();

    latestTerminalSnapshots(bankFiltered).forEach(({ record, terminal: item }) => {
      const period = periodOf(record);
      const current = byPeriod.get(period) || {
        volume: 0,
        net: 0,
        commission: 0,
        tx: 0,
        terminals: new Set<string>(),
      };

      current.volume += Number(item.total_volume || 0);
      current.net += Number(item.net_volume || 0);
      current.commission += Number(item.commission_amount || 0);
      current.tx += Number(item.tx_count || 0);
      current.terminals.add(String(item.terminal_id || '(Без TID)'));
      byPeriod.set(period, current);
    });

    const rows = Array.from(byPeriod.entries())
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([period, values]) => ({
        period,
        label: formatPeriodLabel(period),
        volume: values.volume,
        net: values.net,
        commission: values.commission,
        tx: values.tx,
        terminals: values.terminals.size,
        effectiveCommission: values.volume ? values.commission / values.volume * 100 : 0,
        growth: null as number | null,
      }));

    return rows.map((row, index) => {
      const previous = index > 0 ? rows[index - 1] : null;
      return {
        ...row,
        growth: previous && previous.volume
          ? (row.volume - previous.volume) / previous.volume * 100
          : null,
      };
    });
  }, [bankFiltered]);

  const terminalPeriodRows = useMemo<TerminalPeriodAnalyticsRow[]>(() => {
    return latestTerminalSnapshots(filtered)
      .map(({ record, terminal: item }) => ({
        ...item,
        bank: item.bank_acquirer || record.bank_name,
        period: periodOf(record),
        periodLabel: formatPeriodLabel(periodOf(record)),
        runs: 1,
      }))
      .sort((a, b) => {
        const byPeriod = b.period.localeCompare(a.period);
        if (byPeriod !== 0) return byPeriod;
        return b.total_volume - a.total_volume;
      });
  }, [filtered]);

  const terminalCatalogRows = useMemo(
    () => aggregateTerminals(bankFiltered),
    [bankFiltered],
  );

  const terminalRows = useMemo(
    () => aggregateTerminals(filtered),
    [filtered],
  );

  const visibleTerminalRows = useMemo(() => {
    if (terminal === '(Все)') return terminalPeriodRows;
    return terminalPeriodRows.filter(t => t.terminal_id === terminal);
  }, [terminalPeriodRows, terminal]);

  const totals = useMemo(() => filtered.reduce((sum, record) => {
    const quality = getReconciliationQuality(
      record.matched_count,
      record.mismatch_count,
      record.only_our_count,
      record.only_bank_count,
    );

    return {
      our: sum.our + record.total_our,
      bank: sum.bank + record.total_bank,
      diff: sum.diff + record.difference,
      comm: sum.comm + (record.total_commission || 0),
      exactMatched: sum.exactMatched + quality.exactMatched,
      rrnMatched: sum.rrnMatched + quality.rrnMatched,
      total: sum.total + quality.scope,
      issues: sum.issues + quality.issueCount,
    };
  }, {
    our: 0,
    bank: 0,
    diff: 0,
    comm: 0,
    exactMatched: 0,
    rrnMatched: 0,
    total: 0,
    issues: 0,
  }), [filtered]);

  const selectedTerminal = terminal === '(Все)'
    ? null
    : terminalRows.find(t => t.terminal_id === terminal)
      || terminalCatalogRows.find(t => t.terminal_id === terminal)
      || null;

  const terminalHistory = useMemo<TerminalHistoryRow[]>(() => {
    if (terminal === '(Все)') return [];

    const latestSnapshots = latestSnapshotsForTerminal(bankFiltered, terminal);
    const byPeriod = new Map<string, {
      volume: number;
      net: number;
      commission: number;
      tx: number;
      bankVolume: number;
      runs: number;
    }>();

    latestSnapshots.forEach(({ record, terminal: terminalItem }) => {
      const period = periodOf(record);
      const current = byPeriod.get(period) || {
        volume: 0,
        net: 0,
        commission: 0,
        tx: 0,
        bankVolume: 0,
        runs: 0,
      };

      current.volume += terminalItem.total_volume || 0;
      current.net += terminalItem.net_volume || 0;
      current.commission += terminalItem.commission_amount || 0;
      current.tx += terminalItem.tx_count || 0;
      current.bankVolume += record.total_bank || 0;
      current.runs += 1;
      byPeriod.set(period, current);
    });

    return Array.from(byPeriod.entries())
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([period, values]) => ({
        period,
        label: formatPeriodLabel(period),
        volume: values.volume,
        net: values.net,
        commission: values.commission,
        tx: values.tx,
        avgTicket: values.tx ? values.volume / values.tx : 0,
        effectiveCommission: values.volume ? values.commission / values.volume * 100 : 0,
        bankVolume: bankHistory.find(row => row.period === period)?.volume || values.bankVolume,
        shareOfBank: (bankHistory.find(row => row.period === period)?.volume || values.bankVolume)
          ? values.volume / (bankHistory.find(row => row.period === period)?.volume || values.bankVolume) * 100
          : 0,
        runs: values.runs,
      }));
  }, [bankFiltered, terminal, bankHistory]);

  const terminalFinancials = useMemo(() => {
    if (terminalHistory.length === 0) {
      return {
        volume: 0,
        net: 0,
        commission: 0,
        tx: 0,
        avgTicket: 0,
        effectiveCommission: 0,
        latestShare: 0,
        growth: null as number | null,
      };
    }

    const volume = terminalHistory.reduce((sum, row) => sum + row.volume, 0);
    const net = terminalHistory.reduce((sum, row) => sum + row.net, 0);
    const commission = terminalHistory.reduce((sum, row) => sum + row.commission, 0);
    const tx = terminalHistory.reduce((sum, row) => sum + row.tx, 0);
    const latest = terminalHistory[terminalHistory.length - 1];
    const previous = terminalHistory.length > 1
      ? terminalHistory[terminalHistory.length - 2]
      : null;

    return {
      volume,
      net,
      commission,
      tx,
      avgTicket: tx ? volume / tx : 0,
      effectiveCommission: volume ? commission / volume * 100 : 0,
      latestShare: latest.shareOfBank,
      growth: previous && previous.volume
        ? (latest.volume - previous.volume) / previous.volume * 100
        : null,
    };
  }, [terminalHistory]);

  const bankTrendSummary = useMemo(() => {
    if (bankHistory.length === 0) {
      return {
        latestVolume: 0,
        latestGrowth: null as number | null,
        latestTerminals: 0,
        latestCommissionRate: 0,
      };
    }
    const latest = bankHistory[bankHistory.length - 1];
    return {
      latestVolume: latest.volume,
      latestGrowth: latest.growth,
      latestTerminals: latest.terminals,
      latestCommissionRate: latest.effectiveCommission,
    };
  }, [bankHistory]);

  const matchRate = totals.total ? totals.exactMatched / totals.total * 100 : 0;
  const effectiveCommission = totals.bank ? totals.comm / totals.bank * 100 : 0;

  return (
    <div className="space-y-5">
      <div className="flex flex-col xl:flex-row xl:items-center xl:justify-between gap-4">
        <div>
          <h3 className="text-xl font-bold text-slate-900 flex items-center gap-2">
            <BarChart3 className="w-5 h-5 text-indigo-600" />
            Аналитика Bank RRN
          </h3>
          <p className="text-sm text-slate-500 mt-1">
            Оборот, качество сопоставления, комиссии и финансовая динамика каждого терминала.
          </p>
        </div>

        <div className="flex flex-wrap gap-2">
          <select
            value={bank}
            onChange={e => {
              setBank(e.target.value);
              setTerminal('(Все)');
            }}
            className="px-3 py-2.5 rounded-lg border border-slate-200 bg-white text-sm"
          >
            <option>(Все)</option>
            {banks.map(value => <option key={value}>{value}</option>)}
          </select>

          <select
            value={month}
            onChange={e => setMonth(e.target.value)}
            className="px-3 py-2.5 rounded-lg border border-slate-200 bg-white text-sm"
          >
            <option>(Все)</option>
            {months.map(value => <option key={value}>{value}</option>)}
          </select>

          <select
            value={terminal}
            onChange={e => setTerminal(e.target.value)}
            className="px-3 py-2.5 rounded-lg border border-slate-200 bg-white text-sm min-w-48"
          >
            <option>(Все)</option>
            {terminalCatalogRows.map(item => (
              <option key={item.terminal_id} value={item.terminal_id}>
                {item.terminal_id}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-5 gap-4">
        {[
          {
            label: 'Точное совпадение',
            value: `${matchRate.toFixed(1)}%`,
            icon: CheckCircle2,
            style: 'text-emerald-600 bg-emerald-50',
          },
          {
            label: 'Оборот банка',
            value: money(totals.bank),
            icon: TrendingUp,
            style: 'text-indigo-600 bg-indigo-50',
          },
          {
            label: 'Общая комиссия',
            value: money(totals.comm),
            icon: Coins,
            style: 'text-violet-600 bg-violet-50',
          },
          {
            label: 'Ставка факт.',
            value: pct(effectiveCommission),
            icon: WalletCards,
            style: 'text-sky-600 bg-sky-50',
          },
          {
            label: 'Терминалов',
            value: String(terminalRows.length),
            icon: Terminal,
            style: 'text-amber-600 bg-amber-50',
          },
        ].map(item => {
          const Icon = item.icon;
          return (
            <div key={item.label} className="bg-white border border-slate-200 rounded-xl p-4 shadow-xs">
              <div className="flex justify-between">
                <div>
                  <div className="text-xs text-slate-500">{item.label}</div>
                  <div className="text-xl font-bold mt-1 text-slate-900">{item.value}</div>
                </div>
                <div className={`w-9 h-9 rounded-lg flex items-center justify-center ${item.style}`}>
                  <Icon className="w-4 h-4" />
                </div>
              </div>
            </div>
          );
        })}
      </div>

      <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-xs">
        <div className="flex flex-col xl:flex-row xl:items-start xl:justify-between gap-4 mb-5">
          <div>
            <div className="text-xs font-semibold text-indigo-600 uppercase tracking-wider">
              Динамика банка
            </div>
            <h4 className="text-lg font-bold text-slate-900 mt-1">
              Оборот всех терминалов · {bank === '(Все)' ? 'Все банки' : bank}
            </h4>
            <p className="text-xs text-slate-500 mt-1">
              За каждый месяц берётся последний сохранённый результат каждого TID.
              Столбцы показывают общий оборот, линия — рост или снижение к предыдущему месяцу.
            </p>
          </div>

          <div className="grid grid-cols-2 lg:grid-cols-4 gap-2 min-w-0">
            <div className="rounded-xl bg-slate-50 border border-slate-100 px-3 py-2">
              <div className="text-[11px] text-slate-500">Последний оборот</div>
              <div className="font-bold text-slate-900 mt-1">{money(bankTrendSummary.latestVolume)}</div>
            </div>
            <div className="rounded-xl bg-slate-50 border border-slate-100 px-3 py-2">
              <div className="text-[11px] text-slate-500">Рост м/м</div>
              <div className={`font-bold mt-1 ${
                bankTrendSummary.latestGrowth === null
                  ? 'text-slate-500'
                  : bankTrendSummary.latestGrowth >= 0
                    ? 'text-emerald-600'
                    : 'text-rose-600'
              }`}>
                {bankTrendSummary.latestGrowth === null
                  ? '—'
                  : `${bankTrendSummary.latestGrowth >= 0 ? '+' : ''}${bankTrendSummary.latestGrowth.toFixed(2)}%`}
              </div>
            </div>
            <div className="rounded-xl bg-slate-50 border border-slate-100 px-3 py-2">
              <div className="text-[11px] text-slate-500">Терминалов</div>
              <div className="font-bold text-slate-900 mt-1">{bankTrendSummary.latestTerminals}</div>
            </div>
            <div className="rounded-xl bg-slate-50 border border-slate-100 px-3 py-2">
              <div className="text-[11px] text-slate-500">Эфф. комиссия</div>
              <div className="font-bold text-slate-900 mt-1">{pct(bankTrendSummary.latestCommissionRate)}</div>
            </div>
          </div>
        </div>

        {bankHistory.length > 0 ? (
          <div className="h-96">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={bankHistory}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="label" tick={{ fontSize: 11 }} />
                <YAxis
                  yAxisId="money"
                  tick={{ fontSize: 11 }}
                  tickFormatter={(value: number) => money(value)}
                  width={86}
                />
                <YAxis
                  yAxisId="growth"
                  orientation="right"
                  tick={{ fontSize: 11 }}
                  tickFormatter={(value: number) => `${value.toFixed(1)}%`}
                  width={58}
                />
                <Tooltip
                  formatter={(value: any, name: any) => {
                    if (name === 'growth') {
                      const numeric = Number(value || 0);
                      return [`${numeric >= 0 ? '+' : ''}${numeric.toFixed(2)}%`, 'Рост м/м'];
                    }
                    return [money(Number(value || 0)), 'Оборот'];
                  }}
                  labelFormatter={(label: any) => `Период: ${label}`}
                />
                <Legend
                  formatter={(value: string) => value === 'volume' ? 'Оборот всех терминалов' : 'Рост м/м'}
                />
                <Bar yAxisId="money" dataKey="volume" radius={[5, 5, 0, 0]} />
                <Line
                  yAxisId="growth"
                  type="monotone"
                  dataKey="growth"
                  strokeWidth={2.5}
                  dot={{ r: 3 }}
                  connectNulls={false}
                />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <div className="h-56 flex items-center justify-center text-sm text-slate-500">
            Пока нет сохранённых периодов для построения динамики банка.
          </div>
        )}
      </div>

      {selectedTerminal && (
        <div className="bg-slate-900 text-white rounded-xl p-5 shadow-xs">
          <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
            <div>
              <div className="text-xs font-semibold text-indigo-200 uppercase tracking-wider">
                Детализация терминала
              </div>
              <div className="text-2xl font-bold mt-1 font-mono">{selectedTerminal.terminal_id}</div>
              <div className="text-sm text-slate-300 mt-1">
                {selectedTerminal.merchant_id ? `MID: ${selectedTerminal.merchant_id}` : 'MID не указан'} · периодов: {terminalHistory.length}
              </div>
            </div>

            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 min-w-0">
              <div className="bg-white/5 rounded-xl p-3">
                <div className="text-[11px] text-slate-400">Транзакции</div>
                <div className="font-semibold mt-1">{selectedTerminal.tx_count.toLocaleString('ru-RU')}</div>
              </div>
              <div className="bg-white/5 rounded-xl p-3">
                <div className="text-[11px] text-slate-400">Оборот</div>
                <div className="font-semibold mt-1">{money(selectedTerminal.total_volume)}</div>
              </div>
              <div className="bg-white/5 rounded-xl p-3">
                <div className="text-[11px] text-slate-400">Комиссия</div>
                <div className="font-semibold mt-1">{money(selectedTerminal.commission_amount)}</div>
              </div>
              <div className="bg-white/5 rounded-xl p-3">
                <div className="text-[11px] text-slate-400">Нетто</div>
                <div className="font-semibold mt-1">{money(selectedTerminal.net_volume)}</div>
              </div>
            </div>
          </div>
        </div>
      )}

      {terminal !== '(Все)' && (
        <div className="space-y-5">
          <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-xs">
            <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-3">
              <div>
                <div className="text-xs font-semibold text-indigo-600 uppercase tracking-wider">
                  Финансовая динамика терминала
                </div>
                <h4 className="text-lg font-bold text-slate-900 mt-1 font-mono">{terminal}</h4>
                <p className="text-xs text-slate-500 mt-1">
                  История строится отдельно для каждого TID: для комбинации «период + банк + терминал» берётся последний сохранённый результат. Поэтому сверки других терминалов того же банка не исчезают и повторное сохранение одного TID не удваивает оборот.
                </p>
              </div>
              <div className="text-xs text-slate-500">
                {terminalHistory.length > 0
                  ? `${terminalHistory[0].label} — ${terminalHistory[terminalHistory.length - 1].label}`
                  : 'Нет исторических данных'}
              </div>
            </div>

            <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-7 gap-3 mt-5">
              <div className="rounded-xl bg-slate-50 border border-slate-100 p-3">
                <div className="text-[11px] text-slate-500">Оборот за историю</div>
                <div className="font-bold text-slate-900 mt-1">{money(terminalFinancials.volume)}</div>
              </div>
              <div className="rounded-xl bg-slate-50 border border-slate-100 p-3">
                <div className="text-[11px] text-slate-500">Нетто-поступление</div>
                <div className="font-bold text-slate-900 mt-1">{money(terminalFinancials.net)}</div>
              </div>
              <div className="rounded-xl bg-slate-50 border border-slate-100 p-3">
                <div className="text-[11px] text-slate-500">Комиссия</div>
                <div className="font-bold text-violet-700 mt-1">{money(terminalFinancials.commission)}</div>
              </div>
              <div className="rounded-xl bg-slate-50 border border-slate-100 p-3">
                <div className="text-[11px] text-slate-500">Эфф. ставка</div>
                <div className="font-bold text-slate-900 mt-1">{pct(terminalFinancials.effectiveCommission)}</div>
              </div>
              <div className="rounded-xl bg-slate-50 border border-slate-100 p-3">
                <div className="text-[11px] text-slate-500">Средний чек</div>
                <div className="font-bold text-slate-900 mt-1">{money(terminalFinancials.avgTicket)}</div>
              </div>
              <div className="rounded-xl bg-slate-50 border border-slate-100 p-3">
                <div className="text-[11px] text-slate-500">Доля в обороте банка</div>
                <div className="font-bold text-slate-900 mt-1">{pct(terminalFinancials.latestShare)}</div>
              </div>
              <div className="rounded-xl bg-slate-50 border border-slate-100 p-3">
                <div className="text-[11px] text-slate-500">Изменение к пред. периоду</div>
                <div className={`font-bold mt-1 flex items-center gap-1 ${
                  terminalFinancials.growth === null
                    ? 'text-slate-500'
                    : terminalFinancials.growth >= 0
                      ? 'text-emerald-600'
                      : 'text-rose-600'
                }`}>
                  {terminalFinancials.growth === null ? '—' : (
                    <>
                      {terminalFinancials.growth >= 0
                        ? <ArrowUpRight className="w-4 h-4" />
                        : <ArrowDownRight className="w-4 h-4" />}
                      {pct(Math.abs(terminalFinancials.growth))}
                    </>
                  )}
                </div>
              </div>
            </div>
          </div>

          {terminalHistory.length > 0 ? (
            <>
              <div className="grid grid-cols-1 xl:grid-cols-2 gap-5">
                <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-xs">
                  <div className="mb-4">
                    <h4 className="font-semibold text-slate-900">Оборот терминала по периодам</h4>
                    <p className="text-xs text-slate-500 mt-1">
                      Валовой оборот и чистая сумма после комиссии.
                    </p>
                  </div>
                  <div className="h-80">
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={terminalHistory}>
                        <CartesianGrid strokeDasharray="3 3" vertical={false} />
                        <XAxis dataKey="label" tick={{ fontSize: 11 }} />
                        <YAxis tick={{ fontSize: 11 }} tickFormatter={(value: number) => money(value)} width={82} />
                        <Tooltip
                          formatter={(value: any, name: any) => [
                            money(Number(value || 0)),
                            name === 'volume' ? 'Оборот' : 'Нетто',
                          ]}
                          labelFormatter={(label: any) => `Период: ${label}`}
                        />
                        <Legend
                          formatter={(value: string) => value === 'volume' ? 'Оборот' : 'Нетто'}
                        />
                        <Line type="monotone" dataKey="volume" strokeWidth={2.5} dot={{ r: 3 }} />
                        <Line type="monotone" dataKey="net" strokeWidth={2.5} dot={{ r: 3 }} />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                </div>

                <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-xs">
                  <div className="mb-4">
                    <h4 className="font-semibold text-slate-900">Стоимость эквайринга</h4>
                    <p className="text-xs text-slate-500 mt-1">
                      Сумма комиссии и фактическая эффективная ставка терминала.
                    </p>
                  </div>
                  <div className="h-80">
                    <ResponsiveContainer width="100%" height="100%">
                      <ComposedChart data={terminalHistory}>
                        <CartesianGrid strokeDasharray="3 3" vertical={false} />
                        <XAxis dataKey="label" tick={{ fontSize: 11 }} />
                        <YAxis
                          yAxisId="money"
                          tick={{ fontSize: 11 }}
                          tickFormatter={(value: number) => money(value)}
                          width={82}
                        />
                        <YAxis
                          yAxisId="rate"
                          orientation="right"
                          tick={{ fontSize: 11 }}
                          tickFormatter={(value: number) => `${value.toFixed(2)}%`}
                          width={55}
                        />
                        <Tooltip
                          formatter={(value: any, name: any) => {
                            if (name === 'effectiveCommission') {
                              return [pct(Number(value || 0)), 'Эфф. ставка'];
                            }
                            return [money(Number(value || 0)), 'Комиссия'];
                          }}
                          labelFormatter={(label: any) => `Период: ${label}`}
                        />
                        <Legend
                          formatter={(value: string) => value === 'commission' ? 'Комиссия' : 'Эфф. ставка'}
                        />
                        <Bar yAxisId="money" dataKey="commission" radius={[5, 5, 0, 0]} />
                        <Line
                          yAxisId="rate"
                          type="monotone"
                          dataKey="effectiveCommission"
                          strokeWidth={2.5}
                          dot={{ r: 3 }}
                        />
                      </ComposedChart>
                    </ResponsiveContainer>
                  </div>
                </div>
              </div>

              <div className="bg-white border border-slate-200 rounded-xl shadow-xs overflow-hidden">
                <div className="px-5 py-4 border-b border-slate-100">
                  <h4 className="font-semibold text-slate-900">Финансовая история терминала</h4>
                  <p className="text-xs text-slate-500 mt-0.5">
                    Оборот, средний чек, комиссия, чистое поступление и доля терминала в обороте выбранного банка.
                  </p>
                </div>
                <div className="overflow-x-auto">
                  <table className="min-w-full text-sm">
                    <thead className="bg-slate-50">
                      <tr>
                        {[
                          'Период',
                          'Транзакции',
                          'Оборот',
                          'Средний чек',
                          'Комиссия',
                          'Эфф. ставка',
                          'Нетто',
                          'Доля банка',
                        ].map(header => (
                          <th
                            key={header}
                            className="px-4 py-3 text-left text-[11px] font-semibold uppercase tracking-wider text-slate-400"
                          >
                            {header}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {terminalHistory.slice().reverse().map(row => (
                        <tr key={row.period} className="hover:bg-slate-50">
                          <td className="px-4 py-3.5 font-medium whitespace-nowrap">{row.label}</td>
                          <td className="px-4 py-3.5">{row.tx.toLocaleString('ru-RU')}</td>
                          <td className="px-4 py-3.5 font-semibold">{money(row.volume)}</td>
                          <td className="px-4 py-3.5">{money(row.avgTicket)}</td>
                          <td className="px-4 py-3.5 text-violet-700 font-semibold">{money(row.commission)}</td>
                          <td className="px-4 py-3.5">{pct(row.effectiveCommission)}</td>
                          <td className="px-4 py-3.5 font-semibold">{money(row.net)}</td>
                          <td className="px-4 py-3.5">{pct(row.shareOfBank)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </>
          ) : (
            <div className="bg-white border border-slate-200 rounded-xl p-10 text-center text-sm text-slate-500">
              Для этого терминала пока недостаточно сохранённых данных для построения динамики.
            </div>
          )}
        </div>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-5">
        <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-xs">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h4 className="font-semibold text-slate-900">Динамика по запускам</h4>
              <p className="text-xs text-slate-500">Качество последних результатов выбранного периода.</p>
            </div>
            <Building2 className="w-5 h-5 text-slate-300" />
          </div>

          <div className="space-y-3">
            {filtered.slice(0, 8).map(record => {
              const quality = getReconciliationQuality(
                record.matched_count,
                record.mismatch_count,
                record.only_our_count,
                record.only_bank_count,
              );
              const rate = quality.exactMatchRate;

              return (
                <div key={record.id}>
                  <div className="flex justify-between text-xs mb-1">
                    <span className="text-slate-600">
                      {new Date(record.timestamp).toLocaleDateString('ru-RU')} · {record.bank_name}
                    </span>
                    <span className="font-semibold">{rate.toFixed(1)}%</span>
                  </div>
                  <div className="h-2 rounded-full bg-slate-100 overflow-hidden">
                    <div
                      className="h-full bg-indigo-500 rounded-full"
                      style={{ width: `${Math.min(100, rate)}%` }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        <div className="bg-slate-900 text-white rounded-xl p-5 shadow-xs">
          <div className="text-xs font-semibold text-indigo-200 uppercase tracking-wider">
            Период анализа
          </div>
          <div className="text-3xl font-bold mt-2">{filtered.length}</div>
          <div className="text-sm text-slate-300 mt-1">сохранённых запусков</div>

          <div className="grid grid-cols-2 gap-3 mt-6">
            <div className="bg-white/5 rounded-xl p-3">
              <div className="text-[11px] text-slate-400">Наш реестр</div>
              <div className="font-semibold mt-1">{money(totals.our)}</div>
            </div>
            <div className="bg-white/5 rounded-xl p-3">
              <div className="text-[11px] text-slate-400">Банк</div>
              <div className="font-semibold mt-1">{money(totals.bank)}</div>
            </div>
          </div>

          <div className="mt-4 text-xs text-slate-400">Пользователь: {user.username}</div>
        </div>
      </div>

      <div className="bg-white border border-slate-200 rounded-xl shadow-xs overflow-hidden">
        <div className="px-5 py-4 border-b border-slate-100 flex flex-col md:flex-row md:items-center md:justify-between gap-2">
          <div>
            <h4 className="font-semibold text-slate-900 flex items-center gap-2">
              <ReceiptText className="w-4 h-4 text-indigo-600" />
              Терминальная аналитика
            </h4>
            <p className="text-xs text-slate-500 mt-0.5">
              Последние сохранённые данные каждого терминала по месяцам; один TID может занимать несколько строк за разные периоды.
            </p>
          </div>
          <div className="text-xs text-slate-500">
            Показано {visibleTerminalRows.length} из {terminalPeriodRows.length} строк
          </div>
        </div>

        {visibleTerminalRows.length === 0 ? (
          <div className="p-10 text-center text-sm text-slate-500">
            Нет терминальной детализации.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead className="bg-slate-50">
                <tr>
                  {['TID', 'Месяц', 'Продукт / MID', 'Транзакции', 'Оборот', 'Ставка', 'Комиссия', 'Нетто'].map(header => (
                    <th
                      key={header}
                      className="px-4 py-3 text-left text-[11px] font-semibold uppercase tracking-wider text-slate-400"
                    >
                      {header}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {visibleTerminalRows.map(item => (
                  <tr
                    key={`${item.bank}::${item.terminal_id}::${item.period}`}
                    className={`hover:bg-slate-50 ${terminal === item.terminal_id ? 'bg-indigo-50/60' : ''}`}
                  >
                    <td className="px-4 py-3.5 font-mono font-medium">{item.terminal_id}</td>
                    <td className="px-4 py-3.5 whitespace-nowrap font-medium text-slate-700">{item.periodLabel}</td>
                    <td className="px-4 py-3.5">{item.merchant_id || '—'}</td>
                    <td className="px-4 py-3.5">{item.tx_count.toLocaleString('ru-RU')}</td>
                    <td className="px-4 py-3.5 font-semibold">{money(item.total_volume)}</td>
                    <td className="px-4 py-3.5">{pct(item.commission_pct)}</td>
                    <td className="px-4 py-3.5 text-violet-700 font-semibold">{money(item.commission_amount)}</td>
                    <td className="px-4 py-3.5 font-semibold">{money(item.net_volume)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};
