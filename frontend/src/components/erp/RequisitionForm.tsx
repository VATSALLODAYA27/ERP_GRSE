import { MinusCircleOutlined, PlusOutlined } from '@ant-design/icons'
import { Button, DatePicker, Flex, Form, Input, InputNumber, Modal, Typography } from 'antd'
import dayjs, { type Dayjs } from 'dayjs'
import { useNavigate } from 'react-router-dom'

import { AFFECTS, erp, useAction, useItems, type NewRequisition } from '../../erpApi'
import { ItemSelect, WorkOrderInput } from './Pickers'

type Values = { work_order?: string; note?: string; lines: { item_code?: string; qty?: number; need_by?: Dayjs }[] }

/** Raise a purchase requisition. A reviewer approves it, then converts it into purchase orders. */
export default function RequisitionForm({ open, onClose, items: prefill, workOrder }: { open: boolean; onClose: () => void; items?: string[]; workOrder?: string }) {
  const [form] = Form.useForm<Values>()
  const navigate = useNavigate()
  const items = useItems()
  const create = useAction((body: NewRequisition) => erp.createRequisition(body), AFFECTS.requisition, (pr) => `Requisition ${pr?.pr_no ?? ''} submitted for approval`)

  const needBy = (code?: string) => dayjs().add(items.data?.find((i) => i.item_code === code)?.lead_time_days ?? 30, 'day')
  const initialLines = prefill?.length
    ? prefill.map((code) => ({ item_code: code, qty: items.data?.find((i) => i.item_code === code)?.reorder_qty, need_by: needBy(code) }))
    : [{ need_by: needBy() }]

  const submit = ({ work_order, note, lines }: Values) =>
    create.mutate(
      {
        work_order: work_order?.trim() || undefined,
        note: note?.trim() || undefined,
        lines: lines.map((l) => ({ item_code: l.item_code!, qty: l.qty!, need_by: l.need_by!.format('YYYY-MM-DD') })),
      },
      {
        onSuccess: (pr) => {
          onClose()
          if (pr?.pr_no) navigate(`/requisitions/${encodeURIComponent(pr.pr_no)}`)
        },
      },
    )

  return (
    <Modal open={open} title="New requisition" okText="Submit for approval" width={820} confirmLoading={create.isPending} onOk={() => form.submit()} onCancel={onClose} destroyOnHidden>
      <Typography.Paragraph type="secondary">
        Ask for material against a work order. Each item shows what is already on hand. A reviewer approves the requisition and converts it into purchase orders with the preferred vendors.
      </Typography.Paragraph>
      <Form form={form} layout="vertical" requiredMark={false} initialValues={{ work_order: workOrder, lines: initialLines }} onFinish={submit}>
        <Flex gap={12} wrap>
          <Form.Item name="work_order" label="Work order (optional)" style={{ width: 200 }}>
            <WorkOrderInput />
          </Form.Item>
          <Form.Item name="note" label="Note (optional)" style={{ flex: 1, minWidth: 240 }}>
            <Input maxLength={200} placeholder="What the material is for" />
          </Form.Item>
        </Flex>
        <Typography.Text strong>Lines</Typography.Text>
        <Form.List name="lines" rules={[{ validator: async (_, lines) => (lines?.length ? undefined : Promise.reject(new Error('Add at least one line'))) }]}>
          {(fields, { add, remove }, { errors }) => (
            <div style={{ marginTop: 8 }}>
              {fields.map((field) => (
                <Flex key={field.key} gap={8} align="start" wrap>
                  <Form.Item name={[field.name, 'item_code']} rules={[{ required: true, message: 'Choose an item' }]} style={{ flex: 1, minWidth: 280 }}>
                    <ItemSelect onChange={(code: string) => form.setFieldValue(['lines', field.name, 'need_by'], needBy(code))} />
                  </Form.Item>
                  <Form.Item name={[field.name, 'qty']} rules={[{ required: true, message: 'Quantity' }]}>
                    <InputNumber min={0.01} placeholder="Qty" style={{ width: 110 }} />
                  </Form.Item>
                  <Form.Item name={[field.name, 'need_by']} rules={[{ required: true, message: 'Need-by date' }]}>
                    <DatePicker format="D MMM YYYY" placeholder="Need by" disabledDate={(day) => day.isBefore(dayjs(), 'day')} style={{ width: 150 }} />
                  </Form.Item>
                  <Button type="text" icon={<MinusCircleOutlined />} aria-label="Remove line" disabled={fields.length === 1} onClick={() => remove(field.name)} />
                </Flex>
              ))}
              <Button type="dashed" icon={<PlusOutlined />} onClick={() => add({ need_by: needBy() })}>
                Add line
              </Button>
              <Form.ErrorList errors={errors} />
            </div>
          )}
        </Form.List>
      </Form>
    </Modal>
  )
}
