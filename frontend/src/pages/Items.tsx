import { PlusOutlined } from '@ant-design/icons'
import { Button, Card, Checkbox, Col, Flex, Input, Row, Select, Table, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'

import { can, type User } from '../api'
import { money, moneyShort, qty, useItems, useStores, type Item } from '../erpApi'
import { CriticalTag, ItemLink, StateTag, stateOptions, useDialog } from '../components/erp/Bits'
import RequisitionForm from '../components/erp/RequisitionForm'
import { ErrorAlert } from '../components/Tags'

const COLUMNS: ColumnsType<Item> = [
  {
    title: 'Item',
    dataIndex: 'item_code',
    sorter: (a, b) => a.item_code.localeCompare(b.item_code),
    render: (code, item) => (
      <>
        <ItemLink code={code} /> {item.critical && <CriticalTag />}
      </>
    ),
  },
  { title: 'Description', dataIndex: 'description' },
  { title: 'Category', dataIndex: 'category' },
  { title: 'Grade', dataIndex: 'grade', render: (g) => g || '—' },
  {
    title: 'On hand',
    dataIndex: 'on_hand',
    align: 'right',
    sorter: (a, b) => a.on_hand - b.on_hand,
    render: (v, item) => (
      <Typography.Text type={v <= 0 ? 'danger' : undefined} style={{ whiteSpace: 'nowrap' }}>
        {qty(v)} {item.uom}
      </Typography.Text>
    ),
  },
  { title: 'On order', dataIndex: 'on_order', align: 'right', render: qty },
  { title: 'Reorder level', dataIndex: 'reorder_level', align: 'right', render: qty },
  { title: 'Avg cost', dataIndex: 'avg_cost', align: 'right', render: (v) => money(v, true) },
  { title: 'Stock value', dataIndex: 'stock_value', align: 'right', sorter: (a, b) => a.stock_value - b.stock_value, render: (v) => money(v) },
  { title: 'Status', dataIndex: 'status', render: (s) => <StateTag kind="stock" value={s} /> },
]

/** Every item with its stock across the stores, and the stores themselves. */
export default function Items({ me }: { me: User }) {
  const items = useItems()
  const stores = useStores()
  const [params] = useSearchParams()
  const [search, setSearch] = useState('')
  const [category, setCategory] = useState<string | undefined>(params.get('category') ?? undefined)
  // "REORDER" from the control tower means everything that needs ordering, stock-outs included.
  const [status, setStatus] = useState<string | undefined>(params.get('status') ?? undefined)
  const [critical, setCritical] = useState(false)
  const [selected, setSelected] = useState<string[]>([])
  const dialog = useDialog<string[]>()

  const needle = search.trim().toLowerCase()
  const rows = (items.data ?? []).filter(
    (i) =>
      (!category || i.category === category) &&
      (!status || i.status === status || (status === 'REORDER' && i.status === 'STOCK_OUT')) &&
      (!critical || i.critical) &&
      `${i.item_code} ${i.description} ${i.grade ?? ''}`.toLowerCase().includes(needle),
  )

  return (
    <>
      <ErrorAlert error={items.error ?? stores.error} />
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        {(stores.data ?? []).map((s) => (
          <Col key={s.store_code} xs={12} md={6}>
            <Link to={`/stock?store=${encodeURIComponent(s.store_code)}`} style={{ color: 'inherit' }}>
              <Card size="small" className="kpi" hoverable style={{ height: '100%' }}>
                <Typography.Text strong>{s.name}</Typography.Text>
                <div>
                  <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                    {s.store_code} · {s.location}
                  </Typography.Text>
                </div>
                <div className="kpi-value compact" style={{ marginTop: 6 }}>
                  {moneyShort(s.stock_value)}
                </div>
                <Typography.Text type="secondary">{s.items} items in stock</Typography.Text>
              </Card>
            </Link>
          </Col>
        ))}
      </Row>
      <Card>
        <Flex gap={8} wrap align="center" style={{ marginBottom: 16 }}>
          <Input.Search allowClear placeholder="Item code, description or grade" aria-label="Search items" onChange={(e) => setSearch(e.target.value)} style={{ width: 280 }} />
          <Select
            allowClear
            placeholder="Category"
            aria-label="Filter by category"
            value={category}
            onChange={setCategory}
            options={[...new Set((items.data ?? []).map((i) => i.category))].sort().map((value) => ({ value }))}
            style={{ width: 200 }}
          />
          <Select allowClear placeholder="Stock status" aria-label="Filter by stock status" value={status} onChange={setStatus} options={stateOptions('stock')} style={{ width: 160 }} />
          <Checkbox checked={critical} onChange={(e) => setCritical(e.target.checked)}>
            Critical only
          </Checkbox>
          {can.request(me) && (
            <Button type="primary" icon={<PlusOutlined />} onClick={() => dialog.show(selected)} style={{ marginLeft: 'auto' }}>
              New requisition{selected.length ? ` (${selected.length})` : ''}
            </Button>
          )}
        </Flex>
        <Table
          size="small"
          rowKey="item_code"
          columns={COLUMNS}
          dataSource={rows}
          loading={items.isPending}
          pagination={{ pageSize: 20, hideOnSinglePage: true }}
          rowSelection={can.request(me) ? { selectedRowKeys: selected, onChange: (keys) => setSelected(keys as string[]) } : undefined}
          locale={{ emptyText: 'No items match.' }}
        />
      </Card>
      {dialog.key > 0 && <RequisitionForm key={dialog.key} open={dialog.open} onClose={dialog.hide} items={dialog.data} />}
    </>
  )
}
