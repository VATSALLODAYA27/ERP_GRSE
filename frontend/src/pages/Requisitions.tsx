import { PlusOutlined } from '@ant-design/icons'
import { Button, Card, Flex, Input, Select, Table } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'

import { can, type User } from '../api'
import { fmtDate, money, useRequisitions, type RequisitionSummary } from '../erpApi'
import { PrLink, StateTag, WorkOrderTags, stateOptions, useDialog } from '../components/erp/Bits'
import RequisitionForm from '../components/erp/RequisitionForm'
import { ErrorAlert } from '../components/Tags'

const COLUMNS: ColumnsType<RequisitionSummary> = [
  { title: 'Requisition', dataIndex: 'pr_no', sorter: (a, b) => a.pr_no.localeCompare(b.pr_no), render: (no) => <PrLink no={no} /> },
  { title: 'Raised on', dataIndex: 'created_on', sorter: (a, b) => a.created_on.localeCompare(b.created_on), defaultSortOrder: 'descend', render: fmtDate },
  { title: 'Requested by', dataIndex: 'requested_by' },
  { title: 'Work order', dataIndex: 'work_order', render: (wo) => <WorkOrderTags orders={[wo]} /> },
  {
    title: 'Source',
    dataIndex: 'source',
    filters: stateOptions('source'),
    onFilter: (value, r) => r.source === value,
    render: (source) => <StateTag kind="source" value={source} />,
  },
  { title: 'Lines', dataIndex: 'lines', align: 'right' },
  { title: 'Est. value', dataIndex: 'value', align: 'right', sorter: (a, b) => a.value - b.value, render: (v) => money(v) },
  { title: 'Status', dataIndex: 'status', render: (status) => <StateTag kind="pr" value={status} /> },
]

export default function Requisitions({ me }: { me: User }) {
  const requisitions = useRequisitions()
  const [params] = useSearchParams()
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState<string | undefined>(params.get('status') ?? undefined)
  const dialog = useDialog()

  const needle = search.trim().toLowerCase()
  const rows = (requisitions.data ?? []).filter(
    (r) => (!status || r.status === status) && `${r.pr_no} ${r.requested_by} ${r.work_order ?? ''}`.toLowerCase().includes(needle),
  )

  return (
    <Card>
      <ErrorAlert error={requisitions.error} />
      <Flex gap={8} wrap style={{ marginBottom: 16 }}>
        <Input.Search allowClear placeholder="Requisition, requester or work order" aria-label="Search requisitions" onChange={(e) => setSearch(e.target.value)} style={{ width: 320 }} />
        <Select allowClear placeholder="Status" aria-label="Filter by status" value={status} onChange={setStatus} options={stateOptions('pr')} style={{ width: 200 }} />
        {can.request(me) && (
          <Button type="primary" icon={<PlusOutlined />} onClick={() => dialog.show()} style={{ marginLeft: 'auto' }}>
            New requisition
          </Button>
        )}
      </Flex>
      <Table
        size="small"
        rowKey="pr_no"
        columns={COLUMNS}
        dataSource={rows}
        loading={requisitions.isPending}
        pagination={{ pageSize: 15, hideOnSinglePage: true }}
        locale={{ emptyText: 'No requisitions match.' }}
      />
      {dialog.key > 0 && <RequisitionForm key={dialog.key} open={dialog.open} onClose={dialog.hide} />}
    </Card>
  )
}
