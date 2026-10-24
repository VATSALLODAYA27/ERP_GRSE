import { Card, Flex, Input, Select, Table, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useState } from 'react'

import { money, pct, useVendors, type Vendor } from '../erpApi'
import { MsmeTag, StateTag, VendorLink, stateOptions } from '../components/erp/Bits'
import { ErrorAlert } from '../components/Tags'

const COLUMNS: ColumnsType<Vendor> = [
  {
    title: 'Vendor',
    dataIndex: 'name',
    sorter: (a, b) => a.name.localeCompare(b.name),
    render: (name, v) => (
      <>
        <VendorLink id={v.vendor_id} name={name} /> {v.msme && <MsmeTag />}
        <div>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            {v.vendor_id} · {v.city}
          </Typography.Text>
        </div>
      </>
    ),
  },
  { title: 'Category', dataIndex: 'category' },
  {
    title: 'Grade',
    dataIndex: 'grade',
    filters: stateOptions('grade'),
    onFilter: (value, v) => v.grade === value,
    sorter: (a, b) => a.grade.localeCompare(b.grade),
    render: (grade) => <StateTag kind="grade" value={grade} />,
  },
  {
    title: 'On time',
    dataIndex: 'on_time_pct',
    align: 'right',
    sorter: (a, b) => (a.on_time_pct ?? -1) - (b.on_time_pct ?? -1),
    // No closed deliveries yet means no rate, not a bad one.
    render: (v) => <Typography.Text type={v === null || v === undefined ? undefined : v < 65 ? 'danger' : v < 85 ? 'warning' : undefined}>{pct(v)}</Typography.Text>,
  },
  { title: 'Avg delay', dataIndex: 'avg_delay_days', align: 'right', sorter: (a, b) => (a.avg_delay_days ?? 0) - (b.avg_delay_days ?? 0), render: (v) => (v === null || v === undefined ? '—' : `${Math.round(v * 10) / 10} days`) },
  {
    title: 'Rejected',
    dataIndex: 'rejection_pct',
    align: 'right',
    sorter: (a, b) => (a.rejection_pct ?? 0) - (b.rejection_pct ?? 0),
    render: (v) => <Typography.Text type={v > 2 ? 'danger' : undefined}>{pct(v)}</Typography.Text>,
  },
  { title: 'Spend this year', dataIndex: 'spend_ytd', align: 'right', sorter: (a, b) => a.spend_ytd - b.spend_ytd, render: (v) => money(v) },
  { title: 'Open orders', dataIndex: 'open_po_value', align: 'right', sorter: (a, b) => a.open_po_value - b.open_po_value, render: (v) => money(v) },
  { title: 'Terms', dataIndex: 'payment_terms_days', align: 'right', render: (d) => `${d} days` },
  { title: 'Lead time', dataIndex: 'lead_time_days', align: 'right', render: (d) => `${d} days` },
]

export default function Vendors() {
  const vendors = useVendors()
  const [search, setSearch] = useState('')
  const [category, setCategory] = useState<string>()
  const needle = search.trim().toLowerCase()
  const rows = (vendors.data ?? []).filter(
    (v) => (!category || v.category === category) && `${v.vendor_id} ${v.name} ${v.city}`.toLowerCase().includes(needle),
  )

  return (
    <Card>
      <ErrorAlert error={vendors.error} />
      <Flex gap={8} wrap align="center" style={{ marginBottom: 16 }}>
        <Input.Search allowClear placeholder="Vendor, code or city" aria-label="Search vendors" onChange={(e) => setSearch(e.target.value)} style={{ width: 280 }} />
        <Select
          allowClear
          placeholder="Category"
          aria-label="Filter by category"
          value={category}
          onChange={setCategory}
          options={[...new Set((vendors.data ?? []).map((v) => v.category))].sort().map((value) => ({ value }))}
          style={{ width: 220 }}
        />
        <Typography.Text type="secondary">Grade A: on time 85% or more and rejections 2% or less. Grade B: on time 65% or more. All vendors are representative.</Typography.Text>
      </Flex>
      <Table
        size="small"
        rowKey="vendor_id"
        columns={COLUMNS}
        dataSource={rows}
        loading={vendors.isPending}
        pagination={{ pageSize: 15, hideOnSinglePage: true }}
        locale={{ emptyText: 'No vendors match.' }}
      />
    </Card>
  )
}
