import { Table, Tag } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { Link } from 'react-router-dom'

import type { GateRow } from '../api'
import { GATE, GateTag } from './Tags'

const COLUMNS: ColumnsType<GateRow> = [
  { title: 'Work order', dataIndex: 'order_no', render: (no) => <strong>{no}</strong> },
  { title: 'Drawing no.', dataIndex: 'drawing_no', render: (no) => <Link to={`/register/${no}`}>{no}</Link> },
  { title: 'Released against', dataIndex: 'rev', render: (rev) => `Rev ${rev}` },
  { title: 'Register current', dataIndex: 'current_rev', render: (rev) => (rev ? `Rev ${rev}` : '—') },
  {
    title: 'Work order state',
    dataIndex: 'state',
    render: (state) => (state === 'RELEASED' ? <Tag color="blue">Released</Tag> : <Tag>Created</Tag>),
  },
  {
    title: 'Gate status',
    dataIndex: 'status',
    filters: Object.entries(GATE).map(([value, g]) => ({ value, text: g.label })),
    onFilter: (value, row) => row.status === value,
    render: (status) => <GateTag status={status} />,
  },
  {
    title: 'Reason',
    render: (_, row) => (
      <>
        {row.reasons.length === 0 && 'Current revision, approved, checked and approved for release.'}
        {row.reasons.map((reason) => (
          <div key={reason}>{reason}</div>
        ))}
        {row.check_id && <Link to={`/checks/${row.check_id}`}>Open check #{row.check_id}</Link>}
      </>
    ),
  },
]

export default function GateTable({ rows, loading }: { rows?: GateRow[]; loading: boolean }) {
  return <Table size="small" rowKey="order_no" columns={COLUMNS} dataSource={rows} loading={loading} pagination={false} locale={{ emptyText: 'No work orders.' }} />
}
