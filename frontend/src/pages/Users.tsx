import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Button, Card, Popconfirm, Table, Tag, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'

import { postJson, useUsers, type Account, type User } from '../api'
import { ErrorAlert, ROLE_LABEL } from '../components/Tags'

const STATUS: Record<Account['status'], { label: string; color?: string }> = {
  pending: { label: 'Awaiting approval', color: 'warning' },
  active: { label: 'Active', color: 'success' },
  disabled: { label: 'Disabled' },
}

/** Admin only: approve reviewers who registered, and disable or re-enable accounts. */
export default function Users({ me }: { me: User }) {
  const queryClient = useQueryClient()
  const users = useUsers()
  const setStatus = useMutation({
    mutationFn: ({ username, status }: { username: string; status: 'active' | 'disabled' }) => postJson<Account>(`/users/${encodeURIComponent(username)}/status`, { status }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] })
      queryClient.invalidateQueries({ queryKey: ['audit'] })
    },
  })

  const columns: ColumnsType<Account> = [
    { title: 'Username', dataIndex: 'username', render: (username) => <strong>{username}</strong> },
    { title: 'Name', dataIndex: 'name' },
    { title: 'Role', dataIndex: 'role', render: (role: User['role']) => ROLE_LABEL[role] },
    { title: 'Status', dataIndex: 'status', render: (status: Account['status']) => <Tag color={STATUS[status].color}>{STATUS[status].label}</Tag> },
    {
      title: 'Action',
      render: (_, account) => {
        if (account.username === me.username) return <Typography.Text type="secondary">This is you</Typography.Text>
        if (account.status === 'active') {
          return (
            <Popconfirm title={`Disable ${account.username}? They are signed out at once.`} okText="Disable" onConfirm={() => setStatus.mutate({ username: account.username, status: 'disabled' })}>
              <Button size="small" danger>
                Disable
              </Button>
            </Popconfirm>
          )
        }
        return (
          <Button size="small" type="primary" onClick={() => setStatus.mutate({ username: account.username, status: 'active' })}>
            {account.status === 'pending' ? 'Approve' : 'Enable'}
          </Button>
        )
      },
    },
  ]

  return (
    <Card>
      <ErrorAlert error={users.error ?? setStatus.error} />
      <Typography.Paragraph type="secondary">
        Engineers and reviewers register themselves on the sign-in page and cannot sign in until approved here. The admin account comes from the logins file.
      </Typography.Paragraph>
      <Table size="small" rowKey="username" columns={columns} dataSource={users.data} loading={users.isPending} pagination={false} />
    </Card>
  )
}
