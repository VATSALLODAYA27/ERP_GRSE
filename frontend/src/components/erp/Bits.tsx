import {
  CheckCircleFilled,
  ClockCircleOutlined,
  CloseCircleFilled,
  ExclamationCircleFilled,
  InfoCircleFilled,
  RobotOutlined,
  StopFilled,
  SyncOutlined,
} from '@ant-design/icons'
import { Form, Input, Modal, Progress, Result, Table, Tag, Tooltip, Typography, theme } from 'antd'
import { useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'

import { ApiError, formatTime, type AuditEntry } from '../../api'
import { moneyShort, type RiskLevel } from '../../erpApi'

// Every status has a colour, an icon and a text label, so it never depends on colour alone (as in Tags.tsx).

type Spec = { label: string; color?: string; icon?: ReactNode }

const STATES: Record<string, Record<string, Spec>> = {
  pr: {
    SUBMITTED: { label: 'Submitted', color: 'processing', icon: <ClockCircleOutlined /> },
    APPROVED: { label: 'Approved', color: 'success', icon: <CheckCircleFilled /> },
    REJECTED: { label: 'Rejected', color: 'error', icon: <CloseCircleFilled /> },
    CONVERTED: { label: 'Converted to PO', color: 'cyan', icon: <CheckCircleFilled /> },
  },
  po: {
    DRAFT: { label: 'Draft', icon: <ClockCircleOutlined /> },
    APPROVED: { label: 'Approved', color: 'processing', icon: <CheckCircleFilled /> },
    SENT: { label: 'Sent', color: 'geekblue', icon: <SyncOutlined /> },
    PART_RECEIVED: { label: 'Part received', color: 'warning', icon: <ExclamationCircleFilled /> },
    RECEIVED: { label: 'Received', color: 'success', icon: <CheckCircleFilled /> },
    CLOSED: { label: 'Closed', icon: <CheckCircleFilled /> },
    CANCELLED: { label: 'Cancelled', color: 'error', icon: <StopFilled /> },
  },
  invoice: {
    MATCHED: { label: 'Matched', color: 'success', icon: <CheckCircleFilled /> },
    EXCEPTION: { label: 'Exception', color: 'warning', icon: <ExclamationCircleFilled /> },
    APPROVED: { label: 'Approved', color: 'processing', icon: <CheckCircleFilled /> },
    PAID: { label: 'Paid', color: 'green', icon: <CheckCircleFilled /> },
    REJECTED: { label: 'Rejected', color: 'error', icon: <CloseCircleFilled /> },
  },
  risk: {
    HIGH: { label: 'High', color: 'error', icon: <StopFilled /> },
    MEDIUM: { label: 'Medium', color: 'warning', icon: <ExclamationCircleFilled /> },
    LOW: { label: 'Low', color: 'success', icon: <CheckCircleFilled /> },
  },
  severity: {
    high: { label: 'High', color: 'error', icon: <CloseCircleFilled /> },
    medium: { label: 'Medium', color: 'warning', icon: <ExclamationCircleFilled /> },
    low: { label: 'Low', color: 'processing', icon: <InfoCircleFilled /> },
  },
  stock: {
    OK: { label: 'OK', color: 'success', icon: <CheckCircleFilled /> },
    REORDER: { label: 'Reorder', color: 'warning', icon: <ExclamationCircleFilled /> },
    STOCK_OUT: { label: 'Stock-out', color: 'error', icon: <StopFilled /> },
  },
  followup: {
    DRAFT: { label: 'Draft', color: 'processing', icon: <ClockCircleOutlined /> },
    APPROVED: { label: 'Approved to send', color: 'success', icon: <CheckCircleFilled /> },
    DISMISSED: { label: 'Dismissed', icon: <CloseCircleFilled /> },
  },
  flag: {
    OPEN: { label: 'Open', color: 'warning', icon: <ExclamationCircleFilled /> },
    RESOLVED: { label: 'Resolved', color: 'success', icon: <CheckCircleFilled /> },
  },
  move: {
    OPENING: { label: 'Opening' },
    RECEIPT: { label: 'Receipt', color: 'green' },
    ISSUE: { label: 'Issue', color: 'blue' },
    TRANSFER_IN: { label: 'Transfer in', color: 'cyan' },
    TRANSFER_OUT: { label: 'Transfer out', color: 'cyan' },
    ADJUST: { label: 'Adjustment', color: 'gold' },
  },
  source: {
    MANUAL: { label: 'Manual' },
    WORK_ORDER: { label: 'Work order', color: 'blue' },
    AI_REORDER: { label: 'AI reorder', color: 'purple', icon: <RobotOutlined /> },
  },
  grade: {
    A: { label: 'Grade A', color: 'success' },
    B: { label: 'Grade B', color: 'warning' },
    C: { label: 'Grade C', color: 'error' },
  },
  account: {
    ASSET: { label: 'Asset', color: 'blue' },
    LIABILITY: { label: 'Liability', color: 'orange' },
    EQUITY: { label: 'Equity', color: 'purple' },
    INCOME: { label: 'Income', color: 'green' },
    EXPENSE: { label: 'Expense', color: 'red' },
  },
}

export type StateKind = keyof typeof STATES

/** The options for a status filter, in the order the statuses happen. */
export const stateOptions = (kind: StateKind) => Object.entries(STATES[kind]).map(([value, s]) => ({ value, label: s.label, text: s.label }))

const words = (value: string) => value.replace(/_/g, ' ').toLowerCase().replace(/^./, (c) => c.toUpperCase())

/** A status as a tag. An unknown value still shows, in plain words. */
export function StateTag({ kind, value }: { kind: StateKind; value: string | null | undefined }) {
  if (!value) return <Typography.Text type="secondary">—</Typography.Text>
  const s = STATES[kind][value] ?? { label: words(value) }
  return (
    <Tag color={s.color} icon={s.icon}>
      {s.label}
    </Tag>
  )
}

/** Who wrote a follow-up: the language model or the fixed template. */
export function WrittenByTag({ by }: { by: string }) {
  return by === 'model' ? (
    <Tag color="purple" icon={<RobotOutlined />}>
      written by AI model
    </Tag>
  ) : (
    <Tag>template</Tag>
  )
}

export function MsmeTag() {
  return (
    <Tooltip title="Micro, small or medium enterprise">
      <Tag color="cyan">MSME</Tag>
    </Tooltip>
  )
}

export function CriticalTag() {
  return <Tag color="red">Critical</Tag>
}

// ---- Links between records ----

const enc = encodeURIComponent

export const VendorLink = ({ id, name }: { id: string | null | undefined; name?: string | null }) =>
  id ? <Link to={`/vendors/${enc(id)}`}>{name || id}</Link> : <>{name || '—'}</>
export const ItemLink = ({ code }: { code: string }) => <Link to={`/items/${enc(code)}`}>{code}</Link>
export const PoLink = ({ no }: { no: string | null | undefined }) => (no ? <Link to={`/purchase-orders/${enc(no)}`}>{no}</Link> : <>—</>)
export const PrLink = ({ no }: { no: string | null | undefined }) => (no ? <Link to={`/requisitions/${enc(no)}`}>{no}</Link> : <>—</>)
export const InvoiceLink = ({ no }: { no: string }) => <Link to={`/invoices/${enc(no)}`}>{no}</Link>
export const GrnLink = ({ no }: { no: string }) => <Link to={`/receipts/${enc(no)}`}>{no}</Link>

/** Work orders as tags. Each opens the Release Gate, where the Drawing Release Gate says whether the job may be released. */
export function WorkOrderTags({ orders }: { orders: (string | null | undefined)[] | null | undefined }) {
  const list = (orders ?? []).filter((o): o is string => !!o)
  if (!list.length) return <Typography.Text type="secondary">—</Typography.Text>
  return (
    <>
      {list.map((order) => (
        <Tooltip key={order} title="Open the Release Gate">
          <Link to="/gate">
            <Tag color="blue" style={{ marginBottom: 2 }}>
              {order}
            </Tag>
          </Link>
        </Tooltip>
      ))}
    </>
  )
}

const BY_TYPE: Record<string, string> = {
  GRN: '/receipts/',
  RECEIPT: '/receipts/',
  GOODS_RECEIPT: '/receipts/',
  INVOICE: '/invoices/',
  VENDOR_INVOICE: '/invoices/',
  PO: '/purchase-orders/',
  PURCHASE_ORDER: '/purchase-orders/',
  PROC_ORDER: '/purchase-orders/',
  PR: '/requisitions/',
  REQUISITION: '/requisitions/',
  VENDOR_BILL: '/invoices/',
  ITEM: '/items/',
  VENDOR: '/vendors/',
  DRAWING: '/register/',
  CHECK: '/checks/',
}

const BY_PREFIX: [string, string][] = [
  ['PO-', '/purchase-orders/'],
  ['PR-', '/requisitions/'],
  ['GRN-', '/receipts/'],
  ['VB-', '/invoices/'],
  ['V-', '/vendors/'],
]

/** The page of the record a reference points at, by its type or else by its number's prefix; null when it has no page. */
export function recordPath(refType: string | null | undefined, refNo: string | null | undefined) {
  if (!refNo) return null
  const base = BY_TYPE[(refType ?? '').toUpperCase().replace(/[\s-]/g, '_')] ?? BY_PREFIX.find(([prefix]) => refNo.startsWith(prefix))?.[1]
  return base ? base + enc(refNo) : null
}

export function RefLink({ type, no }: { type?: string | null; no: string | null | undefined }) {
  const path = recordPath(type, no)
  if (!no) return <Typography.Text type="secondary">—</Typography.Text>
  return path ? <Link to={path}>{no}</Link> : <>{no}</>
}

/** An audit log target such as "purchase order PO-4500123", linked to the record it names. */
export function AuditTarget({ target }: { target: string }) {
  const at = target.lastIndexOf(' ')
  const path = at > 0 ? recordPath(target.slice(0, at), target.slice(at + 1)) : null
  return path ? <Link to={path}>{target}</Link> : <>{target || '—'}</>
}

/** A record's own audit trail: who did what to it, newest first. */
export function AuditTable({ entries }: { entries: AuditEntry[] | undefined }) {
  return (
    <Table<AuditEntry>
      size="small"
      rowKey="id"
      pagination={false}
      dataSource={entries}
      locale={{ emptyText: 'No entries.' }}
      columns={[
        { title: 'Time', dataIndex: 'at', width: 180, render: (t) => formatTime(t) },
        { title: 'User', dataIndex: 'username', width: 120 },
        { title: 'Action', dataIndex: 'action', width: 180, render: (a) => <Tag>{a}</Tag> },
        { title: 'Target', dataIndex: 'target', width: 220, render: (t) => <AuditTarget target={t} /> },
        { title: 'Detail', dataIndex: 'detail' },
      ]}
    />
  )
}

// ---- Small charts ----

/** How likely a delivery is to be late, 0 to 100, as a short coloured bar. */
export function RiskBar({ score, level }: { score: number | null | undefined; level: RiskLevel | null | undefined }) {
  const { token } = theme.useToken()
  if (score === null || score === undefined) return <Typography.Text type="secondary">—</Typography.Text>
  const color = level === 'HIGH' ? token.colorError : level === 'MEDIUM' ? token.colorWarning : token.colorSuccess
  return (
    <Progress
      percent={Math.max(0, Math.min(100, score))}
      size={[84, 8]}
      strokeColor={color}
      format={() => <span style={{ fontVariantNumeric: 'tabular-nums' }}>{Math.round(score)}</span>}
      aria-label={`Risk score ${Math.round(score)} of 100`}
      style={{ margin: 0, whiteSpace: 'nowrap' }}
    />
  )
}

/** A plain bar chart in CSS: one labelled bar per row, scaled to the largest. */
export function BarList({ rows, format = moneyShort }: { rows: { key: string; label: ReactNode; value: number; to?: string }[]; format?: (value: number) => string }) {
  const max = Math.max(1, ...rows.map((r) => r.value))
  return (
    <div className="bar-list">
      {rows.map((row) => {
        const body = (
          <>
            <div className="bar-head">
              <span>{row.label}</span>
              <strong>{format(row.value)}</strong>
            </div>
            <div className="bar-track">
              <span style={{ width: `${Math.max(1.5, (row.value / max) * 100)}%` }} />
            </div>
          </>
        )
        return row.to ? (
          <Link key={row.key} to={row.to} className="bar-row">
            {body}
          </Link>
        ) : (
          <div key={row.key} className="bar-row">
            {body}
          </div>
        )
      })}
    </div>
  )
}

/** What a detail page shows when its record cannot be loaded: "not found" for a 404, else the server's message. */
export function LoadError({ error, what, back, backLabel }: { error: Error; what: string; back: string; backLabel: string }) {
  const notFound = error instanceof ApiError && error.status === 404
  return <Result status={notFound ? '404' : 'error'} title={notFound ? `${what} not found` : error.message} extra={<Link to={back}>{backLabel}</Link>} />
}

// ---- Dialogs ----

/**
 * Open and close state for a dialog. Each opening gets a new key, so the form inside starts fresh with that opening's
 * prefilled values: render it as `<XForm key={d.key} open={d.open} ... />`.
 */
export function useDialog<T = undefined>() {
  const [state, setState] = useState<{ open: boolean; key: number; data?: T }>({ open: false, key: 0 })
  return {
    ...state,
    show: (data?: T) => setState((s) => ({ open: true, key: s.key + 1, data })),
    hide: () => setState((s) => ({ ...s, open: false })),
  }
}

/** A dialog that asks for a reason or a note before an action; `required` makes it compulsory. */
export function ReasonModal({
  open,
  title,
  okText,
  label = 'Reason',
  description,
  required,
  danger,
  loading,
  onSubmit,
  onClose,
}: {
  open: boolean
  title: string
  okText: string
  label?: string
  description?: ReactNode
  required?: boolean
  danger?: boolean
  loading?: boolean
  onSubmit: (text: string) => void
  onClose: () => void
}) {
  const [form] = Form.useForm<{ text: string }>()
  return (
    <Modal
      open={open}
      title={title}
      okText={okText}
      okButtonProps={{ danger }}
      confirmLoading={loading}
      onOk={() => form.submit()}
      onCancel={onClose}
      // The next opening starts with an empty box.
      afterClose={() => form.resetFields()}
      destroyOnHidden
    >
      {description && <Typography.Paragraph type="secondary">{description}</Typography.Paragraph>}
      <Form form={form} layout="vertical" requiredMark={false} onFinish={({ text }) => onSubmit((text ?? '').trim())}>
        <Form.Item
          name="text"
          label={required ? label : `${label} (optional)`}
          rules={required ? [{ required: true, whitespace: true, message: `Enter a ${label.toLowerCase()}` }] : []}
        >
          <Input.TextArea rows={3} maxLength={500} showCount autoFocus />
        </Form.Item>
      </Form>
    </Modal>
  )
}
