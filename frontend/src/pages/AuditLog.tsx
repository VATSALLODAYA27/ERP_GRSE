import { Card, Input, Table, Tag } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useState } from 'react'

import { formatTime, useAudit, type AuditEntry } from '../api'
import { AuditTarget } from '../components/erp/Bits'
import { ErrorAlert } from '../components/Tags'

const ACTION_COLOR: Record<string, string> = { 'login.failed': 'error', 'decision.override': 'warning', 'decision.recorded': 'success' }

export default function AuditLog() {
  const audit = useAudit()
  const [search, setSearch] = useState('')
  const needle = search.trim().toLowerCase()
  const rows = (audit.data ?? []).filter((e) => `${e.username} ${e.action} ${e.target} ${e.detail}`.toLowerCase().includes(needle))

  const columns: ColumnsType<AuditEntry> = [
    { title: 'Time', dataIndex: 'at', width: 180, render: formatTime },
    { title: 'User', dataIndex: 'username', width: 120 },
    { title: 'Role', dataIndex: 'role', width: 100, render: (role) => role || '—' },
    {
      title: 'Action',
      dataIndex: 'action',
      width: 170,
      filters: [...new Set((audit.data ?? []).map((e) => e.action))].map((value) => ({ value, text: value })),
      onFilter: (value, e) => e.action === value,
      render: (action) => <Tag color={ACTION_COLOR[action]}>{action}</Tag>,
    },
    {
      title: 'Target',
      dataIndex: 'target',
      width: 200,
      render: (target: string) => <AuditTarget target={target} />,
    },
    { title: 'Detail', dataIndex: 'detail' },
  ]

  return (
    <Card>
      <ErrorAlert error={audit.error} />
      <Input.Search
        allowClear
        placeholder="User, action or detail"
        aria-label="Search the audit log"
        onChange={(e) => setSearch(e.target.value)}
        style={{ width: 300, marginBottom: 16 }}
      />
      <Table
        size="small"
        rowKey="id"
        columns={columns}
        dataSource={rows}
        loading={audit.isPending}
        pagination={{ pageSize: 20, hideOnSinglePage: true }}
        locale={{ emptyText: 'No entries match.' }}
      />
    </Card>
  )
}
