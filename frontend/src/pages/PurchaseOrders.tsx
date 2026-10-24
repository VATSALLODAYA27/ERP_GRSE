import { PlusOutlined } from '@ant-design/icons'
import { Button, Card, Flex, Input, Progress, Select, Table, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'

import { can, type User } from '../api'
import { fmtDate, money, usePurchaseOrders, type PoSummary } from '../erpApi'
import { PoLink, RiskBar, StateTag, VendorLink, stateOptions, useDialog } from '../components/erp/Bits'
import OrderForm from '../components/erp/OrderForm'
import { ErrorAlert } from '../components/Tags'

const OPEN = new Set(['DRAFT', 'APPROVED', 'SENT', 'PART_RECEIVED'])

export const PO_COLUMNS: ColumnsType<PoSummary> = [
  { title: 'Purchase order', dataIndex: 'po_no', sorter: (a, b) => a.po_no.localeCompare(b.po_no), render: (no) => <PoLink no={no} /> },
  { title: 'Vendor', dataIndex: 'vendor_name', sorter: (a, b) => a.vendor_name.localeCompare(b.vendor_name), render: (name, po) => <VendorLink id={po.vendor_id} name={name} /> },
  { title: 'Created', dataIndex: 'created_on', sorter: (a, b) => a.created_on.localeCompare(b.created_on), defaultSortOrder: 'descend', render: fmtDate },
  { title: 'Status', dataIndex: 'status', render: (status) => <StateTag kind="po" value={status} /> },
  { title: 'Lines', dataIndex: 'lines', align: 'right' },
  { title: 'Value', dataIndex: 'value', align: 'right', sorter: (a, b) => a.value - b.value, render: (v) => money(v) },
  {
    title: 'Received',
    dataIndex: 'received_pct',
    width: 130,
    render: (p: number) => <Progress percent={Math.round(p ?? 0)} size="small" style={{ margin: 0, minWidth: 90 }} />,
  },
  {
    title: 'Next promised',
    dataIndex: 'next_promised',
    sorter: (a, b) => (a.next_promised ?? '9').localeCompare(b.next_promised ?? '9'),
    render: (date) => <span style={{ whiteSpace: 'nowrap' }}>{fmtDate(date)}</span>,
  },
  {
    title: 'Delivery risk',
    dataIndex: 'risk_score',
    sorter: (a, b) => (a.risk_score ?? -1) - (b.risk_score ?? -1),
    render: (score, po) =>
      po.risk_level ? (
        <Flex gap={6} align="center">
          <RiskBar score={score} level={po.risk_level} />
          <StateTag kind="risk" value={po.risk_level} />
        </Flex>
      ) : (
        <Typography.Text type="secondary">—</Typography.Text>
      ),
  },
]

export default function PurchaseOrders({ me }: { me: User }) {
  const orders = usePurchaseOrders()
  const [params] = useSearchParams()
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState<string | undefined>(params.get('status') ?? undefined)
  // Arriving from the control tower's "Deliveries at risk" tile shows the open orders at high or medium risk.
  const [risk, setRisk] = useState<string[]>(params.get('at_risk') ? ['HIGH', 'MEDIUM'] : params.get('risk') ? [params.get('risk')!] : [])
  const vendor = params.get('vendor')
  const dialog = useDialog()

  const needle = search.trim().toLowerCase()
  const rows = (orders.data ?? []).filter(
    (po) =>
      (!status || (status === 'OPEN' ? OPEN.has(po.status) : po.status === status)) &&
      (!risk.length || (po.risk_level !== null && risk.includes(po.risk_level))) &&
      (!vendor || po.vendor_id === vendor) &&
      `${po.po_no} ${po.vendor_name}`.toLowerCase().includes(needle),
  )

  return (
    <Card>
      <ErrorAlert error={orders.error} />
      <Flex gap={8} wrap style={{ marginBottom: 16 }}>
        <Input.Search allowClear placeholder="PO number or vendor" aria-label="Search purchase orders" onChange={(e) => setSearch(e.target.value)} style={{ width: 280 }} />
        <Select
          allowClear
          placeholder="Status"
          aria-label="Filter by status"
          value={status}
          onChange={setStatus}
          options={[{ value: 'OPEN', label: 'All open' }, ...stateOptions('po')]}
          style={{ width: 180 }}
        />
        <Select mode="multiple" allowClear placeholder="Delivery risk" aria-label="Filter by delivery risk" value={risk} onChange={setRisk} options={stateOptions('risk')} style={{ minWidth: 200 }} />
        {can.request(me) && (
          <Button type="primary" icon={<PlusOutlined />} onClick={() => dialog.show()} style={{ marginLeft: 'auto' }}>
            New purchase order
          </Button>
        )}
      </Flex>
      <Table
        size="small"
        rowKey="po_no"
        columns={PO_COLUMNS}
        dataSource={rows}
        loading={orders.isPending}
        pagination={{ pageSize: 15, hideOnSinglePage: true }}
        locale={{ emptyText: 'No purchase orders match.' }}
      />
      {dialog.key > 0 && <OrderForm key={dialog.key} open={dialog.open} onClose={dialog.hide} vendorId={vendor ?? undefined} />}
    </Card>
  )
}
