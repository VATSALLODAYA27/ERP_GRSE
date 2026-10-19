import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Button, Card, Empty, Input, Typography } from 'antd'
import { useState } from 'react'

import { formatTime, postJson, type Check } from '../api'
import { ErrorAlert } from './Tags'

/** Notes on a check from anyone signed in. Comments are kept with the check and listed in the audit log. */
export default function Comments({ check }: { check: Check }) {
  const queryClient = useQueryClient()
  const [text, setText] = useState('')
  const add = useMutation({
    mutationFn: () => postJson<Check>(`/checks/${check.id}/comments`, { text }),
    onSuccess: (updated) => {
      queryClient.setQueryData(['checks', String(check.id)], updated)
      queryClient.invalidateQueries({ queryKey: ['audit'] })
      setText('')
    },
  })

  return (
    <Card title={`Comments (${check.comments.length})`} style={{ marginTop: 16 }}>
      {check.comments.length === 0 && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No comments yet" />}
      {check.comments.map((comment) => (
        <div key={comment.id} style={{ marginBottom: 12 }}>
          <Typography.Text strong>{comment.username}</Typography.Text>{' '}
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            {formatTime(comment.created_at)}
          </Typography.Text>
          <div style={{ whiteSpace: 'pre-wrap' }}>{comment.text}</div>
        </div>
      ))}
      <div className="no-print">
        <ErrorAlert error={add.error} />
        <Input.TextArea aria-label="Add a comment" rows={3} maxLength={2000} value={text} onChange={(e) => setText(e.target.value)} placeholder="Add a comment" />
        <Button style={{ marginTop: 8 }} disabled={!text.trim()} loading={add.isPending} onClick={() => add.mutate()}>
          Add comment
        </Button>
      </div>
    </Card>
  )
}
