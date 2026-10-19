import { UploadOutlined } from '@ant-design/icons'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Alert, Button, Form, Input, Modal, Select, Upload } from 'antd'
import { useEffect } from 'react'

import { api, postJson, type Drawing, type ReadResult } from '../api'
import { ErrorAlert } from './Tags'

const STATUSES = ['APPROVED', 'UNDER REVIEW', 'FOR INFORMATION']
type Values = Pick<Drawing, 'drawing_no' | 'title' | 'current_rev' | 'status'>

/** Admin only: add a drawing to the register, or change an existing one. `drawing` given means edit. */
export default function DrawingForm({ open, drawing, onClose }: { open: boolean; drawing?: Drawing; onClose: () => void }) {
  const queryClient = useQueryClient()
  const [form] = Form.useForm<Values>()
  const editing = !!drawing

  useEffect(() => {
    if (open) form.setFieldsValue(drawing ?? { drawing_no: '', title: '', current_rev: '', status: 'UNDER REVIEW' })
  }, [open, drawing, form])

  const save = useMutation({
    mutationFn: ({ drawing_no, ...rest }: Values) =>
      editing
        ? api<Drawing>(`/register/${encodeURIComponent(drawing.drawing_no)}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(rest) })
        : postJson<Drawing>('/register', { drawing_no, ...rest }),
    onSuccess: () => {
      // The register feeds the gate and the dashboard, so they are refreshed too.
      for (const key of ['register', 'gate', 'class-approvals', 'audit']) queryClient.invalidateQueries({ queryKey: [key] })
      onClose()
    },
  })

  // Optional shortcut: read a drawing PDF's title block and put its values in the form for the admin to check.
  const read = useMutation({
    mutationFn: (pdf: File) => {
      const body = new FormData()
      body.append('file', pdf)
      return api<ReadResult>('/checks/read', { method: 'POST', body })
    },
    onSuccess: ({ fields }) =>
      form.setFieldsValue({
        ...(editing ? {} : { drawing_no: fields.drawing_no.value }),
        title: fields.title.value,
        current_rev: fields.revision.value,
        ...(STATUSES.includes(fields.status.value) ? { status: fields.status.value } : {}),
      }),
  })

  const close = () => {
    save.reset()
    read.reset()
    onClose()
  }

  return (
    <Modal
      open={open}
      title={editing ? `Update ${drawing.drawing_no}` : 'Add a drawing to the register'}
      okText={editing ? 'Save changes' : 'Add drawing'}
      confirmLoading={save.isPending}
      onOk={() => form.submit()}
      onCancel={close}
      destroyOnClose
    >
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
        message="This changes the tool's copy of the register. Nothing is written to the ERP, and the next ERP extract will not overwrite it."
      />
      <ErrorAlert error={save.error ?? read.error} />
      <Upload
        accept=".pdf,application/pdf"
        maxCount={1}
        showUploadList={false}
        beforeUpload={(pdf) => {
          read.mutate(pdf)
          return false
        }}
      >
        <Button icon={<UploadOutlined />} loading={read.isPending} style={{ marginBottom: 16 }}>
          Fill in from a drawing PDF
        </Button>
      </Upload>
      <Form form={form} name="drawing" layout="vertical" requiredMark={false} onFinish={save.mutate}>
        <Form.Item
          name="drawing_no"
          label="Drawing number"
          rules={[{ required: true, pattern: /^[A-Za-z0-9][A-Za-z0-9._/-]{1,39}$/, message: 'Letters, digits, dot, dash, slash or underscore; 2 to 40 characters' }]}
        >
          <Input disabled={editing} />
        </Form.Item>
        <Form.Item name="title" label="Title" rules={[{ required: true, whitespace: true, message: 'Enter the title' }]}>
          <Input maxLength={120} />
        </Form.Item>
        <Form.Item
          name="current_rev"
          label="Current revision"
          extra={editing ? 'Changing this makes the previous revision superseded: work orders released against it become blocked.' : undefined}
          rules={[{ required: true, pattern: /^[A-Za-z0-9]{1,5}$/, message: '1 to 5 letters or digits' }]}
        >
          <Input style={{ width: 120 }} />
        </Form.Item>
        <Form.Item name="status" label="Status" extra="Only APPROVED drawings can be released for production." rules={[{ required: true }]}>
          <Select options={STATUSES.map((value) => ({ value }))} style={{ width: 220 }} />
        </Form.Item>
      </Form>
    </Modal>
  )
}
