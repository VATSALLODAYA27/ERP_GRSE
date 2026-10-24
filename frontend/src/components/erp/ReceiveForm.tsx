import { App, AutoComplete, DatePicker, Empty, Flex, Form, InputNumber, Modal, Table, Typography } from 'antd'
import dayjs, { type Dayjs } from 'dayjs'

import { AFFECTS, erp, qty, useAction, type PoLine, type PurchaseOrder, type ReceiveGoods } from '../../erpApi'
import { ItemLink } from './Bits'
import { StoreSelect } from './Pickers'

type LineValues = { qty_received?: number; qty_accepted?: number; reject_reason?: string }
type Values = { store_code?: string; received_on: Dayjs; lines: LineValues[] }

const REASONS = ['Damaged in transit', 'No mill test certificate', 'Wrong grade supplied', 'Dimensions out of tolerance', 'Surface defects (pitting, laminations)'].map((value) => ({ value }))

/** Record a goods receipt against a purchase order: per line what arrived, what passed inspection, and why the rest was rejected. */
export default function ReceiveForm({ po, open, onClose }: { po: PurchaseOrder; open: boolean; onClose: () => void }) {
  const [form] = Form.useForm<Values>()
  const { message } = App.useApp()
  const receive = useAction((body: ReceiveGoods) => erp.receive(po.po_no, body), AFFECTS.receipt, (grn) => `Goods receipt ${grn?.grn_no ?? ''} recorded: stock and ledger updated`)
  const open_lines = po.lines.filter((l) => l.qty - l.received_qty > 0)
  const remaining = (l: PoLine) => Math.round((l.qty - l.received_qty) * 100) / 100

  const submit = ({ store_code, received_on, lines }: Values) => {
    // The rows are the open lines in order, so the line id comes from the order itself.
    const rows = lines.map((l, i) => ({ ...l, line_id: open_lines[i].id })).filter((l) => (l.qty_received ?? 0) > 0)
    if (!rows.length) {
      message.error('Enter a received quantity on at least one line.')
      return
    }
    receive.mutate(
      {
        store_code: store_code!,
        received_on: received_on.format('YYYY-MM-DD'),
        lines: rows.map((l) => ({
          line_id: l.line_id,
          qty_received: l.qty_received!,
          qty_accepted: l.qty_accepted ?? l.qty_received!,
          reject_reason: l.reject_reason?.trim() || undefined,
        })),
      },
      { onSuccess: onClose },
    )
  }

  return (
    <Modal open={open} title={`Receive goods against ${po.po_no}`} okText="Record receipt" width={980} confirmLoading={receive.isPending} onOk={() => form.submit()} onCancel={onClose} destroyOnHidden okButtonProps={{ disabled: !open_lines.length }}>
      <Typography.Paragraph type="secondary">
        Accepted quantities go into the store at the order price (Dr Inventory, Cr Goods received not invoiced). Rejected quantities stay open on the order and need a reason.
      </Typography.Paragraph>
      {open_lines.length === 0 ? (
        <Empty description="Every line of this order has been received." />
      ) : (
        <Form
          form={form}
          layout="vertical"
          requiredMark={false}
          initialValues={{
            received_on: dayjs(),
            lines: open_lines.map((l) => ({ qty_received: remaining(l), qty_accepted: remaining(l) })),
          }}
          onFinish={submit}
        >
          <Flex gap={12} wrap>
            <Form.Item name="store_code" label="Into store" rules={[{ required: true, message: 'Choose the receiving store' }]} style={{ width: 300 }}>
              <StoreSelect />
            </Form.Item>
            <Form.Item name="received_on" label="Received on" rules={[{ required: true }]}>
              <DatePicker format="D MMM YYYY" disabledDate={(day) => day.isAfter(dayjs(), 'day')} />
            </Form.Item>
          </Flex>
          <Form.List name="lines">
            {(fields) => (
              <Table
                size="small"
                pagination={false}
                rowKey="key"
                dataSource={fields}
                columns={[
                  {
                    title: 'Item',
                    render: (_, field) => {
                      const line = open_lines[field.name]
                      return (
                        <>
                          <ItemLink code={line.item_code} />
                          <div>
                            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                              {line.description}
                            </Typography.Text>
                          </div>
                        </>
                      )
                    },
                  },
                  {
                    title: 'Open',
                    render: (_, field) => {
                      const line = open_lines[field.name]
                      return (
                        <Typography.Text type="secondary" style={{ whiteSpace: 'nowrap' }}>
                          {qty(remaining(line))} of {qty(line.qty)}
                        </Typography.Text>
                      )
                    },
                  },
                  {
                    title: 'Received',
                    render: (_, field) => (
                      <Form.Item name={[field.name, 'qty_received']} noStyle>
                        <InputNumber min={0} max={remaining(open_lines[field.name])} style={{ width: 100 }} aria-label="Quantity received" />
                      </Form.Item>
                    ),
                  },
                  {
                    title: 'Accepted',
                    render: (_, field) => (
                      <Form.Item
                        name={[field.name, 'qty_accepted']}
                        dependencies={[['lines', field.name, 'qty_received']]}
                        style={{ margin: 0 }}
                        rules={[
                          ({ getFieldValue }) => ({
                            validator: async (_, value) => {
                              const got = getFieldValue(['lines', field.name, 'qty_received']) ?? 0
                              if ((value ?? 0) > got) throw new Error('More than received')
                            },
                          }),
                        ]}
                      >
                        <InputNumber min={0} style={{ width: 100 }} aria-label="Quantity accepted" />
                      </Form.Item>
                    ),
                  },
                  {
                    title: 'Reject reason',
                    width: 280,
                    render: (_, field) => (
                      <Form.Item
                        name={[field.name, 'reject_reason']}
                        dependencies={[
                          ['lines', field.name, 'qty_received'],
                          ['lines', field.name, 'qty_accepted'],
                        ]}
                        style={{ margin: 0 }}
                        rules={[
                          ({ getFieldValue }) => ({
                            validator: async (_, value) => {
                              const got = getFieldValue(['lines', field.name, 'qty_received']) ?? 0
                              const ok = getFieldValue(['lines', field.name, 'qty_accepted']) ?? got
                              if (ok < got && !String(value ?? '').trim()) throw new Error('Say why the rest was rejected')
                            },
                          }),
                        ]}
                      >
                        <AutoComplete options={REASONS} placeholder="Only if some is rejected" allowClear style={{ width: '100%' }} />
                      </Form.Item>
                    ),
                  },
                ]}
              />
            )}
          </Form.List>
        </Form>
      )}
    </Modal>
  )
}
