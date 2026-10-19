import {
  AlertOutlined,
  ArrowRightOutlined,
  CheckOutlined,
  CloseOutlined,
  DatabaseOutlined,
  FileAddOutlined,
  MailOutlined,
  RadarChartOutlined,
  RobotOutlined,
  ShoppingCartOutlined,
  WalletOutlined,
  WarningOutlined,
} from '@ant-design/icons'
import { Button, Card, Col, Empty, Flex, Row, Skeleton, Space, Table, Tooltip, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useState, type ReactNode } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { can, formatTime, type User } from '../api'
import {
  AFFECTS,
  draftedCount,
  erp,
  fmtDate,
  money,
  moneyShort,
  qty,
  useAction,
  useAnomalies,
  useDeliveryRisk,
  useFollowups,
  useOverview,
  useReorder,
  type Flag,
  type ReorderRow,
  type RiskRow,
} from '../erpApi'
import { BarList, ItemLink, PoLink, ReasonModal, RefLink, RiskBar, StateTag, VendorLink, WorkOrderTags, WrittenByTag, stateOptions } from '../components/erp/Bits'
import { ErrorAlert } from '../components/Tags'
import { TONE } from '../theme'

function greeting() {
  const hour = new Date().getHours()
  return hour < 12 ? 'Good morning' : hour < 17 ? 'Good afternoon' : 'Good evening'
}

/** A number tile. `to` is a page, or `#id` for a card further down this page. */
function Kpi({ title, value, sub, to, icon, tone, loading }: { title: string; value: ReactNode; sub?: ReactNode; to: string; icon: ReactNode; tone: string; loading: boolean }) {
  return (
    <Card className="kpi" loading={loading} style={{ height: '100%' }}>
      {/* "1A" is 10% opacity, so the chip is a tint of the icon colour. */}
      <span className="stat-chip" style={{ color: tone, background: `${tone}1A` }}>
        {icon}
      </span>
      <div className="kpi-value compact">{value}</div>
      <Typography.Text type="secondary">{title}</Typography.Text>
      {sub !== undefined && <div className="kpi-sub">{sub}</div>}
      {to.startsWith('#') ? (
        <a href={to} className="kpi-link">
          View <ArrowRightOutlined />
        </a>
      ) : (
        <Link to={to} className="kpi-link">
          View <ArrowRightOutlined />
        </Link>
      )}
    </Card>
  )
}

function DeliveriesAtRisk({ me }: { me: User }) {
  const risk = useDeliveryRisk()
  const draft = useAction(erp.draftFollowups, AFFECTS.intel, (result) => {
    const n = draftedCount(result)
    return n === undefined ? 'Follow-ups drafted: see the outbox' : n === 0 ? 'No new follow-ups: drafts already exist' : `${n} follow-up${n === 1 ? '' : 's'} drafted: see the outbox`
  })
  const rows = risk.data ?? []
  const high = rows.filter((r) => r.level === 'HIGH').length

  const columns: ColumnsType<RiskRow> = [
    {
      title: 'Risk',
      dataIndex: 'score',
      width: 130,
      sorter: (a, b) => a.score - b.score,
      render: (score, r) => <RiskBar score={score} level={r.level} />,
    },
    {
      title: 'Level',
      dataIndex: 'level',
      filters: stateOptions('risk'),
      defaultFilteredValue: ['HIGH', 'MEDIUM'],
      onFilter: (value, r) => r.level === value,
      render: (level, r) => (
        <Tooltip title={r.reasons.length ? r.reasons.join(' ') : undefined}>
          <span>
            <StateTag kind="risk" value={level} />
          </span>
        </Tooltip>
      ),
    },
    {
      title: 'Order and vendor',
      render: (_, r) => (
        <>
          <PoLink no={r.po_no} />
          <div style={{ fontSize: 12 }}>
            <VendorLink id={r.vendor_id} name={r.vendor_name} />
          </div>
        </>
      ),
    },
    {
      title: 'Item',
      render: (_, r) => (
        <>
          <ItemLink code={r.item_code} /> <Typography.Text type="secondary">× {qty(r.qty_open)}</Typography.Text>
          <div>
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              {r.description}
            </Typography.Text>
          </div>
        </>
      ),
    },
    {
      title: 'Promised → predicted',
      sorter: (a, b) => a.predicted_date.localeCompare(b.predicted_date),
      render: (_, r) => (
        <span style={{ whiteSpace: 'nowrap' }}>
          {fmtDate(r.promised_date)} → <Typography.Text strong>{fmtDate(r.predicted_date)}</Typography.Text>
          {r.days_late_predicted > 0 && (
            <div>
              <Typography.Text type="danger" style={{ fontSize: 12 }}>
                {r.days_late_predicted} day{r.days_late_predicted === 1 ? '' : 's'} late
              </Typography.Text>
            </div>
          )}
        </span>
      ),
    },
    { title: 'Work orders waiting', dataIndex: 'impacted_work_orders', render: (orders) => <WorkOrderTags orders={orders} /> },
    { title: 'Open value', dataIndex: 'value_open', align: 'right', sorter: (a, b) => a.value_open - b.value_open, render: (v) => money(v) },
  ]
  if (can.request(me)) {
    columns.push({
      title: '',
      key: 'draft',
      width: 48,
      render: (_, r) => (
        <Tooltip title={`Draft a follow-up to the vendor for ${r.po_no}`}>
          <Button size="small" type="text" icon={<MailOutlined />} aria-label={`Draft a follow-up for ${r.po_no}`} disabled={draft.isPending} onClick={() => draft.mutate({ po_no: r.po_no })} />
        </Tooltip>
      ),
    })
  }

  return (
    <Card
      id="risk"
      title="Deliveries at risk"
      extra={
        can.request(me) && (
          <Button type="primary" icon={<RobotOutlined />} loading={draft.isPending} disabled={!high} onClick={() => draft.mutate({ all_high: true })}>
            Draft follow-ups for high-risk orders
          </Button>
        )
      }
    >
      <ErrorAlert error={risk.error} />
      <Typography.Paragraph type="secondary" style={{ marginTop: -4 }}>
        Every open order line, scored from the vendor's delivery record, the time left against their usual lead time, part receipts, critical items and the work orders waiting. Open a row for the reasons.
      </Typography.Paragraph>
      <Table
        size="small"
        rowKey={(r) => `${r.po_no}-${r.line_id}`}
        columns={columns}
        dataSource={rows}
        loading={risk.isPending}
        pagination={{ pageSize: 8, hideOnSinglePage: true }}
        scroll={{ x: 'max-content' }}
        expandable={{
          rowExpandable: (r) => r.reasons.length > 0,
          expandedRowRender: (r) => (
            <ul style={{ margin: 0, paddingLeft: 20 }}>
              {r.reasons.map((reason) => (
                <li key={reason}>{reason}</li>
              ))}
            </ul>
          ),
        }}
        locale={{ emptyText: 'No open deliveries at this risk level.' }}
      />
    </Card>
  )
}

function Outbox({ me }: { me: User }) {
  const followups = useFollowups('DRAFT')
  const approve = useAction(erp.approveFollowup, AFFECTS.intel, 'Approved to send. Recorded in the audit log; nothing is e-mailed from the prototype.')
  const dismiss = useAction(erp.dismissFollowup, AFFECTS.intel, 'Follow-up dismissed')
  const drafts = (followups.data ?? []).filter((f) => f.status === 'DRAFT')
  const decides = can.approve(me)

  return (
    <Card title={`Follow-up outbox${drafts.length ? ` (${drafts.length})` : ''}`} style={{ height: '100%' }}>
      <ErrorAlert error={followups.error} />
      <Skeleton loading={followups.isPending} active paragraph={{ rows: 4 }}>
        {drafts.length === 0 && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No drafts waiting. Draft follow-ups from the deliveries at risk." />}
        <Flex vertical gap={10}>
          {drafts.map((f) => (
            <div key={f.id} className="outbox-item" style={{ borderLeftColor: f.risk_level === 'HIGH' ? TONE.bad : f.risk_level === 'MEDIUM' ? TONE.warn : TONE.neutral }}>
              <Flex justify="space-between" align="start" gap={8} wrap>
                <Typography.Text strong>{f.subject}</Typography.Text>
                <span>
                  <StateTag kind="risk" value={f.risk_level} />
                  <WrittenByTag by={f.written_by} />
                </span>
              </Flex>
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                <PoLink no={f.po_no} /> · <VendorLink id={f.vendor_id} name={f.vendor_name} /> · drafted {formatTime(f.created_at)}
              </Typography.Text>
              <Typography.Paragraph ellipsis={{ rows: 3, expandable: true, symbol: 'Read all' }} style={{ margin: '6px 0', whiteSpace: 'pre-line' }}>
                {f.body}
              </Typography.Paragraph>
              {decides ? (
                <Space size={6}>
                  <Button size="small" type="primary" icon={<CheckOutlined />} disabled={approve.isPending || dismiss.isPending} onClick={() => approve.mutate(f.id)}>
                    Approve to send
                  </Button>
                  <Button size="small" icon={<CloseOutlined />} disabled={approve.isPending || dismiss.isPending} onClick={() => dismiss.mutate(f.id)}>
                    Dismiss
                  </Button>
                </Space>
              ) : (
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  A reviewer approves follow-ups before they go out.
                </Typography.Text>
              )}
            </div>
          ))}
        </Flex>
      </Skeleton>
    </Card>
  )
}

function Anomalies({ me }: { me: User }) {
  const anomalies = useAnomalies('OPEN')
  const [resolving, setResolving] = useState<Flag | null>(null)
  const scan = useAction(erp.scanAnomalies, AFFECTS.intel, (r) => (r?.added ? `${r.added} new anomal${r.added === 1 ? 'y' : 'ies'} found` : 'Scan complete: nothing new'))
  const resolve = useAction(({ id, note }: { id: number; note: string }) => erp.resolveAnomaly(id, note), AFFECTS.intel, 'Anomaly resolved')
  const open = (anomalies.data ?? []).filter((f) => f.status === 'OPEN')
  const rank = { high: 0, medium: 1, low: 2 }
  open.sort((a, b) => (rank[a.severity] ?? 3) - (rank[b.severity] ?? 3))

  return (
    <Card
      id="anomalies"
      title={`Anomalies${open.length ? ` (${open.length})` : ''}`}
      style={{ height: '100%' }}
      extra={
        can.request(me) && (
          <Button size="small" icon={<RadarChartOutlined />} loading={scan.isPending} onClick={() => scan.mutate()}>
            Scan now
          </Button>
        )
      }
    >
      <ErrorAlert error={anomalies.error} />
      <Skeleton loading={anomalies.isPending} active paragraph={{ rows: 4 }}>
        {open.length === 0 && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No open anomalies." />}
        <Flex vertical gap={8}>
          {open.map((f) => (
            <Flex key={f.id} className="queue-item flag-item" gap={10} align="start" style={{ borderLeftColor: f.severity === 'high' ? TONE.bad : f.severity === 'medium' ? TONE.warn : TONE.info }}>
              <div style={{ flex: 1, minWidth: 0 }}>
                <StateTag kind="severity" value={f.severity} />
                <Typography.Text>{f.message}</Typography.Text>
                <div style={{ fontSize: 12 }}>
                  <RefLink type={f.ref_type} no={f.ref_no} /> <Typography.Text type="secondary">· {f.kind.replace(/_/g, ' ')} · {fmtDate(f.detected_at)}</Typography.Text>
                </div>
              </div>
              {can.approve(me) && (
                <Button size="small" onClick={() => setResolving(f)}>
                  Resolve
                </Button>
              )}
            </Flex>
          ))}
        </Flex>
      </Skeleton>
      <ReasonModal
        open={!!resolving}
        title={resolving ? `Resolve: ${resolving.message}` : ''}
        okText="Resolve"
        label="Note"
        required
        description="Say what was checked or done. The note is kept with the anomaly and in the audit log."
        loading={resolve.isPending}
        onClose={() => setResolving(null)}
        onSubmit={(note) => resolving && resolve.mutate({ id: resolving.id, note }, { onSuccess: () => setResolving(null) })}
      />
    </Card>
  )
}

function Reorder({ me }: { me: User }) {
  const reorder = useReorder()
  const navigate = useNavigate()
  const [selected, setSelected] = useState<string[]>([])
  const create = useAction(erp.reorderRequisition, AFFECTS.requisition, (pr) => `Requisition ${pr?.pr_no ?? ''} created from the suggestions`)
  const requests = can.request(me)

  const columns: ColumnsType<ReorderRow> = [
    {
      title: 'Item',
      dataIndex: 'item_code',
      render: (code, r) => (
        <>
          <ItemLink code={code} />
          <div>
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              {r.description}
            </Typography.Text>
          </div>
        </>
      ),
    },
    { title: 'On hand', dataIndex: 'on_hand', align: 'right', render: (v, r) => `${qty(v)} ${r.uom}` },
    { title: 'On order', dataIndex: 'on_order', align: 'right', render: qty },
    { title: 'Open demand', dataIndex: 'demand_open', align: 'right', render: qty },
    { title: 'Reorder level', dataIndex: 'reorder_level', align: 'right', render: qty },
    { title: 'Short by', dataIndex: 'net_need', align: 'right', render: (v) => <Typography.Text type="danger">{qty(v)}</Typography.Text> },
    { title: 'Suggested', dataIndex: 'suggested_qty', align: 'right', render: (v) => <strong>{qty(v)}</strong> },
    { title: 'Vendor', dataIndex: 'vendor_name', render: (name, r) => <VendorLink id={r.vendor_id} name={name} /> },
    { title: 'Est. value', dataIndex: 'est_value', align: 'right', render: (v) => money(v) },
    {
      title: 'Why',
      dataIndex: 'reason',
      width: 280,
      onCell: () => ({ style: { minWidth: 220, maxWidth: 320, whiteSpace: 'normal' } }),
      render: (reason) => (
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          {reason}
        </Typography.Text>
      ),
    },
  ]

  return (
    <Card
      id="reorder"
      title="Reorder suggestions"
      extra={
        requests && (
          <Button
            type="primary"
            icon={<FileAddOutlined />}
            disabled={!selected.length}
            loading={create.isPending}
            onClick={() =>
              create.mutate(selected, {
                onSuccess: (pr) => {
                  setSelected([])
                  if (pr?.pr_no) navigate(`/requisitions/${encodeURIComponent(pr.pr_no)}`)
                },
              })
            }
          >
            Create requisition{selected.length ? ` (${selected.length})` : ''}
          </Button>
        )
      }
    >
      <ErrorAlert error={reorder.error} />
      <Typography.Paragraph type="secondary" style={{ marginTop: -4 }}>
        Items where stock on hand plus on order does not cover open work-order demand and the reorder level. Select rows to raise one requisition for them.
      </Typography.Paragraph>
      <Table
        size="small"
        rowKey="item_code"
        columns={columns}
        dataSource={reorder.data}
        loading={reorder.isPending}
        pagination={{ pageSize: 8, hideOnSinglePage: true }}
        scroll={{ x: 'max-content' }}
        rowSelection={requests ? { selectedRowKeys: selected, onChange: (keys) => setSelected(keys as string[]) } : undefined}
        locale={{ emptyText: 'Nothing to reorder: stock and open orders cover the demand.' }}
      />
    </Card>
  )
}

/** PRAVAH's home page: what needs attention across procurement, stores and payables today. */
export default function ControlTower({ me }: { me: User }) {
  const overview = useOverview()
  const k = overview.data?.kpis
  const loading = overview.isPending

  const kpis = [
    { title: 'Open purchase orders', value: moneyShort(k?.open_po_value), sub: `${k?.open_po_count ?? 0} orders`, to: '/purchase-orders', icon: <ShoppingCartOutlined />, tone: TONE.info },
    { title: 'Deliveries at risk', value: k?.at_risk_count ?? 0, sub: `${moneyShort(k?.at_risk_value)} open`, to: '/purchase-orders?at_risk=1', icon: <WarningOutlined />, tone: TONE.bad },
    { title: 'Stock value', value: moneyShort(k?.stock_value), sub: `${k?.stock_outs ?? 0} stock-out${k?.stock_outs === 1 ? '' : 's'}`, to: '/items', icon: <DatabaseOutlined />, tone: TONE.good },
    { title: 'Payables due in 7 days', value: moneyShort(k?.payables_due_7d), to: '/payables', icon: <WalletOutlined />, tone: TONE.warn },
    { title: 'Open anomalies', value: k?.anomalies_open ?? 0, sub: `${k?.followups_pending ?? 0} follow-ups to approve`, to: '#anomalies', icon: <AlertOutlined />, tone: TONE.bad },
    { title: 'Items to reorder', value: k?.reorder_count ?? 0, to: '/items?status=REORDER', icon: <FileAddOutlined />, tone: TONE.info },
  ]

  return (
    <>
      <ErrorAlert error={overview.error} />
      <Row gutter={[16, 16]}>
        <Col span={24}>
          <div className="hero hero-slim">
            <Typography.Title level={2} style={{ margin: 0, color: '#fff' }}>
              {greeting()}, {me.name}
            </Typography.Title>
            <p>
              Deliveries at risk: <b>{k?.at_risk_count ?? '…'}</b> &nbsp;·&nbsp; Open anomalies: <b>{k?.anomalies_open ?? '…'}</b> &nbsp;·&nbsp; Payables due this week: <b>{moneyShort(k?.payables_due_7d)}</b>
            </p>
            <Flex gap={8} wrap>
              <a href="#risk">
                <Button>Review deliveries at risk</Button>
              </a>
              <Link to="/purchase-orders">
                <Button ghost>Open purchase orders</Button>
              </Link>
            </Flex>
          </div>
        </Col>
        {kpis.map((kpi) => (
          <Col key={kpi.title} xs={12} md={8} xxl={4}>
            <Kpi {...kpi} loading={loading} />
          </Col>
        ))}
        <Col span={24}>
          <DeliveriesAtRisk me={me} />
        </Col>
        <Col xs={24} xl={12}>
          <Outbox me={me} />
        </Col>
        <Col xs={24} xl={12}>
          <Anomalies me={me} />
        </Col>
        <Col xs={24} xxl={16}>
          <Reorder me={me} />
        </Col>
        <Col xs={24} xxl={8}>
          <Flex vertical gap={16} style={{ height: '100%' }}>
            <Card title="Spend by category" extra={<Typography.Text type="secondary">last 6 months</Typography.Text>}>
              <Skeleton loading={loading} active paragraph={{ rows: 4 }}>
                {overview.data?.spend_by_category.length ? (
                  <BarList rows={overview.data.spend_by_category.map((s) => ({ key: s.category, label: s.category, value: s.value, to: `/items?category=${encodeURIComponent(s.category)}` }))} />
                ) : (
                  <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No spend recorded" />
                )}
              </Skeleton>
            </Card>
            <Card title="Stock by store" extra={<Link to="/items">Items &amp; stock</Link>}>
              <Skeleton loading={loading} active paragraph={{ rows: 3 }}>
                {overview.data?.stock_by_store.length ? (
                  <BarList rows={overview.data.stock_by_store.map((s) => ({ key: s.store_code, label: s.store_code, value: s.value, to: `/stock?store=${encodeURIComponent(s.store_code)}` }))} />
                ) : (
                  <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No stock recorded" />
                )}
              </Skeleton>
            </Card>
          </Flex>
        </Col>
      </Row>
    </>
  )
}
