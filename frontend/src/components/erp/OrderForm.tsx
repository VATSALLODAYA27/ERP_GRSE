import { MinusCircleOutlined, PlusOutlined } from '@ant-design/icons'
import { Alert, Button, DatePicker, Flex, Form, Input, InputNumber, Modal, Typography } from 'antd'
import dayjs, { type Dayjs } from 'dayjs'
import { useNavigate } from 'react-router-dom'

import { AFFECTS, APPROVAL_LIMIT, erp, money, useAction, useItems, useVendors, type NewOrder } from '../../erpApi'
import { ItemSelect, VendorSelect, WorkOrderInput } from './Pickers'

type Line = { item_code?: string; qty?: number; unit_price?: number; promised_date?: Dayjs; work_order?: string }
type Values = { vendor_id?: string; note?: string; lines: Line[] }

/** Raise a purchase order directly. It starts as a draft; a reviewer approves it (an admin above the approval limit). */
export default function OrderForm({ open, onClose, vendorId }: { open: boolean; onClose: () => void; vendorId?: string }) {
  const [form] = Form.useForm<Values>()
  const navigate = useNavigate()
  const items = useItems()
  const vendors = useVendors()
  const create = useAction((body: NewOrder) => erp.createOrder(body), AFFECTS.order, (po) => `Purchase order ${po?.po_no ?? ''} saved as a draft`)
  const lines = Form.useWatch('lines', form) ?? []
  const vendor = Form.useWatch('vendor_id', form)
  const total = lines.reduce((sum, l) => sum + (l?.qty ?? 0) * (l?.unit_price ?? 0), 0)

  // The promised date starts at the vendor's usual lead time, or the item's when no vendor is chosen yet.
  const promised = (code?: string) =>
    dayjs().add(vendors.data?.find((v) => v.vendor_id === form.getFieldValue('vendor_id'))?.lead_time_days ?? items.data?.find((i) => i.item_code === code)?.lead_time_days ?? 30, 'day')

  const pickItem = (index: number, code: string) => {
    const item = items.data?.find((i) => i.item_code === code)
    if (item) form.setFieldValue(['lines', index, 'unit_price'], item.std_price)
    form.setFieldValue(['lines', index, 'promised_date'], promised(code))
  }

  const submit = ({ vendor_id, note, lines }: Values) =>
    create.mutate(
      {
        vendor_id: vendor_id!,
        note: note?.trim() || undefined,
        lines: lines.map((l) => ({
          item_code: l.item_code!,
          qty: l.qty!,
          unit_price: l.unit_price!,
          promised_date: l.promised_date!.format('YYYY-MM-DD'),
          work_order: l.work_order?.trim() || undefined,
        })),
      },
      {
        onSuccess: (po) => {
          onClose()
          if (po?.po_no) navigate(`/purchase-orders/${encodeURIComponent(po.po_no)}`)
        },
      },
    )

  return (
    <Modal open={open} title="New purchase order" okText="Save as draft" width={1040} confirmLoading={create.isPending} onOk={() => form.submit()} onCancel={onClose} destroyOnHidden>
      <Typography.Paragraph type="secondary">
        Prices start at the item's standard price and dates at the vendor's usual lead time; change either if the quotation differs. Nothing is sent to the vendor until the order is approved and sent.
      </Typography.Paragraph>
      <Form form={form} layout="vertical" requiredMark={false} initialValues={{ vendor_id: vendorId, lines: [{}] }} onFinish={submit}>
        <Flex gap={12} wrap>
          <Form.Item name="vendor_id" label="Vendor" rules={[{ required: true, message: 'Choose a vendor' }]} style={{ width: 380 }}>
            <VendorSelect />
          </Form.Item>
          <Form.Item name="note" label="Note (optional)" style={{ flex: 1, minWidth: 240 }}>
            <Input maxLength={200} placeholder="Quotation reference, delivery terms" />
          </Form.Item>
        </Flex>
        <Typography.Text strong>Lines</Typography.Text>
        <Form.List name="lines" rules={[{ validator: async (_, rows) => (rows?.length ? undefined : Promise.reject(new Error('Add at least one line'))) }]}>
          {(fields, { add, remove }, { errors }) => (
            <div style={{ marginTop: 8 }}>
              {fields.map((field) => (
                <Flex key={field.key} gap={8} align="start" wrap>
                  <Form.Item name={[field.name, 'item_code']} rules={[{ required: true, message: 'Choose an item' }]} style={{ flex: 1, minWidth: 260 }}>
                    <ItemSelect onChange={(code: string) => pickItem(field.name, code)} />
                  </Form.Item>
                  <Form.Item name={[field.name, 'qty']} rules={[{ required: true, message: 'Quantity' }]}>
                    <InputNumber min={0.01} placeholder="Qty" style={{ width: 100 }} />
                  </Form.Item>
                  <Form.Item name={[field.name, 'unit_price']} rules={[{ required: true, message: 'Unit price' }]}>
                    <InputNumber min={0.01} prefix="₹" placeholder="Unit price" style={{ width: 140 }} />
                  </Form.Item>
                  <Form.Item name={[field.name, 'promised_date']} rules={[{ required: true, message: 'Promised date' }]}>
                    <DatePicker format="D MMM YYYY" placeholder="Promised" disabledDate={(day) => day.isBefore(dayjs(), 'day')} style={{ width: 140 }} />
                  </Form.Item>
                  <Form.Item name={[field.name, 'work_order']}>
                    <WorkOrderInput style={{ width: 130 }} placeholder="Work order" />
                  </Form.Item>
                  <Button type="text" icon={<MinusCircleOutlined />} aria-label="Remove line" disabled={fields.length === 1} onClick={() => remove(field.name)} />
                </Flex>
              ))}
              <Button type="dashed" icon={<PlusOutlined />} onClick={() => add({})}>
                Add line
              </Button>
              <Form.ErrorList errors={errors} />
            </div>
          )}
        </Form.List>
      </Form>
      <Flex justify="end" style={{ marginTop: 12 }}>
        <Typography.Text>
          Order value before tax: <strong>{money(total)}</strong>
        </Typography.Text>
      </Flex>
      {vendor && total > APPROVAL_LIMIT && (
        <Alert type="info" showIcon style={{ marginTop: 12 }} message={`Above ${money(APPROVAL_LIMIT)}, so an admin must approve this order (approval limit).`} />
      )}
    </Modal>
  )
}
