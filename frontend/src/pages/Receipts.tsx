import { Alert, Card, Descriptions, Drawer, Flex, Input, Result, Skeleton, Table, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'

import { ApiError } from '../api'
import { fmtDate, qty, useReceipt, useReceipts, type GrnLine, type ReceiptSummary } from '../erpApi'
import { GrnLink, ItemLink, PoLink, VendorLink } from '../components/erp/Bits'
import { ErrorAlert } from '../components/Tags'
import { JournalTable } from './GeneralLedger'

const COLUMNS: ColumnsType<ReceiptSummary> = [
  { title: 'Goods receipt', dataIndex: 'grn_no', sorter: (a, b) => a.grn_no.localeCompare(b.grn_no), render: (no) => <GrnLink no={no} /> },
  { title: 'Purchase order', dataIndex: 'po_no', render: (no) => <PoLink no={no} /> },
  { title: 'Vendor', dataIndex: 'vendor_name', render: (name, r) => (name ? <VendorLink id={r.vendor_id} name={name} /> : '—') },
  { title: 'Received on', dataIndex: 'received_on', sorter: (a, b) => a.received_on.localeCompare(b.received_on), defaultSortOrder: 'descend', render: fmtDate },
  { title: 'Store', dataIndex: 'store_code' },
  { title: 'Received by', dataIndex: 'received_by' },
  { title: 'Accepted', dataIndex: 'qty_accepted', align: 'right', render: qty },
  { title: 'Rejected', dataIndex: 'qty_rejected', align: 'right', render: (v) => (v ? <Typography.Text type="danger">{qty(v)}</Typography.Text> : qty(v)) },
]

/** One goods receipt, in a drawer over the list. */
function ReceiptDrawer({ grnNo, onClose }: { grnNo?: string; onClose: () => void }) {
  const receipt = useReceipt(grnNo)
  const r = receipt.data
  const missing = receipt.error instanceof ApiError && receipt.error.status === 404
  return (
    <Drawer open={!!grnNo} onClose={onClose} width={760} title={grnNo ? `Goods receipt ${grnNo}` : ''}>
      {receipt.isPending && <Skeleton active />}
      {receipt.isError && <Result status={missing ? '404' : 'error'} title={missing ? 'Goods receipt not found' : receipt.error.message} />}
      {r && (
        <>
          <Descriptions column={{ xs: 1, md: 2 }} size="small" style={{ marginBottom: 16 }}>
            <Descriptions.Item label="Purchase order">
              <PoLink no={r.po_no} />
            </Descriptions.Item>
            <Descriptions.Item label="Vendor">{r.vendor_name ? <VendorLink id={r.vendor_id} name={r.vendor_name} /> : '—'}</Descriptions.Item>
            <Descriptions.Item label="Received on">{fmtDate(r.received_on)}</Descriptions.Item>
            <Descriptions.Item label="Store">{r.store_name ? `${r.store_code} · ${r.store_name}` : r.store_code}</Descriptions.Item>
            <Descriptions.Item label="Received by">{r.received_by}</Descriptions.Item>
          </Descriptions>
          {r.flags?.map((f) => (
            <Alert key={f.id} type={f.severity === 'high' ? 'error' : 'warning'} showIcon style={{ marginBottom: 12 }} message={f.message} />
          ))}
          <Table<GrnLine>
            size="small"
            rowKey="id"
            pagination={false}
            dataSource={r.lines}
            columns={[
              {
                title: 'Item',
                dataIndex: 'item_code',
                render: (code, l) => (
                  <>
                    <ItemLink code={code} />
                    {l.description && (
                      <div>
                        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                          {l.description}
                        </Typography.Text>
                      </div>
                    )}
                  </>
                ),
              },
              { title: 'Received', dataIndex: 'qty_received', align: 'right', render: qty },
              { title: 'Accepted', dataIndex: 'qty_accepted', align: 'right', render: (v) => <Typography.Text type="success">{qty(v)}</Typography.Text> },
              { title: 'Rejected', dataIndex: 'qty_rejected', align: 'right', render: (v) => (v ? <Typography.Text type="danger">{qty(v)}</Typography.Text> : qty(v)) },
              { title: 'Reject reason', dataIndex: 'reject_reason', render: (reason) => reason || '—' },
            ]}
          />
          {r.journal && r.journal.length > 0 && (
            <>
              <Typography.Title level={5} style={{ marginTop: 20 }}>
                Ledger postings
              </Typography.Title>
              <JournalTable entries={r.journal} loading={false} />
            </>
          )}
        </>
      )}
    </Drawer>
  )
}

export default function Receipts() {
  const receipts = useReceipts()
  const { grnNo } = useParams()
  const navigate = useNavigate()
  const [search, setSearch] = useState('')
  const needle = search.trim().toLowerCase()
  const rows = (receipts.data ?? []).filter((r) => `${r.grn_no} ${r.po_no} ${r.vendor_name ?? ''} ${r.store_code}`.toLowerCase().includes(needle))

  return (
    <Card>
      <ErrorAlert error={receipts.error} />
      <Flex gap={8} wrap style={{ marginBottom: 16 }}>
        <Input.Search allowClear placeholder="Receipt, order, vendor or store" aria-label="Search goods receipts" onChange={(e) => setSearch(e.target.value)} style={{ width: 320 }} />
        <Typography.Text type="secondary" style={{ alignSelf: 'center' }}>
          Goods are received from the purchase order page.
        </Typography.Text>
      </Flex>
      <Table
        size="small"
        rowKey="grn_no"
        columns={COLUMNS}
        dataSource={rows}
        loading={receipts.isPending}
        pagination={{ pageSize: 15, hideOnSinglePage: true }}
        locale={{ emptyText: 'No goods receipts match.' }}
      />
      <ReceiptDrawer grnNo={grnNo} onClose={() => navigate('/receipts')} />
    </Card>
  )
}
