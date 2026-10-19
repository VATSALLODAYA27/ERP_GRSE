import { CheckCircleFilled, ClockCircleOutlined, CloseCircleFilled, ExclamationCircleFilled, InfoCircleFilled, StopFilled } from '@ant-design/icons'
import { Alert, Tag } from 'antd'
import type { ReactNode } from 'react'

import type { Decision, GateStatus, Role, Severity, Verdict } from '../api'
import { TONE } from '../theme'

// Every status has a colour, an icon and a text label, so it never depends on colour alone.

export const VERDICT: Record<Verdict, { label: string; color: string; tone: string; icon: ReactNode }> = {
  PASS: { label: 'PASS', color: 'success', tone: TONE.good, icon: <CheckCircleFilled /> },
  NEEDS_REVIEW: { label: 'NEEDS REVIEW', color: 'warning', tone: TONE.warn, icon: <ExclamationCircleFilled /> },
  BLOCKED: { label: 'BLOCKED', color: 'error', tone: TONE.bad, icon: <StopFilled /> },
}

export const SEVERITY: Record<Severity, { label: string; color: string; tone: string; icon: ReactNode }> = {
  critical: { label: 'Critical', color: 'error', tone: TONE.bad, icon: <CloseCircleFilled /> },
  major: { label: 'Major', color: 'warning', tone: TONE.warn, icon: <ExclamationCircleFilled /> },
  minor: { label: 'Minor', color: 'processing', tone: TONE.info, icon: <InfoCircleFilled /> },
}

export const ROLE_LABEL: Record<Role, string> = { engineer: 'Engineer', reviewer: 'Reviewer', admin: 'Admin' }

export const GATE: Record<GateStatus, { label: string; color: string; icon: ReactNode }> = {
  CLEAR: { label: 'Clear', color: 'success', icon: <CheckCircleFilled /> },
  WARN: { label: 'Warn', color: 'warning', icon: <ExclamationCircleFilled /> },
  BLOCKED: { label: 'Blocked', color: 'error', icon: <StopFilled /> },
}

export function GateTag({ status }: { status: GateStatus }) {
  const g = GATE[status]
  return (
    <Tag color={g.color} icon={g.icon}>
      {g.label}
    </Tag>
  )
}

/** Class or customer approval state. */
export function ApprovalTag({ state }: { state: string | null }) {
  if (!state) return <Tag>Not submitted</Tag>
  if (state === 'APPROVED') return <Tag color="success" icon={<CheckCircleFilled />}>Approved</Tag>
  if (state === 'AWAITING') return <Tag color="warning" icon={<ClockCircleOutlined />}>Awaiting</Tag>
  return <Tag color="error" icon={<ExclamationCircleFilled />}>{state[0] + state.slice(1).toLowerCase()}</Tag>
}

export function VerdictTag({ verdict }: { verdict: Verdict }) {
  const v = VERDICT[verdict]
  return (
    <Tag color={v.color} icon={v.icon}>
      {v.label}
    </Tag>
  )
}

export function SeverityTag({ severity }: { severity: Severity }) {
  const s = SEVERITY[severity]
  return (
    <Tag color={s.color} icon={s.icon}>
      {s.label}
    </Tag>
  )
}

/** Register status, as a solid pill. */
export function StatusTag({ status }: { status: string }) {
  const color = status === 'APPROVED' ? TONE.good : status === 'SUPERSEDED' ? TONE.bad : TONE.neutral
  return <Tag color={color}>{status}</Tag>
}

export function DecisionTag({ decision }: { decision: Decision | null }) {
  if (!decision) return <Tag icon={<ClockCircleOutlined />}>Awaiting decision</Tag>
  const approved = decision.decision === 'APPROVED'
  return (
    <Tag color={approved ? 'success' : 'error'} icon={approved ? <CheckCircleFilled /> : <CloseCircleFilled />}>
      {approved ? 'Approved' : 'Rejected'}
      {decision.is_override && ' (override)'}
    </Tag>
  )
}

export function ErrorAlert({ error }: { error: Error | null }) {
  return error ? <Alert type="error" showIcon message={error.message} style={{ marginBottom: 16 }} /> : null
}
