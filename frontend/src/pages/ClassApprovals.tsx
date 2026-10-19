import { CheckOutlined, PlusOutlined, RollbackOutlined } from '@ant-design/icons'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Button, Card, DatePicker, Flex, Form, Input, Modal, Select, Space, Table, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import dayjs, { type Dayjs } from 'dayjs'
import { useState } from 'react'
import { Link } from 'react-router-dom'

import { can, postJson, useClassApprovals, useRegister, type ClassApproval, type User } from '../api'
import { ApprovalTag, ErrorAlert } from '../components/Tags'

export const LONG_WAIT_DAYS = 30
const STATES = ['AWAITING', 'APPROVED', 'RETURNED WITH COMMENTS']

type Submission = Pick<ClassApproval, 'drawing_no' | 'rev' | 'submitted_to' | 'submitted_on' | 'state'>

export function WaitingDays({ days }: { days: number | null }) {
  if (days === null) return <Typography.Text type="secondary">—</Typography.Text>
  return days > LONG_WAIT_DAYS ? (
    <Typography.Text type="danger" strong>
      {days} days (over {LONG_WAIT_DAYS})
    </Typography.Text>
  ) : (
    <>{days} days</>
  )
}

/** Saves a submission or its new state. The server keeps one record per drawing revision. */
function useRecord(onDone?: () => void) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (submission: Submission) => postJson<ClassApproval>('/class-approvals', submission),
    onSuccess: () => {
      // Class approval feeds the register, the gate and the dashboard.
      for (const key of ['class-approvals', 'register', 'gate', 'audit']) queryClient.invalidateQueries({ queryKey: [key] })
      onDone?.()
    },
  })
}

function SubmissionForm({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [form] = Form.useForm<Omit<Submission, 'submitted_on'> & { submitted_on: Dayjs }>()
  const register = useRegister()
  // The form outlives the dialog, so it is cleared on the way out: the next submission starts empty.
  const done = () => {
    form.resetFields()
    onClose()
  }
  const record = useRecord(done)
  const close = () => {
    record.reset()
    done()
  }

  return (
    <Modal open={open} title="Record a submission" okText="Save" confirmLoading={record.isPending} onOk={() => form.submit()} onCancel={close} destroyOnClose>
      <Typography.Paragraph type="secondary">
        If this drawing revision already has a record, it is updated. Nothing is written to the ERP, and the next ERP extract will not overwrite it.
      </Typography.Paragraph>
      <ErrorAlert error={record.error} />
      <Form
        form={form}
        name="submission"
        layout="vertical"
        requiredMark={false}
        initialValues={{ submitted_to: 'Classification society', submitted_on: dayjs(), state: 'AWAITING' }}
        onFinish={({ submitted_on, ...rest }) => record.mutate({ ...rest, submitted_on: submitted_on.format('YYYY-MM-DD') })}
      >
        <Form.Item name="drawing_no" label="Drawing" rules={[{ required: true, message: 'Choose a drawing' }]}>
          <Select
            showSearch
            loading={register.isPending}
            placeholder="Drawing number"
            options={(register.data ?? []).map((d) => ({ value: d.drawing_no, label: `${d.drawing_no}  ${d.title}` }))}
            onChange={(no) => form.setFieldValue('rev', register.data?.find((d) => d.drawing_no === no)?.current_rev)}
          />
        </Form.Item>
        <Form.Item name="rev" label="Revision" extra="Filled in with the current revision; change it if an older one was submitted." rules={[{ required: true, pattern: /^[A-Za-z0-9]{1,5}$/, message: '1 to 5 letters or digits' }]}>
          <Input style={{ width: 120 }} />
        </Form.Item>
        <Form.Item name="submitted_to" label="Submitted to" rules={[{ required: true, whitespace: true, message: 'Who it was sent to' }]}>
          <Select options={['Classification society', 'Customer'].map((value) => ({ value }))} style={{ width: 260 }} />
        </Form.Item>
        <Form.Item name="submitted_on" label="Submitted on" rules={[{ required: true }]}>
          <DatePicker disabledDate={(day) => day.isAfter(dayjs(), 'day')} />
        </Form.Item>
        <Form.Item name="state" label="State" rules={[{ required: true }]}>
          <Select options={STATES.map((value) => ({ value }))} style={{ width: 260 }} />
        </Form.Item>
      </Form>
    </Modal>
  )
}

const COLUMNS: ColumnsType<ClassApproval> = [
  { title: 'Drawing no.', dataIndex: 'drawing_no', render: (no) => <Link to={`/register/${no}`}>{no}</Link> },
  { title: 'Title', dataIndex: 'title' },
  { title: 'Rev', dataIndex: 'rev', width: 70 },
  { title: 'Submitted to', dataIndex: 'submitted_to' },
  { title: 'Submitted on', dataIndex: 'submitted_on' },
  { title: 'Waiting', dataIndex: 'days_waiting', render: (days) => <WaitingDays days={days} /> },
  {
    title: 'State',
    dataIndex: 'state',
    filters: STATES.map((value) => ({ value, text: value })),
    onFilter: (value, a) => a.state === value,
    render: (state) => <ApprovalTag state={state} />,
  },
]

export default function ClassApprovals({ me }: { me: User }) {
  const approvals = useClassApprovals()
  const record = useRecord()
  const [adding, setAdding] = useState(false)
  const records = can.recordApprovals(me)

  const actions: ColumnsType<ClassApproval>[number] = {
    title: '',
    key: 'actions',
    render: (_, a) => {
      const set = (state: string) => record.mutate({ drawing_no: a.drawing_no, rev: a.rev, submitted_to: a.submitted_to, submitted_on: a.submitted_on, state })
      return (
        <Space size={4}>
          {a.state !== 'APPROVED' && (
            <Button size="small" icon={<CheckOutlined />} disabled={record.isPending} onClick={() => set('APPROVED')}>
              Mark approved
            </Button>
          )}
          {a.state === 'AWAITING' && (
            <Button size="small" icon={<RollbackOutlined />} disabled={record.isPending} onClick={() => set('RETURNED WITH COMMENTS')}>
              Returned
            </Button>
          )}
        </Space>
      )
    },
  }

  return (
    <Card>
      <ErrorAlert error={approvals.error ?? record.error} />
      <Flex justify="space-between" align="start" gap={16} wrap>
        <Typography.Paragraph type="secondary" style={{ maxWidth: 720 }}>
          Drawings submitted to the classification society or the customer, longest wait first. A drawing that is not yet approved puts a warning on its work orders in the Release Gate.
        </Typography.Paragraph>
        {records && (
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setAdding(true)}>
            Record submission
          </Button>
        )}
      </Flex>
      <Table
        size="small"
        rowKey="id"
        columns={records ? [...COLUMNS, actions] : COLUMNS}
        dataSource={approvals.data}
        loading={approvals.isPending}
        pagination={false}
        locale={{ emptyText: 'Nothing has been submitted.' }}
      />
      {records && <SubmissionForm open={adding} onClose={() => setAdding(false)} />}
    </Card>
  )
}
