import { Button, Card, Col, Drawer, Row, Skeleton, Table, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useState } from 'react'
import { Link } from 'react-router-dom'

import { fmtDate, money, moneyShort, usePayables, useVendorLedger, type PayablesRow, type VendorLedgerRow } from '../erpApi'
import { RefLink, VendorLink } from '../components/erp/Bits'
import { ErrorAlert } from '../components/Tags'
import { TONE } from '../theme'

const side = (v: number | null | undefined) => (v ? money(v, true) : '')

/** A vendor's payables account line by line, with the running balance owed. */
export function VendorLedgerTable({ rows, loading }: { rows?: VendorLedgerRow[]; loading: boolean }) {
  return (
    <Table<VendorLedgerRow & { key: number }>
      size="small"
      rowKey="key"
      pagination={false}
      loading={loading}
      dataSource={rows?.map((r, i) => ({ ...r, key: i }))}
      locale={{ emptyText: 'Nothing posted to this vendor yet.' }}
      columns={[
        { title: 'Date', dataIndex: 'on_date', render: (d) => <span style={{ whiteSpace: 'nowrap' }}>{fmtDate(d)}</span> },
        { title: 'Document', dataIndex: 'source_no', render: (no, r) => <RefLink type={r.source_type} no={no ?? r.je_no} /> },
        { title: 'Narration', dataIndex: 'narration', render: (n) => n || '—' },
        { title: 'Debit (paid)', dataIndex: 'debit', align: 'right', render: side },
        { title: 'Credit (billed)', dataIndex: 'credit', align: 'right', render: side },
        { title: 'Balance owed', dataIndex: 'balance', align: 'right', render: (v) => <strong>{money(v, true)}</strong> },
      ]}
    />
  )
}

const BUCKETS: { key: keyof PayablesRow; label: string; tone: string }[] = [
  { key: 'current', label: 'Not yet due', tone: TONE.good },
  { key: 'd1_30', label: '1–30 days overdue', tone: TONE.info },
  { key: 'd31_60', label: '31–60 days overdue', tone: TONE.warn },
  { key: 'd61_90', label: '61–90 days overdue', tone: TONE.bad },
  { key: 'over_90', label: 'Over 90 days overdue', tone: TONE.bad },
]

/** Money owed to vendors, aged by invoice due date. */
export default function Payables() {
  const payables = usePayables()
  const [open, setOpen] = useState<PayablesRow | null>(null)
  const ledger = useVendorLedger(open?.vendor_id)
  const vendors = payables.data?.vendors ?? []
  const totals = BUCKETS.map((b) => ({ ...b, value: vendors.reduce((sum, v) => sum + ((v[b.key] as number) ?? 0), 0) }))

  const amount = (danger: boolean) => (v: number) =>
    v ? <Typography.Text type={danger ? 'danger' : undefined}>{money(v)}</Typography.Text> : <Typography.Text type="secondary">—</Typography.Text>

  const columns: ColumnsType<PayablesRow> = [
    { title: 'Vendor', dataIndex: 'name', sorter: (a, b) => a.name.localeCompare(b.name), render: (name, v) => <VendorLink id={v.vendor_id} name={name} /> },
    { title: 'Owed', dataIndex: 'balance', align: 'right', defaultSortOrder: 'descend', sorter: (a, b) => a.balance - b.balance, render: (v) => <strong>{money(v)}</strong> },
    ...BUCKETS.map((b, i) => ({
      title: b.label.replace(' overdue', '').replace('Not yet due', 'Current'),
      dataIndex: b.key,
      align: 'right' as const,
      sorter: (x: PayablesRow, y: PayablesRow) => (x[b.key] as number) - (y[b.key] as number),
      render: amount(i >= 2),
    })),
    { title: 'Next due', dataIndex: 'next_due', render: (d) => <span style={{ whiteSpace: 'nowrap' }}>{fmtDate(d)}</span> },
    { title: '', key: 'ledger', render: (_, v) => <Button size="small" onClick={() => setOpen(v)}>Ledger</Button> },
  ]

  return (
    <>
      <ErrorAlert error={payables.error} />
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={24} md={8} xl={4}>
          <Card className="kpi" loading={payables.isPending} style={{ height: '100%' }}>
            <Typography.Text type="secondary">Total owed to vendors</Typography.Text>
            <div className="kpi-value compact">{moneyShort(payables.data?.total)}</div>
            <Link to="/invoices?status=APPROVED" className="kpi-link">
              Invoices awaiting payment
            </Link>
          </Card>
        </Col>
        {totals.map((b) => (
          <Col key={b.key} xs={12} md={8} xl={4}>
            <Card loading={payables.isPending} style={{ height: '100%', borderTop: `3px solid ${b.tone}` }}>
              <Typography.Text type="secondary">{b.label}</Typography.Text>
              <div className="kpi-value compact">{moneyShort(b.value)}</div>
            </Card>
          </Col>
        ))}
      </Row>
      <Card>
        <Table
          size="small"
          rowKey="vendor_id"
          columns={columns}
          dataSource={vendors}
          loading={payables.isPending}
          pagination={false}
          onRow={(v) => ({ onDoubleClick: () => setOpen(v) })}
          locale={{ emptyText: 'Nothing is owed to any vendor.' }}
        />
      </Card>
      <Drawer open={!!open} onClose={() => setOpen(null)} width={820} title={open ? `${open.name}: payables ledger` : ''}>
        {open && (
          <>
            <Typography.Paragraph>
              Owed now: <strong>{money(open.balance)}</strong> · next due {fmtDate(open.next_due)} · <VendorLink id={open.vendor_id} name="Open the vendor page" />
            </Typography.Paragraph>
            <ErrorAlert error={ledger.error} />
            {ledger.isPending ? <Skeleton active /> : <VendorLedgerTable rows={ledger.data} loading={false} />}
          </>
        )}
      </Drawer>
    </>
  )
}
