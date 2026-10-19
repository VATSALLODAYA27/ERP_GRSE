import { Table } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { Link } from 'react-router-dom'

import { formatTime, type CheckSummary } from '../api'
import { DecisionTag, VERDICT, VerdictTag } from './Tags'

const COLUMNS: ColumnsType<CheckSummary> = [
  { title: 'Check', dataIndex: 'id', width: 80, render: (id) => <Link to={`/checks/${id}`}>#{id}</Link> },
  { title: 'Drawing no.', dataIndex: 'drawing_no', render: (no, c) => <Link to={`/checks/${c.id}`}>{no || '(unreadable)'}</Link> },
  { title: 'Rev', dataIndex: 'revision', width: 70 },
  {
    title: 'Verdict',
    dataIndex: 'verdict',
    filters: Object.entries(VERDICT).map(([value, v]) => ({ value, text: v.label })),
    onFilter: (value, c) => c.verdict === value,
    render: (verdict) => <VerdictTag verdict={verdict} />,
  },
  {
    title: 'Decision',
    dataIndex: 'decision',
    filters: [
      { value: 'none', text: 'Awaiting decision' },
      { value: 'APPROVED', text: 'Approved' },
      { value: 'REJECTED', text: 'Rejected' },
    ],
    onFilter: (value, c) => (c.decision?.decision ?? 'none') === value,
    render: (decision) => <DecisionTag decision={decision} />,
  },
  { title: 'Submitted by', dataIndex: 'submitted_by' },
  { title: 'Time', dataIndex: 'created_at', render: (time) => <span style={{ whiteSpace: 'nowrap' }}>{formatTime(time)}</span> },
]

export default function ChecksTable({ checks, loading, pageSize }: { checks?: CheckSummary[]; loading: boolean; pageSize?: number }) {
  return (
    <Table
      size="small"
      rowKey="id"
      columns={COLUMNS}
      dataSource={checks}
      loading={loading}
      pagination={pageSize ? { pageSize, hideOnSinglePage: true } : false}
      locale={{ emptyText: 'No checks yet. Upload a drawing under New Check.' }}
    />
  )
}
