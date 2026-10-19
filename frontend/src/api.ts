import { useQuery } from '@tanstack/react-query'

export type Role = 'engineer' | 'reviewer' | 'admin'
export type Verdict = 'PASS' | 'NEEDS_REVIEW' | 'BLOCKED'
export type Severity = 'critical' | 'major' | 'minor'
export type Box = [number, number, number, number]

export interface User {
  username: string
  name: string
  role: Role
}

export interface Account extends User {
  status: 'pending' | 'active' | 'disabled'
}

export interface Comment {
  id: number
  username: string
  text: string
  created_at: string
}

export interface Drawing {
  drawing_no: string
  title: string
  current_rev: string
  status: string
  /** "manual" when an admin added or edited it in the tool; "erp" when it is as the extract gave it. */
  source?: 'erp' | 'manual'
}

export interface RegisterRow extends Drawing {
  class_approval: string | null
}

export type GateStatus = 'CLEAR' | 'WARN' | 'BLOCKED'

export interface WorkOrder {
  order_no: string
  drawing_no: string
  rev: string
  state: string
}

export interface GateRow extends WorkOrder {
  current_rev: string | null
  check_id: number | null
  status: GateStatus
  reasons: string[]
}

export interface ClassApproval {
  id: number
  drawing_no: string
  rev: string
  submitted_to: string
  submitted_on: string
  state: string
  days_waiting: number | null
  title?: string
}

export interface DrawingDetail {
  drawing: Drawing
  revisions: { id: number; rev: string; status: string; issued_on: string }[]
  change_notes: { ecn_no: string; from_rev: string; to_rev: string; changed_on: string; description: string; reason: string }[]
  bom: { id: number; rev: string; part_no: string; description: string; material: string; thickness_mm: number; qty: number }[]
  work_orders: GateRow[]
  class_approvals: ClassApproval[]
}

export interface BomValues {
  material: string
  thickness_mm: string
  qty: string
}

export interface BomRow {
  part_no: string
  description: string
  drawing: BomValues | null
  erp: BomValues | null
  result: 'match' | 'mismatch' | 'not_in_erp' | 'not_on_drawing'
}

export interface Impact {
  from_revision: string
  work_orders: WorkOrder[]
  purchase_orders: { po_no: string; part_no: string; qty: number; state: string; change: string }[]
}

export interface Finding {
  rule_id: string
  rule_name: string
  severity: Severity
  clause: string
  standard: string
  evidence: string
  bbox: Box | null
}

export interface Decision {
  decision: 'APPROVED' | 'REJECTED'
  is_override: boolean
  reason: string
  decided_by: string
  decided_at: string
}

export interface CheckSummary {
  id: number
  drawing_no: string
  revision: string
  filename: string
  verdict: Verdict
  submitted_by: string
  created_at: string
  decision: Decision | null
}

export interface Change {
  area: string
  kind: 'added' | 'removed' | 'changed'
  what: string
  old: string | null
  new: string | null
  old_bbox: Box | null
  new_bbox: Box | null
}

export interface RevisionDiff {
  from_revision: string
  page_size: [number, number]
  changes: Change[]
  change_note: { ecn_no: string; from_rev: string; to_rev: string; changed_on: string; description: string; reason: string } | null
}

export interface Check extends CheckSummary {
  extracted: {
    source: 'vector' | 'scan'
    /** For a scan: how sure OCR was (0 to 100), and what it read if the person corrected the value. */
    fields: Record<string, { value: string; bbox: Box | null; confidence?: number; read_as?: string }>
    page_size: [number, number]
    confirmed_by?: string
  }
  register_row: { title: string; current_rev: string; status: string } | null
  revision_diff: RevisionDiff | null
  bom_check: BomRow[] | null
  explanation: { text: string; model: string; unsupported_numbers: string[]; requested_by: string; at: string } | null
  impact: Impact | null
  findings: Finding[]
  comments: Comment[]
}

/** What the tool read from a drawing before any check is run. */
export interface ReadResult {
  source: 'vector' | 'scan'
  fields: Record<string, { value: string; confidence: number | null }>
  parts: number
}

export const TITLE_BLOCK_FIELDS: [string, string][] = [
  ['drawing_no', 'Drawing number'],
  ['title', 'Title'],
  ['revision', 'Revision'],
  ['status', 'Status'],
  ['material', 'Material'],
  ['thickness_mm', 'Plate thickness (mm)'],
  ['date', 'Date'],
  ['hull_no', 'Hull number'],
  ['zone', 'Structural zone'],
  ['spacing_mm', 'Stiffener spacing (mm)'],
]

/** Below this OCR confidence a value is marked for a closer look. */
export const LOW_CONFIDENCE = 90

export interface Rule {
  id: string
  name: string
  type: string
  severity: Severity
  clause: string
  standard: string
  edition: number
  params?: Record<string, unknown>
  /** approved: runs. draft: never approved. changed: edited in the rule file since it was approved, so it does not run. */
  state: 'approved' | 'draft' | 'changed'
  approved_by: string | null
  approved_at: string | null
  approval_note: string | null
}

export interface AuditEntry {
  id: number
  at: string
  username: string
  role: string
  action: string
  target: string
  detail: string
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message)
  }
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, init)
  if (!res.ok) {
    const detail = (await res.json().catch(() => null))?.detail
    throw new ApiError(res.status, typeof detail === 'string' ? detail : `The request failed (${res.status}).`)
  }
  return res.status === 204 ? (undefined as T) : res.json()
}

export const postJson = <T>(path: string, body?: unknown) =>
  api<T>(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body ?? {}) })

/** The signed-in user, or null when nobody is signed in. */
export const useMe = () =>
  useQuery({
    queryKey: ['me'],
    queryFn: () =>
      api<User>('/auth/me').catch((e) => {
        if (e instanceof ApiError && e.status === 401) return null
        throw e
      }),
  })

export const useChecks = () => useQuery({ queryKey: ['checks'], queryFn: () => api<CheckSummary[]>('/checks') })
export const useCheck = (id: string) => useQuery({ queryKey: ['checks', id], queryFn: () => api<Check>(`/checks/${id}`) })
export const useRegister = () => useQuery({ queryKey: ['register'], queryFn: () => api<RegisterRow[]>('/register') })
export const useDrawing = (drawingNo: string) =>
  useQuery({ queryKey: ['register', drawingNo], queryFn: () => api<DrawingDetail>(`/register/${encodeURIComponent(drawingNo)}`) })
export const useGate = () => useQuery({ queryKey: ['gate'], queryFn: () => api<GateRow[]>('/gate') })
export const useClassApprovals = () => useQuery({ queryKey: ['class-approvals'], queryFn: () => api<ClassApproval[]>('/class-approvals') })
export const useRules = () => useQuery({ queryKey: ['rules'], queryFn: () => api<Rule[]>('/rules') })
export const useSettings = () =>
  useQuery({ queryKey: ['settings'], queryFn: () => api<{ explainer: { enabled: boolean; model: string } }>('/settings'), staleTime: Infinity })
export const useUsers = () => useQuery({ queryKey: ['users'], queryFn: () => api<Account[]>('/users') })
export const useAudit = () => useQuery({ queryKey: ['audit'], queryFn: () => api<AuditEntry[]>('/audit') })

/** What each role may do. The server enforces the same rules; this only decides what to show. */
export const can = {
  decide: (user: User) => user.role === 'reviewer' || user.role === 'admin',
  readAudit: (user: User) => user.role === 'reviewer' || user.role === 'admin',
  manageUsers: (user: User) => user.role === 'admin',
  editRegister: (user: User) => user.role === 'admin',
  approveRules: (user: User) => user.role === 'admin',
  recordApprovals: (user: User) => user.role === 'reviewer' || user.role === 'admin',
}

export const formatTime = (iso: string) => new Date(iso).toLocaleString('en-GB', { dateStyle: 'medium', timeStyle: 'short' })
