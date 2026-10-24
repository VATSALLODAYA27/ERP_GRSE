// SENTINEL, the ERP half of the site: types, queries and actions for procurement, inventory, finance and the control tower.
// Field names follow docs/SENTINEL_ERP_SPEC.md section 2.
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { App as AntApp } from 'antd'
import dayjs from 'dayjs'

import { api, postJson, type AuditEntry } from './api'

// ---- Formatting ----

const INR = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 })
const INR_PAISE = new Intl.NumberFormat('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
const QTY = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 2 })

const missing = (value: number | null | undefined): value is null | undefined => value === null || value === undefined || Number.isNaN(value)

/** Rupees with Indian grouping: ₹12,34,567. `paise` keeps two decimals, for unit prices. */
export function money(value: number | null | undefined, paise = false) {
  if (missing(value)) return '—'
  return `${value < 0 ? '-' : ''}₹${(paise ? INR_PAISE : INR).format(Math.abs(value))}`
}

/** The short form for number tiles: ₹1.24 Cr, ₹8.50 L, or the full amount below a lakh. */
export function moneyShort(value: number | null | undefined) {
  if (missing(value)) return '—'
  const abs = Math.abs(value)
  const sign = value < 0 ? '-' : ''
  if (abs >= 1e7) return `${sign}₹${(abs / 1e7).toFixed(2)} Cr`
  if (abs >= 1e5) return `${sign}₹${(abs / 1e5).toFixed(2)} L`
  return money(value)
}

/** A quantity with Indian grouping and at most two decimals. */
export const qty = (value: number | null | undefined) => (missing(value) ? '—' : QTY.format(value))

/** A percentage given as 0 to 100. */
export const pct = (value: number | null | undefined) => (missing(value) ? '—' : `${QTY.format(Math.round(value * 10) / 10)}%`)

/** "19 Oct 2026". Accepts an ISO date or date-time. */
export function fmtDate(iso: string | null | undefined) {
  if (!iso) return '—'
  const day = dayjs(iso)
  return day.isValid() ? day.format('D MMM YYYY') : iso
}

/** Today as the API writes dates. */
export const today = () => dayjs().format('YYYY-MM-DD')

// ---- Types ----

export type PrStatus = 'SUBMITTED' | 'APPROVED' | 'REJECTED' | 'CONVERTED'
export type PrSource = 'MANUAL' | 'WORK_ORDER' | 'AI_REORDER'
export type PoStatus = 'DRAFT' | 'APPROVED' | 'SENT' | 'PART_RECEIVED' | 'RECEIVED' | 'CLOSED' | 'CANCELLED'
export type InvoiceStatus = 'MATCHED' | 'EXCEPTION' | 'APPROVED' | 'PAID' | 'REJECTED'
export type RiskLevel = 'HIGH' | 'MEDIUM' | 'LOW'
export type FlagSeverity = 'high' | 'medium' | 'low'
export type StockStatus = 'OK' | 'REORDER' | 'STOCK_OUT'
export type MoveKind = 'OPENING' | 'RECEIPT' | 'ISSUE' | 'TRANSFER_IN' | 'TRANSFER_OUT' | 'ADJUST'
export type AccountType = 'ASSET' | 'LIABILITY' | 'EQUITY' | 'INCOME' | 'EXPENSE'

/** Purchase orders above this need an admin to approve them. */
export const APPROVAL_LIMIT = 1_000_000

export interface VendorMetrics {
  grade: 'A' | 'B' | 'C'
  /** 0 to 100. */
  on_time_pct: number
  avg_delay_days: number
  /** 0 to 100. */
  rejection_pct: number
  spend_ytd: number
  open_po_value: number
}

export interface Vendor extends VendorMetrics {
  vendor_id: string
  name: string
  city: string
  category: string
  msme: boolean
  payment_terms_days: number
  lead_time_days: number
  gstin?: string
  active?: boolean
}

/** One row of a vendor's payables ledger, with the balance after it. shortcut: the spec does not pin these names. */
export interface VendorLedgerRow {
  on_date: string
  je_no?: string
  source_type?: string
  source_no?: string
  narration?: string
  debit: number
  credit: number
  balance: number
}

export interface VendorDetail extends Vendor {
  scorecard: VendorMetrics & { orders_closed: number }
  orders: PoSummary[]
  payables: { balance: number; entries: VendorLedgerRow[] }
}

export interface Item {
  item_code: string
  description: string
  category: string
  uom: string
  grade: string
  std_price: number
  reorder_level: number
  critical: boolean
  on_hand: number
  on_order: number
  stock_value: number
  avg_cost: number
  status: StockStatus
  reorder_qty?: number
  lead_time_days?: number
  preferred_vendor_id?: string | null
  preferred_vendor_name?: string | null
}

export interface StockMove {
  id: number
  on_date: string
  item_code: string
  description: string
  store_code: string
  kind: MoveKind
  qty: number
  unit_cost: number
  value: number
  ref_type: string
  ref_no: string
  work_order: string | null
  created_by: string
  note?: string | null
}

export interface ItemDetail extends Item {
  by_store: { store_code: string; store_name: string; qty: number; value: number }[]
  moves: StockMove[]
  open_orders: { po_no: string; vendor_name: string; qty: number; received_qty: number; promised_date: string; risk_level: RiskLevel | null }[]
  where_used: { drawing_no: string; rev: string; part_no: string; qty: number }[]
}

export interface Store {
  store_code: string
  name: string
  location: string
  stock_value: number
  items: number
}

export interface RequisitionSummary {
  pr_no: string
  created_on: string
  requested_by: string
  work_order: string | null
  source: PrSource
  status: PrStatus
  lines: number
  value: number
}

export interface RequisitionLine {
  id: number
  item_code: string
  description: string
  qty: number
  need_by: string
  po_no: string | null
  est_value: number
}

export interface Requisition extends Omit<RequisitionSummary, 'lines' | 'value'> {
  value?: number
  decided_by?: string | null
  note?: string | null
  lines: RequisitionLine[]
  audit?: AuditEntry[]
}

export interface PoSummary {
  po_no: string
  vendor_id: string
  vendor_name: string
  created_on: string
  status: PoStatus
  value: number
  lines: number
  /** 0 to 100. */
  received_pct: number
  next_promised: string | null
  risk_level: RiskLevel | null
  risk_score: number | null
}

export interface LineRisk {
  score: number
  level: RiskLevel
  predicted_date: string
  reasons: string[]
}

export interface PoLine {
  id: number
  item_code: string
  description: string
  qty: number
  unit_price: number
  value: number
  promised_date: string
  received_qty: number
  work_order: string | null
  risk: LineRisk | null
}

/** A goods receipt as lists show it. shortcut: the spec names only the table columns, so the extras are optional. */
export interface ReceiptSummary {
  grn_no: string
  po_no: string
  received_on: string
  store_code: string
  received_by: string
  vendor_id?: string
  vendor_name?: string
  store_name?: string
  lines?: number
  qty_received?: number
  qty_accepted?: number
  qty_rejected?: number
  value?: number
}

export interface GrnLine {
  id: number
  po_line_id: number
  item_code: string
  description?: string
  qty_received: number
  qty_accepted: number
  qty_rejected: number
  reject_reason: string | null
}

export interface Receipt extends Omit<ReceiptSummary, 'lines'> {
  lines: GrnLine[]
  journal?: JournalEntry[]
  flags?: Flag[]
}

export interface Flag {
  id: number
  kind: string
  severity: FlagSeverity
  ref_type: string
  ref_no: string
  message: string
  detected_at: string
  status: 'OPEN' | 'RESOLVED'
  resolved_by: string | null
  resolution_note: string | null
}

export interface InvoiceSummary {
  inv_no: string
  vendor_invoice_no: string
  vendor_id?: string
  vendor_name: string
  po_no: string
  invoice_date: string
  due_date: string
  status: InvoiceStatus
  total: number
  /** A count, or the flags themselves; both are handled. */
  flags?: number | (Flag | string)[]
}

export interface MatchLine {
  item_code: string
  po_qty: number
  po_price: number
  received_qty: number
  invoiced_qty: number
  invoiced_price: number
  qty_ok: boolean
  price_ok: boolean
  price_variance_pct: number
}

export interface Match {
  ok: boolean
  lines: MatchLine[]
  notes: string[]
}

export interface Payment {
  pay_no: string
  inv_no?: string
  vendor_id?: string
  paid_on: string
  amount: number
  mode: 'NEFT' | 'RTGS'
  paid_by: string
}

export interface JournalLine {
  account_code: string
  account_name: string
  debit: number
  credit: number
  vendor_id: string | null
  item_code: string | null
}

export interface JournalEntry {
  je_no: string
  on_date: string
  source_type: string
  source_no: string
  narration: string
  created_by: string
  total: number
  lines?: JournalLine[]
}

export interface Invoice extends Omit<InvoiceSummary, 'flags'> {
  amount: number
  tax: number
  approved_by: string | null
  approval_reason: string | null
  lines: { id?: number; item_code: string; description?: string; qty: number; unit_price: number }[]
  match: Match | null
  payments: Payment[]
  journal: JournalEntry[]
  flags: (Flag | string)[]
  audit?: AuditEntry[]
}

export interface Followup {
  id: number
  po_no: string
  vendor_id: string
  vendor_name?: string
  created_at: string
  risk_level: RiskLevel
  subject: string
  body: string
  status: 'DRAFT' | 'APPROVED' | 'DISMISSED'
  decided_by: string | null
  written_by: 'model' | 'template'
}

export interface PurchaseOrder {
  po_no: string
  vendor_id: string
  vendor_name?: string
  pr_no: string | null
  created_on: string
  buyer: string
  status: PoStatus
  approved_by: string | null
  note: string | null
  value?: number
  /** 0 to 100, by value. */
  received_pct?: number
  vendor?: Partial<Vendor>
  lines: PoLine[]
  receipts: ReceiptSummary[]
  invoices: InvoiceSummary[]
  followups: Followup[]
  journal: JournalEntry[]
  audit: AuditEntry[]
}

export interface LedgerAccount {
  code: string
  name: string
  type: AccountType
  debit: number
  credit: number
  balance: number
}

export interface TrialBalance {
  rows: { code: string; name: string; type: AccountType; debit: number; credit: number }[]
  total_debit: number
  total_credit: number
  balanced: boolean
}

export interface PayablesRow {
  vendor_id: string
  name: string
  balance: number
  current: number
  d1_30: number
  d31_60: number
  d61_90: number
  over_90: number
  next_due: string | null
}

export interface RiskRow {
  po_no: string
  line_id: number
  vendor_id: string
  vendor_name: string
  item_code: string
  description: string
  qty_open: number
  promised_date: string
  predicted_date: string
  days_late_predicted: number
  /** 0 to 100. */
  score: number
  level: RiskLevel
  reasons: string[]
  impacted_work_orders: string[]
  value_open: number
}

export interface Overview {
  kpis: {
    open_po_value: number
    open_po_count: number
    at_risk_count: number
    at_risk_value: number
    stock_value: number
    stock_outs: number
    reorder_count: number
    payables_due_7d: number
    anomalies_open: number
    followups_pending: number
  }
  spend_by_category: { category: string; value: number }[]
  stock_by_store: { store_code: string; value: number }[]
  top_risks: RiskRow[]
  recent_flags: Flag[]
}

export interface ReorderRow {
  item_code: string
  description: string
  uom: string
  on_hand: number
  on_order: number
  demand_open: number
  reorder_level: number
  net_need: number
  suggested_qty: number
  vendor_id: string | null
  vendor_name: string | null
  est_value: number
  reason: string
}

// ---- Queries ----

const enc = encodeURIComponent

export const useVendors = () => useQuery({ queryKey: ['vendors'], queryFn: () => api<Vendor[]>('/vendors') })
export const useVendor = (id: string) => useQuery({ queryKey: ['vendors', id], queryFn: () => api<VendorDetail>(`/vendors/${enc(id)}`) })
export const useItems = () => useQuery({ queryKey: ['items'], queryFn: () => api<Item[]>('/items') })
export const useItem = (code: string | undefined) =>
  useQuery({ queryKey: ['items', code], queryFn: () => api<ItemDetail>(`/items/${enc(code ?? '')}`), enabled: !!code })
export const useStores = () => useQuery({ queryKey: ['stores'], queryFn: () => api<Store[]>('/stores') })
export const useStockMoves = () => useQuery({ queryKey: ['stock-moves'], queryFn: () => api<StockMove[]>('/stock/moves') })

export const useRequisitions = () => useQuery({ queryKey: ['requisitions'], queryFn: () => api<RequisitionSummary[]>('/requisitions') })
export const useRequisition = (no: string) => useQuery({ queryKey: ['requisitions', no], queryFn: () => api<Requisition>(`/requisitions/${enc(no)}`) })
export const usePurchaseOrders = () => useQuery({ queryKey: ['purchase-orders'], queryFn: () => api<PoSummary[]>('/purchase-orders') })
export const usePurchaseOrder = (no: string) =>
  useQuery({ queryKey: ['purchase-orders', no], queryFn: () => api<PurchaseOrder>(`/purchase-orders/${enc(no)}`), enabled: !!no })
export const useReceipts = () => useQuery({ queryKey: ['receipts'], queryFn: () => api<ReceiptSummary[]>('/receipts') })
export const useReceipt = (no: string | undefined) =>
  useQuery({ queryKey: ['receipts', no], queryFn: () => api<Receipt>(`/receipts/${enc(no ?? '')}`), enabled: !!no })
export const useInvoices = () => useQuery({ queryKey: ['invoices'], queryFn: () => api<InvoiceSummary[]>('/invoices') })
export const useInvoice = (no: string | undefined) =>
  useQuery({ queryKey: ['invoices', no], queryFn: () => api<Invoice>(`/invoices/${enc(no ?? '')}`), enabled: !!no })

export const useAccounts = () => useQuery({ queryKey: ['ledger', 'accounts'], queryFn: () => api<LedgerAccount[]>('/ledger/accounts') })
export const useJournal = () => useQuery({ queryKey: ['ledger', 'journal'], queryFn: () => api<JournalEntry[]>('/ledger/journal') })
export const useTrialBalance = () => useQuery({ queryKey: ['ledger', 'trial-balance'], queryFn: () => api<TrialBalance>('/ledger/trial-balance') })
export const usePayables = () => useQuery({ queryKey: ['ledger', 'payables'], queryFn: () => api<{ vendors: PayablesRow[]; total: number }>('/ledger/payables') })
export const useVendorLedger = (id: string | undefined) =>
  useQuery({ queryKey: ['ledger', 'vendor', id], queryFn: () => api<VendorLedgerRow[]>(`/ledger/vendor/${enc(id ?? '')}`), enabled: !!id })

export const useOverview = () => useQuery({ queryKey: ['intel', 'overview'], queryFn: () => api<Overview>('/intel/overview') })
export const useDeliveryRisk = () => useQuery({ queryKey: ['intel', 'delivery-risk'], queryFn: () => api<RiskRow[]>('/intel/delivery-risk') })
export const useFollowups = (status?: Followup['status']) =>
  useQuery({ queryKey: ['intel', 'followups', status ?? 'all'], queryFn: () => api<Followup[]>(`/intel/followups${status ? `?status=${status}` : ''}`) })
export const useReorder = () => useQuery({ queryKey: ['intel', 'reorder'], queryFn: () => api<ReorderRow[]>('/intel/reorder') })
export const useAnomalies = (status?: Flag['status']) =>
  useQuery({ queryKey: ['intel', 'anomalies', status ?? 'all'], queryFn: () => api<Flag[]>(`/intel/anomalies${status ? `?status=${status}` : ''}`) })

// ---- Actions ----

/** The cached lists each kind of action changes. Every action is audited, so the audit log is always refreshed too. */
export const AFFECTS = {
  requisition: ['requisitions', 'intel'],
  order: ['purchase-orders', 'requisitions', 'vendors', 'items', 'intel'],
  receipt: ['purchase-orders', 'receipts', 'items', 'stores', 'stock-moves', 'ledger', 'vendors', 'intel'],
  invoice: ['invoices', 'purchase-orders', 'ledger', 'vendors', 'intel'],
  stock: ['items', 'stores', 'stock-moves', 'ledger', 'intel'],
  intel: ['intel', 'purchase-orders'],
} as const

/**
 * A POST that refreshes what it changed and reports the outcome in a toast: the server's own message when it refuses.
 * Pass per-call `onSuccess` to `mutate` to close a dialog or move to the new record.
 */
export function useAction<V = void, R = unknown>(call: (vars: V) => Promise<R>, affects: readonly string[], success?: string | ((result: R, vars: V) => string)) {
  const queryClient = useQueryClient()
  const { message } = AntApp.useApp()
  return useMutation({
    mutationFn: call,
    onSuccess: (result, vars) => {
      for (const key of [...affects, 'audit']) queryClient.invalidateQueries({ queryKey: [key] })
      const text = typeof success === 'function' ? success(result, vars) : success
      if (text) message.success(text)
    },
    onError: (error) => {
      message.error(error.message)
    },
  })
}

export interface NewRequisition {
  work_order?: string
  note?: string
  lines: { item_code: string; qty: number; need_by: string }[]
}

export interface NewOrder {
  vendor_id: string
  note?: string
  lines: { item_code: string; qty: number; unit_price: number; promised_date: string; work_order?: string }[]
}

export interface ReceiveGoods {
  store_code: string
  received_on?: string
  lines: { line_id: number; qty_received: number; qty_accepted: number; reject_reason?: string }[]
}

export interface NewInvoice {
  vendor_invoice_no: string
  po_no: string
  invoice_date: string
  lines: { item_code: string; qty: number; unit_price: number }[]
}

export const erp = {
  createRequisition: (body: NewRequisition) => postJson<Requisition>('/requisitions', body),
  approveRequisition: (no: string, reason?: string) => postJson<Requisition>(`/requisitions/${enc(no)}/approve`, { reason }),
  rejectRequisition: (no: string, reason: string) => postJson<Requisition>(`/requisitions/${enc(no)}/reject`, { reason }),
  convertRequisition: (no: string) => postJson<{ orders: string[] }>(`/requisitions/${enc(no)}/convert`),
  createOrder: (body: NewOrder) => postJson<PurchaseOrder>('/purchase-orders', body),
  approveOrder: (no: string) => postJson<PurchaseOrder>(`/purchase-orders/${enc(no)}/approve`),
  sendOrder: (no: string) => postJson<PurchaseOrder>(`/purchase-orders/${enc(no)}/send`),
  receive: (no: string, body: ReceiveGoods) => postJson<Receipt>(`/purchase-orders/${enc(no)}/receive`, body),
  createInvoice: (body: NewInvoice) => postJson<Invoice>('/invoices', body),
  approveInvoice: (no: string, reason?: string) => postJson<Invoice>(`/invoices/${enc(no)}/approve`, { reason }),
  rejectInvoice: (no: string, reason: string) => postJson<Invoice>(`/invoices/${enc(no)}/reject`, { reason }),
  pay: (no: string, body: { mode: 'NEFT' | 'RTGS'; paid_on: string }) => postJson<Payment>(`/invoices/${enc(no)}/pay`, body),
  issue: (body: { item_code: string; store_code: string; qty: number; work_order: string; note?: string }) => postJson<StockMove>('/stock/issue', body),
  transfer: (body: { item_code: string; from_store: string; to_store: string; qty: number; note?: string }) => postJson<unknown>('/stock/transfer', body),
  adjust: (body: { item_code: string; store_code: string; qty: number; note: string }) => postJson<StockMove>('/stock/adjust', body),
  draftFollowups: (body: { po_no: string } | { all_high: true }) => postJson<DraftResult>('/intel/followups/draft', body),
  approveFollowup: (id: number) => postJson<Followup>(`/intel/followups/${id}/approve`),
  dismissFollowup: (id: number) => postJson<Followup>(`/intel/followups/${id}/dismiss`),
  reorderRequisition: (itemCodes: string[]) => postJson<Requisition>('/intel/reorder/requisition', { item_codes: itemCodes }),
  scanAnomalies: () => postJson<{ added: number }>('/intel/anomalies/scan'),
  resolveAnomaly: (id: number, note: string) => postJson<Flag>(`/intel/anomalies/${id}/resolve`, { note }),
}

/** What a draft call answers: the follow-ups it wrote, and the orders skipped because a draft is already waiting. */
export type DraftResult = { created?: Followup[]; skipped?: unknown[] } | Followup[]

/** How many follow-ups a draft call wrote, whatever shape the server answered in. */
export const draftedCount = (result: DraftResult | null | undefined) =>
  Array.isArray(result) ? result.length : Array.isArray(result?.created) ? result.created.length : undefined
