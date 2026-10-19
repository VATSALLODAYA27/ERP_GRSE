import { ExportOutlined, SlidersOutlined, SwapOutlined } from '@ant-design/icons'
import { Button, Card, Flex, Input, Select, Space, Table, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'

import { can, type User } from '../api'
import { fmtDate, money, qty, useStockMoves, useStores, type StockMove } from '../erpApi'
import { ItemLink, RefLink, StateTag, WorkOrderTags, stateOptions, useDialog } from '../components/erp/Bits'
import StockForm, { type StockMode } from '../components/erp/StockForm'
import { ErrorAlert } from '../components/Tags'

/** Stock movements, newest first. `withItem` adds the item column (left out on an item's own page). */
export function MovesTable({ moves, loading, withItem = true, pageSize = 20 }: { moves?: StockMove[]; loading: boolean; withItem?: boolean; pageSize?: number }) {
  const columns: ColumnsType<StockMove> = [
    { title: 'Date', dataIndex: 'on_date', render: (d) => <span style={{ whiteSpace: 'nowrap' }}>{fmtDate(d)}</span> },
    ...(withItem
      ? ([
          {
            title: 'Item',
            dataIndex: 'item_code',
            render: (code: string, m: StockMove) => (
              <>
                <ItemLink code={code} />
                <div>
                  <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                    {m.description}
                  </Typography.Text>
                </div>
              </>
            ),
          },
        ] as ColumnsType<StockMove>)
      : []),
    { title: 'Store', dataIndex: 'store_code' },
    { title: 'Movement', dataIndex: 'kind', render: (k) => <StateTag kind="move" value={k} /> },
    {
      title: 'Qty',
      dataIndex: 'qty',
      align: 'right',
      render: (v: number) => (
        <Typography.Text type={v < 0 ? 'danger' : 'success'} style={{ whiteSpace: 'nowrap' }}>
          {v > 0 ? '+' : ''}
          {qty(v)}
        </Typography.Text>
      ),
    },
    { title: 'Unit cost', dataIndex: 'unit_cost', align: 'right', render: (v) => money(v, true) },
    { title: 'Value', dataIndex: 'value', align: 'right', render: (v) => money(v) },
    { title: 'Reference', dataIndex: 'ref_no', render: (no, m) => <RefLink type={m.ref_type} no={no} /> },
    { title: 'Work order', dataIndex: 'work_order', render: (wo) => <WorkOrderTags orders={[wo]} /> },
    { title: 'By', dataIndex: 'created_by' },
  ]
  return (
    <Table
      size="small"
      rowKey="id"
      columns={columns}
      dataSource={moves}
      loading={loading}
      pagination={{ pageSize, hideOnSinglePage: true }}
      locale={{ emptyText: 'No stock movements match.' }}
    />
  )
}

/** Stock action buttons by role: anyone issues and transfers; a reviewer adjusts. */
export function StockActions({ me, onAction }: { me: User; onAction: (mode: StockMode) => void }) {
  return (
    <Space wrap>
      {can.request(me) && (
        <>
          <Button type="primary" icon={<ExportOutlined />} onClick={() => onAction('issue')}>
            Issue to work order
          </Button>
          <Button icon={<SwapOutlined />} onClick={() => onAction('transfer')}>
            Transfer
          </Button>
        </>
      )}
      {can.approve(me) && (
        <Button icon={<SlidersOutlined />} onClick={() => onAction('adjust')}>
          Adjust
        </Button>
      )}
    </Space>
  )
}

export default function StockLedger({ me }: { me: User }) {
  const moves = useStockMoves()
  const stores = useStores()
  const [params] = useSearchParams()
  const [search, setSearch] = useState(params.get('item') ?? '')
  const [store, setStore] = useState<string | undefined>(params.get('store') ?? undefined)
  const [kind, setKind] = useState<string | undefined>(params.get('kind') ?? undefined)
  const dialog = useDialog<StockMode>()

  const needle = search.trim().toLowerCase()
  const rows = (moves.data ?? []).filter(
    (m) =>
      (!store || m.store_code === store) &&
      (!kind || m.kind === kind) &&
      `${m.item_code} ${m.description} ${m.ref_no} ${m.work_order ?? ''}`.toLowerCase().includes(needle),
  )

  return (
    <Card>
      <ErrorAlert error={moves.error} />
      <Flex gap={8} wrap style={{ marginBottom: 16 }}>
        <Input.Search
          allowClear
          defaultValue={search}
          placeholder="Item, reference or work order"
          aria-label="Search stock movements"
          onChange={(e) => setSearch(e.target.value)}
          style={{ width: 280 }}
        />
        <Select
          allowClear
          placeholder="Store"
          aria-label="Filter by store"
          value={store}
          onChange={setStore}
          loading={stores.isPending}
          options={(stores.data ?? []).map((s) => ({ value: s.store_code, label: `${s.store_code} · ${s.name}` }))}
          style={{ width: 260 }}
        />
        <Select allowClear placeholder="Movement" aria-label="Filter by movement" value={kind} onChange={setKind} options={stateOptions('move')} style={{ width: 170 }} />
        <div style={{ marginLeft: 'auto' }}>
          <StockActions me={me} onAction={(mode) => dialog.show(mode)} />
        </div>
      </Flex>
      <MovesTable moves={rows} loading={moves.isPending} />
      {dialog.key > 0 && dialog.data && <StockForm key={dialog.key} mode={dialog.data} open={dialog.open} onClose={dialog.hide} store={store} />}
    </Card>
  )
}
