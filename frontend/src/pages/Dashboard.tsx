import { ArrowRightOutlined, ClockCircleOutlined, FileDoneOutlined, FileProtectOutlined, StopOutlined } from '@ant-design/icons'
import { Button, Card, Col, Empty, Flex, Row, Skeleton, Typography } from 'antd'
import { Link } from 'react-router-dom'

import { can, useChecks, useClassApprovals, useGate, type User, type Verdict } from '../api'
import ChecksTable from '../components/ChecksTable'
import { ErrorAlert, VERDICT, VerdictTag } from '../components/Tags'
import { TONE } from '../theme'

const WEEK_MS = 7 * 24 * 60 * 60 * 1000

function greeting() {
  const hour = new Date().getHours()
  return hour < 12 ? 'Good morning' : hour < 17 ? 'Good afternoon' : 'Good evening'
}

export default function Dashboard({ me }: { me: User }) {
  const checks = useChecks()
  const gate = useGate()
  const approvals = useClassApprovals()
  const loading = checks.isPending || gate.isPending || approvals.isPending
  const all = checks.data ?? []
  const open = all.filter((c) => !c.decision)
  const blocked = (gate.data ?? []).filter((row) => row.status === 'BLOCKED').length
  const decides = can.decide(me)
  // A reviewer acts on other people's open checks and the admin on all of them; an engineer waits on their own.
  const own = (c: { submitted_by: string }) => c.submitted_by === me.username
  const mine = open.filter((c) => (decides ? me.role === 'admin' || !own(c) : own(c)))

  const stats = [
    { title: 'Checks awaiting decision', value: open.length, to: '/checks', icon: <ClockCircleOutlined />, tone: TONE.warn },
    { title: 'Blocked work orders', value: blocked, to: '/gate', icon: <StopOutlined />, tone: TONE.bad },
    { title: 'Drawings awaiting class approval', value: (approvals.data ?? []).filter((a) => a.days_waiting !== null).length, to: '/class-approvals', icon: <FileProtectOutlined />, tone: TONE.info },
    { title: 'Checks in the last 7 days', value: all.filter((c) => Date.now() - Date.parse(c.created_at) < WEEK_MS).length, icon: <FileDoneOutlined />, tone: TONE.good },
  ]
  const mix = (Object.keys(VERDICT) as Verdict[]).map((verdict) => ({ verdict, count: all.filter((c) => c.verdict === verdict).length }))

  return (
    <>
      <ErrorAlert error={checks.error ?? gate.error ?? approvals.error} />
      <Row gutter={[16, 16]}>
        <Col xs={24} xl={16}>
          <div className="hero">
            <Typography.Title level={2} style={{ margin: 0, color: '#fff' }}>
              {greeting()}, {me.name}
            </Typography.Title>
            <p>
              Awaiting a decision: <b>{open.length}</b> &nbsp;·&nbsp; Blocked work orders: <b>{blocked}</b>
            </p>
            <Flex gap={8} wrap>
              <Link to="/checks">
                <Button>Review checks</Button>
              </Link>
              <Link to="/gate">
                <Button ghost>Open the release gate</Button>
              </Link>
            </Flex>
          </div>
        </Col>
        <Col xs={24} xl={8}>
          <Card title="Verdicts so far" style={{ height: '100%' }}>
            <Skeleton loading={checks.isPending} active paragraph={{ rows: 3 }}>
              {all.length === 0 ? (
                <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No checks yet" />
              ) : (
                <>
                  <div className="mix-bar" role="img" aria-label={mix.map((m) => `${VERDICT[m.verdict].label} ${m.count}`).join(', ')}>
                    {mix.map((m) => (
                      <span key={m.verdict} style={{ flexGrow: m.count, background: VERDICT[m.verdict].tone }} />
                    ))}
                  </div>
                  <Flex vertical gap={8}>
                    {mix.map((m) => (
                      <Flex key={m.verdict} justify="space-between" align="center">
                        <VerdictTag verdict={m.verdict} />
                        <Typography.Text strong>
                          {m.count} <Typography.Text type="secondary">of {all.length}</Typography.Text>
                        </Typography.Text>
                      </Flex>
                    ))}
                  </Flex>
                </>
              )}
            </Skeleton>
          </Card>
        </Col>
        {stats.map((stat) => (
          <Col key={stat.title} xs={12} xl={6}>
            <Card className="kpi" loading={loading}>
              {/* "1A" is 10% opacity, so the chip is a tint of the icon colour. */}
              <span className="stat-chip" style={{ color: stat.tone, background: `${stat.tone}1A` }}>
                {stat.icon}
              </span>
              <div className="kpi-value">{stat.value}</div>
              <Typography.Text type="secondary">{stat.title}</Typography.Text>
              {stat.to && (
                <Link to={stat.to} className="kpi-link">
                  View <ArrowRightOutlined />
                </Link>
              )}
            </Card>
          </Col>
        ))}
        <Col xs={24} xl={16}>
          <Card title="Recent checks" extra={<Link to="/checks">All checks</Link>}>
            <ChecksTable checks={all.slice(0, 8)} loading={checks.isPending} />
          </Card>
        </Col>
        <Col xs={24} xl={8}>
          <Card title={decides ? 'Needs your decision' : 'Your checks awaiting a decision'} loading={checks.isPending}>
            {mine.length === 0 && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="Nothing waiting" />}
            <Flex vertical gap={8}>
              {mine.map((c) => (
                <Link key={c.id} to={`/checks/${c.id}`} className="queue-item" style={{ borderLeftColor: VERDICT[c.verdict].tone }}>
                  <Typography.Text strong>
                    {c.drawing_no} rev {c.revision}
                  </Typography.Text>
                  <VerdictTag verdict={c.verdict} />
                </Link>
              ))}
            </Flex>
          </Card>
        </Col>
      </Row>
    </>
  )
}
