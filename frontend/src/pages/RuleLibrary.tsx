import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Alert, Button, Card, Input, Popconfirm, Table, Tag, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useState } from 'react'

import { can, formatTime, postJson, useRules, type Rule, type User } from '../api'
import { ErrorAlert, SeverityTag } from '../components/Tags'

const STATE: Record<Rule['state'], { label: string; color?: string }> = {
  approved: { label: 'Approved', color: 'success' },
  changed: { label: 'Changed since approval (not run)', color: 'warning' },
  draft: { label: 'Draft (not run)' },
}

/** The rules, with who approved each. A rule is defined in the rule file and approved here; only approved rules run. */
export default function RuleLibrary({ me }: { me: User }) {
  const queryClient = useQueryClient()
  const rules = useRules()
  const [note, setNote] = useState('')
  const change = useMutation({
    mutationFn: ({ id, action }: { id: string; action: 'approval' | 'withdrawal' }) => postJson<Rule>(`/rules/${id}/${action}`, action === 'approval' ? { note } : undefined),
    onSuccess: () => {
      setNote('')
      queryClient.invalidateQueries({ queryKey: ['rules'] })
      queryClient.invalidateQueries({ queryKey: ['audit'] })
    },
  })

  const columns: ColumnsType<Rule> = [
    { title: 'ID', dataIndex: 'id', width: 90, render: (id) => <strong>{id}</strong> },
    { title: 'Rule', dataIndex: 'name' },
    { title: 'Check type', dataIndex: 'type', render: (type) => <Typography.Text code>{type}</Typography.Text> },
    { title: 'Clause', dataIndex: 'clause' },
    { title: 'Standard and edition', render: (_, r) => `${r.standard}, ${r.edition}` },
    { title: 'Severity', dataIndex: 'severity', render: (s) => <SeverityTag severity={s} /> },
    {
      title: 'State',
      dataIndex: 'state',
      filters: Object.entries(STATE).map(([value, s]) => ({ value, text: s.label })),
      onFilter: (value, r) => r.state === value,
      render: (state: Rule['state'], r) => (
        <>
          <Tag color={STATE[state].color}>{STATE[state].label}</Tag>
          {r.approved_by && r.approved_at && (
            <div style={{ fontSize: 12 }}>
              <Typography.Text type="secondary">
                {state === 'changed' ? 'Earlier content approved by' : 'by'} {r.approved_by}, {formatTime(r.approved_at)}
              </Typography.Text>
            </div>
          )}
        </>
      ),
    },
  ]
  if (can.approveRules(me)) {
    columns.push({
      title: 'Action',
      render: (_, r) =>
        r.state === 'approved' ? (
          <Popconfirm title={`Withdraw ${r.id}? New checks will no longer run it.`} okText="Withdraw" onConfirm={() => change.mutate({ id: r.id, action: 'withdrawal' })}>
            <Button size="small" danger>
              Withdraw
            </Button>
          </Popconfirm>
        ) : (
          <Popconfirm
            title={`Approve ${r.id} exactly as shown?`}
            description={<Input.TextArea aria-label="Approval note" rows={2} maxLength={500} value={note} onChange={(e) => setNote(e.target.value)} placeholder="Note (what it was reviewed against)" />}
            okText="Approve"
            onConfirm={() => change.mutate({ id: r.id, action: 'approval' })}
          >
            <Button size="small" type="primary">
              Approve
            </Button>
          </Popconfirm>
        ),
    })
  }

  return (
    <Card>
      <ErrorAlert error={rules.error ?? change.error} />
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
        message="How rule approval works"
        description="A rule is written in the rule file and approved here by an admin. An approval covers the rule exactly as it stands: if its clause, severity or parameters are edited, it stops running until it is approved again."
      />
      <Table
        size="small"
        rowKey="id"
        columns={columns}
        dataSource={rules.data}
        loading={rules.isPending}
        pagination={false}
        expandable={{
          rowExpandable: (r) => !!r.params || !!r.approval_note,
          expandedRowRender: (r) => (
            <>
              {r.approval_note && <Typography.Paragraph>Approval note: {r.approval_note}</Typography.Paragraph>}
              {r.params && (
                <>
                  <Typography.Text type="secondary">Parameters (L = ship's rule length in metres, s = stiffener spacing in mm)</Typography.Text>
                  <pre style={{ margin: '4px 0 0' }}>{JSON.stringify(r.params, null, 2)}</pre>
                </>
              )}
            </>
          ),
        }}
      />
    </Card>
  )
}
