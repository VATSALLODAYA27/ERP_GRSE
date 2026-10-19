import { EditOutlined } from '@ant-design/icons'
import { Button, Card, Descriptions, Flex, Result, Skeleton, Table, Tabs, Tag, Timeline, Typography } from 'antd'
import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { ApiError, can, useChecks, useDrawing, type User } from '../api'
import DrawingForm from '../components/DrawingForm'
import ChecksTable from '../components/ChecksTable'
import GateTable from '../components/GateTable'
import { ApprovalTag, StatusTag } from '../components/Tags'
import { WaitingDays } from './ClassApprovals'

/** Everything the ERP extract holds about one drawing, plus the checks run on it. */
export default function DrawingDetail({ me }: { me: User }) {
  const [editing, setEditing] = useState(false)
  const { drawingNo = '' } = useParams()
  const query = useDrawing(drawingNo)
  const checks = useChecks()

  if (query.isPending) return <Skeleton active paragraph={{ rows: 10 }} />
  if (query.isError) {
    const missing = query.error instanceof ApiError && query.error.status === 404
    return <Result status={missing ? '404' : 'error'} title={missing ? 'Drawing not found in the register' : query.error.message} extra={<Link to="/register">Back to the register</Link>} />
  }
  const { drawing, revisions, change_notes, bom, work_orders, class_approvals } = query.data
  const noteFor = (rev: string) => change_notes.find((note) => note.to_rev === rev)

  return (
    <>
      <Card style={{ marginBottom: 16 }}>
        <Flex justify="space-between" align="start">
          <Typography.Title level={3} style={{ marginTop: 0 }}>
            {drawing.drawing_no} {drawing.source === 'manual' && <Tag>Edited in the tool</Tag>}
          </Typography.Title>
          {can.editRegister(me) && (
            <Button icon={<EditOutlined />} onClick={() => setEditing(true)}>
              Update drawing
            </Button>
          )}
        </Flex>
        <DrawingForm open={editing} drawing={drawing} onClose={() => setEditing(false)} />
        <Descriptions column={{ xs: 1, md: 3 }} size="small">
          <Descriptions.Item label="Title">{drawing.title}</Descriptions.Item>
          <Descriptions.Item label="Current revision">{drawing.current_rev}</Descriptions.Item>
          <Descriptions.Item label="Register status">
            <StatusTag status={drawing.status} />
          </Descriptions.Item>
        </Descriptions>
      </Card>
      <Card>
        <Tabs
          items={[
            {
              key: 'revisions',
              label: `Revision history (${revisions.length})`,
              children: (
                <Timeline
                  style={{ marginTop: 8 }}
                  items={revisions.map((revision) => {
                    const note = noteFor(revision.rev)
                    return {
                      color: revision.rev === drawing.current_rev ? 'green' : 'gray',
                      children: (
                        <>
                          <Typography.Text strong>Rev {revision.rev}</Typography.Text> <StatusTag status={revision.status} /> issued {revision.issued_on}
                          {note && (
                            <Typography.Paragraph style={{ margin: '4px 0 0' }}>
                              <Typography.Text strong>{note.ecn_no}:</Typography.Text> {note.description}. <Typography.Text type="secondary">Reason: {note.reason}.</Typography.Text>
                            </Typography.Paragraph>
                          )}
                        </>
                      ),
                    }
                  })}
                />
              ),
            },
            {
              key: 'bom',
              label: 'Bill of materials',
              children: (
                <Table
                  size="small"
                  rowKey="id"
                  pagination={false}
                  dataSource={bom}
                  columns={[
                    {
                      title: 'Rev',
                      dataIndex: 'rev',
                      width: 80,
                      filters: revisions.map((r) => ({ value: r.rev, text: `Rev ${r.rev}` })),
                      defaultFilteredValue: [drawing.current_rev],
                      onFilter: (value, item) => item.rev === value,
                    },
                    { title: 'Part no.', dataIndex: 'part_no', render: (no) => <strong>{no}</strong> },
                    { title: 'Description', dataIndex: 'description' },
                    { title: 'Material', dataIndex: 'material' },
                    { title: 'Thk (mm)', dataIndex: 'thickness_mm' },
                    { title: 'Qty', dataIndex: 'qty' },
                  ]}
                />
              ),
            },
            { key: 'orders', label: `Work orders (${work_orders.length})`, children: <GateTable rows={work_orders} loading={false} /> },
            {
              key: 'approvals',
              label: 'Class approvals',
              children: (
                <Table
                  size="small"
                  rowKey="id"
                  pagination={false}
                  dataSource={class_approvals}
                  locale={{ emptyText: 'Not submitted for class or customer approval.' }}
                  columns={[
                    { title: 'Rev', dataIndex: 'rev', width: 80 },
                    { title: 'Submitted to', dataIndex: 'submitted_to' },
                    { title: 'Submitted on', dataIndex: 'submitted_on' },
                    { title: 'Waiting', dataIndex: 'days_waiting', render: (days) => <WaitingDays days={days} /> },
                    { title: 'State', dataIndex: 'state', render: (state) => <ApprovalTag state={state} /> },
                  ]}
                />
              ),
            },
            {
              key: 'checks',
              label: 'Checks',
              children: <ChecksTable checks={checks.data?.filter((c) => c.drawing_no === drawing.drawing_no)} loading={checks.isPending} />,
            },
          ]}
        />
      </Card>
    </>
  )
}
