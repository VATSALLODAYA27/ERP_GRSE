import { CheckOutlined, CloseOutlined, WalletOutlined } from '@ant-design/icons'
import { Alert, Button, Card, DatePicker, Descriptions, Flex, Form, Modal, Radio, Skeleton, Space, Table, Tabs, Typography } from 'antd'
import dayjs, { type Dayjs } from 'dayjs'
import { useState } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'

import { can, type User } from '../api'
import { AFFECTS, erp, fmtDate, money, qty, useAction, useInvoice, type Invoice, type Payment } from '../erpApi'
import { AuditTable, ItemLink, LoadError, PoLink, ReasonModal, RefLink, StateTag, VendorLink } from '../components/erp/Bits'
import MatchTable from '../components/erp/MatchTable'
import { JournalTable } from './GeneralLedger'
import { DueDate } from './Invoices'

/** RTGS is for payments of ₹2 lakh and more; below that NEFT is the usual mode. */
const RTGS_FROM = 200_000

function PayModal({ invoice, open, onClose }: { invoice: Invoice; open: boolean; onClose: () => void }) {
  const [form] = Form.useForm<{ mode: 'NEFT' | 'RTGS'; paid_on: Dayjs }>()
  const pay = useAction((body: { mode: 'NEFT' | 'RTGS'; paid_on: string }) => erp.pay(invoice.inv_no, body), AFFECTS.invoice, `Payment recorded for ${invoice.inv_no}`)
  return (
    <Modal open={open} title={`Pay ${invoice.inv_no}`} okText={`Pay ${money(invoice.total)}`} confirmLoading={pay.isPending} onOk={() => form.submit()} onCancel={onClose} destroyOnHidden>
      <Typography.Paragraph type="secondary">
        Records the payment and posts it (Dr Accounts payable, Cr Bank). shortcut: simulated; no bank file is produced.
      </Typography.Paragraph>
      <Form
        form={form}
        layout="vertical"
        requiredMark={false}
        initialValues={{ mode: invoice.total >= RTGS_FROM ? 'RTGS' : 'NEFT', paid_on: dayjs() }}
        onFinish={({ mode, paid_on }) => pay.mutate({ mode, paid_on: paid_on.format('YYYY-MM-DD') }, { onSuccess: onClose })}
      >
        <Form.Item name="mode" label="Mode">
          <Radio.Group
            options={[
              { value: 'NEFT', label: 'NEFT' },
              { value: 'RTGS', label: 'RTGS' },
            ]}
          />
        </Form.Item>
        <Form.Item name="paid_on" label="Paid on" rules={[{ required: true }]}>
          <DatePicker format="D MMM YYYY" disabledDate={(day) => day.isAfter(dayjs(), 'day')} />
        </Form.Item>
      </Form>
    </Modal>
  )
}

/** One vendor invoice: the 3-way match, the decision, the payment and the ledger postings. */
export default function InvoiceDetail({ me }: { me: User }) {
  const { invNo = '' } = useParams()
  const query = useInvoice(invNo)
  const [params, setParams] = useSearchParams()
  const [dialog, setDialog] = useState<'approve' | 'reject' | 'pay' | null>(null)
  const approve = useAction((reason: string) => erp.approveInvoice(invNo, reason || undefined), AFFECTS.invoice, `Invoice ${invNo} approved and posted to the ledger`)
  const reject = useAction((reason: string) => erp.rejectInvoice(invNo, reason), AFFECTS.invoice, `Invoice ${invNo} rejected`)
  const close = () => setDialog(null)

  if (query.isPending) return <Skeleton active paragraph={{ rows: 10 }} />
  if (query.isError) return <LoadError error={query.error} what="Invoice" back="/invoices" backLabel="Back to vendor invoices" />
  const inv = query.data
  const decides = can.approve(me)
  const exception = inv.status === 'EXCEPTION'
  const undecided = inv.status === 'MATCHED' || exception
  const flags = inv.flags ?? []

  return (
    <>
      <Card style={{ marginBottom: 16 }}>
        <Flex justify="space-between" align="start" gap={16} wrap>
          <div>
            <Typography.Title level={3} style={{ margin: 0 }}>
              {inv.inv_no} <StateTag kind="invoice" value={inv.status} />
            </Typography.Title>
            <Typography.Text type="secondary">
              <VendorLink id={inv.vendor_id} name={inv.vendor_name} /> · vendor's invoice {inv.vendor_invoice_no}
            </Typography.Text>
          </div>
          {decides && (
            <Space wrap>
              {undecided && (
                <>
                  <Button type="primary" icon={<CheckOutlined />} onClick={() => setDialog('approve')}>
                    Approve
                  </Button>
                  <Button danger icon={<CloseOutlined />} onClick={() => setDialog('reject')}>
                    Reject
                  </Button>
                </>
              )}
              {inv.status === 'APPROVED' && (
                <Button type="primary" icon={<WalletOutlined />} onClick={() => setDialog('pay')}>
                  Pay
                </Button>
              )}
            </Space>
          )}
        </Flex>
        {flags.length > 0 && (
          <Alert
            type="warning"
            showIcon
            style={{ marginTop: 12 }}
            message={`${flags.length} anomal${flags.length === 1 ? 'y' : 'ies'} flagged on this invoice`}
            description={flags.map((f, i) => (
              <div key={typeof f === 'string' ? `${f}-${i}` : f.id}>
                {typeof f === 'string' ? (
                  f
                ) : (
                  <>
                    <StateTag kind="severity" value={f.severity} /> {f.message} {f.ref_no !== inv.inv_no && <RefLink type={f.ref_type} no={f.ref_no} />}
                  </>
                )}
              </div>
            ))}
          />
        )}
        {!decides && undecided && <Alert type="info" showIcon style={{ marginTop: 12 }} message="A reviewer approves or rejects the invoice; an exception needs a written reason." />}
        <Descriptions column={{ xs: 1, md: 3 }} size="small" style={{ marginTop: 16 }}>
          <Descriptions.Item label="Purchase order">
            <PoLink no={inv.po_no} />
          </Descriptions.Item>
          <Descriptions.Item label="Invoice date">{fmtDate(inv.invoice_date)}</Descriptions.Item>
          <Descriptions.Item label="Due">
            <DueDate date={inv.due_date} status={inv.status} />
          </Descriptions.Item>
          <Descriptions.Item label="Amount before tax">{money(inv.amount, true)}</Descriptions.Item>
          <Descriptions.Item label="GST">{money(inv.tax, true)}</Descriptions.Item>
          <Descriptions.Item label="Total">
            <strong>{money(inv.total, true)}</strong>
          </Descriptions.Item>
          <Descriptions.Item label="Approved by">{inv.approved_by || '—'}</Descriptions.Item>
          {inv.approval_reason && <Descriptions.Item label="Reason">{inv.approval_reason}</Descriptions.Item>}
        </Descriptions>
      </Card>
      <Card>
        <Tabs
          activeKey={params.get('tab') ?? 'match'}
          onChange={(tab) => setParams({ tab }, { replace: true })}
          items={[
            { key: 'match', label: '3-way match', children: <MatchTable match={inv.match} /> },
            {
              key: 'lines',
              label: `Lines (${inv.lines.length})`,
              children: (
                <Table
                  size="small"
                  rowKey="key"
                  pagination={false}
                  dataSource={inv.lines.map((l, i) => ({ ...l, key: l.id ?? i }))}
                  columns={[
                    { title: 'Item', dataIndex: 'item_code', render: (code) => <ItemLink code={code} /> },
                    { title: 'Description', dataIndex: 'description', render: (d) => d || '—' },
                    { title: 'Qty', dataIndex: 'qty', align: 'right', render: qty },
                    { title: 'Unit price', dataIndex: 'unit_price', align: 'right', render: (v) => money(v, true) },
                    { title: 'Value', align: 'right', render: (_, l) => money(l.qty * l.unit_price, true) },
                  ]}
                />
              ),
            },
            {
              key: 'payments',
              label: `Payments (${inv.payments.length})`,
              children: (
                <Table<Payment>
                  size="small"
                  rowKey="pay_no"
                  pagination={false}
                  dataSource={inv.payments}
                  locale={{ emptyText: 'Not paid yet.' }}
                  columns={[
                    { title: 'Payment', dataIndex: 'pay_no', render: (no) => <strong>{no}</strong> },
                    { title: 'Paid on', dataIndex: 'paid_on', render: fmtDate },
                    { title: 'Mode', dataIndex: 'mode' },
                    { title: 'Paid by', dataIndex: 'paid_by' },
                    { title: 'Amount', dataIndex: 'amount', align: 'right', render: (v) => money(v, true) },
                  ]}
                />
              ),
            },
            { key: 'journal', label: `Ledger postings (${inv.journal.length})`, children: <JournalTable entries={inv.journal} loading={false} /> },
            ...(inv.audit ? [{ key: 'audit', label: `Audit trail (${inv.audit.length})`, children: <AuditTable entries={inv.audit} /> }] : []),
          ]}
        />
      </Card>
      <ReasonModal
        open={dialog === 'approve'}
        title={`Approve ${inv.inv_no}`}
        okText="Approve and post"
        required={exception}
        description={
          exception
            ? 'The 3-way match found differences. Say why the invoice may still be approved; the reason is kept with the invoice and in the audit log.'
            : 'The invoice matches the order and the receipt. Approving posts it to the ledger (Dr GRNI and GST, Cr Accounts payable).'
        }
        loading={approve.isPending}
        onClose={close}
        onSubmit={(reason) => approve.mutate(reason, { onSuccess: close })}
      />
      <ReasonModal
        open={dialog === 'reject'}
        title={`Reject ${inv.inv_no}`}
        okText="Reject"
        danger
        required
        description="The vendor is asked for a corrected invoice. Nothing is posted to the ledger."
        loading={reject.isPending}
        onClose={close}
        onSubmit={(reason) => reject.mutate(reason, { onSuccess: close })}
      />
      {dialog === 'pay' && <PayModal invoice={inv} open onClose={close} />}
    </>
  )
}
