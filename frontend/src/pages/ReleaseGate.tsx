import { Alert, Card } from 'antd'

import { useGate } from '../api'
import GateTable from '../components/GateTable'
import { ErrorAlert } from '../components/Tags'

export default function ReleaseGate() {
  const gate = useGate()
  return (
    <Card>
      <ErrorAlert error={gate.error} />
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
        message="This view is read-only and does not write to the ERP."
        description="For each work order in the ERP extract it answers one question: may this job be released against the drawing revision it names? Blocked means the revision is superseded or not approved, or a check blocked or rejected it. Warn means something is still open: no check yet, the release decision, or class approval."
      />
      <GateTable rows={gate.data} loading={gate.isPending} />
    </Card>
  )
}
