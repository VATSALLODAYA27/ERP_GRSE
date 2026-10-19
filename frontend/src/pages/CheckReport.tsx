import { CheckOutlined, PrinterOutlined } from '@ant-design/icons'
import { Alert, Button, Card, Col, Empty, Flex, Result, Row, Skeleton, Table, Tabs, Tag, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { Link, useParams, useSearchParams } from 'react-router-dom'

import { ApiError, formatTime, LOW_CONFIDENCE, useCheck, type Check, type Finding, type Severity, type User } from '../api'
import Comments from '../components/Comments'
import DecisionPanel from '../components/DecisionPanel'
import { BomCheck, ImpactView } from '../components/ErpChecks'
import RevisionChanges from '../components/RevisionChanges'
import SheetViewer, { type Mark } from '../components/SheetViewer'
import { SEVERITY, SeverityTag, StatusTag, VERDICT } from '../components/Tags'

const SEVERITY_ORDER: Severity[] = ['critical', 'major', 'minor']

function VerdictBanner({ check }: { check: Check }) {
  const v = VERDICT[check.verdict]
  const counts = SEVERITY_ORDER.map((s) => [check.findings.filter((f) => f.severity === s).length, s] as const)
    .filter(([n]) => n > 0)
    .map(([n, s]) => `${n} ${s}`)
  return (
    <Flex align="center" gap={16} style={{ padding: '14px 20px', marginBottom: 16, background: v.tone, color: '#fff', borderRadius: 12 }}>
      <span style={{ fontSize: 30, lineHeight: 1 }}>{v.icon}</span>
      <div>
        <div style={{ fontSize: 20, fontWeight: 700, letterSpacing: '0.03em' }}>{v.label}</div>
        <div>{counts.length ? `${counts.join(', ')} finding${check.findings.length > 1 ? 's' : ''}` : 'No findings. The drawing matches the register and passes every rule.'}</div>
      </div>
    </Flex>
  )
}

/** Title block values next to what the register holds for the same drawing. */
function Comparison({ check }: { check: Check }) {
  const field = (name: string) => check.extracted.fields[name]?.value ?? ''
  const reg = check.register_row
  const rows: { name: string; label: string; drawing: string; register?: string; status?: boolean; differs?: boolean }[] = [
    { name: 'drawing_no', label: 'Drawing number', drawing: field('drawing_no'), register: reg ? field('drawing_no') : 'Not in the register', differs: !reg },
    { name: 'title', label: 'Title', drawing: field('title'), register: reg?.title },
    { name: 'revision', label: 'Revision', drawing: field('revision'), register: reg?.current_rev },
    { name: 'status', label: 'Status', drawing: field('status'), register: reg?.status, status: true },
    { name: 'material', label: 'Material', drawing: field('material') },
    { name: 'thickness_mm', label: 'Plate thickness (mm)', drawing: field('thickness_mm') },
    { name: 'date', label: 'Date', drawing: field('date') },
    { name: 'hull_no', label: 'Hull number', drawing: field('hull_no') },
    { name: 'zone', label: 'Structural zone', drawing: field('zone') },
    { name: 'spacing_mm', label: 'Stiffener spacing (mm)', drawing: field('spacing_mm') },
  ]
    // A check made before a field existed simply has no row for it.
    .filter((row) => row.name in check.extracted.fields)
    .map((row) => ({ ...row, differs: row.differs ?? (row.register !== undefined && row.register !== row.drawing) }))

  const cell = (value: string | undefined, row: (typeof rows)[number]) => {
    if (value === undefined) return <Typography.Text type="secondary">—</Typography.Text>
    if (value === '') return <Typography.Text type="danger">(unreadable)</Typography.Text>
    return row.status ? <StatusTag status={value} /> : value
  }

  /** For a scan: how the value on the drawing was arrived at. */
  const drawingCell = (value: string, row: (typeof rows)[number]) => {
    const { confidence, read_as } = check.extracted.fields[row.name] ?? {}
    return (
      <>
        {cell(value, row)}
        {read_as !== undefined && (
          <div>
            <Tag color="processing">Corrected</Tag>
            <Typography.Text type="secondary">OCR read "{read_as || 'nothing'}"</Typography.Text>
          </div>
        )}
        {read_as === undefined && confidence !== undefined && confidence < LOW_CONFIDENCE && (
          <div>
            <Tag color="warning">Low OCR confidence ({confidence}%), confirmed as read</Tag>
          </div>
        )}
      </>
    )
  }

  return (
    <Table
      size="small"
      rowKey="label"
      pagination={false}
      dataSource={rows}
      columns={[
        { title: 'Field', dataIndex: 'label', width: 190 },
        { title: 'On the drawing', dataIndex: 'drawing', render: drawingCell },
        { title: 'In the register', dataIndex: 'register', render: cell },
        {
          title: 'Result',
          width: 120,
          render: (_, row) => {
            if (row.differs) return <Tag color="error">Mismatch</Tag>
            return row.register === undefined ? null : (
              <Tag color="success" icon={<CheckOutlined />}>
                Match
              </Tag>
            )
          },
        },
      ]}
    />
  )
}

const FINDING_COLUMNS: ColumnsType<Finding> = [
  { title: '#', width: 48, render: (_, __, i) => i + 1 },
  { title: 'Severity', dataIndex: 'severity', width: 110, render: (s) => <SeverityTag severity={s} /> },
  {
    title: 'Rule',
    render: (_, f) => (
      <>
        <Typography.Text strong>{f.rule_id}</Typography.Text> {f.rule_name}
      </>
    ),
  },
  {
    title: 'Clause',
    render: (_, f) => (
      <>
        <Typography.Text strong>{f.clause}</Typography.Text>
        <br />
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          {f.standard}
        </Typography.Text>
      </>
    ),
  },
  { title: 'Evidence on the drawing', dataIndex: 'evidence' },
]

export default function CheckReport({ me }: { me: User }) {
  const { id = '' } = useParams()
  const query = useCheck(id)
  // The open tab is part of the address, so a refresh or a shared link shows the same view.
  const [params, setParams] = useSearchParams()

  if (query.isPending) return <Skeleton active paragraph={{ rows: 10 }} />
  if (query.isError) {
    const missing = query.error instanceof ApiError && query.error.status === 404
    return <Result status={missing ? '404' : 'error'} title={missing ? 'Check not found' : query.error.message} extra={<Link to="/checks">Back to checks</Link>} />
  }
  const check = query.data
  const bomProblems = check.bom_check?.filter((row) => row.result !== 'match').length ?? 0
  // Numbers match the rows of the findings table.
  const marks: Mark[] = check.findings.flatMap((f, i) => (f.bbox ? [{ bbox: f.bbox, number: i + 1, tone: SEVERITY[f.severity].tone }] : []))

  return (
    <>
      <Flex justify="space-between" align="start" style={{ marginBottom: 16 }}>
        <div>
          <Typography.Title level={3} style={{ margin: 0 }}>
            {check.drawing_no || '(unreadable drawing number)'} · Rev {check.revision || '?'}
          </Typography.Title>
          <Typography.Text type="secondary">
            Check #{check.id} · {check.filename} · submitted by {check.submitted_by} on {formatTime(check.created_at)}
          </Typography.Text>
        </div>
        <Button className="no-print" icon={<PrinterOutlined />} onClick={() => window.print()}>
          Print report
        </Button>
      </Flex>
      <VerdictBanner check={check} />
      {check.extracted.source === 'scan' && (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 16 }}
          message="Read from a scanned drawing by OCR"
          description={`The title block values were confirmed by ${check.extracted.confirmed_by} before the check ran. The parts list and notes are as OCR read them and may contain a misread character: compare any finding about them with the drawing sheet.`}
        />
      )}
      <Row gutter={[16, 16]}>
        <Col xs={24} xl={17}>
          <Card title="Title block and register" style={{ marginBottom: 16 }}>
            <Comparison check={check} />
          </Card>
          <Card>
            <Tabs
              activeKey={params.get('tab') ?? 'findings'}
              onChange={(tab) => setParams({ tab }, { replace: true })}
              items={[
                {
                  key: 'findings',
                  label: `Findings (${check.findings.length})`,
                  children: (
                    <Table
                      size="small"
                      rowKey={(f) => `${f.rule_id}|${f.evidence}`}
                      pagination={false}
                      columns={FINDING_COLUMNS}
                      dataSource={check.findings}
                      locale={{ emptyText: 'No findings.' }}
                    />
                  ),
                },
                {
                  key: 'sheet',
                  label: 'Drawing sheet',
                  children: (
                    <>
                      <SheetViewer src={`/api/checks/${check.id}/sheet.png`} alt={`Sheet 1 of drawing ${check.drawing_no} revision ${check.revision}`} pageSize={check.extracted.page_size} marks={marks} />
                      {marks.length === 0 && check.findings.length > 0 && (
                        <Empty description="These findings are about something missing, so there is nothing to mark on the sheet." />
                      )}
                    </>
                  ),
                },
                {
                  key: 'changes',
                  label: check.revision_diff ? `Revision changes (${check.revision_diff.changes.length})` : 'Revision changes',
                  children: <RevisionChanges check={check} />,
                },
                {
                  key: 'bom',
                  label: bomProblems ? `BOM (${bomProblems} mismatch${bomProblems === 1 ? '' : 'es'})` : 'BOM',
                  children: <BomCheck check={check} />,
                },
                {
                  key: 'impact',
                  label: check.impact ? `Impact (${check.impact.work_orders.length + check.impact.purchase_orders.length})` : 'Impact',
                  children: <ImpactView check={check} />,
                },
              ]}
            />
          </Card>
        </Col>
        <Col xs={24} xl={7}>
          <div className="decision-panel">
            <DecisionPanel check={check} me={me} />
            <Comments check={check} />
          </div>
        </Col>
      </Row>
    </>
  )
}
