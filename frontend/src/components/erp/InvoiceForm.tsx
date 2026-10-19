import { Button, DatePicker, Descriptions, Flex, Form, Input, InputNumber, Modal, Select, Skeleton, Table, Typography } from 'antd'
import dayjs, { type Dayjs } from 'dayjs'
import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { AFFECTS, erp, money, useAction, useInvoice, usePurchaseOrder, usePurchaseOrders, type Invoice, type NewInvoice } from '../../erpApi'
import { ItemLink, StateTag } from './Bits'
import MatchTable from './MatchTable'

type Line = { item_code: string; description?: string; qty?: number; unit_price?: number }
type Values = { po_no?: string; vendor_invoice_no?: string; invoice_date: Dayjs; lines: Line[] }

/** Orders a vendor can bill: approved or later, not cancelled. */
const BILLABLE = new Set(['SENT', 'PART_RECEIVED', 'RECEIVED', 'CLOSED', 'APPROVED'])

/** shortcut: the dialog estimates GST at 18% for the preview; the server computes the figures it stores. */
const GST = 0.18

/**
 * Enter a vendor's invoice against a purchase order. Lines start from the order (accepted quantity, order price) and
 * are edited to what the paper invoice says; on saving, the 3-way match result is shown straight away.
 */
export default function InvoiceForm({ open, onClose, poNo }: { open: boolean; onClose: () => void; poNo?: string }) {
  const [form] = Form.useForm<Values>()
  const navigate = useNavigate()
  const [saved, setSaved] = useState<Invoice | null>(null)
  const orders = usePurchaseOrders()
  const chosen = Form.useWatch('po_no', form) ?? poNo
  const po = usePurchaseOrder(chosen ?? '')
  const lines = Form.useWatch('lines', form) ?? []
  const amount = lines.reduce((sum, l) => sum + (l?.qty ?? 0) * (l?.unit_price ?? 0), 0)
  // The answer to the POST may not carry the match; then the saved invoice is read back.
  const readBack = useInvoice(saved && !saved.match ? saved.inv_no : undefined)
  const result = saved?.match ? saved : readBack.data

  const create = useAction((body: NewInvoice) => erp.createInvoice(body), AFFECTS.invoice, (inv) => `Invoice ${inv?.inv_no ?? ''} entered`)

  // Fill the lines from the order once per chosen order, so edits are not overwritten on the next refresh.
  const filledFor = useRef<string>()
  useEffect(() => {
    if (!po.data || filledFor.current === po.data.po_no) return
    filledFor.current = po.data.po_no
    form.setFieldValue(
      'lines',
      po.data.lines.map((l) => ({ item_code: l.item_code, description: l.description, qty: l.received_qty > 0 ? l.received_qty : l.qty, unit_price: l.unit_price })),
    )
  }, [po.data, form])

  const submit = ({ po_no, vendor_invoice_no, invoice_date, lines }: Values) =>
    create.mutate(
      {
        po_no: (po_no ?? poNo)!,
        vendor_invoice_no: vendor_invoice_no!.trim(),
        invoice_date: invoice_date.format('YYYY-MM-DD'),
        lines: lines.filter((l) => (l.qty ?? 0) > 0).map((l) => ({ item_code: l.item_code, qty: l.qty!, unit_price: l.unit_price! })),
      },
      { onSuccess: (inv) => setSaved(inv) },
    )

  const openInvoice = () => {
    onClose()
    if (saved?.inv_no) navigate(`/invoices/${encodeURIComponent(saved.inv_no)}`)
  }

  const resultView = result ? (
    <>
      <Descriptions size="small" column={{ xs: 1, md: 3 }} style={{ marginBottom: 12 }}>
        <Descriptions.Item label="Status">
          <StateTag kind="invoice" value={result.status} />
        </Descriptions.Item>
        <Descriptions.Item label="Vendor invoice no.">{result.vendor_invoice_no}</Descriptions.Item>
        <Descriptions.Item label="Total with tax">{money(result.total)}</Descriptions.Item>
      </Descriptions>
      <MatchTable match={result.match} />
    </>
  ) : readBack.isError ? (
    <Typography.Text type="danger">{readBack.error.message}</Typography.Text>
  ) : !saved?.inv_no ? (
    <Typography.Text>The invoice was saved. Its match result is on the invoice page.</Typography.Text>
  ) : (
    <Skeleton active />
  )

  const formView = (
    <>
      <Typography.Paragraph type="secondary">
        Lines start from the order: accepted quantity at the order price. Change them to what the vendor's invoice says. On saving, the invoice is matched against the order and the goods receipt.
      </Typography.Paragraph>
      <Form form={form} layout="vertical" requiredMark={false} initialValues={{ po_no: poNo, invoice_date: dayjs(), lines: [] }} onFinish={submit}>
        <Flex gap={12} wrap>
          <Form.Item name="po_no" label="Purchase order" rules={[{ required: true, message: 'Choose the order' }]} style={{ width: 300 }}>
            <Select
              showSearch
              disabled={!!poNo}
              loading={orders.isPending}
              placeholder="PO number or vendor"
              optionFilterProp="label"
              options={(orders.data ?? []).filter((o) => BILLABLE.has(o.status)).map((o) => ({ value: o.po_no, label: `${o.po_no} · ${o.vendor_name}` }))}
            />
          </Form.Item>
          <Form.Item name="vendor_invoice_no" label="Vendor's invoice number" rules={[{ required: true, whitespace: true, message: 'As printed on the invoice' }]} style={{ width: 220 }}>
            <Input maxLength={40} placeholder="INV/26/0412" />
          </Form.Item>
          <Form.Item name="invoice_date" label="Invoice date" rules={[{ required: true }]}>
            <DatePicker format="D MMM YYYY" disabledDate={(day) => day.isAfter(dayjs(), 'day')} />
          </Form.Item>
        </Flex>
        <Form.List name="lines" rules={[{ validator: async (_, rows) => (rows?.length ? undefined : Promise.reject(new Error('Choose an order to fill the lines'))) }]}>
          {(fields, _, { errors }) => (
            <>
              <Table
                size="small"
                pagination={false}
                rowKey="key"
                dataSource={fields}
                loading={!!chosen && po.isPending}
                locale={{ emptyText: chosen ? 'This order has no lines.' : 'Choose a purchase order to fill the lines.' }}
                columns={[
                  {
                    title: 'Item',
                    render: (_, field) => {
                      const line: Line | undefined = form.getFieldValue(['lines', field.name])
                      return line ? (
                        <>
                          <ItemLink code={line.item_code} />
                          <div>
                            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                              {line.description}
                            </Typography.Text>
                          </div>
                        </>
                      ) : null
                    },
                  },
                  {
                    title: 'Invoiced qty',
                    render: (_, field) => (
                      <Form.Item name={[field.name, 'qty']} noStyle>
                        <InputNumber min={0} style={{ width: 110 }} aria-label="Invoiced quantity" />
                      </Form.Item>
                    ),
                  },
                  {
                    title: 'Invoiced unit price',
                    render: (_, field) => (
                      <Form.Item name={[field.name, 'unit_price']} noStyle>
                        <InputNumber min={0} prefix="₹" style={{ width: 150 }} aria-label="Invoiced unit price" />
                      </Form.Item>
                    ),
                  },
                  {
                    title: 'Line value',
                    align: 'right',
                    render: (_, field) => money((lines[field.name]?.qty ?? 0) * (lines[field.name]?.unit_price ?? 0)),
                  },
                ]}
              />
              <Form.ErrorList errors={errors} />
            </>
          )}
        </Form.List>
      </Form>
      <Flex justify="end" gap={24} style={{ marginTop: 12 }}>
        <Typography.Text type="secondary">Before tax {money(amount)}</Typography.Text>
        <Typography.Text type="secondary">GST 18% (estimate) {money(amount * GST)}</Typography.Text>
        <Typography.Text strong>Total {money(amount * (1 + GST))}</Typography.Text>
      </Flex>
    </>
  )

  return (
    // One dialog for both steps, so it does not close and reopen when the invoice is saved.
    <Modal
      open={open}
      title={saved ? `Invoice ${saved.inv_no} entered` : 'Enter vendor invoice'}
      okText="Save and match"
      width={980}
      confirmLoading={create.isPending}
      onOk={() => form.submit()}
      onCancel={onClose}
      destroyOnHidden
      footer={
        saved ? (
          <Flex justify="end" gap={8}>
            <Button onClick={onClose}>Done</Button>
            <Button type="primary" onClick={openInvoice}>
              Open the invoice
            </Button>
          </Flex>
        ) : undefined
      }
    >
      {saved ? resultView : formView}
    </Modal>
  )
}
