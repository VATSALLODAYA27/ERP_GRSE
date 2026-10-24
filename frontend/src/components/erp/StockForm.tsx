import { Form, Input, InputNumber, Modal, Typography } from 'antd'

import { AFFECTS, erp, qty, useAction, useItem } from '../../erpApi'
import { ItemSelect, StoreSelect, WorkOrderInput } from './Pickers'

export type StockMode = 'issue' | 'transfer' | 'adjust'

type Values = { item_code?: string; store_code?: string; to_store?: string; qty?: number; work_order?: string; note?: string }

const TEXT: Record<StockMode, { title: string; ok: string; done: string; about: string }> = {
  issue: {
    title: 'Issue stock to a work order',
    ok: 'Issue',
    done: 'Stock issued to the work order',
    about: 'Issued at the moving-average cost and charged to the work order (Dr Work in progress, Cr Inventory). A store cannot go below zero.',
  },
  transfer: {
    title: 'Transfer between stores',
    ok: 'Transfer',
    done: 'Stock transferred',
    about: 'Moves stock from one store to another at the same cost. The ledger does not change; the stock ledger shows a move out and a move in.',
  },
  adjust: {
    title: 'Adjust stock',
    ok: 'Post adjustment',
    done: 'Adjustment posted',
    about: 'Corrects a store after a physical count: a positive quantity adds stock, a negative one removes it. Posted against Inventory adjustment (5300).',
  },
}

/** Issue, transfer or adjust stock. The quantity on hand in the chosen store is shown under the store. */
export default function StockForm({ mode, open, onClose, item, store }: { mode: StockMode; open: boolean; onClose: () => void; item?: string; store?: string }) {
  const [form] = Form.useForm<Values>()
  const text = TEXT[mode]
  const code = Form.useWatch('item_code', form) ?? item
  const from = Form.useWatch('store_code', form) ?? store
  const detail = useItem(code)
  const here = detail.data?.by_store.find((s) => s.store_code === from)
  const uom = detail.data?.uom ?? ''

  const post = useAction(
    ({ item_code, store_code, to_store, qty: amount, work_order, note }: Values) => {
      const base = { item_code: item_code!, qty: amount!, note: note?.trim() || undefined }
      if (mode === 'issue') return erp.issue({ ...base, store_code: store_code!, work_order: work_order!.trim() })
      if (mode === 'transfer') return erp.transfer({ ...base, from_store: store_code!, to_store: to_store! })
      return erp.adjust({ ...base, store_code: store_code!, note: note!.trim() })
    },
    AFFECTS.stock,
    text.done,
  )

  const inStore = from && code ? `In this store: ${qty(here?.qty ?? 0)} ${uom}` : undefined

  return (
    <Modal open={open} title={text.title} okText={text.ok} confirmLoading={post.isPending} onOk={() => form.submit()} onCancel={onClose} destroyOnHidden>
      <Typography.Paragraph type="secondary">{text.about}</Typography.Paragraph>
      <Form form={form} layout="vertical" requiredMark={false} initialValues={{ item_code: item, store_code: store }} onFinish={(values) => post.mutate(values, { onSuccess: onClose })}>
        <Form.Item name="item_code" label="Item" rules={[{ required: true, message: 'Choose an item' }]}>
          <ItemSelect disabled={!!item} />
        </Form.Item>
        <Form.Item name="store_code" label={mode === 'transfer' ? 'From store' : 'Store'} extra={inStore} rules={[{ required: true, message: 'Choose a store' }]}>
          <StoreSelect />
        </Form.Item>
        {mode === 'transfer' && (
          <Form.Item
            name="to_store"
            label="To store"
            dependencies={['store_code']}
            rules={[
              { required: true, message: 'Choose where it goes' },
              ({ getFieldValue }) => ({ validator: async (_, value) => (value && value === getFieldValue('store_code') ? Promise.reject(new Error('Choose a different store')) : undefined) }),
            ]}
          >
            <StoreSelect exclude={from} />
          </Form.Item>
        )}
        <Form.Item
          name="qty"
          label={mode === 'adjust' ? 'Quantity (+ adds, - removes)' : 'Quantity'}
          rules={[
            { required: true, message: 'Enter a quantity' },
            { validator: async (_, value) => (value === 0 ? Promise.reject(new Error('Must not be zero')) : undefined) },
          ]}
        >
          <InputNumber min={mode === 'adjust' ? undefined : 0.01} addonAfter={uom || undefined} style={{ width: 200 }} />
        </Form.Item>
        {mode === 'issue' && (
          <Form.Item name="work_order" label="Work order" rules={[{ required: true, whitespace: true, message: 'The work order the material is for' }]}>
            <WorkOrderInput />
          </Form.Item>
        )}
        <Form.Item
          name="note"
          label={mode === 'adjust' ? 'Reason' : 'Note (optional)'}
          rules={mode === 'adjust' ? [{ required: true, whitespace: true, message: 'Say why the count differs' }] : []}
        >
          <Input.TextArea rows={2} maxLength={300} />
        </Form.Item>
      </Form>
    </Modal>
  )
}
