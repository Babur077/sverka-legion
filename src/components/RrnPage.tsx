import React, { useState, useMemo, useEffect } from 'react';
import {
  Upload, FileSpreadsheet, Play, Download, Save, CheckCircle2, AlertTriangle, XCircle,
  HelpCircle, ChevronDown, ChevronUp, Filter, Sparkles, RefreshCw, BarChart2, Eye,
  Settings, UploadCloud, Landmark, CalendarDays, Key, Coins, Tag as TagIcon, Settings2,
  Unlink, Percent, CalendarRange, Search, AlertCircle, Copy, FileText, CheckSquare,
  Square, FileCheck, Layers, Building2, Plus, RotateCcw
} from 'lucide-react';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer, ReferenceLine, Cell
} from 'recharts';
import { RawRow, ReconciliationConfig, ReconciliationResult, UnmatchedRow, AmountMismatchRow, DateSummaryRow, SystemSettings, User, EposTerminal } from '../types';
import { parseFile, guessCol, exportReconciliationToExcel } from '../utils/fileParser';
import { runBankRrnViaApi } from '../utils/bankRrnApi';
import { getStoredDraft, saveActiveDraft, clearActiveDraft } from '../utils/storage';
import { getEposViaApi } from '../utils/eposApi';
import { DEFAULT_BANKS, getBanksViaApi } from '../utils/banksApi';
import { AlertModal, ConfirmModal } from './Modal';
import { saveBankRrnArchive } from '../utils/archiveApi';
import { getReconciliationQuality } from '../utils/reconciliationMetrics';

interface RrnPageProps {
  user: User;
  settings: SystemSettings;
}

const REASON_OPTIONS = [
  '',
  'Тестовая транзакция',
  'Ожидает расчёта',
  'Спор / Chargeback',
  'Системная ошибка',
  'Ошибка загрузки данных',
  'Технический возврат',
  'Другое',
];

export const RrnPage: React.FC<RrnPageProps> = ({ user, settings }) => {
  const isAuditor = user.role === 'auditor';

  // Modal states
  const [alertState, setAlertState] = useState<{
    isOpen: boolean;
    title: string;
    message: string;
    type?: 'info' | 'success' | 'warning' | 'error';
  }>({
    isOpen: false,
    title: '',
    message: '',
    type: 'info',
  });

  const [confirmState, setConfirmState] = useState<{
    isOpen: boolean;
    title: string;
    message: string;
    confirmText?: string;
    cancelText?: string;
    isDanger?: boolean;
    onConfirm: () => void;
  }>({
    isOpen: false,
    title: '',
    message: '',
    onConfirm: () => {},
  });

  // Draft banner & persistence
  const [savedDraft, setSavedDraft] = useState<any | null>(null);
  const [showDraftBanner, setShowDraftBanner] = useState<boolean>(false);
  const [draftRestored, setDraftRestored] = useState<boolean>(false);

  // File upload state
  const [ourFile, setOurFile] = useState<{ name: string; rows: RawRow[]; columns: string[] } | null>(null);
  const [bankFile, setBankFile] = useState<{ name: string; rows: RawRow[]; columns: string[] } | null>(null);
  const [ourSourceFile, setOurSourceFile] = useState<File | null>(null);
  const [bankSourceFile, setBankSourceFile] = useState<File | null>(null);
  const [showPreviewOur, setShowPreviewOur] = useState(false);
  const [showPreviewBank, setShowPreviewBank] = useState(false);

  // Column selectors
  const [ourDateCol, setOurDateCol] = useState<string>('');
  const [ourRrnCol, setOurRrnCol] = useState<string>('');
  const [ourAmtCol, setOurAmtCol] = useState<string>('');
  const [ourStatusCol, setOurStatusCol] = useState<string>('');

  const [bankDateCol, setBankDateCol] = useState<string>('');
  const [bankRrnCol, setBankRrnCol] = useState<string>('');
  const [bankAmtCol, setBankAmtCol] = useState<string>('');
  const [bankStatusCol, setBankStatusCol] = useState<string>('');
  const [bankTidCol, setBankTidCol] = useState<string>('');

  // Processing rules
  const [revInput, setRevInput] = useState('reversed, возврат, refund, отказ, ошибка');
  const [ourRev, setOurRev] = useState('Минусовать сумму');
  const [bankRev, setBankRev] = useState('Удалить строку');
  const [dupAction, setDupAction] = useState('Ничего не делать (оставить все)');
  const [unbindMismatches, setUnbindMismatches] = useState(false);
  const [deductCommission, setDeductCommission] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);

  // Calculation & Results
  const [isProcessing, setIsProcessing] = useState(false);
  const [reconData, setReconData] = useState<ReconciliationResult | null>(null);
  const [activeTab, setActiveTab] = useState<'summary' | 'charts' | 'terminals' | 'unmatched' | 'mismatches' | 'dups'>('summary');
  const [selectedDrilldownDate, setSelectedDrilldownDate] = useState<string | null>(null);
  const [commissionPct, setCommissionPct] = useState<number>(1.2);
  const [selectedArchiveMonth, setSelectedArchiveMonth] = useState<string>(new Date().toISOString().slice(0, 7));
  const [saveSuccessMsg, setSaveSuccessMsg] = useState<string | null>(null);

  // Bank selection state (Quick Bank Select)
  const [availableBanks, setAvailableBanks] = useState<string[]>(DEFAULT_BANKS);
  const [eposTerminals, setEposTerminals] = useState<EposTerminal[]>([]);
  const [selectedBank, setSelectedBank] = useState<string>('Aloqa Bank');
  const [showAddBank, setShowAddBank] = useState<boolean>(false);
  const [newBankInput, setNewBankInput] = useState<string>('');

  const filesReady = !!ourFile && !!bankFile && !!ourSourceFile && !!bankSourceFile;
  const mappingReady = !!ourDateCol && !!ourRrnCol && !!bankDateCol && !!bankRrnCol;
  const amountsReady = !!ourAmtCol && !!bankAmtCol;
  const runReady = filesReady && mappingReady && amountsReady && !isProcessing;

  // Check stored draft on initial mount
  useEffect(() => {
    const draft = getStoredDraft();
    if (draft) {
      setSavedDraft(draft);
      setShowDraftBanner(true);
    }
  }, []);

  // Server-backed reference data. Custom banks added during a reconciliation stay
  // local to the current workspace until they are registered through EPOS.
  useEffect(() => {
    let active = true;

    void getBanksViaApi()
      .then((banks) => {
        if (active) setAvailableBanks(prev => Array.from(new Set([...prev, ...banks])));
      })
      .catch(() => {});

    void getEposViaApi(user.username)
      .then((terminals) => {
        if (!active) return;
        setEposTerminals(terminals);
        setAvailableBanks(prev => Array.from(new Set([
          ...prev,
          ...terminals.map(t => t.bank_acquirer).filter(Boolean),
        ])));
      })
      .catch(() => {});

    return () => { active = false; };
  }, [user.username]);

  // Auto-save active draft to localStorage
  useEffect(() => {
    if (ourFile || bankFile || ourRrnCol || bankRrnCol) {
      saveActiveDraft({
        timestamp: new Date().toISOString(),
        selectedBank,
        commissionPct,
        ourFile: ourFile ? { name: ourFile.name, columns: ourFile.columns, rows: ourFile.rows } : null,
        bankFile: bankFile ? { name: bankFile.name, columns: bankFile.columns, rows: bankFile.rows } : null,
        columns: {
          ourDateCol, ourRrnCol, ourAmtCol, ourStatusCol,
          bankDateCol, bankRrnCol, bankAmtCol, bankStatusCol, bankTidCol,
        },
        rules: {
          revInput, ourRev, bankRev, dupAction, unbindMismatches, deductCommission,
        },
      });
    }
  }, [
    ourFile, bankFile, selectedBank, commissionPct,
    ourDateCol, ourRrnCol, ourAmtCol, ourStatusCol,
    bankDateCol, bankRrnCol, bankAmtCol, bankStatusCol, bankTidCol,
    revInput, ourRev, bankRev, dupAction, unbindMismatches, deductCommission
  ]);

  // A result is valid only for the exact files and reconciliation settings
  // used to produce it. Changing an input invalidates the previous result so
  // it cannot accidentally be saved under a different bank or configuration.
  useEffect(() => {
    if (!reconData) return;
    setReconData(null);
    setSaveSuccessMsg(null);
    setSelectedDrilldownDate(null);
    setActiveTab('summary');
  }, [
    ourSourceFile, bankSourceFile, selectedBank,
    ourDateCol, ourRrnCol, ourAmtCol, ourStatusCol,
    bankDateCol, bankRrnCol, bankAmtCol, bankStatusCol, bankTidCol,
    revInput, ourRev, bankRev, dupAction, unbindMismatches, deductCommission,
    settings.amount_tolerance,
  ]);

  const handleRestoreDraft = () => {
    if (!savedDraft) return;
    if (savedDraft.selectedBank) setSelectedBank(savedDraft.selectedBank);
    if (typeof savedDraft.commissionPct === 'number') setCommissionPct(savedDraft.commissionPct);
    if (savedDraft.columns) {
      setOurDateCol(savedDraft.columns.ourDateCol || '');
      setOurRrnCol(savedDraft.columns.ourRrnCol || '');
      setOurAmtCol(savedDraft.columns.ourAmtCol || '');
      setOurStatusCol(savedDraft.columns.ourStatusCol || '');
      setBankDateCol(savedDraft.columns.bankDateCol || '');
      setBankRrnCol(savedDraft.columns.bankRrnCol || '');
      setBankAmtCol(savedDraft.columns.bankAmtCol || '');
      setBankStatusCol(savedDraft.columns.bankStatusCol || '');
      setBankTidCol(savedDraft.columns.bankTidCol || '');
    }
    if (savedDraft.rules) {
      setRevInput(savedDraft.rules.revInput || '');
      setOurRev(savedDraft.rules.ourRev || 'Минусовать сумму');
      setBankRev(savedDraft.rules.bankRev || 'Удалить строку');
      setDupAction(savedDraft.rules.dupAction || 'Ничего не делать (оставить все)');
      setUnbindMismatches(!!savedDraft.rules.unbindMismatches);
      setDeductCommission(!!savedDraft.rules.deductCommission);
    }
    setDraftRestored(true);
    setShowDraftBanner(true);
  };

  const handleDismissDraft = () => {
    clearActiveDraft();
    setSavedDraft(null);
    setDraftRestored(false);
    setShowDraftBanner(false);
  };

  const handleResetAll = () => {
    setConfirmState({
      isOpen: true,
      title: 'Сбросить текущие данные?',
      message: 'Все загруженные файлы, параметры сопоставления колонок и результаты сверки будут очищены.',
      confirmText: 'Сбросить данные',
      isDanger: true,
      onConfirm: () => {
        setOurFile(null);
        setBankFile(null);
        setOurSourceFile(null);
        setBankSourceFile(null);
        setReconData(null);
        setOurDateCol('');
        setOurRrnCol('');
        setOurAmtCol('');
        setOurStatusCol('');
        setBankDateCol('');
        setBankRrnCol('');
        setBankAmtCol('');
        setBankStatusCol('');
        setBankTidCol('');
        setShowPreviewOur(false);
        setShowPreviewBank(false);
        setActiveTab('summary');
        setSelectedDrilldownDate(null);
        setSaveSuccessMsg(null);
        setDraftRestored(false);
        setFilterDateOur('(Все)');
        setFilterStatusOur('(Все)');
        setFilterDateBank('(Все)');
        setFilterStatusBank('(Все)');
        setUnmatchedPageOur(1);
        setUnmatchedPageBank(1);
        clearActiveDraft();
        setSavedDraft(null);
        setShowDraftBanner(false);
        setConfirmState(prev => ({ ...prev, isOpen: false }));
      }
    });
  };

  const handleSelectBank = (bankName: string) => {
    setSelectedBank(bankName);
    const bankEpos = eposTerminals.find(
      t => t.bank_acquirer.toLowerCase() === bankName.toLowerCase() && t.is_active,
    );
    if (bankEpos) {
      setCommissionPct(bankEpos.commission_pct);
    }
  };

  const handleAddNewBank = (e: React.FormEvent) => {
    e.preventDefault();
    const clean = newBankInput.trim();
    if (!clean) return;
    setAvailableBanks(prev => Array.from(new Set([...prev, clean])));
    setSelectedBank(clean);
    setNewBankInput('');
    setShowAddBank(false);
  };

  // Unmatched items bulk actions
  const [filterDateOur, setFilterDateOur] = useState('(Все)');
  const [filterStatusOur, setFilterStatusOur] = useState('(Все)');
  const [filterDateBank, setFilterDateBank] = useState('(Все)');
  const [filterStatusBank, setFilterStatusBank] = useState('(Все)');
  const UNMATCHED_PAGE_SIZE = 100;
  const [unmatchedPageOur, setUnmatchedPageOur] = useState(1);
  const [unmatchedPageBank, setUnmatchedPageBank] = useState(1);

  const unmatchedOurFiltered = useMemo(() => {
    if (!reconData || activeTab !== 'unmatched') return [];
    return reconData.only_our
      .map((item, originalIndex) => ({ item, originalIndex }))
      .filter(({ item }) =>
        (filterDateOur === '(Все)' || item.date_str === filterDateOur) &&
        (filterStatusOur === '(Все)' || (item.status || '') === filterStatusOur)
      );
  }, [reconData, activeTab, filterDateOur, filterStatusOur]);

  const unmatchedBankFiltered = useMemo(() => {
    if (!reconData || activeTab !== 'unmatched') return [];
    return reconData.only_bank
      .map((item, originalIndex) => ({ item, originalIndex }))
      .filter(({ item }) =>
        (filterDateBank === '(Все)' || item.date_str === filterDateBank) &&
        (filterStatusBank === '(Все)' || (item.status || '') === filterStatusBank)
      );
  }, [reconData, activeTab, filterDateBank, filterStatusBank]);

  const unmatchedOurPageCount = Math.max(1, Math.ceil(unmatchedOurFiltered.length / UNMATCHED_PAGE_SIZE));
  const unmatchedBankPageCount = Math.max(1, Math.ceil(unmatchedBankFiltered.length / UNMATCHED_PAGE_SIZE));

  const unmatchedOurPageItems = unmatchedOurFiltered.slice(
    (unmatchedPageOur - 1) * UNMATCHED_PAGE_SIZE,
    unmatchedPageOur * UNMATCHED_PAGE_SIZE
  );
  const unmatchedBankPageItems = unmatchedBankFiltered.slice(
    (unmatchedPageBank - 1) * UNMATCHED_PAGE_SIZE,
    unmatchedPageBank * UNMATCHED_PAGE_SIZE
  );

  const unmatchedOurDates = useMemo(() => {
    if (!reconData || activeTab !== 'unmatched') return [];
    return Array.from(new Set(reconData.only_our.map(x => x.date_str)));
  }, [reconData, activeTab]);

  const unmatchedOurStatuses = useMemo(() => {
    if (!reconData || activeTab !== 'unmatched') return [];
    return Array.from(new Set(reconData.only_our.map(x => x.status || ''))).filter(Boolean);
  }, [reconData, activeTab]);

  const unmatchedBankDates = useMemo(() => {
    if (!reconData || activeTab !== 'unmatched') return [];
    return Array.from(new Set(reconData.only_bank.map(x => x.date_str)));
  }, [reconData, activeTab]);

  const unmatchedBankStatuses = useMemo(() => {
    if (!reconData || activeTab !== 'unmatched') return [];
    return Array.from(new Set(reconData.only_bank.map(x => x.status || ''))).filter(Boolean);
  }, [reconData, activeTab]);

  useEffect(() => {
    setUnmatchedPageOur(1);
    setUnmatchedPageBank(1);
  }, [filterDateOur, filterStatusOur, filterDateBank, filterStatusBank]);

  useEffect(() => {
    if (unmatchedPageOur > unmatchedOurPageCount) setUnmatchedPageOur(unmatchedOurPageCount);
    if (unmatchedPageBank > unmatchedBankPageCount) setUnmatchedPageBank(unmatchedBankPageCount);
  }, [unmatchedOurPageCount, unmatchedBankPageCount, unmatchedPageOur, unmatchedPageBank]);

  // File Handlers
  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>, isOur: boolean) => {
    const file = e.target.files?.[0];
    if (!file) return;

    try {
      const parsed = await parseFile(file);
      if (isOur) {
        setOurSourceFile(file);
        setOurFile({ name: parsed.fileName, rows: parsed.rows, columns: parsed.columns });
        setDraftRestored(false);
        setOurDateCol(guessCol(parsed.columns, ['date', 'дата']) || parsed.columns[0] || '');
        setOurRrnCol(guessCol(parsed.columns, ['rrn', 'ref']) || parsed.columns[1] || '');
        setOurAmtCol(guessCol(parsed.columns, ['amount', 'сумма']) || '');
        setOurStatusCol(guessCol(parsed.columns, ['status', 'статус']) || '');
      } else {
        setBankSourceFile(file);
        setBankFile({ name: parsed.fileName, rows: parsed.rows, columns: parsed.columns });
        setDraftRestored(false);
        setBankDateCol(guessCol(parsed.columns, ['date', 'дата']) || parsed.columns[0] || '');
        setBankRrnCol(guessCol(parsed.columns, ['rrn', 'ref']) || parsed.columns[1] || '');
        setBankAmtCol(guessCol(parsed.columns, ['amount', 'сумма']) || '');
        setBankStatusCol(guessCol(parsed.columns, ['status', 'статус']) || '');
        setBankTidCol(guessCol(parsed.columns, ['tid', 'terminal', 'терминал']) || '');
      }
    } catch (err) {
      setAlertState({
        isOpen: true,
        title: 'Ошибка чтения файла',
        message: `Не удалось прочитать загруженный файл: ${err}`,
        type: 'error',
      });
    }
  };

  const handleRunReconciliation = async () => {
    // Validation checks
    if (!ourFile || !bankFile) {
      setAlertState({
        isOpen: true,
        title: 'Файлы не выбраны',
        message: 'Пожалуйста, загрузите реестр (1C / Система) и выписку банка (Excel или CSV).',
        type: 'warning',
      });
      return;
    }

    if (!ourDateCol || !bankDateCol) {
      setAlertState({
        isOpen: true,
        title: 'Не выбраны колонки даты',
        message: 'Для обеих сторон обязательно выберите колонку даты операции.',
        type: 'warning',
      });
      return;
    }

    if (!ourRrnCol || !bankRrnCol) {
      setAlertState({
        isOpen: true,
        title: 'Не указана колонка RRN',
        message: 'Для сверки транзакций обязательно выберите колонку с RRN / кодом операции как в вашей системе, так и в выписке банка.',
        type: 'error',
      });
      return;
    }

    if (!ourAmtCol || !bankAmtCol) {
      setAlertState({
        isOpen: true,
        title: 'Не выбраны колонки сумм',
        message: 'Пожалуйста, выберите колонки с суммами платежей с обеих сторон для корректного расчета расхождений и финансового баланса.',
        type: 'warning',
      });
      return;
    }

    setIsProcessing(true);
    setSaveSuccessMsg(null);

    try {
      const revWords = revInput.split(',').map(w => w.trim()).filter(Boolean);

      const cfg: ReconciliationConfig = {
        our_date: ourDateCol,
        our_rrn: ourRrnCol,
        our_amt: ourAmtCol || null,
        our_status: ourStatusCol || null,
        bank_date: bankDateCol,
        bank_rrn: bankRrnCol,
        bank_amt: bankAmtCol || null,
        bank_status: bankStatusCol || null,
        bank_tid: bankTidCol || null,
        rev_words: revWords,
        our_rev: ourRev,
        bank_rev: bankRev,
        dup_action: dupAction,
        unbind_mismatches: unbindMismatches,
        tolerance: settings.amount_tolerance,
        deduct_commission: deductCommission,
      };

      if (!ourSourceFile || !bankSourceFile) {
        throw new Error('После восстановления черновика необходимо заново выбрать оба исходных файла.');
      }

      const result = await runBankRrnViaApi(ourSourceFile, bankSourceFile, cfg, user.username);
      setReconData(result);
      if (result.detected_months && result.detected_months.length > 0) {
        setSelectedArchiveMonth(result.detected_months[0]);
      }
      setSelectedDrilldownDate(null);
    } catch (err: any) {
      setAlertState({
        isOpen: true,
        title: 'Ошибка сверки',
        message: `Не удалось завершить расчет: ${err?.message || err}`,
        type: 'error',
      });
    } finally {
      setIsProcessing(false);
    }
  };

  // Toggle single unmatched check
  const handleToggleCheck = (index: number, isOur: boolean) => {
    if (!reconData || isAuditor) return;
    const key = isOur ? 'only_our' : 'only_bank';
    const updated = reconData[key].map((item, idx) => 
      idx === index ? { ...item, checked: !item.checked } : item
    );
    setReconData({ ...reconData, [key]: updated });
  };

  // Change reason
  const handleChangeReason = (index: number, reason: string, isOur: boolean) => {
    if (!reconData || isAuditor) return;
    const key = isOur ? 'only_our' : 'only_bank';
    const updated = reconData[key].map((item, idx) => 
      idx === index ? { ...item, reason } : item
    );
    setReconData({ ...reconData, [key]: updated });
  };

  // Bulk check / uncheck
  const handleBulkToggle = (checked: boolean, isOur: boolean) => {
    if (!reconData || isAuditor) return;
    const list = isOur ? [...reconData.only_our] : [...reconData.only_bank];
    const dateFilter = isOur ? filterDateOur : filterDateBank;
    const statFilter = isOur ? filterStatusOur : filterStatusBank;

    const updated = list.map(item => {
      const matchDate = dateFilter === '(Все)' || item.date_str === dateFilter;
      const matchStat = statFilter === '(Все)' || (item.status || '') === statFilter;
      if (matchDate && matchStat) {
        return { ...item, checked };
      }
      return item;
    });

    setReconData({
      ...reconData,
      [isOur ? 'only_our' : 'only_bank']: updated,
    });
  };

  // Auto-exclude offsetting reversal pairs
  const handleExcludeOffsets = (isOur: boolean) => {
    if (!reconData || isAuditor) return;
    const list = isOur ? [...reconData.only_our] : [...reconData.only_bank];
    const revWords = revInput.split(',').map(w => w.trim().toLowerCase()).filter(Boolean);

    // Find RRNs that have both a normal row and a reversal row
    const rrnMap = new Map<string, { hasNormal: boolean; hasRev: boolean }>();
    list.filter(item => item.checked).forEach(item => {
      const isRev = revWords.some(w => (item.status || '').toLowerCase().includes(w));
      const entry = rrnMap.get(item.RRN) || { hasNormal: false, hasRev: false };
      if (isRev) entry.hasRev = true;
      else entry.hasNormal = true;
      rrnMap.set(item.RRN, entry);
    });

    const offsetRrns = new Set<string>();
    rrnMap.forEach((val, rrn) => {
      if (val.hasNormal && val.hasRev) offsetRrns.add(rrn);
    });

    if (offsetRrns.size === 0) {
      setAlertState({
        isOpen: true,
        title: 'Компенсирующие возвраты',
        message: 'Компенсирующих пар по статусу возврата не обнаружено среди отмеченных строк.',
        type: 'info',
      });
      return;
    }

    const updated = list.map(item => {
      if (offsetRrns.has(item.RRN)) {
        return { ...item, checked: false, reason: 'Технический возврат' };
      }
      return item;
    });

    setReconData({
      ...reconData,
      [isOur ? 'only_our' : 'only_bank']: updated,
    });
  };

  // DYNAMIC RECALCULATION of Summary and Totals based on exclusions
  const dynamicCalculations = useMemo(() => {
    if (!reconData) return null;

    const excludedOur = reconData.only_our.filter(r => !r.checked);
    const excludedBank = reconData.only_bank.filter(r => !r.checked);

    const excludedOurByDate = new Map<string, { count: number; sum: number }>();
    excludedOur.forEach(r => {
      const cur = excludedOurByDate.get(r.date_str) || { count: 0, sum: 0 };
      cur.count += 1;
      cur.sum += r.amount;
      excludedOurByDate.set(r.date_str, cur);
    });

    const excludedBankByDate = new Map<string, { count: number; sum: number }>();
    excludedBank.forEach(r => {
      const cur = excludedBankByDate.get(r.date_str) || { count: 0, sum: 0 };
      cur.count += 1;
      cur.sum += r.amount;
      excludedBankByDate.set(r.date_str, cur);
    });

    const nonTotalSummary = reconData.summary.filter(r => !r.date.includes('ИТОГО'));

    const adjustedSummary: DateSummaryRow[] = nonTotalSummary.map(row => {
      const exOur = excludedOurByDate.get(row.date) || { count: 0, sum: 0 };
      const exBank = excludedBankByDate.get(row.date) || { count: 0, sum: 0 };

      const ourCount = row.Кол_во_у_нас - exOur.count;
      const ourSum = row.Сумма_у_нас - exOur.sum;
      const bankCount = row.Кол_во_в_банке - exBank.count;
      const bankSum = row.Сумма_в_банке - exBank.sum;

      return {
        date: row.date,
        Кол_во_у_нас: ourCount,
        Кол_во_в_банке: bankCount,
        'Δ кол-во': bankCount - ourCount,
        Сумма_у_нас: ourSum,
        Сумма_в_банке: bankSum,
        'Δ суммы': bankSum - ourSum,
      };
    });

    const totalOurSum = adjustedSummary.reduce((a, b) => a + b.Сумма_у_нас, 0);
    const totalBankSum = adjustedSummary.reduce((a, b) => a + b.Сумма_в_банке, 0);
    const totalOurCount = adjustedSummary.reduce((a, b) => a + b.Кол_во_у_нас, 0);
    const totalBankCount = adjustedSummary.reduce((a, b) => a + b.Кол_во_в_банке, 0);
    const totalDiff = totalBankSum - totalOurSum;

    adjustedSummary.push({
      date: 'ИТОГО (с учётом исключений)',
      Кол_во_у_нас: totalOurCount,
      Кол_во_в_банке: totalBankCount,
      'Δ кол-во': totalBankCount - totalOurCount,
      Сумма_у_нас: totalOurSum,
      Сумма_в_банке: totalBankSum,
      'Δ суммы': totalDiff,
    });

    const activeOnlyOurCount = reconData.only_our.length - excludedOur.length;
    const activeOnlyBankCount = reconData.only_bank.length - excludedBank.length;
    const quality = getReconciliationQuality(
      reconData.matched_count,
      reconData.mismatch_count,
      activeOnlyOurCount,
      activeOnlyBankCount,
    );

    const excludedByTerminal = new Map<string, { tx: number; volume: number; commission: number }>();
    excludedBank.forEach(row => {
      const terminalId = String(row.terminal_id || row.raw?.terminal_id || '').trim();
      if (!terminalId) return;
      const rawAmount = Number(row.raw?.raw_amount ?? row.amount ?? 0);
      const commissionPct = Number(row.raw?.commission_pct ?? row.commission_pct ?? 0);
      const directCommission = Number(row.raw?.commission_amount);
      const commission = Number.isFinite(directCommission)
        ? directCommission
        : (Number.isFinite(rawAmount) && Number.isFinite(commissionPct) ? rawAmount * commissionPct / 100 : 0);
      const current = excludedByTerminal.get(terminalId) || { tx: 0, volume: 0, commission: 0 };
      current.tx += 1;
      current.volume += Number.isFinite(rawAmount) ? rawAmount : 0;
      current.commission += Number.isFinite(commission) ? commission : 0;
      excludedByTerminal.set(terminalId, current);
    });

    const adjustedTerminalSummary = (reconData.terminal_summary || [])
      .map(terminal => {
        const excluded = excludedByTerminal.get(terminal.terminal_id) || { tx: 0, volume: 0, commission: 0 };
        const txCount = Math.max(0, terminal.tx_count - excluded.tx);
        const totalVolume = terminal.total_volume - excluded.volume;
        const commissionAmount = Math.max(0, terminal.commission_amount - excluded.commission);
        return {
          ...terminal,
          tx_count: txCount,
          total_volume: totalVolume,
          commission_amount: commissionAmount,
          net_volume: totalVolume - commissionAmount,
        };
      })
      .filter(terminal => terminal.tx_count > 0 || Math.abs(terminal.total_volume) > 0.000001);

    const fallbackExcludedCommission = excludedBank.reduce((sum, row) => {
      const directCommission = Number(row.raw?.commission_amount);
      if (Number.isFinite(directCommission)) return sum + directCommission;
      const rawAmount = Number(row.raw?.raw_amount ?? row.amount ?? 0);
      const commissionPct = Number(row.raw?.commission_pct ?? row.commission_pct ?? 0);
      return sum + (
        Number.isFinite(rawAmount) && Number.isFinite(commissionPct)
          ? rawAmount * commissionPct / 100
          : 0
      );
    }, 0);

    const adjustedCommission = adjustedTerminalSummary.length
      ? adjustedTerminalSummary.reduce((sum, terminal) => sum + terminal.commission_amount, 0)
      : Math.max(0, (reconData.total_commission || 0) - fallbackExcludedCommission);

    const netBankSettlement = reconData.deduct_commission
      ? totalBankSum
      : totalBankSum - adjustedCommission;

    return {
      adjustedSummary,
      adjustedTerminalSummary,
      adjustedCommission,
      netBankSettlement,
      totalOurSum,
      totalBankSum,
      totalDiff,
      excludedOurCount: excludedOur.length,
      excludedBankCount: excludedBank.length,
      activeOnlyOurCount,
      activeOnlyBankCount,
      quality,
    };
  }, [reconData]);

  // Generate selectable months (detected from file dates + last 12 calendar months)
  const availableMonths = useMemo(() => {
    const list: { value: string; label: string }[] = [];
    const added = new Set<string>();

    const monthNames = [
      'Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
      'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь'
    ];

    const formatMonthLabel = (mStr: string) => {
      const [y, m] = mStr.split('-');
      const mIdx = parseInt(m, 10) - 1;
      return `${monthNames[mIdx] || m} ${y} (${mStr})`;
    };

    if (reconData?.detected_months) {
      reconData.detected_months.forEach(m => {
        if (!added.has(m)) {
          added.add(m);
          list.push({ value: m, label: `Обнаружен: ${formatMonthLabel(m)}` });
        }
      });
    }

    const now = new Date();
    for (let i = 0; i < 12; i++) {
      const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
      const val = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
      if (!added.has(val)) {
        added.add(val);
        list.push({ value: val, label: formatMonthLabel(val) });
      }
    }
    return list;
  }, [reconData]);

  // Save to Archive
  const handleSaveToArchive = async () => {
    if (isAuditor) {
      setAlertState({
        isOpen: true,
        title: 'Ограничение прав доступа',
        message: 'Пользователям с ролью «Аудитор» доступен только режим просмотра. Сохранение результатов в архив базы данных разрешено только бухгалтерам и администраторам.',
        type: 'warning',
      });
      return;
    }

    if (!dynamicCalculations || !reconData) return;
    const bankNameForArchive = selectedBank || bankFile?.name.replace(/\.[^/.]+$/, '') || 'Банк';

    try {
      await saveBankRrnArchive(
        user.username,
        bankNameForArchive,
        reconData,
        {
          total_our: dynamicCalculations.totalOurSum,
          total_bank: dynamicCalculations.totalBankSum,
          difference: dynamicCalculations.totalDiff,
          period_month: selectedArchiveMonth,
          only_our_count: dynamicCalculations.activeOnlyOurCount,
          only_bank_count: dynamicCalculations.activeOnlyBankCount,
          total_commission: dynamicCalculations.adjustedCommission,
          terminals_summary: dynamicCalculations.adjustedTerminalSummary,
        },
      );
      setSaveSuccessMsg(`Сверка за ${selectedArchiveMonth} успешно записана в архив!`);
      setAlertState({
        isOpen: true,
        title: 'Успешно сохранено',
        message: `Сверка по банку "${bankNameForArchive}" за месяц ${selectedArchiveMonth} успешно зафиксирована в серверном архиве с аналитикой по терминалам.`,
        type: 'success',
      });
    } catch (error: any) {
      setAlertState({
        isOpen: true,
        title: 'Ошибка сохранения',
        message: error?.message || 'Не удалось сохранить сверку в серверный архив.',
        type: 'error',
      });
    }
  };

  // Export to Excel
  const handleExportExcel = () => {
    if (!dynamicCalculations || !reconData) return;
    exportReconciliationToExcel(
      dynamicCalculations.adjustedSummary,
      reconData.only_our,
      reconData.only_bank,
      reconData.amt_mismatches,
      reconData.dups_our,
      reconData.dups_bank,
      dynamicCalculations.adjustedTerminalSummary
    );
  };

  const currency = settings.currency || 'UZS';
  const tolerance = settings.amount_tolerance || 0.01;

  const fmt = (n: number) => {
    return n.toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  };

  return (
    <div className="p-8 max-w-7xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight flex items-center gap-2">
            <span>Сверка по RRN</span>
            <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-indigo-50 text-indigo-700 border border-indigo-200">
              EPOS Core
            </span>
            {isAuditor && (
              <span className="text-xs font-semibold px-2.5 py-0.5 rounded-full bg-amber-50 text-amber-800 border border-amber-200 inline-flex items-center gap-1">
                <Eye className="w-3 h-3 text-amber-600" />
                Только чтение
              </span>
            )}
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            Потранзакционная сверка с автоматическим расчётом комиссий на базе реестра EPOS.
          </p>
        </div>

        <div className="flex items-center gap-2">
          {(ourFile || bankFile) && (
            <button
              id="btn-reset-all"
              type="button"
              onClick={handleResetAll}
              className="inline-flex items-center gap-1.5 px-3 py-2 bg-white hover:bg-rose-50 text-slate-600 hover:text-rose-600 text-xs font-semibold rounded-xl border border-slate-200 transition-colors cursor-pointer"
            >
              <RotateCcw className="w-3.5 h-3.5" />
              <span>Сбросить данные</span>
            </button>
          )}

        </div>
      </div>

      {/* ─── DRAFT RECOVERY BANNER ─── */}
      {showDraftBanner && (!ourFile || !bankFile) && (
        <div className="p-4 rounded-2xl bg-indigo-50/80 border border-indigo-200 flex flex-col lg:flex-row items-start lg:items-center justify-between gap-4 text-xs">
          <div className="flex items-start gap-2.5 text-indigo-950 min-w-0">
            <Sparkles className="w-4 h-4 text-indigo-600 shrink-0 mt-0.5" />
            <div className="min-w-0">
              <div>
                <span className="font-bold">{draftRestored ? 'Параметры сверки восстановлены' : 'Обнаружен сохранённый черновик'}</span>{' '}
                {savedDraft?.timestamp && (
                  <span className="text-indigo-700">от {new Date(savedDraft.timestamp).toLocaleString('ru-RU')}</span>
                )}
                {savedDraft?.selectedBank && (
                  <span className="text-slate-600 ml-1">({savedDraft.selectedBank})</span>
                )}
              </div>
              {draftRestored ? (
                <div className="mt-1 text-slate-700">Файлы не хранятся в черновике — выберите их заново ниже. Параметры колонок и правил уже восстановлены.</div>
              ) : (
                <div className="mt-1 text-slate-600">Будут восстановлены параметры сверки. Исходные файлы потребуют повторного выбора.</div>
              )}
              {savedDraft?.fileMeta && (
                <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-slate-600">
                  {savedDraft.fileMeta.our && (
                    <span><strong className="text-slate-800">Ваши данные:</strong> {savedDraft.fileMeta.our.name} · {savedDraft.fileMeta.our.rowCount.toLocaleString('ru-RU')} строк</span>
                  )}
                  {savedDraft.fileMeta.bank && (
                    <span><strong className="text-slate-800">Банк:</strong> {savedDraft.fileMeta.bank.name} · {savedDraft.fileMeta.bank.rowCount.toLocaleString('ru-RU')} строк</span>
                  )}
                </div>
              )}
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {!draftRestored && (
              <button
                type="button"
                onClick={handleRestoreDraft}
                className="px-3 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white font-semibold rounded-lg shadow-xs transition-colors cursor-pointer"
              >
                Восстановить параметры
              </button>
            )}
            <button
              type="button"
              onClick={handleDismissDraft}
              className="px-3 py-1.5 bg-white border border-slate-200 hover:bg-slate-100 text-slate-600 font-medium rounded-lg transition-colors cursor-pointer"
            >
              Очистить
            </button>
          </div>
        </div>
      )}

      {/* ─── WORKFLOW READINESS ─── */}
      <div className="bg-white rounded-2xl border border-slate-200 p-4 shadow-xs">
        <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-3">
          <div>
            <div className="text-sm font-bold text-slate-900">Готовность к запуску</div>
            <div className="text-xs text-slate-500 mt-0.5">Результат всегда относится к текущим файлам и настройкам. При их изменении предыдущий результат автоматически сбрасывается.</div>
          </div>
          <div className="grid grid-cols-3 gap-2 min-w-0 lg:min-w-[430px]">
            {[
              { label: '1. Банк', ready: !!selectedBank },
              { label: '2. Файлы', ready: filesReady },
              { label: '3. Колонки', ready: mappingReady && amountsReady },
            ].map(step => (
              <div
                key={step.label}
                className={`rounded-xl border px-3 py-2 text-xs font-semibold flex items-center gap-2 ${
                  step.ready
                    ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
                    : 'border-slate-200 bg-slate-50 text-slate-500'
                }`}
              >
                {step.ready ? <CheckCircle2 className="w-3.5 h-3.5 shrink-0" /> : <Square className="w-3.5 h-3.5 shrink-0" />}
                <span>{step.label}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* ─── ВЫБОР БАНКА-ЭКВАЙЕРА (БЫСТРЫЙ НАБОР) ─── */}
      <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-xs space-y-3">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center font-bold">
              <Landmark className="w-4 h-4" />
            </div>
            <div>
              <h2 className="text-sm font-bold text-slate-900">Банк-эквайер для сверки</h2>
              <p className="text-xs text-slate-500">Выберите банк для текущей сверки; временное название можно добавить только в этот рабочий сеанс</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs text-slate-500">Выбран банк:</span>
            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 bg-indigo-50 text-indigo-700 border border-indigo-200 rounded-lg text-xs font-bold">
              <Building2 className="w-3.5 h-3.5" />
              <span>{selectedBank}</span>
            </span>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2 pt-1">
          {availableBanks.map((b) => {
            const isSelected = selectedBank.toLowerCase() === b.toLowerCase();
            return (
              <button
                key={b}
                type="button"
                onClick={() => handleSelectBank(b)}
                className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all flex items-center gap-1.5 cursor-pointer border ${
                  isSelected
                    ? 'bg-indigo-600 text-white border-indigo-600 shadow-xs ring-2 ring-indigo-200'
                    : 'bg-slate-50 hover:bg-slate-100 text-slate-700 border-slate-200'
                }`}
              >
                {isSelected ? <CheckCircle2 className="w-3.5 h-3.5" /> : <Building2 className="w-3 h-3 text-slate-400" />}
                <span>{b}</span>
              </button>
            );
          })}

          <button
            type="button"
            onClick={() => setShowAddBank(!showAddBank)}
            className="px-2.5 py-1.5 rounded-lg text-xs font-semibold text-indigo-600 hover:text-indigo-700 bg-indigo-50/70 hover:bg-indigo-100/70 border border-indigo-200/80 transition-colors flex items-center gap-1 cursor-pointer"
          >
            <Plus className="w-3.5 h-3.5" />
            <span>Добавить в текущий список</span>
          </button>
        </div>

        {showAddBank && (
          <form onSubmit={handleAddNewBank} className="flex items-center gap-2 pt-2 border-t border-slate-100 max-w-md">
            <input
              type="text"
              value={newBankInput}
              onChange={(e) => setNewBankInput(e.target.value)}
              placeholder="Название банка для текущей сверки"
              className="flex-1 py-1.5 px-3 border border-slate-300 rounded-lg text-xs focus:ring-1 focus:ring-indigo-500"
              autoFocus
            />
            <button
              type="submit"
              className="px-3 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold rounded-lg shadow-xs transition-colors shrink-0 cursor-pointer"
            >
              Добавить
            </button>
          </form>
        )}
      </div>

      {/* ─── UPLOAD BOXES ─── */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Our Data File */}
        <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-xs">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2 font-semibold text-sm text-slate-900">
              <Upload className="w-4 h-4 text-indigo-600" />
              <span>Ваши данные (Excel / CSV)</span>
            </div>
            {ourFile && (
              <button
                onClick={() => setShowPreviewOur(!showPreviewOur)}
                className="text-xs text-indigo-600 hover:text-indigo-800 font-medium inline-flex items-center gap-1"
              >
                <Eye className="w-3 h-3" />
                <span>{showPreviewOur ? 'Скрыть предпросмотр' : 'Предпросмотр'}</span>
              </button>
            )}
          </div>

          <label className="border-2 border-dashed border-slate-200 hover:border-indigo-400 rounded-xl p-4 flex flex-col items-center justify-center cursor-pointer transition-colors bg-slate-50/50 hover:bg-indigo-50/20">
            <input
              type="file"
              accept=".xlsx,.xls,.csv"
              onChange={(e) => handleFileUpload(e, true)}
              className="hidden"
            />
            <FileSpreadsheet className="w-8 h-8 text-slate-400 mb-1.5" />
            <span className="text-xs font-medium text-slate-700">
              {ourFile ? ourFile.name : 'Нажмите для выбора файла'}
            </span>
            <span className="text-[11px] text-slate-400 mt-0.5">.xlsx, .xls или .csv (до 200 МБ)</span>
          </label>

          {ourFile && (
            <div className="mt-2 text-xs text-slate-500 flex items-center justify-between">
              <span>Строк загружено: <strong className="text-slate-800">{ourFile.rows.length}</strong></span>
              <span>Колонок: <strong className="text-slate-800">{ourFile.columns.length}</strong></span>
            </div>
          )}

          {showPreviewOur && ourFile && (
            <div className="mt-3 overflow-x-auto rounded-lg border border-slate-200 text-xs">
              <table className="min-w-full divide-y divide-slate-200">
                <thead className="bg-slate-50 font-semibold text-slate-700">
                  <tr>
                    {ourFile.columns.slice(0, 5).map(c => <th key={c} className="px-2 py-1 text-left">{c}</th>)}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 bg-white">
                  {ourFile.rows.slice(0, 4).map((r, i) => (
                    <tr key={i}>
                      {ourFile.columns.slice(0, 5).map(c => <td key={c} className="px-2 py-1 text-slate-600 truncate max-w-[120px]">{String(r[c])}</td>)}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Bank Data File */}
        <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-xs">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2 font-semibold text-sm text-slate-900">
              <Upload className="w-4 h-4 text-emerald-600" />
              <span>Данные {selectedBank} (Excel / CSV)</span>
            </div>
            {bankFile && (
              <button
                onClick={() => setShowPreviewBank(!showPreviewBank)}
                className="text-xs text-indigo-600 hover:text-indigo-800 font-medium inline-flex items-center gap-1"
              >
                <Eye className="w-3 h-3" />
                <span>{showPreviewBank ? 'Скрыть предпросмотр' : 'Предпросмотр'}</span>
              </button>
            )}
          </div>

          <label className="border-2 border-dashed border-slate-200 hover:border-emerald-400 rounded-xl p-4 flex flex-col items-center justify-center cursor-pointer transition-colors bg-slate-50/50 hover:bg-emerald-50/20">
            <input
              type="file"
              accept=".xlsx,.xls,.csv"
              onChange={(e) => handleFileUpload(e, false)}
              className="hidden"
            />
            <FileSpreadsheet className="w-8 h-8 text-slate-400 mb-1.5" />
            <span className="text-xs font-medium text-slate-700">
              {bankFile ? bankFile.name : 'Нажмите для выбора файла'}
            </span>
            <span className="text-[11px] text-slate-400 mt-0.5">.xlsx, .xls или .csv (до 200 МБ)</span>
          </label>

          {bankFile && (
            <div className="mt-2 text-xs text-slate-500 flex items-center justify-between">
              <span>Строк загружено: <strong className="text-slate-800">{bankFile.rows.length}</strong></span>
              <span>Колонок: <strong className="text-slate-800">{bankFile.columns.length}</strong></span>
            </div>
          )}

          {showPreviewBank && bankFile && (
            <div className="mt-3 overflow-x-auto rounded-lg border border-slate-200 text-xs">
              <table className="min-w-full divide-y divide-slate-200">
                <thead className="bg-slate-50 font-semibold text-slate-700">
                  <tr>
                    {bankFile.columns.slice(0, 5).map(c => <th key={c} className="px-2 py-1 text-left">{c}</th>)}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 bg-white">
                  {bankFile.rows.slice(0, 4).map((r, i) => (
                    <tr key={i}>
                      {bankFile.columns.slice(0, 5).map(c => <td key={c} className="px-2 py-1 text-slate-600 truncate max-w-[120px]">{String(r[c])}</td>)}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {/* ─── COLUMN MAPPING & RULES ─── */}
      {ourFile && bankFile && (
        <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-xs space-y-6">
          <div className="border-b border-slate-100 pb-4">
            <h2 className="text-base font-bold text-slate-900 flex items-center gap-2">
              <Settings2 className="w-5 h-5 text-slate-700" />
              <span>Настройка колонок и правил сверки</span>
            </h2>
            <p className="text-xs text-slate-500 mt-0.5">
              Укажите соответствие колонок для обеих сторон. Поля были предварительно определены автоматически.
            </p>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Our Column Mapping */}
            <div className="p-4 rounded-xl border border-slate-200 bg-slate-50/40">
              <h3 className="text-xs font-bold text-slate-800 uppercase tracking-wider mb-3">
                <div className="flex items-center gap-1.5"><UploadCloud className="w-4 h-4 text-indigo-600"/> Ваши данные: соответствие колонок</div>
              </h3>
              <div className="grid grid-cols-2 gap-3">
                <div>
                 <label className="flex items-center gap-1 text-[11px] font-semibold text-slate-600 mb-1">
                    <CalendarDays className="w-3 h-3 text-slate-400"/>
                    <span>Дата*</span>
                  </label>
                  <select
                    value={ourDateCol}
                    onChange={(e) => setOurDateCol(e.target.value)}
                    className="w-full text-xs py-1.5 px-2 bg-white border border-slate-200 rounded-lg focus:ring-1 focus:ring-indigo-500"
                  >
                    {ourFile.columns.map(c => <option key={c} value={c}>{c}</option>)}
                  </select>
                </div>
                <div>
                  <label className="block text-[11px] font-semibold text-slate-600 mb-1"><div className="flex items-center gap-1"><Key className="w-3 h-3 text-slate-400"/> RRN*</div></label>
                  <select
                    value={ourRrnCol}
                    onChange={(e) => setOurRrnCol(e.target.value)}
                    className="w-full text-xs py-1.5 px-2 bg-white border border-slate-200 rounded-lg focus:ring-1 focus:ring-indigo-500"
                  >
                    {ourFile.columns.map(c => <option key={c} value={c}>{c}</option>)}
                  </select>
                </div>
                <div>
                  <label className="block text-[11px] font-semibold text-slate-600 mb-1"><div className="flex items-center gap-1"><Coins className="w-3 h-3 text-slate-400"/> Сумма</div></label>
                  <select
                    value={ourAmtCol}
                    onChange={(e) => setOurAmtCol(e.target.value)}
                    className="w-full text-xs py-1.5 px-2 bg-white border border-slate-200 rounded-lg focus:ring-1 focus:ring-indigo-500"
                  >
                    <option value="">(нет)</option>
                    {ourFile.columns.map(c => <option key={c} value={c}>{c}</option>)}
                  </select>
                </div>
                <div>
                  <label className="block text-[11px] font-semibold text-slate-600 mb-1"><div className="flex items-center gap-1"><TagIcon className="w-3 h-3 text-slate-400"/> Статус</div></label>
                  <select
                    value={ourStatusCol}
                    onChange={(e) => setOurStatusCol(e.target.value)}
                    className="w-full text-xs py-1.5 px-2 bg-white border border-slate-200 rounded-lg focus:ring-1 focus:ring-indigo-500"
                  >
                    <option value="">(нет)</option>
                    {ourFile.columns.map(c => <option key={c} value={c}>{c}</option>)}
                  </select>
                </div>
              </div>
            </div>

            {/* Bank Column Mapping */}
            <div className="p-4 rounded-xl border border-slate-200 bg-slate-50/40">
              <h3 className="text-xs font-bold text-slate-800 uppercase tracking-wider mb-3">
                <div className="flex items-center gap-1.5"><Landmark className="w-4 h-4 text-emerald-600"/> Данные банка: соответствие колонок</div>
              </h3>
              <div className="grid grid-cols-3 gap-3">
                <div>
                  <label className="block text-[11px] font-semibold text-slate-600 mb-1">Дата*</label>
                  <select
                    value={bankDateCol}
                    onChange={(e) => setBankDateCol(e.target.value)}
                    className="w-full text-xs py-1.5 px-2 bg-white border border-slate-200 rounded-lg focus:ring-1 focus:ring-indigo-500"
                  >
                    {bankFile.columns.map(c => <option key={c} value={c}>{c}</option>)}
                  </select>
                </div>
                <div>
                  <label className="block text-[11px] font-semibold text-slate-600 mb-1">RRN*</label>
                  <select
                    value={bankRrnCol}
                    onChange={(e) => setBankRrnCol(e.target.value)}
                    className="w-full text-xs py-1.5 px-2 bg-white border border-slate-200 rounded-lg focus:ring-1 focus:ring-indigo-500"
                  >
                    {bankFile.columns.map(c => <option key={c} value={c}>{c}</option>)}
                  </select>
                </div>
                <div>
                  <label className="block text-[11px] font-semibold text-slate-600 mb-1">Сумма</label>
                  <select
                    value={bankAmtCol}
                    onChange={(e) => setBankAmtCol(e.target.value)}
                    className="w-full text-xs py-1.5 px-2 bg-white border border-slate-200 rounded-lg focus:ring-1 focus:ring-indigo-500"
                  >
                    <option value="">(нет)</option>
                    {bankFile.columns.map(c => <option key={c} value={c}>{c}</option>)}
                  </select>
                </div>
                <div>
                  <label className="block text-[11px] font-semibold text-slate-600 mb-1">Статус</label>
                  <select
                    value={bankStatusCol}
                    onChange={(e) => setBankStatusCol(e.target.value)}
                    className="w-full text-xs py-1.5 px-2 bg-white border border-slate-200 rounded-lg focus:ring-1 focus:ring-indigo-500"
                  >
                    <option value="">(нет)</option>
                    {bankFile.columns.map(c => <option key={c} value={c}>{c}</option>)}
                  </select>
                </div>
                <div className="col-span-2">
                  <label className="block text-[11px] font-semibold text-slate-600 mb-1">
                    Terminal ID (TID) EPOS
                  </label>
                  <select
                    value={bankTidCol}
                    onChange={(e) => setBankTidCol(e.target.value)}
                    className="w-full text-xs py-1.5 px-2 bg-white border border-slate-200 rounded-lg focus:ring-1 focus:ring-indigo-500"
                  >
                    <option value="">(нет - без расчета комиссии по EPOS)</option>
                    {bankFile.columns.map(c => <option key={c} value={c}>{c}</option>)}
                  </select>
                </div>
              </div>
            </div>
          </div>

          {/* Advanced Rules Accordion */}
          <div className="border border-slate-200 rounded-xl overflow-hidden">
            <button
              type="button"
              onClick={() => setShowAdvanced(!showAdvanced)}
              className="w-full px-4 py-3 bg-slate-50 flex items-center justify-between text-xs font-bold text-slate-700 hover:bg-slate-100 transition-colors cursor-pointer">
             <span className="flex items-center gap-2">
                <Settings2 className="w-4 h-4 text-slate-500"/> 
                 Расширенные настройки (возвраты, дубликаты, строгий допуск)
            </span>{showAdvanced ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
            </button>

            {showAdvanced && (
              <div className="p-4 space-y-4 bg-white text-xs">
                <div>
                  <label className="block font-semibold text-slate-700 mb-1">
                    1. Маркеры возврата в статусе (через запятую):
                  </label>
                  <input
                    type="text"
                    value={revInput}
                    onChange={(e) => setRevInput(e.target.value)}
                    className="w-full py-1.5 px-3 border border-slate-200 rounded-lg text-xs"
                  />
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block font-semibold text-slate-700 mb-1">Действие в НАШИХ данных:</label>
                    <select
                      value={ourRev}
                      onChange={(e) => setOurRev(e.target.value)}
                      className="w-full py-1.5 px-2 border border-slate-200 rounded-lg text-xs"
                    >
                      <option value="Минусовать сумму">Минусовать сумму</option>
                      <option value="Удалить строку">Удалить строку</option>
                      <option value="Удалить RRN полностью">Удалить RRN полностью</option>
                      <option value="Не обрабатывать">Не обрабатывать</option>
                    </select>
                  </div>
                  <div>
                    <label className="block font-semibold text-slate-700 mb-1">Действие в данных БАНКА:</label>
                    <select
                      value={bankRev}
                      onChange={(e) => setBankRev(e.target.value)}
                      className="w-full py-1.5 px-2 border border-slate-200 rounded-lg text-xs"
                    >
                      <option value="Удалить строку">Удалить строку</option>
                      <option value="Минусовать сумму">Минусовать сумму</option>
                      <option value="Удалить RRN полностью">Удалить RRN полностью</option>
                      <option value="Не обрабатывать">Не обрабатывать</option>
                    </select>
                  </div>
                </div>

                <div className="border-t border-slate-100 pt-3">
                  <label className="block font-semibold text-slate-700 mb-1">2. Действие при обнаружении дубликатов:</label>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                    {[
                      'Ничего не делать (оставить все)',
                      'Оставить первую строку',
                      'Оставить последнюю строку',
                      'Удалить все дубли (и оригинал)',
                    ].map(opt => (
                      <label key={opt} className="flex items-center gap-1.5 p-2 rounded-lg border border-slate-200 bg-slate-50/50 cursor-pointer text-[11px]">
                        <input
                          type="radio"
                          name="dupAction"
                          checked={dupAction === opt}
                          onChange={() => setDupAction(opt)}
                          className="text-indigo-600"
                        />
                        <span>{opt}</span>
                      </label>
                    ))}
                  </div>
                </div>

                <div className="border-t border-slate-100 pt-3">
                  <label className="block font-semibold text-slate-700 mb-1">3. Режим сверки сумм при наличии комиссии EPOS:</label>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                    <label className={`flex items-start gap-2 p-2.5 rounded-lg border cursor-pointer text-xs ${!deductCommission ? 'border-emerald-300 bg-emerald-50/50 text-emerald-950' : 'border-slate-200 bg-slate-50/50 text-slate-700'}`}>
                      <input
                        type="radio"
                        name="deductCommissionRadio"
                        checked={!deductCommission}
                        onChange={() => setDeductCommission(false)}
                        className="mt-0.5 text-emerald-600"
                      />
                      <div>
                        <div className="font-semibold">🟢 Сверять суммы операций брутто (без вычета комиссии)</div>
                        <div className="text-[11px] text-slate-500">Сравниваются номинальные суммы платежей. Рекомендуется, когда файлы содержат исходные суммы покупок.</div>
                      </div>
                    </label>

                    <label className={`flex items-start gap-2 p-2.5 rounded-lg border cursor-pointer text-xs ${deductCommission ? 'border-indigo-300 bg-indigo-50/50 text-indigo-950' : 'border-slate-200 bg-slate-50/50 text-slate-700'}`}>
                      <input
                        type="radio"
                        name="deductCommissionRadio"
                        checked={deductCommission}
                        onChange={() => setDeductCommission(true)}
                        className="mt-0.5 text-indigo-600"
                      />
                      <div>
                        <div className="font-semibold">💳 Сверять зачисление нетто (за вычетом комиссии)</div>
                        <div className="text-[11px] text-slate-500">Из суммы банка вычитается ставка комиссии эквайера из реестра EPOS.</div>
                      </div>
                    </label>
                  </div>
                </div>

                <div className="border-t border-slate-100 pt-3 flex items-center gap-2">
                  <input
                    id="chk-unbind"
                    type="checkbox"
                    checked={unbindMismatches}
                    onChange={(e) => setUnbindMismatches(e.target.checked)}
                    className="rounded text-indigo-600"
                  />
                  <label htmlFor="chk-unbind" className="font-semibold text-slate-800 cursor-pointer">
                    <div className="flex items-center gap-1"><Unlink className="w-4 h-4 text-indigo-500"/> Разрывать связи при расхождении сумм</div>
                  </label>
                  <span className="text-slate-400 text-[11px]">
                    (Транзакции с одинаковым RRN, но разной суммой, будут перемещены в «Несопоставленные»)
                  </span>
                </div>
              </div>
            )}
          </div>

          {/* Run Reconciliation Button */}
          <button
            id="btn-run-recon"
            type="button"
            onClick={handleRunReconciliation}
            disabled={!runReady}
            title={!filesReady ? 'Загрузите оба исходных файла' : !mappingReady ? 'Выберите обязательные колонки даты и RRN' : !amountsReady ? 'Выберите колонки сумм' : 'Запустить сверку'}
            className="w-full py-3 px-4 bg-indigo-600 hover:bg-indigo-700 active:bg-indigo-800 text-white font-semibold text-sm rounded-xl shadow-sm transition-colors flex items-center justify-center gap-2 cursor-pointer disabled:cursor-not-allowed disabled:bg-slate-300 disabled:text-slate-600"
          >
            {isProcessing ? (
              <RefreshCw className="w-4 h-4 animate-spin" />
            ) : (
              <Play className="w-4 h-4 fill-current" />
            )}
            <span>
              {isProcessing
                ? 'Выполняется расчет...'
                : runReady
                  ? 'Запустить сверку транзакций'
                  : 'Заполните обязательные данные для запуска'}
            </span>
          </button>
        </div>
      )}

      {/* ─── RESULTS DISPLAY ─── */}
      {reconData && dynamicCalculations && (
        <div className="space-y-6 pt-2">
          {/* Status Alert Banner */}
          {reconData.matched_count === 0 ? (
            <div className="p-4 rounded-xl bg-rose-50 border border-rose-200 flex items-center gap-3 text-rose-800 text-sm">
              <XCircle className="w-5 h-5 text-rose-600 shrink-0" />
              <span><strong>Ни одного совпадения по RRN!</strong> Проверьте правильность выбранных колонок.</span>
            </div>
          ) : Math.abs(dynamicCalculations.totalDiff) <= tolerance ? (
            <div className="p-4 rounded-xl bg-emerald-50 border border-emerald-200 flex items-center gap-3 text-emerald-800 text-sm">
              <CheckCircle2 className="w-5 h-5 text-emerald-600 shrink-0" />
              <span>
                <strong>Сверка сошлась!</strong> Разница в пределах допуска ({fmt(tolerance)} {currency}).
                {dynamicCalculations.excludedOurCount > 0 || dynamicCalculations.excludedBankCount > 0 ? (
                  <span className="ml-2 text-xs text-emerald-700">
                    (С учётом исключения: {dynamicCalculations.excludedOurCount} у нас + {dynamicCalculations.excludedBankCount} банк)
                  </span>
                ) : null}
              </span>
            </div>
          ) : (
            <div className="p-4 rounded-xl bg-amber-50 border border-amber-200 flex items-center gap-3 text-amber-800 text-sm">
              <AlertTriangle className="w-5 h-5 text-amber-600 shrink-0" />
              <span>
                <strong>Обнаружено расхождение:</strong> {fmt(dynamicCalculations.totalDiff)} {currency}
                {dynamicCalculations.excludedOurCount > 0 || dynamicCalculations.excludedBankCount > 0 ? (
                  <span className="ml-2 text-xs text-amber-700">
                    (Исключено: {dynamicCalculations.excludedOurCount} у нас + {dynamicCalculations.excludedBankCount} банк)
                  </span>
                ) : null}
              </span>
            </div>
          )}

          {/* Metric Dashboard Cards */}
          {/* FIX: min-w-0 on every card + break-words/tabular-nums on the value so large
              formatted sums (with non-breaking thousands separators) wrap instead of
              overflowing the grid and getting clipped by the app's overflow-hidden shell. */}
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
            <div className="min-w-0 bg-white rounded-xl border border-slate-200 p-4 shadow-xs">
              <div className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">Итого (Мы), {currency}</div>
              <div className="text-base font-bold text-slate-900 mt-1 break-words tabular-nums">{fmt(dynamicCalculations.totalOurSum)}</div>
            </div>

            <div className="min-w-0 bg-white rounded-xl border border-slate-200 p-4 shadow-xs">
              <div className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">Итого (Банк), {currency}</div>
              <div className="text-base font-bold text-slate-900 mt-1 break-words tabular-nums">{fmt(dynamicCalculations.totalBankSum)}</div>
            </div>

            <div className="min-w-0 bg-white rounded-xl border border-slate-200 p-4 shadow-xs">
              <div className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">Разница (Δ)</div>
              <div className={`text-base font-bold mt-1 break-words tabular-nums ${Math.abs(dynamicCalculations.totalDiff) <= tolerance ? 'text-emerald-600' : 'text-rose-600'}`}>
                {dynamicCalculations.totalDiff > 0 ? `+${fmt(dynamicCalculations.totalDiff)}` : fmt(dynamicCalculations.totalDiff)}
              </div>
            </div>

            <div className="min-w-0 bg-white rounded-xl border border-slate-200 p-4 shadow-xs">
              <div className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">Точно / Δ сумм</div>
              <div className="text-base font-bold text-slate-900 mt-1 break-words tabular-nums">
                {dynamicCalculations.quality.exactMatched} <span className="text-xs text-slate-400 font-normal">/</span> <span className={reconData.mismatch_count > 0 ? 'text-amber-600' : 'text-slate-500'}>{reconData.mismatch_count}</span>
              </div>
            </div>

            <div className="min-w-0 bg-white rounded-xl border border-slate-200 p-4 shadow-xs col-span-2 md:col-span-1">
              <div className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">Точное совпадение</div>
              <div className="text-base font-bold text-indigo-600 mt-1 break-words tabular-nums">
                {dynamicCalculations.quality.exactMatchRate.toFixed(1)}%
              </div>
              <div className="text-[10px] text-slate-400 mt-0.5">RRN найдено: {dynamicCalculations.quality.rrnMatchRate.toFixed(1)}%</div>
            </div>
          </div>

          {/* Commission & EPOS Analysis Banner */}
          <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-xs flex flex-col lg:flex-row items-start lg:items-center justify-between gap-4">
            <div className="flex flex-wrap items-center gap-4 text-xs">
              <div className="flex items-center gap-2">
                <span className="p-1.5 rounded-lg bg-indigo-50 text-indigo-700">
                  <Building2 className="w-4 h-4" />
                </span>
                <div>
                  <div className="font-bold text-slate-900">
                    Комиссия эквайринга EPOS:
                    <span className="ml-1.5 text-rose-600 font-extrabold tabular-nums">
                      {fmt(dynamicCalculations.adjustedCommission)} {currency}
                    </span>
                  </div>
                  <div className="text-[11px] text-slate-500">
                    Эффективная ставка: <strong className="text-slate-800">{reconData.effective_commission_rate?.toFixed(2) || 0}%</strong> по операциям банка
                  </div>
                </div>
              </div>

              <div className="hidden sm:block border-l border-slate-200 pl-4">
                <span className="text-slate-500">К зачислению (нетто): </span>
                <strong className="text-emerald-700 tabular-nums">
                  {fmt(dynamicCalculations.netBankSettlement)} {currency}
                </strong>
              </div>

              <button
                type="button"
                onClick={() => setActiveTab('terminals')}
                className="px-2.5 py-1 bg-indigo-50 hover:bg-indigo-100 text-indigo-700 text-xs font-semibold rounded-lg transition-colors cursor-pointer"
              >
                Детализация по {dynamicCalculations.adjustedTerminalSummary.length} терминалам →
              </button>
            </div>

            <div className="flex items-center gap-3 pt-2 lg:pt-0 border-t lg:border-t-0 border-slate-100 w-full lg:w-auto justify-end text-xs">
              <span className="text-slate-500 flex items-center gap-1 font-medium">
                <Percent className="w-3.5 h-3.5 text-slate-400"/> Фикс. ставка (%):
              </span>
              <input
                type="number"
                min="0"
                max="100"
                step="0.1"
                value={commissionPct}
                onChange={(e) => setCommissionPct(parseFloat(e.target.value) || 0)}
                className="w-20 px-2 py-1 bg-slate-50 border border-slate-200 rounded-lg text-xs font-semibold text-slate-900"
                title="Ручная проверка комиссии"
              />
              <span className="text-slate-600 tabular-nums font-semibold">
                = {fmt(dynamicCalculations.totalBankSum * (commissionPct / 100))} {currency}
              </span>
            </div>
          </div>

          {/* Tab Navigation */}
          <div className="flex border-b border-slate-200 gap-2 overflow-x-auto">
            <button
              onClick={() => setActiveTab('summary')}
              className={`pb-3 px-3 text-xs font-semibold border-b-2 transition-all whitespace-nowrap cursor-pointer ${
                activeTab === 'summary' ? 'border-indigo-600 text-indigo-700' : 'border-transparent text-slate-500 hover:text-slate-800'
              }`}
            >
              <div className="flex items-center gap-1.5"><CalendarRange className="w-4 h-4"/> Сводка по датам</div>
            </button>
            <button
              onClick={() => setActiveTab('charts')}
              className={`pb-3 px-3 text-xs font-semibold border-b-2 transition-all whitespace-nowrap cursor-pointer ${
                activeTab === 'charts' ? 'border-indigo-600 text-indigo-700' : 'border-transparent text-slate-500 hover:text-slate-800'
              }`}
            >
              <div className="flex items-center gap-1.5"><BarChart2 className="w-4 h-4"/> Графики</div>
            </button>
            <button
              onClick={() => setActiveTab('terminals')}
              className={`pb-3 px-3 text-xs font-semibold border-b-2 transition-all whitespace-nowrap cursor-pointer ${
                activeTab === 'terminals' ? 'border-indigo-600 text-indigo-700' : 'border-transparent text-slate-500 hover:text-slate-800'
              }`}
            >
              <div className="flex items-center gap-1.5">
                <Building2 className="w-4 h-4"/> Терминалы и комиссия ({reconData.terminal_summary?.length || 0})
              </div>
            </button>
            <button
              onClick={() => setActiveTab('unmatched')}
              className={`pb-3 px-3 text-xs font-semibold border-b-2 transition-all whitespace-nowrap cursor-pointer ${
                activeTab === 'unmatched' ? 'border-indigo-600 text-indigo-700' : 'border-transparent text-slate-500 hover:text-slate-800'
              }`}
            >
              <div className="flex items-center gap-1.5"><Search className="w-4 h-4"/> Несопоставленные ({reconData.only_our.length + reconData.only_bank.length})</div>
            </button>
            <button
              onClick={() => setActiveTab('mismatches')}
              className={`pb-3 px-3 text-xs font-semibold border-b-2 transition-all whitespace-nowrap cursor-pointer ${
                activeTab === 'mismatches' ? 'border-indigo-600 text-indigo-700' : 'border-transparent text-slate-500 hover:text-slate-800'
              }`}
            >
              <div className="flex items-center gap-1.5"><AlertCircle className="w-4 h-4"/> Расхождения сумм ({reconData.mismatch_count})</div>
            </button>
            <button
              onClick={() => setActiveTab('dups')}
              className={`pb-3 px-3 text-xs font-semibold border-b-2 transition-all whitespace-nowrap cursor-pointer ${
                activeTab === 'dups' ? 'border-indigo-600 text-indigo-700' : 'border-transparent text-slate-500 hover:text-slate-800'
              }`}
            >
              <div className="flex items-center gap-1.5"><Copy className="w-4 h-4"/> Дубликаты ({reconData.dup_our_c + reconData.dup_bank_c})</div>
            </button>
          </div>

          {/* ─── TAB 0: SUMMARY BY DATES ─── */}
          {activeTab === 'summary' && (
            <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-xs space-y-4">
              <div className="flex items-center justify-between">
                <span className="text-xs text-slate-500">
                  Нажмите на любую строку таблицы, чтобы увидеть детальные расхождения за этот день.
                </span>
                {selectedDrilldownDate && (
                  <button
                    onClick={() => setSelectedDrilldownDate(null)}
                    className="text-xs text-slate-500 hover:text-slate-800 font-medium"
                  >
                    Сбросить выбор
                  </button>
                )}
              </div>

              <div className="overflow-x-auto rounded-xl border border-slate-200 text-xs">
                <table className="min-w-full divide-y divide-slate-200">
                  <thead className="bg-slate-50 font-bold text-slate-700">
                    <tr>
                      <th className="px-3 py-2.5 text-left">Дата</th>
                      <th className="px-3 py-2.5 text-right">Кол-во (Банк)</th>
                      <th className="px-3 py-2.5 text-right">Сумма (Банк)</th>
                      <th className="px-3 py-2.5 text-right bg-slate-100/50">Δ Суммы</th>
                      <th className="px-3 py-2.5 text-right bg-slate-100/50">Δ Кол-во</th>
                      <th className="px-3 py-2.5 text-right">Кол-во (Мы)</th>
                      <th className="px-3 py-2.5 text-right">Сумма (Мы)</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 bg-white">
                    {dynamicCalculations.adjustedSummary.map((row, idx) => {
                      const isTotal = row.date.includes('ИТОГО');
                      const isSelected = selectedDrilldownDate === row.date;
                      const hasDelta = Math.abs(row['Δ суммы']) > tolerance;

                      return (
                        <tr
                          key={idx}
                          onClick={() => !isTotal && setSelectedDrilldownDate(isSelected ? null : row.date)}
                          className={`transition-colors ${isTotal ? 'bg-slate-50 font-bold text-slate-900 border-t-2 border-slate-300' : 'hover:bg-indigo-50/40 cursor-pointer'} ${isSelected ? 'bg-indigo-50/70 font-semibold' : ''}`}
                        >
                          <td className="px-3 py-2 text-slate-800 whitespace-nowrap">{row.date}</td>
                          <td className="px-3 py-2 text-right text-slate-700">{row.Кол_во_в_банке}</td>
                          <td className="px-3 py-2 text-right text-slate-900 font-medium tabular-nums tracking-tight whitespace-nowrap">{fmt(row.Сумма_в_банке)}</td>
                          <td className={`px-3 py-2 text-right font-bold bg-slate-50/50 ${hasDelta ? 'text-rose-600' : 'text-emerald-700'}`}>
                            {row['Δ суммы'] > 0 ? `+${fmt(row['Δ суммы'])}` : fmt(row['Δ суммы'])}
                          </td>
                          <td className={`px-3 py-2 text-right bg-slate-50/50 ${row['Δ кол-во'] !== 0 ? 'text-amber-700 font-semibold' : 'text-slate-500'}`}>
                            {row['Δ кол-во']}
                          </td>
                          <td className="px-3 py-2 text-right text-slate-700">{row.Кол_во_у_нас}</td>
                          <td className="px-3 py-2 text-right text-slate-900 font-medium tabular-nums tracking-tight whitespace-nowrap">{fmt(row.Сумма_у_нас)}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>

              {/* Drilldown Section */}
              {selectedDrilldownDate && (
                <div className="p-4 rounded-xl border border-indigo-200 bg-indigo-50/30 space-y-3">
                  <div className="flex items-center justify-between">
                    <h3 className="text-xs font-bold text-indigo-900 uppercase tracking-wider">
                      Детализация транзакций за: {selectedDrilldownDate}
                    </h3>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {/* Missing in bank for this date */}
                    <div className="bg-white rounded-xl border border-slate-200 p-3">
                      <div className="text-xs font-semibold text-rose-700 mb-2">
                        Отсутствуют в банке ({reconData.only_our.filter(x => x.date_str === selectedDrilldownDate && x.checked).length})
                      </div>
                      <div className="max-h-48 overflow-y-auto text-[11px] space-y-1">
                        {reconData.only_our.filter(x => x.date_str === selectedDrilldownDate).length === 0 ? (
                          <span className="text-slate-400">Нет расхождений</span>
                        ) : (
                          reconData.only_our.filter(x => x.date_str === selectedDrilldownDate).map(x => (
                            <div key={x.RRN} className="flex justify-between border-b border-slate-100 py-1">
                              <span className="font-mono text-slate-700">{x.RRN}</span>
                              <span className="font-semibold text-slate-900">{fmt(x.amount)}</span>
                            </div>
                          ))
                        )}
                      </div>
                    </div>

                    {/* Extra from bank for this date */}
                    <div className="bg-white rounded-xl border border-slate-200 p-3">
                      <div className="text-xs font-semibold text-indigo-700 mb-2">
                        Лишние от банка ({reconData.only_bank.filter(x => x.date_str === selectedDrilldownDate && x.checked).length})
                      </div>
                      <div className="max-h-48 overflow-y-auto text-[11px] space-y-1">
                        {reconData.only_bank.filter(x => x.date_str === selectedDrilldownDate).length === 0 ? (
                          <span className="text-slate-400">Нет расхождений</span>
                        ) : (
                          reconData.only_bank.filter(x => x.date_str === selectedDrilldownDate).map(x => (
                            <div key={x.RRN} className="flex justify-between border-b border-slate-100 py-1">
                              <span className="font-mono text-slate-700">{x.RRN}</span>
                              <span className="font-semibold text-slate-900">{fmt(x.amount)}</span>
                            </div>
                          ))
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* ─── TAB 1: CHARTS ─── */}
          {activeTab === 'charts' && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-xs">
                <h3 className="text-xs font-bold text-slate-800 uppercase tracking-wider mb-4">
                  Сравнение сумм по дням ({currency})
                </h3>
                <div className="h-64">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart
                      data={dynamicCalculations.adjustedSummary.filter(r => !r.date.includes('ИТОГО'))}
                      margin={{ top: 10, right: 10, left: 10, bottom: 20 }}
                    >
                      <XAxis dataKey="date" tick={{ fontSize: 10 }} />
                      <YAxis tick={{ fontSize: 10 }} />
                      <Tooltip formatter={(v: number) => fmt(v)} />
                      <Legend wrapperStyle={{ fontSize: 11 }} />
                      <Bar dataKey="Сумма_у_нас" name="Наши данные" fill="#4f46e5" radius={[4, 4, 0, 0]} />
                      <Bar dataKey="Сумма_в_банке" name="Данные банка" fill="#059669" radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>

              <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-xs">
                <h3 className="text-xs font-bold text-slate-800 uppercase tracking-wider mb-4">
                  Разница (Банк - Мы) по дням
                </h3>
                <div className="h-64">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart
                      data={dynamicCalculations.adjustedSummary.filter(r => !r.date.includes('ИТОГО'))}
                      margin={{ top: 10, right: 10, left: 10, bottom: 20 }}
                    >
                      <XAxis dataKey="date" tick={{ fontSize: 10 }} />
                      <YAxis tick={{ fontSize: 10 }} />
                      <Tooltip formatter={(v: number) => fmt(v)} />
                      <ReferenceLine y={0} stroke="#94a3b8" strokeDasharray="3 3" />
                      {/* FIX: exact palette hex values (indigo/emerald/rose) instead of
                          the previous generic red/blue/green tones. */}
                      <Bar dataKey="Δ суммы" name="Разница">
                        {dynamicCalculations.adjustedSummary
                          .filter(r => !r.date.includes('ИТОГО'))
                          .map((entry, index) => (
                            <Cell
                              key={`cell-${index}`}
                              fill={Math.abs(entry['Δ суммы']) <= tolerance ? '#059669' : entry['Δ суммы'] > 0 ? '#4f46e5' : '#e11d48'}
                            />
                          ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>
            </div>
          )}

          {/* ─── TAB: TERMINALS & EPOS COMMISSION ─── */}
          {activeTab === 'terminals' && (
            <div className="space-y-4">
              {/* Cards row */}
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
                <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-xs">
                  <div className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">Всего терминалов (TID)</div>
                  <div className="text-xl font-bold text-slate-900 mt-1">{reconData.terminal_summary?.length || 0}</div>
                  <div className="text-[11px] text-slate-400 mt-0.5">В текущей банковской выписке</div>
                </div>

                <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-xs">
                  <div className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">Общий оборот терминалов</div>
                  <div className="text-base font-bold text-slate-900 mt-1 break-words tabular-nums">
                    {fmt(reconData.terminal_summary?.reduce((a, b) => a + b.total_volume, 0) || 0)} {currency}
                  </div>
                  <div className="text-[11px] text-slate-400 mt-0.5">Номинальная сумма операций</div>
                </div>

                <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-xs">
                  <div className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">Начислено комиссии EPOS</div>
                  <div className="text-base font-bold text-rose-600 mt-1 break-words tabular-nums">
                    {fmt(reconData.total_commission || 0)} {currency}
                  </div>
                  <div className="text-[11px] text-slate-500 mt-0.5">
                    Средняя ставка: <span className="font-semibold text-slate-700">{reconData.effective_commission_rate?.toFixed(2) || 0}%</span>
                  </div>
                </div>

                <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-xs">
                  <div className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">К зачислению (нетто)</div>
                  <div className="text-base font-bold text-emerald-600 mt-1 break-words tabular-nums">
                    {fmt((reconData.terminal_summary?.reduce((a, b) => a + b.total_volume, 0) || 0) - (reconData.total_commission || 0))} {currency}
                  </div>
                  <div className="text-[11px] text-emerald-700 mt-0.5">Оборот минус комиссия банка</div>
                </div>
              </div>

              {/* Terminals Table */}
              <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-xs">
                <div className="flex items-center justify-between mb-4">
                  <div>
                    <h3 className="text-sm font-bold text-slate-900">Реестр терминалов и аналитика комиссии</h3>
                    <p className="text-xs text-slate-500 mt-0.5">
                      Комиссия рассчитывается по ставке каждого терминала из справочника EPOS по всем совпавшим транзакциям.
                    </p>
                  </div>
                </div>

                <div className="overflow-x-auto">
                  <table className="w-full text-xs text-left">
                    <thead className="bg-slate-50 text-slate-600 font-semibold border-b border-slate-200">
                      <tr>
                        <th className="py-2.5 px-3">TID Терминала</th>
                        <th className="py-2.5 px-3">Банк-эквайер</th>
                        <th className="py-2.5 px-3">Мерчант / Организация</th>
                        <th className="py-2.5 px-3 text-right">Транзакций</th>
                        <th className="py-2.5 px-3 text-right">Оборот ({currency})</th>
                        <th className="py-2.5 px-3 text-right">Ставка %</th>
                        <th className="py-2.5 px-3 text-right">Комиссия ({currency})</th>
                        <th className="py-2.5 px-3 text-right">К зачислению ({currency})</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {reconData.terminal_summary && reconData.terminal_summary.length > 0 ? (
                        reconData.terminal_summary.map((t, idx) => (
                          <tr key={idx} className="hover:bg-slate-50/80 transition-colors">
                            <td className="py-2.5 px-3 font-mono font-bold text-slate-900">{t.terminal_id}</td>
                            <td className="py-2.5 px-3 text-slate-700">{t.bank_acquirer || '—'}</td>
                            <td className="py-2.5 px-3 text-slate-600">
                              {t.legal_entity || t.merchant_id || '—'}
                            </td>
                            <td className="py-2.5 px-3 text-right font-medium text-slate-700">{t.tx_count}</td>
                            <td className="py-2.5 px-3 text-right font-semibold text-slate-900 tabular-nums">{fmt(t.total_volume)}</td>
                            <td className="py-2.5 px-3 text-right font-medium text-indigo-600">{t.commission_pct}%</td>
                            <td className="py-2.5 px-3 text-right font-semibold text-rose-600 tabular-nums">{fmt(t.commission_amount)}</td>
                            <td className="py-2.5 px-3 text-right font-bold text-emerald-600 tabular-nums">{fmt(t.net_volume)}</td>
                          </tr>
                        ))
                      ) : (
                        <tr>
                          <td colSpan={8} className="py-8 text-center text-slate-400">
                            Терминалы не найдены или колонка TID не выбрана в выписке банка.
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}

          {/* ─── TAB 2: UNMATCHED TRANSACTIONS ─── */}
          {activeTab === 'unmatched' && (
            <div className="space-y-4">
              {/* FIX: was bg-blue-50/70 / text-blue-900 / text-blue-600 — switched to
                  indigo to match the rest of the palette (no plain "blue" elsewhere in the app). */}
              <div className="p-3.5 bg-indigo-50/70 border border-indigo-200 rounded-xl text-xs text-indigo-900 flex items-center gap-2">
                <HelpCircle className="w-4 h-4 text-indigo-600 shrink-0" />
                <span>
                  Снимайте галочки с транзакций или исключайте компенсирующие пары — итоговые суммы и разница автоматически пересчитаются в реальном времени!
                </span>
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Left Panel: ONLY OUR */}
                <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-xs space-y-3">
                  <div className="flex items-center justify-between border-b border-slate-100 pb-2">
                    <h3 className="text-xs font-bold text-rose-700 uppercase tracking-wider flex items-center gap-1.5">
                      Отсутствуют в банке ({reconData.only_our.length})
                    </h3>
                  </div>

                  {/* Bulk Controls */}
                  <div className="p-3 bg-slate-50 rounded-xl border border-slate-200 space-y-2 text-xs">
                    <div className="grid grid-cols-2 gap-2">
                      <div>
                        <label className="text-[10px] text-slate-500 font-semibold">Дата:</label>
                        <select
                          value={filterDateOur}
                          onChange={(e) => setFilterDateOur(e.target.value)}
                          className="w-full text-xs p-1 bg-white border border-slate-200 rounded"
                        >
                          <option value="(Все)">(Все даты)</option>
                          {unmatchedOurDates.map(d => (
                            <option key={d} value={d}>{d}</option>
                          ))}
                        </select>
                      </div>
                      <div>
                        <label className="text-[10px] text-slate-500 font-semibold">Статус:</label>
                        <select
                          value={filterStatusOur}
                          onChange={(e) => setFilterStatusOur(e.target.value)}
                          className="w-full text-xs p-1 bg-white border border-slate-200 rounded"
                        >
                          <option value="(Все)">(Все статусы)</option>
                          {unmatchedOurStatuses.map(s => (
                            <option key={s} value={s}>{s}</option>
                          ))}
                        </select>
                      </div>
                    </div>

                    <div className="flex gap-2 pt-1">
                      <button
                        onClick={() => handleBulkToggle(false, true)}
                        className="flex-1 py-1 px-2 bg-white border border-slate-200 hover:bg-slate-100 text-[11px] font-medium rounded cursor-pointer"
                      >
                        Снять галочки
                      </button>
                      <button
                        onClick={() => handleBulkToggle(true, true)}
                        className="flex-1 py-1 px-2 bg-white border border-slate-200 hover:bg-slate-100 text-[11px] font-medium rounded cursor-pointer"
                      >
                        Вернуть галочки
                      </button>
                      <button
                        onClick={() => handleExcludeOffsets(true)}
                        className="py-1 px-2 bg-indigo-50 border border-indigo-200 text-indigo-700 text-[11px] font-medium rounded hover:bg-indigo-100 cursor-pointer"
                        title="Исключить компенсирующие пары возвратов"
                      >
                        Офсеты
                      </button>
                    </div>
                  </div>

                  {/* Table */}
                  <div className="max-h-96 overflow-y-auto rounded-xl border border-slate-200 text-xs">
                    <table className="min-w-full divide-y divide-slate-100">
                      <thead className="bg-slate-50 font-bold text-slate-700 sticky top-0">
                        <tr>
                          <th className="px-2 py-2 w-8 text-center">Вкл.</th>
                          <th className="px-2 py-2 text-left">Дата</th>
                          <th className="px-2 py-2 text-left">RRN</th>
                          <th className="px-2 py-2 text-right">Сумма</th>
                          <th className="px-2 py-2 text-left">Причина</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100 bg-white">
                        {unmatchedOurPageItems.map(({ item, originalIndex: idx }) => (
                          <tr key={idx} className={item.checked ? '' : 'bg-slate-50/70 opacity-60'}>
                            <td className="px-2 py-1.5 text-center">
                              <input
                                type="checkbox"
                                checked={item.checked}
                                onChange={() => handleToggleCheck(idx, true)}
                                className="rounded text-indigo-600"
                              />
                            </td>
                            <td className="px-2 py-1.5 whitespace-nowrap">{item.date_str}</td>
                            <td className="px-2 py-1.5 font-mono text-[11px] text-slate-800">{item.RRN}</td>
                            <td className="px-2 py-1.5 text-right font-semibold text-slate-900 tabular-nums tracking-tight whitespace-nowrap">{fmt(item.amount)}</td>
                            <td className="px-2 py-1.5">
                              <select
                                value={item.reason}
                                onChange={(e) => handleChangeReason(idx, e.target.value, true)}
                                className="text-[11px] p-1 bg-white border border-slate-200 rounded max-w-[120px]"
                              >
                                {REASON_OPTIONS.map(opt => <option key={opt} value={opt}>{opt || '(без причины)'}</option>)}
                              </select>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <div className="flex items-center justify-between gap-2 border border-t-0 border-slate-200 rounded-b-xl bg-white px-3 py-2 text-[11px]">
                    <span className="text-slate-500">
                      {unmatchedOurFiltered.length === 0
                        ? 'Нет строк по текущему фильтру'
                        : `Показано ${(unmatchedPageOur - 1) * UNMATCHED_PAGE_SIZE + 1}–${Math.min(unmatchedPageOur * UNMATCHED_PAGE_SIZE, unmatchedOurFiltered.length)} из ${unmatchedOurFiltered.length}`}
                    </span>
                    <div className="flex items-center gap-1">
                      <button
                        type="button"
                        disabled={unmatchedPageOur <= 1}
                        onClick={() => setUnmatchedPageOur(prev => Math.max(1, prev - 1))}
                        className="rounded-md border border-slate-200 bg-white px-2 py-1 font-medium text-slate-600 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
                      >
                        Назад
                      </button>
                      <span className="min-w-[58px] text-center text-slate-600">
                        {unmatchedPageOur} / {unmatchedOurPageCount}
                      </span>
                      <button
                        type="button"
                        disabled={unmatchedPageOur >= unmatchedOurPageCount}
                        onClick={() => setUnmatchedPageOur(prev => Math.min(unmatchedOurPageCount, prev + 1))}
                        className="rounded-md border border-slate-200 bg-white px-2 py-1 font-medium text-slate-600 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
                      >
                        Далее
                      </button>
                    </div>
                  </div>
                </div>

                {/* Right Panel: ONLY BANK */}
                <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-xs space-y-3">
                  <div className="flex items-center justify-between border-b border-slate-100 pb-2">
                    <h3 className="text-xs font-bold text-indigo-700 uppercase tracking-wider flex items-center gap-1.5">
                      Лишние данные банка ({reconData.only_bank.length})
                    </h3>
                  </div>

                  {/* Bulk Controls */}
                  <div className="p-3 bg-slate-50 rounded-xl border border-slate-200 space-y-2 text-xs">
                    <div className="grid grid-cols-2 gap-2">
                      <div>
                        <label className="text-[10px] text-slate-500 font-semibold">Дата:</label>
                        <select
                          value={filterDateBank}
                          onChange={(e) => setFilterDateBank(e.target.value)}
                          className="w-full text-xs p-1 bg-white border border-slate-200 rounded"
                        >
                          <option value="(Все)">(Все даты)</option>
                          {unmatchedBankDates.map(d => (
                            <option key={d} value={d}>{d}</option>
                          ))}
                        </select>
                      </div>
                      <div>
                        <label className="text-[10px] text-slate-500 font-semibold">Статус:</label>
                        <select
                          value={filterStatusBank}
                          onChange={(e) => setFilterStatusBank(e.target.value)}
                          className="w-full text-xs p-1 bg-white border border-slate-200 rounded"
                        >
                          <option value="(Все)">(Все статусы)</option>
                          {unmatchedBankStatuses.map(s => (
                            <option key={s} value={s}>{s}</option>
                          ))}
                        </select>
                      </div>
                    </div>

                    <div className="flex gap-2 pt-1">
                      <button
                        onClick={() => handleBulkToggle(false, false)}
                        className="flex-1 py-1 px-2 bg-white border border-slate-200 hover:bg-slate-100 text-[11px] font-medium rounded cursor-pointer"
                      >
                        Снять галочки
                      </button>
                      <button
                        onClick={() => handleBulkToggle(true, false)}
                        className="flex-1 py-1 px-2 bg-white border border-slate-200 hover:bg-slate-100 text-[11px] font-medium rounded cursor-pointer"
                      >
                        Вернуть галочки
                      </button>
                      <button
                        onClick={() => handleExcludeOffsets(false)}
                        className="py-1 px-2 bg-indigo-50 border border-indigo-200 text-indigo-700 text-[11px] font-medium rounded hover:bg-indigo-100 cursor-pointer"
                        title="Исключить компенсирующие пары возвратов"
                      >
                        Офсеты
                      </button>
                    </div>
                  </div>

                  {/* Table */}
                  <div className="max-h-96 overflow-y-auto rounded-xl border border-slate-200 text-xs">
                    <table className="min-w-full divide-y divide-slate-100">
                      <thead className="bg-slate-50 font-bold text-slate-700 sticky top-0">
                        <tr>
                          <th className="px-2 py-2 w-8 text-center">Вкл.</th>
                          <th className="px-2 py-2 text-left">Дата</th>
                          <th className="px-2 py-2 text-left">RRN</th>
                          <th className="px-2 py-2 text-right">Сумма</th>
                          <th className="px-2 py-2 text-left">Причина</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100 bg-white">
                        {unmatchedBankPageItems.map(({ item, originalIndex: idx }) => (
                          <tr key={idx} className={item.checked ? '' : 'bg-slate-50/70 opacity-60'}>
                            <td className="px-2 py-1.5 text-center">
                              <input
                                type="checkbox"
                                checked={item.checked}
                                onChange={() => handleToggleCheck(idx, false)}
                                className="rounded text-indigo-600"
                              />
                            </td>
                            <td className="px-2 py-1.5 whitespace-nowrap">{item.date_str}</td>
                            <td className="px-2 py-1.5 font-mono text-[11px] text-slate-800">{item.RRN}</td>
                            <td className="px-2 py-1.5 text-right font-semibold text-slate-900 tabular-nums tracking-tight whitespace-nowrap">{fmt(item.amount)}</td>
                            <td className="px-2 py-1.5">
                              <select
                                value={item.reason}
                                onChange={(e) => handleChangeReason(idx, e.target.value, false)}
                                className="text-[11px] p-1 bg-white border border-slate-200 rounded max-w-[120px]"
                              >
                                {REASON_OPTIONS.map(opt => <option key={opt} value={opt}>{opt || '(без причины)'}</option>)}
                              </select>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <div className="flex items-center justify-between gap-2 border border-t-0 border-slate-200 rounded-b-xl bg-white px-3 py-2 text-[11px]">
                    <span className="text-slate-500">
                      {unmatchedBankFiltered.length === 0
                        ? 'Нет строк по текущему фильтру'
                        : `Показано ${(unmatchedPageBank - 1) * UNMATCHED_PAGE_SIZE + 1}–${Math.min(unmatchedPageBank * UNMATCHED_PAGE_SIZE, unmatchedBankFiltered.length)} из ${unmatchedBankFiltered.length}`}
                    </span>
                    <div className="flex items-center gap-1">
                      <button
                        type="button"
                        disabled={unmatchedPageBank <= 1}
                        onClick={() => setUnmatchedPageBank(prev => Math.max(1, prev - 1))}
                        className="rounded-md border border-slate-200 bg-white px-2 py-1 font-medium text-slate-600 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
                      >
                        Назад
                      </button>
                      <span className="min-w-[58px] text-center text-slate-600">
                        {unmatchedPageBank} / {unmatchedBankPageCount}
                      </span>
                      <button
                        type="button"
                        disabled={unmatchedPageBank >= unmatchedBankPageCount}
                        onClick={() => setUnmatchedPageBank(prev => Math.min(unmatchedBankPageCount, prev + 1))}
                        className="rounded-md border border-slate-200 bg-white px-2 py-1 font-medium text-slate-600 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
                      >
                        Далее
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* ─── TAB 3: AMOUNT MISMATCHES ─── */}
          {activeTab === 'mismatches' && (
            <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-xs space-y-4">
              {reconData.amt_mismatches.length === 0 ? (
                <div className="p-4 rounded-xl bg-emerald-50 text-emerald-800 text-xs flex items-center gap-2">
                  <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                  <span>Нет расхождений в суммах! Все сопоставленные RRN имеют одинаковые суммы.</span>
                </div>
              ) : (
                <div className="overflow-x-auto rounded-xl border border-slate-200 text-xs">
                  <table className="min-w-full divide-y divide-slate-200">
                    <thead className="bg-slate-50 font-bold text-slate-700">
                      <tr>
                        <th className="px-3 py-2 text-left">RRN</th>
                        <th className="px-3 py-2 text-left">Дата (Мы)</th>
                        <th className="px-3 py-2 text-left">Дата (Банк)</th>
                        <th className="px-3 py-2 text-right">Сумма (Мы)</th>
                        <th className="px-3 py-2 text-right">Сумма (Банк)</th>
                        <th className="px-3 py-2 text-right">Δ Разница</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100 bg-white">
                      {reconData.amt_mismatches.map((m, i) => (
                        <tr key={i} className="hover:bg-slate-50">
                          <td className="px-3 py-2 font-mono text-slate-800">{m.RRN}</td>
                          <td className="px-3 py-2 text-slate-600">{m.date_our}</td>
                          <td className="px-3 py-2 text-slate-600">{m.date_bank}</td>
                          <td className="px-3 py-2 text-right text-slate-900 tabular-nums tracking-tight whitespace-nowrap">{fmt(m.net_amount_our)}</td>
                          <td className="px-3 py-2 text-right text-slate-900 tabular-nums tracking-tight whitespace-nowrap">{fmt(m.net_amount_bank)}</td>
                          <td className="px-3 py-2 text-right font-bold text-rose-600">
                            {m['Δ сумма'] > 0 ? `+${fmt(m['Δ сумма'])}` : fmt(m['Δ сумма'])}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}

          {/* ─── TAB 4: DUPLICATES ─── */}
          {activeTab === 'dups' && (
            <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
              {[
                { title: 'Наши данные', rows: reconData.dups_our, count: reconData.dup_our_c, side: 'our' as const },
                { title: 'Данные банка', rows: reconData.dups_bank, count: reconData.dup_bank_c, side: 'bank' as const },
              ].map(group => (
                <div key={group.side} className="bg-white rounded-2xl border border-slate-200 p-5 shadow-xs space-y-3">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <h3 className="text-xs font-bold text-slate-800 uppercase tracking-wider">
                        Дубликаты RRN — {group.title}
                      </h3>
                      <p className="text-[11px] text-slate-500 mt-1">
                        Повторяющиеся RRN показаны строками, как обычные транзакции.
                      </p>
                    </div>
                    <span className="shrink-0 rounded-full bg-indigo-50 border border-indigo-200 px-2.5 py-1 text-[11px] font-bold text-indigo-700">
                      {group.count}
                    </span>
                  </div>

                  {group.count === 0 ? (
                    <div className="p-4 rounded-xl bg-emerald-50 border border-emerald-100 text-xs text-emerald-700">
                      Дубликатов не обнаружено
                    </div>
                  ) : (
                    <div className="max-h-[420px] overflow-auto rounded-xl border border-slate-200">
                      <table className="min-w-full text-[11px]">
                        <thead className="sticky top-0 bg-slate-50 border-b border-slate-200 text-slate-600 font-semibold">
                          <tr>
                            <th className="px-3 py-2 text-left">Дата</th>
                            <th className="px-3 py-2 text-left">RRN</th>
                            {group.side === 'bank' && <th className="px-3 py-2 text-left">TID</th>}
                            <th className="px-3 py-2 text-left">Статус</th>
                            <th className="px-3 py-2 text-right">Сумма</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100 bg-white">
                          {group.rows.map((row, idx) => {
                            const rawDate = group.side === 'bank' ? (row.date_bank ?? row.date) : row.date;
                            const dateText = rawDate == null ? '—' : String(rawDate).slice(0, 10).split('-').reverse().join('.');
                            const amountValue = group.side === 'bank'
                              ? Number(row.net_amount_bank ?? row.raw_amount ?? row.amount ?? 0)
                              : Number(row.net_amount_our ?? row.amount ?? 0);
                            const statusText = group.side === 'bank'
                              ? String(row.status_bank ?? row.status ?? '—')
                              : String(row.status_our ?? row.status ?? '—');

                            return (
                              <tr key={idx} className="hover:bg-slate-50/70 transition-colors">
                                <td className="px-3 py-2 whitespace-nowrap text-slate-600">{dateText}</td>
                                <td className="px-3 py-2 font-mono font-semibold text-slate-900">{String(row.RRN ?? '—')}</td>
                                {group.side === 'bank' && (
                                  <td className="px-3 py-2 font-mono text-slate-600">{String(row.terminal_id ?? '—')}</td>
                                )}
                                <td className="px-3 py-2 text-slate-600">{statusText}</td>
                                <td className="px-3 py-2 text-right font-semibold text-slate-900 tabular-nums">
                                  {fmt(Number.isFinite(amountValue) ? amountValue : 0)}
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}

          {/* ─── EXPORT & SAVE BUTTONS ─── */}
          <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-xs flex flex-col xl:flex-row items-start xl:items-center justify-between gap-5">
            <div>
              <h3 className="text-sm font-bold text-slate-900">Экспорт и фиксация в системе</h3>
              <p className="text-xs text-slate-500 mt-0.5">
                Выгрузите готовый сводный отчет со всеми вкладками в Excel или сохраните результаты в системный архив базы данных.
              </p>
              {saveSuccessMsg && (
                <div className="mt-2 text-xs font-semibold text-emerald-600 flex items-center gap-1.5">
                  <CheckCircle2 className="w-3.5 h-3.5" />
                  <span>{saveSuccessMsg}</span>
                </div>
              )}
            </div>

            <div className="flex flex-wrap items-center gap-3 w-full xl:w-auto justify-end">
              {/* Month Selector for Archive */}
              <div className="flex items-center gap-2 bg-slate-50 border border-slate-200 rounded-xl px-3 py-2 text-xs">
                <CalendarDays className="w-4 h-4 text-indigo-600 shrink-0" />
                <span className="font-semibold text-slate-700 whitespace-nowrap">Месяц архива:</span>
                <select
                  value={selectedArchiveMonth}
                  onChange={(e) => setSelectedArchiveMonth(e.target.value)}
                  className="bg-white border border-slate-300 rounded-lg px-2.5 py-1 text-xs font-bold text-slate-900 focus:outline-none focus:ring-1 focus:ring-indigo-500 cursor-pointer"
                >
                  {availableMonths.map((m) => (
                    <option key={m.value} value={m.value}>
                      {m.label}
                    </option>
                  ))}
                </select>
              </div>

              <button
                id="btn-export-excel"
                type="button"
                onClick={handleExportExcel}
                className="px-4 py-2.5 bg-white border border-slate-300 hover:bg-slate-50 active:bg-slate-100 text-slate-700 text-xs font-semibold rounded-xl shadow-xs transition-colors flex items-center gap-2 cursor-pointer"
              >
                <Download className="w-4 h-4 text-emerald-600" />
                <span>Скачать Excel-отчет</span>
              </button>

              <button
                id="btn-save-db"
                type="button"
                onClick={handleSaveToArchive}
                disabled={isAuditor}
                title={isAuditor ? 'Режим аудитора: сохранение недоступно' : 'Записать в Архив БД'}
                className={`px-4 py-2.5 text-xs font-semibold rounded-xl shadow-xs transition-colors flex items-center gap-2 ${
                  isAuditor
                    ? 'bg-slate-200 text-slate-400 cursor-not-allowed border border-slate-200'
                    : 'bg-indigo-600 hover:bg-indigo-700 active:bg-indigo-800 text-white cursor-pointer'
                }`}
              >
                <Save className="w-4 h-4" />
                <span>Записать в Архив БД</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Modals */}
      <AlertModal
        isOpen={alertState.isOpen}
        title={alertState.title}
        message={alertState.message}
        type={alertState.type}
        onClose={() => setAlertState(prev => ({ ...prev, isOpen: false }))}
      />

      <ConfirmModal
        isOpen={confirmState.isOpen}
        title={confirmState.title}
        message={confirmState.message}
        confirmText={confirmState.confirmText}
        cancelText={confirmState.cancelText}
        isDanger={confirmState.isDanger}
        onConfirm={confirmState.onConfirm}
        onClose={() => setConfirmState(prev => ({ ...prev, isOpen: false }))}
      />
    </div>
  );
};
