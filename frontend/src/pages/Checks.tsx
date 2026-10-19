import { Card, Input } from 'antd'
import { useState } from 'react'

import { useChecks } from '../api'
import ChecksTable from '../components/ChecksTable'
import { ErrorAlert } from '../components/Tags'

export default function Checks() {
  const checks = useChecks()
  const [search, setSearch] = useState('')
  const needle = search.trim().toLowerCase()

  return (
    <Card>
      <ErrorAlert error={checks.error} />
      <Input.Search
        allowClear
        placeholder="Drawing number"
        aria-label="Search by drawing number"
        onChange={(e) => setSearch(e.target.value)}
        style={{ width: 300, marginBottom: 16 }}
      />
      <ChecksTable checks={checks.data?.filter((c) => c.drawing_no.toLowerCase().includes(needle))} loading={checks.isPending} pageSize={15} />
    </Card>
  )
}
