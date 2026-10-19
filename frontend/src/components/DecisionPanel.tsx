import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Alert, Button, Card, Descriptions, Flex, Input, Popconfirm, Typography } from 'antd'
import { useState } from 'react'

import { can, formatTime, postJson, type Check, type Decision, type User } from '../api'
import { DecisionTag, ErrorAlert, VERDICT } from './Tags'

// A decision that simply follows the verdict needs no reason; the server enforces the same rule.
const FOLLOWS_VERDICT: Record<string, Decision['decision']> = { PASS: 'APPROVED', BLOCKED: 'REJECTED' }

export default function DecisionPanel({ check, me }: { check: Check; me: User }) {
  const queryClient = useQueryClient()
  // The draft is kept for this browser tab, so a page refresh does not lose what the reviewer has typed.
  const draftKey = `decision-reason-${check.id}`
  const [reason, setReasonState] = useState(() => sessionStorage.getItem(draftKey) ?? '')
  const setReason = (value: string) => {
    setReasonState(value)
    sessionStorage.setItem(draftKey, value)
  }
  const decide = useMutation({
    mutationFn: (decision: Decision['decision']) => postJson<Check>(`/checks/${check.id}/decision`, { decision, reason }),
    onSuccess: (updated) => {
      sessionStorage.removeItem(draftKey)
      queryClient.setQueryData(['checks', String(check.id)], updated)
      queryClient.invalidateQueries({ queryKey: ['checks'], exact: true })
      queryClient.invalidateQueries({ queryKey: ['audit'] })
      // A decision can clear or block work orders, on the gate page and on the drawing's own page.
      queryClient.invalidateQueries({ queryKey: ['gate'] })
      queryClient.invalidateQueries({ queryKey: ['register'] })
    },
  })

  const d = check.decision
  if (d) {
    return (
      <Card title="Release decision">
        <Descriptions column={1} size="small">
          <Descriptions.Item label="Decision">
            <DecisionTag decision={d} />
          </Descriptions.Item>
          <Descriptions.Item label="Decided by">{d.decided_by}</Descriptions.Item>
          <Descriptions.Item label="Time">{formatTime(d.decided_at)}</Descriptions.Item>
          <Descriptions.Item label="Reason">{d.reason || 'None given (decision follows the verdict)'}</Descriptions.Item>
        </Descriptions>
        {d.is_override && (
          <Alert type="warning" showIcon style={{ marginTop: 12 }} message="This decision went against the tool's verdict. It is recorded in the audit log." />
        )}
      </Card>
    )
  }

  if (!can.decide(me)) {
    return (
      <Card title="Release decision">
        <Alert type="info" showIcon message="Awaiting a decision" description="A reviewer or the admin approves or rejects a release. You can add a comment below." />
      </Card>
    )
  }

  // Two people: whoever uploaded a drawing does not also release it. The server enforces the same rule.
  if (me.role !== 'admin' && check.submitted_by === me.username) {
    return (
      <Card title="Release decision">
        <Alert type="info" showIcon message="You submitted this check" description="Another reviewer or the admin must approve or reject it. You can add a comment below." />
      </Card>
    )
  }

  const hasReason = reason.trim() !== ''
  const needsReason = (decision: Decision['decision']) => FOLLOWS_VERDICT[check.verdict] !== decision
  const overridesBlock = check.verdict === 'BLOCKED'

  return (
    <Card title="Release decision" className="no-print">
      <Typography.Paragraph>
        The tool's verdict is <strong>{VERDICT[check.verdict].label}</strong>. The final call is yours, and it cannot be changed afterwards.
      </Typography.Paragraph>
      <Typography.Text strong>
        <label htmlFor="decision-reason">Reason</label>
      </Typography.Text>
      <Input.TextArea
        id="decision-reason"
        rows={4}
        maxLength={1000}
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        placeholder="Why this drawing can or cannot be released"
        style={{ margin: '4px 0' }}
      />
      <Typography.Paragraph type="secondary" style={{ fontSize: 12 }}>
        {needsReason('APPROVED') && needsReason('REJECTED')
          ? 'Required for either decision.'
          : `Required to ${needsReason('APPROVED') ? 'approve' : 'reject'}, because that goes against the verdict.`}
      </Typography.Paragraph>
      <ErrorAlert error={decide.error} />
      <Flex gap={8} vertical>
        <Popconfirm
          title={overridesBlock ? 'Override the block and approve release?' : 'Approve this drawing for release?'}
          okText="Approve"
          onConfirm={() => decide.mutate('APPROVED')}
        >
          <Button type="primary" danger={overridesBlock} block loading={decide.isPending} disabled={needsReason('APPROVED') && !hasReason}>
            {overridesBlock ? 'Override and approve release' : 'Approve for release'}
          </Button>
        </Popconfirm>
        <Popconfirm title="Reject this drawing for release?" okText="Reject" onConfirm={() => decide.mutate('REJECTED')}>
          <Button block loading={decide.isPending} disabled={needsReason('REJECTED') && !hasReason}>
            Reject
          </Button>
        </Popconfirm>
      </Flex>
    </Card>
  )
}
