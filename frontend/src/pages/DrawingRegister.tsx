import { PlusOutlined } from '@ant-design/icons'
import { Button, Card, Flex, Input, Select, Table, Tag, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useState } from 'react'
import { Link } from 'react-router-dom'

import { can, useChecks, useRegister, type CheckSummary, type RegisterRow, type User } from '../api'
import DrawingForm from '../components/DrawingForm'
import { ApprovalTag, ErrorAlert, StatusTag, VerdictTag } from '../components/Tags'

export default function DrawingRegister({ me }: { me: User }) {
  const [adding, setAdding] = useState(false)
  const register = useRegister()
  const checks = useChecks()
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState<string>()

  // Checks arrive newest first, so the first one seen for a drawing is its latest.
  const latest = new Map<string, CheckSummary>()
  for (const check of checks.data ?? []) if (!latest.has(check.drawing_no)) latest.set(check.drawing_no, check)

  const needle = search.trim().toLowerCase()
  const rows = (register.data ?? []).filter(
    (d) => (!status || d.status === status) && (d.drawing_no.toLowerCase().includes(needle) || d.title.toLowerCase().includes(needle)),
  )

  const columns: ColumnsType<RegisterRow> = [
    { title: 'Drawing number', dataIndex: 'drawing_no', sorter: (a, b) => a.drawing_no.localeCompare(b.drawing_no), render: (no, d) => (
        <>
          <Link to={`/register/${no}`}>{no}</Link> {d.source === 'manual' && <Tag>Edited in the tool</Tag>}
        </>
      ) },
    { title: 'Title', dataIndex: 'title', sorter: (a, b) => a.title.localeCompare(b.title) },
    { title: 'Current rev', dataIndex: 'current_rev', width: 110 },
    { title: 'Register status', dataIndex: 'status', render: (s) => <StatusTag status={s} /> },
    { title: 'Class approval', dataIndex: 'class_approval', render: (state) => <ApprovalTag state={state} /> },
    {
      title: 'Latest check',
      render: (_, d) => {
        const check = latest.get(d.drawing_no)
        if (!check) return <Typography.Text type="secondary">Not checked</Typography.Text>
        return (
          <Link to={`/checks/${check.id}`}>
            <VerdictTag verdict={check.verdict} /> rev {check.revision}
          </Link>
        )
      },
    },
  ]

  return (
    <Card>
      <ErrorAlert error={register.error} />
      <Flex gap={8} style={{ marginBottom: 16 }}>
        <Input.Search
          allowClear
          placeholder="Drawing number or title"
          aria-label="Search by drawing number or title"
          onChange={(e) => setSearch(e.target.value)}
          style={{ width: 300 }}
        />
        <Select
          allowClear
          placeholder="Register status"
          aria-label="Filter by register status"
          value={status}
          onChange={setStatus}
          options={[...new Set((register.data ?? []).map((d) => d.status))].map((value) => ({ value }))}
          style={{ width: 200 }}
        />
        {can.editRegister(me) && (
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setAdding(true)} style={{ marginLeft: 'auto' }}>
            Add drawing
          </Button>
        )}
      </Flex>
      <DrawingForm open={adding} onClose={() => setAdding(false)} />
      <Table
        size="small"
        rowKey="drawing_no"
        columns={columns}
        dataSource={rows}
        loading={register.isPending}
        pagination={{ pageSize: 15, hideOnSinglePage: true }}
        locale={{ emptyText: 'No drawings match.' }}
      />
    </Card>
  )
}
