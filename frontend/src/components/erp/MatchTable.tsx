import { CheckOutlined, CloseOutlined } from '@ant-design/icons'
import { Alert, Table, Tag } from 'antd'

import { money, qty, type Match, type MatchLine } from '../../erpApi'
import { ItemLink } from './Bits'

const mark = (ok: boolean) => ({ className: ok ? 'cell-ok' : 'cell-bad' })
const icon = (ok: boolean) => (ok ? <CheckOutlined aria-label="within tolerance" /> : <CloseOutlined aria-label="outside tolerance" />)

/**
 * The 3-way match: what was ordered, what was accepted at the gate, what the vendor billed. Invoiced quantity must not
 * exceed accepted quantity, and the invoiced price must be within 2% of the order price. Green passes, red does not.
 */
export default function MatchTable({ match }: { match: Match | null | undefined }) {
  if (!match) return <Alert type="info" showIcon message="No match result is recorded for this invoice." />
  return (
    <>
      <Alert
        type={match.ok ? 'success' : 'warning'}
        showIcon
        style={{ marginBottom: 12 }}
        message={match.ok ? '3-way match passed: order, receipt and invoice agree.' : '3-way match found differences: a reviewer must give a reason to approve.'}
        description={match.notes?.length ? match.notes.map((note) => <div key={note}>{note}</div>) : undefined}
      />
      <Table<MatchLine>
        size="small"
        rowKey="item_code"
        pagination={false}
        dataSource={match.lines}
        columns={[
          { title: 'Item', dataIndex: 'item_code', render: (code) => <ItemLink code={code} /> },
          { title: 'PO qty', dataIndex: 'po_qty', align: 'right', render: qty },
          { title: 'Accepted', dataIndex: 'received_qty', align: 'right', render: qty },
          {
            title: 'Invoiced qty',
            dataIndex: 'invoiced_qty',
            align: 'right',
            onCell: (l) => mark(l.qty_ok),
            render: (v, l) => (
              <>
                {qty(v)} {icon(l.qty_ok)}
              </>
            ),
          },
          { title: 'PO price', dataIndex: 'po_price', align: 'right', render: (v) => money(v, true) },
          {
            title: 'Invoiced price',
            dataIndex: 'invoiced_price',
            align: 'right',
            onCell: (l) => mark(l.price_ok),
            render: (v, l) => (
              <>
                {money(v, true)} {icon(l.price_ok)}
              </>
            ),
          },
          {
            title: 'Variance',
            dataIndex: 'price_variance_pct',
            align: 'right',
            onCell: (l) => mark(l.price_ok),
            render: (v: number) => (v === null || v === undefined ? '—' : `${v > 0 ? '+' : ''}${v.toFixed(1)}%`),
          },
          {
            title: 'Result',
            render: (_, l) =>
              l.qty_ok && l.price_ok ? (
                <Tag color="success" icon={<CheckOutlined />}>
                  Match
                </Tag>
              ) : (
                <Tag color="error" icon={<CloseOutlined />}>
                  {!l.qty_ok && !l.price_ok ? 'Qty and price' : !l.qty_ok ? 'Qty over accepted' : 'Price outside ±2%'}
                </Tag>
              ),
          },
        ]}
      />
    </>
  )
}
