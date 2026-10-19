import { RobotOutlined } from '@ant-design/icons'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Alert, Button, Card, Tag, Typography } from 'antd'

import { formatTime, postJson, useSettings, type Check } from '../api'
import { ErrorAlert } from './Tags'

/** An optional AI-written summary of the revision changes. A reading aid only: the verdict never uses it. */
export default function Explanation({ check }: { check: Check }) {
  const queryClient = useQueryClient()
  const settings = useSettings()
  const generate = useMutation({
    mutationFn: () => postJson<Check>(`/checks/${check.id}/explanation`),
    onSuccess: (updated) => {
      queryClient.setQueryData(['checks', String(check.id)], updated)
      queryClient.invalidateQueries({ queryKey: ['audit'] })
    },
  })
  const explanation = check.explanation
  const explainer = settings.data?.explainer
  // Nothing to explain, or the feature is off and was never used on this check: show nothing at all.
  if (!check.revision_diff?.changes.length || (!explanation && !explainer?.enabled)) return null

  return (
    <Card
      size="small"
      style={{ marginBottom: 16 }}
      title={
        <>
          <RobotOutlined /> Plain-language summary
        </>
      }
    >
      <Tag color="purple" style={{ marginBottom: 8, whiteSpace: 'normal' }}>
        AI-written, not part of the compliance decision
      </Tag>
      {explanation ? (
        <>
          <Typography.Paragraph style={{ whiteSpace: 'pre-wrap' }}>{explanation.text}</Typography.Paragraph>
          {explanation.unsupported_numbers.length > 0 && (
            <Alert
              type="warning"
              showIcon
              style={{ marginBottom: 8 }}
              message={`This summary mentions ${explanation.unsupported_numbers.join(', ')}, which ${explanation.unsupported_numbers.length === 1 ? 'is' : 'are'} not in the change list. Rely on the list below.`}
            />
          )}
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            Written by {explanation.model} from the change list below, requested by {explanation.requested_by} on {formatTime(explanation.at)}. It can be wrong: the list
            below is what the tool actually found.
          </Typography.Text>
        </>
      ) : (
        <>
          <Typography.Paragraph type="secondary">
            Sends the change list below (not the drawing) to {explainer?.model}, a language model hosted outside this network, and shows its summary here.
          </Typography.Paragraph>
          <ErrorAlert error={generate.error} />
          <Button className="no-print" loading={generate.isPending} onClick={() => generate.mutate()}>
            Explain these changes in plain words
          </Button>
        </>
      )}
    </Card>
  )
}
