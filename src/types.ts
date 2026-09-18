export type Role = 'admin' | 'finance_manager' | 'accountant_acquiring' | 'auditor' | 'accountant';

export interface PermissionOverrides {
  allow: string[];
  deny: string[];
}

export interface User {
  id: number;
  username: string;
  role: Role;
  permissions?: string[];
  permission_overrides?: PermissionOverrides;
}

export interface ReconciliationModuleManifest {
  id: string;
  name: string;
  version: string;
  description: string;
  category: string;
  icon: string;
  author: string;
  status: 'active' | 'draft' | 'deprecated';
  workspace?: string | null;
  required_permissions: string[];
  available_permissions?: string[];
  required_files: Array<{
    key: string;
    label: string;
  }>;
}

export interface EposTerminal {
  terminal_id: string;
  merchant_id?: string;
  bank_acquirer: string;
  legal_entity?: string;
  commission_pct: number;
  is_active: boolean;
}

export interface AuditLog {
  id: number;
  timestamp: string;
  username: string;
  action: string;
  details: string;
}

export interface TerminalSummaryItem {
  terminal_id: string;
  merchant_id?: string;
  bank_acquirer?: string;
  legal_entity?: string;
  tx_count: number;
  total_volume: number;
  commission_pct: number;
  commission_amount: number;
  net_volume: number;
}

export interface ReconciliationArchive {
  id: number;
  timestamp: string;
  username: string;
  bank_name: string;
  total_our: number;
  total_bank: number;
  difference: number;
  matched_count: number;
  mismatch_count: number;
  only_our_count: number;
  only_bank_count: number;
  period_month?: string;
  total_commission?: number;
  terminals_summary?: TerminalSummaryItem[];
  run_id?: string;
  source_our_name?: string;
  source_bank_name?: string;
  config?: Record<string, any>;
}

export interface SystemSettings {
  amount_tolerance: number;
  currency: string;
  dayfirst?: boolean;
}

export interface RawRow {
  [key: string]: any;
}

export interface ReconciliationConfig {
  our_date: string;
  our_rrn: string;
  our_amt: string | null;
  our_status: string | null;
  bank_date: string;
  bank_rrn: string;
  bank_amt: string | null;
  bank_status: string | null;
  bank_tid: string | null;
  rev_words: string[];
  our_rev: string;
  bank_rev: string;
  dup_action: string;
  unbind_mismatches: boolean;
  tolerance: number;
  deduct_commission?: boolean;
}

export interface DateSummaryRow {
  date: string;
  Кол_во_у_нас: number;
  Кол_во_в_банке: number;
  'Δ кол-во': number;
  Сумма_у_нас: number;
  Сумма_в_банке: number;
  'Δ суммы': number;
}

export interface UnmatchedRow {
  checked: boolean;
  reason: string;
  date_str: string;
  RRN: string;
  amount: number | null;
  status?: string;
  terminal_id?: string;
  commission_pct?: number;
  raw?: RawRow;
}

export interface AmountMismatchRow {
  RRN: string;
  date_our: string;
  date_bank: string;
  net_amount_our: number | null;
  net_amount_bank: number | null;
  'Δ сумма': number | null;
  amount_issue?: string;
  status_our?: string;
  status_bank?: string;
}

export interface ReconciliationResult {
  summary: DateSummaryRow[];
  only_our: UnmatchedRow[];
  only_bank: UnmatchedRow[];
  amt_mismatches: AmountMismatchRow[];
  dups_our: RawRow[];
  dups_bank: RawRow[];
  dup_our_c: number;
  dup_bank_c: number;
  matched_count: number;
  mismatch_count: number;
  terminal_summary?: TerminalSummaryItem[];
  total_commission?: number;
  effective_commission_rate?: number;
  comm_only_diff_count?: number;
  deduct_commission?: boolean;
  data_quality?: {
    our?: { missing_date?: number; invalid_date?: number; empty_rrn?: number; missing_amount?: number; invalid_amount?: number };
    bank?: { missing_date?: number; invalid_date?: number; empty_rrn?: number; missing_amount?: number; invalid_amount?: number };
  };
  run_id?: string;
  run_timestamp?: string;
  detected_months?: string[];
  merged_rows: Array<{
    date_str: string;
    RRN: string;
    type: 'both' | 'left_only' | 'right_only';
    net_amount_our?: number;
    net_amount_bank?: number;
    status_our?: string;
    status_bank?: string;
  }>;
  dup_action: string;
}

export interface PermissionCatalogItem {
  id: string;
  label: string;
}

export interface PermissionCatalogGroup {
  id: string;
  name: string;
  type: 'module' | 'platform';
  module_id?: string;
  status?: 'active' | 'draft' | 'deprecated';
  permissions: PermissionCatalogItem[];
}

export interface PermissionCatalog {
  roles: Record<string, string[]>;
  groups: PermissionCatalogGroup[];
}

