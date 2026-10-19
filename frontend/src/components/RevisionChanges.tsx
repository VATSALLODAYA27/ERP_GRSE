import { EditOutlined, MinusCircleOutlined, PlusCircleOutlined } from '@ant-design/icons'
import { Alert, Col, Empty, Flex, Row, Segmented, Table, Tag, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useState, type ReactNode } from 'react'

import type { Change, Check } from '../api'
import { TONE } from '../theme'
import Explanation from './Explanation'
import SheetViewer, { type Mark } from './SheetViewer'

const KIND: Record<Change['kind'], { label: string; color: string; tone: string; icon: ReactNode }> = {
  added: { label: 'Added', color: 'success', tone: TONE.good, icon: <PlusCircleOutlined /> },
  removed: { label: 'Removed', color: 'error', tone: TONE.bad, icon: <MinusCircleOutlined /> },
  changed: { label: 'Changed', color: 'warning', tone: TONE.warn, icon: <EditOutlined /> },
}

const value = (text: string | null) => text ?? <Typography.Text type="secondary">—</Typography.Text>

const COLUMNS: ColumnsType<Change> = [
  { title: '#', width: 48, render: (_, __, i) => i + 1 },
  { title: 'Where', dataIndex: 'area', width: 120 },
  {
    title: 'Change',
    dataIndex: 'kind',
    width: 120,
    render: (kind: Change['kind']) => (
      <Tag color={KIND[kind].color} icon={KIND[kind].icon}>
        {KIND[kind].label}
      </Tag>
    ),
  },
  { title: 'What', dataIndex: 'what' },
  { title: 'Before', dataIndex: 'old', render: value },
  { title: 'After', dataIndex: 'new', render: value },
]

function Swatch({ colour, children }: { colour: string; children: ReactNode }) {
  return (
    <Flex align="center" gap={6}>
      <span style={{ width: 14, height: 14, background: colour, borderRadius: 2 }} />
      {children}
    </Flex>
  )
}

/** What changed between the previous revision and this one: the ERP's change note, the two sheets, and a list. */
export default function RevisionChanges({ check }: { check: Check }) {
  const [view, setView] = useState<'Overlay' | 'Side by side'>('Overlay')
  const diff = check.revision_diff
  if (!diff) {
    return (
      <Empty description="No earlier revision of this drawing has been checked, so there is nothing to compare with. To compare, upload the previous revision together with the drawing under New Check." />
    )
  }

  const marks = (side: 'old_bbox' | 'new_bbox'): Mark[] =>
    diff.changes.flatMap((change, i) => (change[side] ? [{ bbox: change[side], number: i + 1, tone: KIND[change.kind].tone }] : []))
  const note = diff.change_note

  return (
    <>
      {note ? (
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
          message={`ERP change note ${note.ecn_no} (rev ${note.from_rev} to ${note.to_rev}, ${note.changed_on})`}
          description={`${note.description}. Reason: ${note.reason}.`}
        />
      ) : (
        <Alert type="warning" showIcon style={{ marginBottom: 16 }} message={`The ERP extract has no change note for revision ${check.revision} of this drawing.`} />
      )}

      <Flex justify="space-between" align="center" wrap gap={8} style={{ marginBottom: 12 }}>
        <Typography.Text strong>
          Rev {diff.from_revision} compared with Rev {check.revision}: {diff.changes.length} change{diff.changes.length === 1 ? '' : 's'} in the text
        </Typography.Text>
        <Segmented className="no-print" options={['Overlay', 'Side by side']} value={view} onChange={setView} />
      </Flex>

      {view === 'Overlay' ? (
        <>
          <Flex gap={16} wrap style={{ marginBottom: 8 }}>
            <Swatch colour={TONE.bad}>Only in Rev {diff.from_revision} (removed)</Swatch>
            <Swatch colour={TONE.good}>Only in Rev {check.revision} (added)</Swatch>
            <Swatch colour="#A5A5A5">Unchanged</Swatch>
          </Flex>
          <div className="sheet">
            <img src={`/api/checks/${check.id}/diff.png`} alt={`Revision ${diff.from_revision} and revision ${check.revision} overlaid, differences coloured`} />
          </div>
          <Typography.Paragraph type="secondary" style={{ marginTop: 8 }}>
            The overlay compares the two sheets pixel by pixel. Something that only moved shows as both red and green; the list below shows whether its wording changed.
          </Typography.Paragraph>
        </>
      ) : (
        <Row gutter={12}>
          <Col span={12}>
            <Typography.Text strong>Rev {diff.from_revision} (previous)</Typography.Text>
            <SheetViewer src={`/api/checks/${check.id}/previous.png`} alt={`Revision ${diff.from_revision}`} pageSize={diff.page_size} marks={marks('old_bbox')} />
          </Col>
          <Col span={12}>
            <Typography.Text strong>Rev {check.revision} (this check)</Typography.Text>
            <SheetViewer src={`/api/checks/${check.id}/sheet.png`} alt={`Revision ${check.revision}`} pageSize={check.extracted.page_size} marks={marks('new_bbox')} />
          </Col>
        </Row>
      )}

      <div style={{ marginTop: 16 }}>
        <Explanation check={check} />
      </div>
      <Table
        size="small"
        rowKey={(change) => `${change.area}|${change.what}|${change.old}|${change.new}`}
        pagination={false}
        columns={COLUMNS}
        dataSource={diff.changes}
        locale={{ emptyText: 'No differences in the text. Check the overlay for redrawn lines.' }}
      />
    </>
  )
}
