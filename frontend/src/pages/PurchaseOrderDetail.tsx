import { CheckOutlined, FileTextOutlined, InboxOutlined, MailOutlined, SendOutlined } from '@ant-design/icons'
import { Alert, Button, Card, Descriptions, Flex, Popconfirm, Progress, Skeleton, Space, Table, Tabs, Tag, Tooltip, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useParams, useSearchParams } from 'react-router-dom'

import { can, formatTime, type User } from '../api'
import { AFFECTS, APPROVAL_LIMIT, draftedCount, erp, fmtDate, money, qty, useAction, usePurchaseOrder, type PoLine } from '../erpApi'
import { AuditTable, GrnLink, InvoiceLink, ItemLink, LoadError, PrLink, RiskBar, StateTag, VendorLink, WorkOrderTags, WrittenByTag, useDialog } from '../components/erp/Bits'
import InvoiceForm from '../components/erp/InvoiceForm'
import ReceiveForm from '../components/erp/ReceiveForm'
import { JournalTable } from './GeneralLedger'

const RECEIVABLE = new Set(['APPROVED', 'SENT', 'PART_RECEIVED'])
const OPEN = new Set(['DRAFT', 'APPROVED', 'SENT', 'PART_RECEIVED'])

/** One purchase order: lines with their delivery risk, receipts, invoices, follow-ups, ledger postings and audit trail. */
export default function PurchaseOrderDetail({ me }: { me: User }) {
  const { poNo = '' } = useParams()
  const query = usePurchaseOrder(poNo)
  const [params, setParams] = useSearchParams()
  const receiving = useDialog()
  const invoicing = useDialog()
  const approve = useAction(() => erp.approveOrder(poNo), AFFECTS.order, `Purchase order ${poNo} approved`)
  const send = useAction(() => erp.sendOrder(poNo), AFFECTS.order, `Purchase order ${poNo} marked as sent (simulated: nothing leaves the system)`)
  const draft = useAction(() => erp.draftFollowups({ po_no: poNo }), AFFECTS.intel, (r) =>
    draftedCount(r) === 0 ? 'A draft follow-up already exists for this order' : 'Follow-up drafted: it waits in the control tower outbox',
  )

  if (query.isPending) return <Skeleton active paragraph={{ rows: 10 }} />
  if (query.isError) return <LoadError error={query.error} what="Purchase order" back="/purchase-orders" backLabel="Back to purchase orders" />
  const po = query.data
  const value = po.value ?? po.lines.reduce((sum, l) => sum + (l.value ?? l.qty * l.unit_price), 0)
  const ordered = po.lines.reduce((sum, l) => sum + l.qty, 0)
  const received = po.lines.reduce((sum, l) => sum + l.received_qty, 0)
  const vendorName = po.vendor?.name ?? po.vendor_name
  const overLimit = value > APPROVAL_LIMIT && me.role !== 'admin'
  const requests = can.request(me)

  const lineColumns: ColumnsType<PoLine> = [
    {
      title: 'Item',
      dataIndex: 'item_code',
      render: (code, l) => (
        <>
          <ItemLink code={code} />
          <div>
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              {l.description}
            </Typography.Text>
          </div>
        </>
      ),
    },
    { title: 'Qty', dataIndex: 'qty', align: 'right', render: qty },
    { title: 'Received', dataIndex: 'received_qty', align: 'right', render: (v, l) => <Typography.Text type={v >= l.qty ? 'success' : undefined}>{qty(v)}</Typography.Text> },
    { title: 'Unit price', dataIndex: 'unit_price', align: 'right', render: (v) => money(v, true) },
    { title: 'Value', dataIndex: 'value', align: 'right', render: (v, l) => money(v ?? l.qty * l.unit_price) },
    { title: 'Promised', dataIndex: 'promised_date', render: (d) => <span style={{ whiteSpace: 'nowrap' }}>{fmtDate(d)}</span> },
    {
      title: 'Delivery risk',
      render: (_, l) =>
        l.risk ? (
          <Tooltip title={l.risk.reasons.length ? <ul style={{ margin: 0, paddingLeft: 16 }}>{l.risk.reasons.map((r) => <li key={r}>{r}</li>)}</ul> : undefined}>
            <div>
              <Flex gap={6} align="center">
                <RiskBar score={l.risk.score} level={l.risk.level} />
                <StateTag kind="risk" value={l.risk.level} />
              </Flex>
              <Typography.Text type="secondary" style={{ fontSize: 12, whiteSpace: 'nowrap' }}>
                predicted {fmtDate(l.risk.predicted_date)}
              </Typography.Text>
            </div>
          </Tooltip>
        ) : (
          <Typography.Text type="secondary">—</Typography.Text>
        ),
    },
    { title: 'Work order', dataIndex: 'work_order', render: (wo) => <WorkOrderTags orders={[wo]} /> },
  ]

  return (
    <>
      <Card style={{ marginBottom: 16 }}>
        <Flex justify="space-between" align="start" gap={16} wrap>
          <div>
            <Typography.Title level={3} style={{ margin: 0 }}>
              {po.po_no} <StateTag kind="po" value={po.status} />
            </Typography.Title>
            <Typography.Text type="secondary">
              <VendorLink id={po.vendor_id} name={vendorName} /> · {money(value)} before tax
            </Typography.Text>
          </div>
          <Space wrap>
            {po.status === 'DRAFT' && can.approve(me) && (
              <Tooltip title={overLimit ? `Above ${money(APPROVAL_LIMIT)}: an admin approves this order (approval limit).` : undefined}>
                <Button type="primary" icon={<CheckOutlined />} disabled={overLimit} loading={approve.isPending} onClick={() => approve.mutate()}>
                  Approve
                </Button>
              </Tooltip>
            )}
            {po.status === 'APPROVED' && requests && (
              <Popconfirm title="Mark this order as sent to the vendor?" description="Simulated: nothing leaves the system." okText="Mark as sent" onConfirm={() => send.mutate()}>
                <Button type="primary" icon={<SendOutlined />} loading={send.isPending}>
                  Send to vendor
                </Button>
              </Popconfirm>
            )}
            {RECEIVABLE.has(po.status) && requests && (
              <Button type={po.status === 'APPROVED' ? 'default' : 'primary'} icon={<InboxOutlined />} onClick={() => receiving.show()}>
                Receive goods
              </Button>
            )}
            {received > 0 && requests && po.status !== 'DRAFT' && po.status !== 'CANCELLED' && (
              <Button icon={<FileTextOutlined />} onClick={() => invoicing.show()}>
                Enter vendor invoice
              </Button>
            )}
            {OPEN.has(po.status) && po.status !== 'DRAFT' && requests && (
              <Button icon={<MailOutlined />} loading={draft.isPending} onClick={() => draft.mutate()}>
                Draft follow-up
              </Button>
            )}
          </Space>
        </Flex>
        {po.status === 'DRAFT' && !can.approve(me) && (
          <Alert type="info" showIcon style={{ marginTop: 12 }} message={`A reviewer approves this draft${value > APPROVAL_LIMIT ? ', and above the approval limit an admin' : ''}.`} />
        )}
        <Descriptions column={{ xs: 1, md: 3 }} size="small" style={{ marginTop: 16 }}>
          <Descriptions.Item label="Vendor">
            <VendorLink id={po.vendor_id} name={vendorName} />
            {po.vendor?.grade && <Tag style={{ marginLeft: 8 }}>Grade {po.vendor.grade}</Tag>}
          </Descriptions.Item>
          <Descriptions.Item label="Created">{fmtDate(po.created_on)}</Descriptions.Item>
          <Descriptions.Item label="Buyer">{po.buyer || '—'}</Descriptions.Item>
          <Descriptions.Item label="Requisition">
            <PrLink no={po.pr_no} />
          </Descriptions.Item>
          <Descriptions.Item label="Approved by">{po.approved_by || '—'}</Descriptions.Item>
          <Descriptions.Item label="Received">
            {/* By value, as the server works it out; by quantity only if it does not say. */}
            <Progress percent={Math.round(po.received_pct ?? (ordered ? (received / ordered) * 100 : 0))} size="small" style={{ margin: 0, width: 160 }} />
          </Descriptions.Item>
          {po.note && <Descriptions.Item label="Note">{po.note}</Descriptions.Item>}
        </Descriptions>
      </Card>
      <Card>
        <Tabs
          activeKey={params.get('tab') ?? 'lines'}
          onChange={(tab) => setParams({ tab }, { replace: true })}
          items={[
            {
              key: 'lines',
              label: `Lines (${po.lines.length})`,
              children: <Table size="small" rowKey="id" pagination={false} dataSource={po.lines} columns={lineColumns} scroll={{ x: 'max-content' }} />,
            },
            {
              key: 'receipts',
              label: `Receipts (${po.receipts.length})`,
              children: (
                <Table
                  size="small"
                  rowKey="grn_no"
                  pagination={false}
                  dataSource={po.receipts}
                  locale={{ emptyText: 'Nothing received yet.' }}
                  columns={[
                    { title: 'Goods receipt', dataIndex: 'grn_no', render: (no) => <GrnLink no={no} /> },
                    { title: 'Received on', dataIndex: 'received_on', render: fmtDate },
                    { title: 'Store', dataIndex: 'store_code' },
                    { title: 'Received by', dataIndex: 'received_by' },
                    { title: 'Accepted', dataIndex: 'qty_accepted', align: 'right', render: qty },
                    { title: 'Rejected', dataIndex: 'qty_rejected', align: 'right', render: (v) => (v ? <Typography.Text type="danger">{qty(v)}</Typography.Text> : qty(v)) },
                  ]}
                />
              ),
            },
            {
              key: 'invoices',
              label: `Invoices (${po.invoices.length})`,
              children: (
                <Table
                  size="small"
                  rowKey="inv_no"
                  pagination={false}
                  dataSource={po.invoices}
                  locale={{ emptyText: 'No invoices entered.' }}
                  columns={[
                    { title: 'Invoice', dataIndex: 'inv_no', render: (no) => <InvoiceLink no={no} /> },
                    { title: "Vendor's no.", dataIndex: 'vendor_invoice_no' },
                    { title: 'Date', dataIndex: 'invoice_date', render: fmtDate },
                    { title: 'Due', dataIndex: 'due_date', render: fmtDate },
                    { title: 'Status', dataIndex: 'status', render: (s) => <StateTag kind="invoice" value={s} /> },
                    { title: 'Total', dataIndex: 'total', align: 'right', render: (v) => money(v) },
                  ]}
                />
              ),
            },
            {
              key: 'followups',
              label: `Follow-ups (${po.followups.length})`,
              children: (
                <Table
                  size="small"
                  rowKey="id"
                  pagination={false}
                  dataSource={po.followups}
                  locale={{ emptyText: 'No follow-ups drafted.' }}
                  expandable={{ expandedRowRender: (f) => <Typography.Paragraph style={{ whiteSpace: 'pre-line', margin: 0 }}>{f.body}</Typography.Paragraph> }}
                  columns={[
                    { title: 'Subject', dataIndex: 'subject' },
                    { title: 'Risk', dataIndex: 'risk_level', render: (l) => <StateTag kind="risk" value={l} /> },
                    { title: 'Written by', dataIndex: 'written_by', render: (by) => <WrittenByTag by={by} /> },
                    { title: 'Status', dataIndex: 'status', render: (s) => <StateTag kind="followup" value={s} /> },
                    { title: 'Decided by', dataIndex: 'decided_by', render: (by) => by || '—' },
                    { title: 'Drafted', dataIndex: 'created_at', render: (t) => (t ? formatTime(t) : '—') },
                  ]}
                />
              ),
            },
            {
              key: 'journal',
              label: `Ledger postings (${po.journal.length})`,
              children: <JournalTable entries={po.journal} loading={false} />,
            },
            {
              key: 'audit',
              label: `Audit trail (${po.audit.length})`,
              children: <AuditTable entries={po.audit} />,
            },
          ]}
        />
      </Card>
      {receiving.key > 0 && <ReceiveForm key={`receive-${receiving.key}`} po={po} open={receiving.open} onClose={receiving.hide} />}
      {invoicing.key > 0 && <InvoiceForm key={`invoice-${invoicing.key}`} poNo={po.po_no} open={invoicing.open} onClose={invoicing.hide} />}
    </>
  )
}
